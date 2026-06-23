"""MCP server tools for Curator for Zotero."""

from __future__ import annotations

import re
from copy import deepcopy
from tempfile import TemporaryDirectory
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from zotero_curator.arxiv import (
    arxiv_imported_pdf_attachment_item,
    arxiv_pdf_attachment_item,
    arxiv_record_to_zotero_item,
    download_arxiv_pdf,
    fetch_arxiv_record,
    first_success_key,
)
from zotero_curator.client import get_attachment_details, get_zotero_client
from zotero_curator.formatting import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_CHUNK_OVERLAP,
    MAX_CHUNK_CHARS,
    MAX_CONTEXT_CHARS,
    PROTECTED_ITEM_FIELDS,
    chunk_bounds,
    chunk_count,
    chunk_index_for_offset,
    clamp_int,
    collection_keys,
    format_action,
    format_item,
    format_item_summary,
    make_snippet,
    normalize_doi,
    normalize_whitespace,
    note_text_to_html,
    response_summary,
    set_item_collections,
    set_item_tags,
    tag_names,
    tokenize_query,
    unique_strings,
)
from zotero_curator.pdf_tools import OptionalPdfDependencyError, extract_pages, outline, page_count
from zotero_curator.runtime import configure_logging, log_event, runtime_diagnostics
from zotero_curator.semantic import (
    OptionalSemanticDependencyError,
    SemanticIndexBusyError,
    build_semantic_index,
    semantic_search,
)
from zotero_curator.settings import config_status_lines, load_config

mcp = FastMCP("Curator for Zotero")

# Zotero's current Local API v3 documentation says write requests are unsupported and
# only GET is accepted. When Zotero ships local write support, flip this gate and
# update the tests/docs that intentionally encode the current API protocol.
LOCAL_API_WRITES_SUPPORTED = False


def zotero_backend_write_capable(cfg: Any) -> bool:
    if cfg.local:
        return LOCAL_API_WRITES_SUPPORTED
    return bool(cfg.api_key)


def write_enabled() -> bool:
    cfg = load_config()
    return cfg.write_enabled and zotero_backend_write_capable(cfg)


def write_guard(dry_run: bool) -> str | None:
    if dry_run:
        return None
    cfg = load_config()
    if cfg.local and not LOCAL_API_WRITES_SUPPORTED:
        return (
            "Write blocked. The Zotero Local API currently accepts only GET requests, "
            "so local mode is read-only for Curator write tools. Real writes require "
            "Zotero Web API mode with an API key that has write access. Run "
            "`zotero-curator setup --web --library-id YOUR_LIBRARY_ID "
            "--api-key YOUR_WRITE_ENABLED_API_KEY --write-enabled`."
        )
    if not zotero_backend_write_capable(cfg):
        return (
            "Write blocked. Zotero Web API writes require an API key with write access. "
            "Run `zotero-curator setup --web --library-id YOUR_LIBRARY_ID "
            "--api-key YOUR_WRITE_ENABLED_API_KEY --write-enabled`."
        )
    if not cfg.write_enabled:
        return (
            "Write blocked. Set `write_enabled = true` in the Curator settings or set "
            "ZOTERO_WRITE_ENABLED=true, then call the tool with dry_run=false."
        )
    return None


def get_indexed_attachment_text(
    zot: Any, item_key: str
) -> tuple[dict[str, Any] | None, Any | None, str | None, str | None]:
    item: Any = zot.item(item_key)
    if not item:
        return None, None, None, f"No item found with key: {item_key}"
    attachment = get_attachment_details(zot, item)
    if attachment is None:
        return item, None, None, "No suitable attachment found for full text extraction."
    full_text_data: Any = zot.fulltext_item(attachment.key)
    if not full_text_data or "content" not in full_text_data:
        return item, attachment, None, "Attachment is available but indexed text is not available."
    return item, attachment, full_text_data["content"], None


def get_pdf_attachment_bytes(zot: Any, item_key: str) -> tuple[dict[str, Any] | None, Any | None, bytes | None, str | None]:
    item: Any = zot.item(item_key)
    if not item:
        return None, None, None, f"No item found with key: {item_key}"
    attachment = get_attachment_details(zot, item)
    if attachment is None:
        return item, None, None, "No suitable attachment found."
    if attachment.content_type and attachment.content_type != "application/pdf":
        return item, attachment, None, f"Best attachment is not a PDF: {attachment.content_type}"
    pdf_data: Any = zot.file(attachment.key)
    if isinstance(pdf_data, str):
        pdf_data = pdf_data.encode("utf-8")
    if not isinstance(pdf_data, bytes):
        return item, attachment, None, "Zotero did not return PDF bytes for the attachment."
    return item, attachment, pdf_data, None


def iter_lines_with_offsets(content: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    offset = 0
    for raw_line in content.splitlines(keepends=True):
        stripped = raw_line.strip()
        if stripped:
            line_start = offset + raw_line.find(stripped)
            lines.append((line_start, normalize_whitespace(stripped)))
        offset += len(raw_line)
    return lines


def heading_score(line: str) -> int:
    if len(line) < 3 or len(line) > 140 or re.fullmatch(r"\d+", line):
        return 0
    score = 0
    if re.match(r"^(chapter|section|appendix|part)\b", line, flags=re.IGNORECASE):
        score += 5
    if re.match(r"^\d+(?:\.\d+){0,4}\s+\S", line):
        score += 4
    if re.search(r"\.{3,}\s*\d+$", line):
        score += 3
    alpha_chars = [char for char in line if char.isalpha()]
    if alpha_chars and sum(char.isupper() for char in alpha_chars) / len(alpha_chars) > 0.75:
        score += 2
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", line)
    if 1 <= len(words) <= 12 and line[:1].isupper():
        score += 1
    return score


def extract_headings(
    content: str, limit: int = 80, dedupe: bool = True
) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset, line in iter_lines_with_offsets(content):
        score = heading_score(line)
        if score < 3:
            continue
        normalized = line.lower()
        if dedupe and normalized in seen:
            continue
        seen.add(normalized)
        headings.append(
            {"title": line, "offset": offset, "score": score, "chunk": chunk_index_for_offset(offset)}
        )
        if len(headings) >= limit:
            break
    return headings


def section_end_offset(headings: list[dict[str, Any]], start: int, content_length: int) -> int:
    for heading in headings:
        if heading["offset"] > start:
            return heading["offset"]
    return content_length


def find_heading_matches(
    headings: list[dict[str, Any]], section_title: str
) -> list[dict[str, Any]]:
    needle = normalize_whitespace(section_title).lower()
    if not needle:
        return []
    needle_tokens = set(tokenize_query(needle))
    matches = []
    for heading in headings:
        title = heading["title"]
        haystack = title.lower()
        haystack_tokens = set(tokenize_query(haystack))
        if needle in haystack or haystack in needle or (needle_tokens and needle_tokens.issubset(haystack_tokens)):
            matches.append(heading)
    return matches


@mcp.tool(name="zotero_healthcheck", description="Check Zotero configuration and API reachability.")
def healthcheck() -> str:
    configure_logging()
    lines = ["# Curator for Zotero Health", *config_status_lines()]
    try:
        zot = get_zotero_client()
        sample_items: Any = zot.items(limit=1)
    except Exception as exc:
        log_event("healthcheck_error", error_type=type(exc).__name__, error=str(exc))
        lines.extend(["Status: ERROR", f"Error: {exc}"])
        lines.append("Hint: open Zotero and enable the local API, or configure Web API credentials.")
        return "\n".join(lines)
    log_event("healthcheck_ok", endpoint=str(getattr(zot, "endpoint", "unknown")), sample_count=len(sample_items))
    lines.extend(["Status: OK", f"Endpoint: {getattr(zot, 'endpoint', 'unknown')}"])
    if sample_items:
        sample = sample_items[0]
        data = sample.get("data", {})
        lines.append(f"Sample Item: {data.get('title', 'Untitled')} (`{sample['key']}`)")
    return "\n".join(lines)


@mcp.tool(name="zotero_diagnostics", description="Show runtime diagnostics, logging paths, and Zotero API status.")
def diagnostics() -> str:
    cfg = load_config()
    log_path = configure_logging(cfg)
    info = runtime_diagnostics(cfg)
    lines = ["# Curator Diagnostics", *(f"{key}: {value}" for key, value in info.items())]
    try:
        zot = get_zotero_client(cfg)
        items: Any = zot.items(limit=1)
    except Exception as exc:
        log_event("diagnostics_error", error_type=type(exc).__name__, error=str(exc))
        lines.extend(["Zotero API: ERROR", f"{type(exc).__name__}: {exc}"])
    else:
        log_event("diagnostics_ok", sample_count=len(items), log_file=str(log_path))
        lines.append("Zotero API: OK")
        if items:
            lines.append(f"Sample item key: `{items[0].get('key')}`")
    if cfg.response_format == "json":
        import json

        return json.dumps({**info, "zotero_api": lines[-1]}, indent=2, sort_keys=True)
    return "\n".join(lines)


@mcp.tool(name="zotero_search_items", description="Search Zotero items by query, qmode, optional tag, and limit.")
def search_items(
    query: str,
    qmode: Literal["titleCreatorYear", "everything"] | None = "titleCreatorYear",
    tag: str | None = None,
    limit: int | None = 10,
) -> str:
    try:
        zot = get_zotero_client()
        params: dict[str, Any] = {"q": query, "qmode": qmode, "limit": limit}
        if tag:
            params["tag"] = tag
        zot.add_parameters(**params)
        results: Any = zot.items()
    except Exception as exc:
        return f"Error searching Zotero items: {exc}"
    if not results:
        return "No items found matching your query."
    header = [
        f"# Search Results for: {query!r}",
        f"Found {len(results)} item(s).",
        "Use item keys with zotero_item_metadata or zotero_item_fulltext_info.",
    ]
    return "\n\n".join(
        header + [format_item_summary(item, i + 1) for i, item in enumerate(results)]
    )


@mcp.tool(name="zotero_item_metadata", description="Get detailed metadata for one Zotero item key.")
def get_item_metadata(item_key: str) -> str:
    try:
        zot = get_zotero_client()
        item: Any = zot.item(item_key)
    except Exception as exc:
        return f"Error retrieving item metadata: {exc}"
    if not item:
        return f"No item found with key: {item_key}"
    return format_item(item)


@mcp.tool(name="zotero_find_item_by_doi", description="Find exact Zotero item matches by DOI.")
def find_item_by_doi(doi: str, limit: int | None = 25) -> str:
    normalized = normalize_doi(doi)
    if not normalized:
        return "Please provide a DOI to search for."
    try:
        zot = get_zotero_client()
        results: Any = zot.items(q=normalized, qmode="everything", limit=limit)
    except Exception as exc:
        return f"Error searching Zotero items by DOI: {exc}"
    exact_matches = [
        item for item in results if normalize_doi(item.get("data", {}).get("DOI", "")) == normalized
    ]
    if exact_matches:
        header = [f"# DOI Match: {normalized}", f"Found {len(exact_matches)} exact match(es)."]
        return "\n\n".join(header + [format_item(item) for item in exact_matches])
    if results:
        header = [
            f"# DOI Search: {normalized}",
            "No exact DOI match found, but possible matches were returned.",
        ]
        return "\n\n".join(
            header + [format_item_summary(item, i + 1) for i, item in enumerate(results)]
        )
    return f"No Zotero item found with DOI: {normalized}"


@mcp.tool(name="zotero_item_fulltext", description="Get full indexed text for a Zotero item or attachment key.")
def get_item_fulltext(item_key: str) -> str:
    try:
        zot = get_zotero_client()
        item, attachment, content, error = get_indexed_attachment_text(zot, item_key)
    except Exception as exc:
        return f"Error retrieving item full text: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and content is not None
    return f"{format_item(item)}\n\n## Attachment\nKey: `{attachment.key}`\nType: {attachment.content_type}\n\n## Document Content\n\n{content}"


@mcp.tool(name="zotero_item_fulltext_info", description="Inspect indexed full-text size and chunk count without dumping content.")
def get_item_fulltext_info(
    item_key: str,
    chunk_chars: int | None = DEFAULT_CHUNK_CHARS,
    overlap_chars: int | None = DEFAULT_CHUNK_OVERLAP,
) -> str:
    chunk_chars = clamp_int(chunk_chars, DEFAULT_CHUNK_CHARS, 1000, MAX_CHUNK_CHARS)
    overlap_chars = clamp_int(overlap_chars, DEFAULT_CHUNK_OVERLAP, 0, chunk_chars - 1)
    try:
        zot = get_zotero_client()
        item, attachment, content, error = get_indexed_attachment_text(zot, item_key)
    except Exception as exc:
        return f"Error retrieving item full text information: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and content is not None
    data = item.get("data", {})
    text_length = len(content)
    return "\n".join(
        [
            f"# Full-Text Info: {data.get('title', 'Untitled')}",
            f"Item Key: `{item_key}`",
            f"Attachment Key: `{attachment.key}`",
            f"Attachment Type: {attachment.content_type}",
            f"Characters: {text_length}",
            f"Words: ~{len(content.split())}",
            f"Chunk Size: {chunk_chars}",
            f"Chunk Overlap: {overlap_chars}",
            f"Estimated Chunks: {chunk_count(text_length, chunk_chars, overlap_chars)}",
            "",
            "## Start Preview",
            make_snippet(content, 0, 500),
            "",
            "## End Preview",
            make_snippet(content, max(0, text_length - 1), 500),
        ]
    )


@mcp.tool(name="zotero_pdf_pages", description="Read page-aware PDF text via the optional pdf extra.")
def get_pdf_pages(item_key: str, start_page: int = 1, end_page: int | None = None) -> str:
    try:
        zot = get_zotero_client()
        item, attachment, pdf_data, error = get_pdf_attachment_bytes(zot, item_key)
    except Exception as exc:
        return f"Error retrieving PDF attachment: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and pdf_data is not None
    try:
        pages = extract_pages(pdf_data, start_page, end_page)
        total_pages = page_count(pdf_data)
    except OptionalPdfDependencyError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error reading PDF pages: {exc}"
    title = item.get("data", {}).get("title", "Untitled")
    lines = [
        f"# PDF Pages: {title}",
        f"Item Key: `{item_key}`",
        f"Attachment Key: `{attachment.key}`",
        f"Total Pages: {total_pages}",
    ]
    for page in pages:
        lines.extend(["", f"## Page {page.number}", page.text.strip() or "(no text extracted)"])
    return "\n".join(lines)


@mcp.tool(name="zotero_pdf_outline", description="Read PDF bookmarks/table of contents via the optional pdf extra.")
def get_pdf_outline(item_key: str) -> str:
    try:
        zot = get_zotero_client()
        item, attachment, pdf_data, error = get_pdf_attachment_bytes(zot, item_key)
    except Exception as exc:
        return f"Error retrieving PDF attachment: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and pdf_data is not None
    try:
        entries = outline(pdf_data)
        total_pages = page_count(pdf_data)
    except OptionalPdfDependencyError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error reading PDF outline: {exc}"
    title = item.get("data", {}).get("title", "Untitled")
    lines = [
        f"# PDF Outline: {title}",
        f"Item Key: `{item_key}`",
        f"Attachment Key: `{attachment.key}`",
        f"Total Pages: {total_pages}",
    ]
    if not entries:
        lines.append("No PDF bookmarks found.")
    for entry in entries:
        indent = "  " * max(0, int(entry["level"]) - 1)
        lines.append(f"{indent}- Page {entry['page']}: {entry['title']}")
    return "\n".join(lines)


@mcp.tool(name="zotero_item_text_chunk", description="Read one bounded overlapping chunk of indexed attachment text.")
def get_item_text_chunk(
    item_key: str,
    chunk_index: int = 1,
    chunk_chars: int | None = DEFAULT_CHUNK_CHARS,
    overlap_chars: int | None = DEFAULT_CHUNK_OVERLAP,
) -> str:
    chunk_chars = clamp_int(chunk_chars, DEFAULT_CHUNK_CHARS, 1000, MAX_CHUNK_CHARS)
    overlap_chars = clamp_int(overlap_chars, DEFAULT_CHUNK_OVERLAP, 0, chunk_chars - 1)
    chunk_index = max(1, chunk_index)
    try:
        zot = get_zotero_client()
        item, attachment, content, error = get_indexed_attachment_text(zot, item_key)
    except Exception as exc:
        return f"Error retrieving item text chunk: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and content is not None
    total_chunks = chunk_count(len(content), chunk_chars, overlap_chars)
    if chunk_index > total_chunks:
        return f"Requested chunk {chunk_index}, but item `{item_key}` only has {total_chunks} chunk(s)."
    start, end = chunk_bounds(len(content), chunk_index, chunk_chars, overlap_chars)
    data = item.get("data", {})
    lines = [
        f"# Text Chunk {chunk_index}/{total_chunks}: {data.get('title', 'Untitled')}",
        f"Item Key: `{item_key}`",
        f"Attachment Key: `{attachment.key}`",
        f"Character Range: {start}-{end}",
    ]
    if chunk_index > 1:
        lines.append(f"Previous Chunk: {chunk_index - 1}")
    if chunk_index < total_chunks:
        lines.append(f"Next Chunk: {chunk_index + 1}")
    lines.extend(["", "## Content", content[start:end]])
    return "\n".join(lines)


@mcp.tool(name="zotero_item_search_text", description="Search within one item's indexed attachment text.")
def search_item_text(
    item_key: str,
    query: str,
    match_mode: Literal["auto", "phrase", "all_terms", "any_term"] | None = "auto",
    max_results: int | None = 10,
    context_chars: int | None = 500,
) -> str:
    max_results = clamp_int(max_results, 10, 1, 25)
    context_chars = clamp_int(context_chars, 500, 80, MAX_CONTEXT_CHARS)
    if not query.strip():
        return "Please provide a query to search for."
    try:
        zot = get_zotero_client()
        item, attachment, content, error = get_indexed_attachment_text(zot, item_key)
    except Exception as exc:
        return f"Error searching item text: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and content is not None
    phrase_matches = list(re.finditer(re.escape(query.strip()), content, flags=re.IGNORECASE))
    effective_mode = "phrase" if match_mode == "auto" and phrase_matches else (match_mode or "auto")
    results: list[dict[str, Any]] = []
    if effective_mode == "phrase":
        for match in phrase_matches[:max_results]:
            results.append(
                {"offset": match.start(), "score": 1, "snippet": make_snippet(content, match.start(), context_chars)}
            )
    else:
        terms = tokenize_query(query)
        if not terms:
            return "Please provide at least one searchable word."
        total_chunks = chunk_count(len(content), DEFAULT_CHUNK_CHARS, DEFAULT_CHUNK_OVERLAP)
        for index in range(1, total_chunks + 1):
            start, end = chunk_bounds(len(content), index, DEFAULT_CHUNK_CHARS, DEFAULT_CHUNK_OVERLAP)
            chunk = content[start:end]
            chunk_lower = chunk.lower()
            term_counts = {term: chunk_lower.count(term.lower()) for term in terms}
            present_terms = [term for term, count in term_counts.items() if count > 0]
            if effective_mode == "all_terms" and len(present_terms) != len(terms):
                continue
            if effective_mode == "any_term" and not present_terms:
                continue
            score = sum(term_counts.values())
            first_match = min(
                (chunk_lower.find(term) for term in present_terms if chunk_lower.find(term) >= 0),
                default=0,
            )
            results.append(
                {"offset": start + first_match, "score": score, "snippet": make_snippet(content, start + first_match, context_chars)}
            )
        results.sort(key=lambda result: (-result["score"], result["offset"]))
        results = results[:max_results]
    if not results:
        return f"No indexed-text matches found for `{query}` in item `{item_key}`."
    data = item.get("data", {})
    header = [
        f"# Text Search: {query}",
        f"Item: {data.get('title', 'Untitled')} (`{item_key}`)",
        f"Attachment: `{attachment.key}`",
        f"Mode: {effective_mode}",
        f"Results: {len(results)}",
    ]
    formatted_results = []
    for index, result in enumerate(results, start=1):
        offset = result["offset"]
        formatted_results.append(
            "\n".join(
                [
                    f"## {index}. Match",
                    f"Character Offset: {offset}",
                    f"Approx. Chunk: {chunk_index_for_offset(offset)}",
                    f"Score: {result['score']}",
                    "",
                    result["snippet"],
                ]
            )
        )
    return "\n\n".join(header + formatted_results)


@mcp.tool(name="zotero_item_outline", description="Extract a heuristic outline from indexed attachment text.")
def get_item_outline(item_key: str, limit: int | None = 80) -> str:
    limit = clamp_int(limit, 80, 5, 200)
    try:
        zot = get_zotero_client()
        item, attachment, content, error = get_indexed_attachment_text(zot, item_key)
    except Exception as exc:
        return f"Error extracting item outline: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and content is not None
    headings = extract_headings(content, limit=limit)
    data = item.get("data", {})
    if not headings:
        return f"No likely headings found in `{data.get('title', 'Untitled')}` (`{item_key}`)."
    lines = [
        f"# Outline: {data.get('title', 'Untitled')}",
        f"Item Key: `{item_key}`",
        f"Attachment Key: `{attachment.key}`",
        f"Headings: {len(headings)}",
        "",
    ]
    for heading in headings:
        lines.append(
            f"- chunk {heading['chunk']}, offset {heading['offset']}: {heading['title']}"
        )
    return "\n".join(lines)


@mcp.tool(name="zotero_item_read_section", description="Read a heuristic section by heading title from indexed attachment text.")
def read_item_section(
    item_key: str,
    section_title: str,
    max_chars: int | None = 12000,
) -> str:
    max_chars = clamp_int(max_chars, 12000, 1000, MAX_CHUNK_CHARS)
    try:
        zot = get_zotero_client()
        item, attachment, content, error = get_indexed_attachment_text(zot, item_key)
    except Exception as exc:
        return f"Error reading item section: {exc}"
    if error:
        return f"Error: {error}"
    assert item is not None and attachment is not None and content is not None
    headings = extract_headings(content, limit=250, dedupe=False)
    matches = find_heading_matches(headings, section_title)
    if not matches:
        return f"No section heading matching `{section_title}` found in item `{item_key}`. Try zotero_item_outline first."
    match = matches[0]
    start = match["offset"]
    end = min(section_end_offset(headings, start, len(content)), start + max_chars)
    data = item.get("data", {})
    lines = [
        f"# Section: {match['title']}",
        f"Item: {data.get('title', 'Untitled')} (`{item_key}`)",
        f"Attachment: `{attachment.key}`",
        f"Character Range: {start}-{end}",
        f"Approx. Chunk: {chunk_index_for_offset(start)}",
        "",
        content[start:end],
    ]
    if end < section_end_offset(headings, start, len(content)):
        lines.insert(-1, "Truncated by max_chars; increase max_chars or use zotero_item_text_chunk.")
    return "\n".join(lines)


@mcp.tool(name="zotero_item_children", description="List child notes and attachments for an item key.")
def item_children(item_key: str) -> str:
    try:
        zot = get_zotero_client()
        item: Any = zot.item(item_key)
        children: Any = zot.children(item_key)
    except Exception as exc:
        return f"Error retrieving Zotero item children: {exc}"
    if not item:
        return f"No item found with key: {item_key}"
    if not children:
        return f"No child items found for `{item_key}`."
    lines = [f"# Children for `{item_key}`", ""]
    for index, child in enumerate(children, start=1):
        data = child.get("data", {})
        lines.append(
            f"{index}. **{data.get('itemType', 'unknown')}** `{child.get('key')}` - {data.get('title') or data.get('note', '')[:80] or 'Untitled'}"
        )
    return "\n".join(lines)


@mcp.tool(name="zotero_list_collections", description="List Zotero collections.")
def list_collections(limit: int | None = 100) -> str:
    limit = clamp_int(limit, 100, 1, 500)
    try:
        zot = get_zotero_client()
        collections: Any = zot.collections(limit=limit)
    except Exception as exc:
        return f"Error listing Zotero collections: {exc}"
    if not collections:
        return "No Zotero collections found."
    lines = [f"# Zotero Collections ({len(collections)})", ""]
    for collection in collections:
        data = collection.get("data", {})
        parent = data.get("parentCollection")
        suffix = f" (parent `{parent}`)" if parent else ""
        lines.append(f"- `{collection.get('key')}` {data.get('name', 'Untitled')}{suffix}")
    return "\n".join(lines)


@mcp.tool(name="zotero_collection_items", description="List items in a collection key.")
def collection_items(collection_key: str, limit: int | None = 50) -> str:
    limit = clamp_int(limit, 50, 1, 200)
    try:
        zot = get_zotero_client()
        items: Any = zot.collection_items(collection_key, limit=limit)
    except Exception as exc:
        return f"Error retrieving collection items: {exc}"
    if not items:
        return f"No items found in collection `{collection_key}`."
    header = [f"# Items in Collection `{collection_key}`", f"Items: {len(items)}"]
    return "\n\n".join(header + [format_item_summary(item, i + 1) for i, item in enumerate(items)])


@mcp.tool(name="zotero_list_tags", description="List Zotero tags.")
def list_tags(limit: int | None = 200) -> str:
    limit = clamp_int(limit, 200, 1, 1000)
    try:
        zot = get_zotero_client()
        tags: Any = zot.tags(limit=limit)
    except Exception as exc:
        return f"Error listing Zotero tags: {exc}"
    if not tags:
        return "No Zotero tags found."
    names = []
    for tag in tags:
        if isinstance(tag, dict):
            names.append(str(tag.get("tag") or tag.get("name") or tag))
        else:
            names.append(str(tag))
    return "# Zotero Tags\n\n" + "\n".join(f"- {name}" for name in sorted(names, key=str.lower))


@mcp.tool(name="zotero_semantic_rebuild", description="Build or refresh the optional semantic search index.")
def semantic_rebuild(limit: int | None = 500, collection_name: str = "zotero-items") -> str:
    try:
        zot = get_zotero_client()
        result = build_semantic_index(zot, limit=clamp_int(limit, 500, 1, 5000), collection_name=collection_name)
    except OptionalSemanticDependencyError as exc:
        return str(exc)
    except SemanticIndexBusyError as exc:
        return f"Semantic index busy: {exc}"
    except Exception as exc:
        return f"Error rebuilding semantic index: {exc}"
    log_event("semantic_rebuild", indexed=result.get("indexed"), store=result.get("store"))
    return "\n".join([
        "# Semantic Index Rebuilt",
        f"Collection: {result['collection']}",
        f"Indexed items: {result['indexed']}",
        f"Storage: {result['store']}",
    ])


@mcp.tool(name="zotero_semantic_search", description="Search the optional local semantic index.")
def semantic_search_items(query: str, n_results: int | None = 5, collection_name: str = "zotero-items") -> str:
    try:
        result = semantic_search(query, n_results=clamp_int(n_results, 5, 1, 25), collection_name=collection_name)
    except OptionalSemanticDependencyError as exc:
        return str(exc)
    except SemanticIndexBusyError as exc:
        return f"Semantic index busy: {exc}"
    except Exception as exc:
        return f"Error searching semantic index: {exc}"
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0] if result.get("distances") else [None] * len(ids)
    lines = [f"# Semantic Search: {query!r}", f"Results: {len(ids)}"]
    for index, item_id in enumerate(ids, start=1):
        metadata = metadatas[index - 1] if index - 1 < len(metadatas) else {}
        document = documents[index - 1] if index - 1 < len(documents) else ""
        distance = distances[index - 1] if index - 1 < len(distances) else None
        lines.extend(["", f"## {index}. {metadata.get('title', 'Untitled')}", f"Key: `{item_id}` | Type: {metadata.get('itemType', 'unknown')}"])
        lines.append(f"Distance: {distance}" if distance is not None else "Distance: unavailable")
        lines.append(make_snippet(document, 0, 500))
    return "\n".join(lines)


@mcp.tool(name="zotero_write_status", description="Show whether write tools are enabled.")
def write_status() -> str:
    cfg = load_config()
    backend_capable = zotero_backend_write_capable(cfg)
    effective_enabled = cfg.write_enabled and backend_capable
    lines = [
        "# Zotero Write Status",
        f"Write setting: {'enabled' if cfg.write_enabled else 'disabled'}",
        f"Mode: {cfg.mode_label}",
        f"Backend write-capable: {'yes' if backend_capable else 'no'}",
        f"Effective writes: {'enabled' if effective_enabled else 'disabled'}",
        "Most write tools default to dry_run=true. Set dry_run=false to apply changes.",
    ]
    if cfg.local and not LOCAL_API_WRITES_SUPPORTED:
        lines.append("Local mode is read-only for Curator write tools because the current Zotero Local API accepts only GET requests.")
    elif not cfg.api_key:
        lines.append("Web API mode is missing an API key. Configure a key with write access before applying writes.")
    return "\n".join(lines)


@mcp.tool(name="zotero_add_arxiv", description="Add an arXiv preprint item with an optional stored or linked PDF attachment.")
def add_arxiv_paper(
    source: str,
    collections: list[str] | None = None,
    tags: list[str] | None = None,
    pdf_mode: Literal["stored", "linked", "none"] = "stored",
    allow_duplicate: bool = False,
    dry_run: bool = True,
) -> str:
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Add arXiv Paper\n{block}"
    try:
        record = fetch_arxiv_record(source)
    except Exception as exc:
        return f"Error retrieving arXiv metadata: {exc}"
    item_payload = arxiv_record_to_zotero_item(record, collections, tags)
    lines = [
        f"arXiv ID: `{record.arxiv_id}`",
        f"Title: {record.title}",
        f"Authors: {', '.join(record.authors) if record.authors else 'No authors'}",
        f"Abstract URL: {record.abs_url}",
        f"PDF mode: {pdf_mode}",
    ]
    if pdf_mode != "none":
        lines.append(f"PDF URL: {record.pdf_url}")
    if collections:
        lines.append("Collections: " + ", ".join(f"`{collection}`" for collection in collections))
    if tags:
        lines.append("Tags: " + ", ".join(f"`{tag}`" for tag in tags))
    try:
        zot = get_zotero_client()
        matches: Any = zot.items(q=record.arxiv_id, qmode="everything", limit=5)
    except Exception as exc:
        return f"Error checking Zotero for existing arXiv item: {exc}"
    if matches and not allow_duplicate:
        lines.append(f"Existing possible match(es): {len(matches)}")
        lines.append("Set allow_duplicate=true to create another copy.")
        return format_action("Add arXiv Paper", lines, dry_run=True)
    if dry_run:
        lines.append("Item type: preprint")
        if pdf_mode == "stored":
            lines.append("The arXiv PDF will be downloaded to a temporary file and uploaded as a stored Zotero attachment.")
        elif pdf_mode == "linked":
            lines.append("The arXiv PDF will be attached as a linked URL, not a stored Zotero file.")
        lines.append("This creates metadata directly from arXiv rather than relying on PDF metadata recognition.")
        return format_action("Add arXiv Paper", lines, dry_run=True)
    try:
        item_response: Any = zot.create_items([item_payload])
        parent_key = first_success_key(item_response)
        if not parent_key:
            lines.append(response_summary(item_response))
            return format_action("Add arXiv Paper", lines, dry_run=False)
        lines.append(f"Created item: `{parent_key}`")
        if pdf_mode == "linked":
            attachment_response: Any = zot.create_items([arxiv_pdf_attachment_item(record, parent_key)])
            attachment_key = first_success_key(attachment_response)
            if attachment_key:
                lines.append(f"Created PDF URL attachment: `{attachment_key}`")
            else:
                lines.append("PDF URL attachment response: " + response_summary(attachment_response))
        elif pdf_mode == "stored":
            with TemporaryDirectory(prefix="zotero-curator-arxiv-") as temp_dir:
                pdf_path = download_arxiv_pdf(record, temp_dir)
                upload_payload = arxiv_imported_pdf_attachment_item(record, pdf_path.name)
                upload_response: Any = zot.upload_attachments([upload_payload], parentid=parent_key, basedir=temp_dir)
            uploaded = upload_response.get("success", []) if isinstance(upload_response, dict) else []
            if uploaded:
                attachment_key = uploaded[0].get("key") if isinstance(uploaded[0], dict) else None
                if attachment_key:
                    lines.append(f"Stored PDF attachment: `{attachment_key}`")
                else:
                    lines.append("Stored PDF attachment uploaded.")
            else:
                lines.append("Stored PDF attachment response: " + response_summary(upload_response))
    except Exception as exc:
        return f"Error creating Zotero arXiv item: {exc}"
    return format_action("Add arXiv Paper", lines, dry_run=False)


@mcp.tool(name="zotero_create_collection", description="Create a Zotero collection.")
def create_collection(
    name: str,
    parent_collection: str | None = None,
    dry_run: bool = True,
) -> str:
    block = write_guard(dry_run)
    lines = [f"Collection name: {name}"]
    if parent_collection:
        lines.append(f"Parent collection: `{parent_collection}`")
    if block:
        return f"# Blocked: Create Collection\n{block}"
    if dry_run:
        return format_action("Create Collection", lines, dry_run=True)
    try:
        zot = get_zotero_client()
        payload: dict[str, str] = {"name": name}
        if parent_collection:
            payload["parentCollection"] = parent_collection
        response: Any = zot.create_collections([payload])
    except Exception as exc:
        return f"Error creating collection: {exc}"
    lines.append(response_summary(response))
    return format_action("Create Collection", lines, dry_run=False)


@mcp.tool(name="zotero_rename_collection", description="Rename a Zotero collection.")
def rename_collection(collection_key: str, name: str, dry_run: bool = True) -> str:
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Rename Collection\n{block}"
    try:
        zot = get_zotero_client()
        collection: Any = zot.collection(collection_key)
    except Exception as exc:
        return f"Error retrieving collection: {exc}"
    if not collection:
        return f"No collection found with key: {collection_key}"
    old_name = collection.get("data", {}).get("name", "Untitled")
    lines = [f"Collection: `{collection_key}`", f"Old name: {old_name}", f"New name: {name}"]
    if dry_run:
        return format_action("Rename Collection", lines, dry_run=True)
    collection.setdefault("data", {})["name"] = name
    try:
        response: Any = zot.update_collection(collection)
    except Exception as exc:
        return f"Error renaming collection: {exc}"
    lines.append(response_summary(response))
    return format_action("Rename Collection", lines, dry_run=False)


@mcp.tool(name="zotero_delete_collection", description="Delete a Zotero collection by key.")
def delete_collection(collection_key: str, dry_run: bool = True) -> str:
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Delete Collection\n{block}"
    try:
        zot = get_zotero_client()
        collection: Any = zot.collection(collection_key)
    except Exception as exc:
        return f"Error retrieving collection: {exc}"
    if not collection:
        return f"No collection found with key: {collection_key}"
    lines = [f"Collection: `{collection_key}`", f"Name: {collection.get('data', {}).get('name', 'Untitled')}"]
    if dry_run:
        return format_action("Delete Collection", lines, dry_run=True)
    try:
        response: Any = zot.delete_collection(collection)
    except Exception as exc:
        return f"Error deleting collection: {exc}"
    lines.append(response_summary(response))
    return format_action("Delete Collection", lines, dry_run=False)


@mcp.tool(name="zotero_update_item_tags", description="Replace, add, or remove tags on one item.")
def update_item_tags(
    item_key: str,
    tags: list[str] | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    dry_run: bool = True,
) -> str:
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Update Item Tags\n{block}"
    try:
        zot = get_zotero_client()
        item: Any = zot.item(item_key)
    except Exception as exc:
        return f"Error retrieving item: {exc}"
    if not item:
        return f"No item found with key: {item_key}"
    before = tag_names(item)
    if tags is not None:
        after = unique_strings(tags)
    else:
        after = before.copy()
        for tag in unique_strings(add_tags):
            if tag not in after:
                after.append(tag)
        remove_set = set(unique_strings(remove_tags))
        after = [tag for tag in after if tag not in remove_set]
    lines = [f"Item: `{item_key}`", f"Before: {before}", f"After: {after}"]
    if before == after:
        lines.append("No tag changes detected.")
        return format_action("Update Item Tags", lines, dry_run=True)
    if dry_run:
        return format_action("Update Item Tags", lines, dry_run=True)
    set_item_tags(item, after)
    try:
        response: Any = zot.update_item(item)
    except Exception as exc:
        return f"Error updating item tags: {exc}"
    lines.append(response_summary(response))
    return format_action("Update Item Tags", lines, dry_run=False)


@mcp.tool(name="zotero_update_item_collections", description="Replace, add, or remove collection membership for one item.")
def update_item_collections(
    item_key: str,
    collections: list[str] | None = None,
    add_collections: list[str] | None = None,
    remove_collections: list[str] | None = None,
    dry_run: bool = True,
) -> str:
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Update Item Collections\n{block}"
    try:
        zot = get_zotero_client()
        item: Any = zot.item(item_key)
    except Exception as exc:
        return f"Error retrieving item: {exc}"
    if not item:
        return f"No item found with key: {item_key}"
    before = collection_keys(item)
    if collections is not None:
        after = unique_strings(collections)
    else:
        after = before.copy()
        for key in unique_strings(add_collections):
            if key not in after:
                after.append(key)
        remove_set = set(unique_strings(remove_collections))
        after = [key for key in after if key not in remove_set]
    lines = [f"Item: `{item_key}`", f"Before: {before}", f"After: {after}"]
    if before == after:
        lines.append("No collection changes detected.")
        return format_action("Update Item Collections", lines, dry_run=True)
    if dry_run:
        return format_action("Update Item Collections", lines, dry_run=True)
    set_item_collections(item, after)
    try:
        response: Any = zot.update_item(item)
    except Exception as exc:
        return f"Error updating item collections: {exc}"
    lines.append(response_summary(response))
    return format_action("Update Item Collections", lines, dry_run=False)


@mcp.tool(name="zotero_update_item_metadata", description="Update allowed metadata fields on one item.")
def update_item_metadata(
    item_key: str,
    fields: dict[str, Any],
    dry_run: bool = True,
) -> str:
    if not fields:
        return "Provide at least one metadata field to update."
    blocked_fields = sorted(set(fields) & PROTECTED_ITEM_FIELDS)
    if blocked_fields:
        return "Refusing to update protected fields: " + ", ".join(blocked_fields)
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Update Item Metadata\n{block}"
    try:
        zot = get_zotero_client()
        item: Any = zot.item(item_key)
    except Exception as exc:
        return f"Error retrieving item: {exc}"
    if not item:
        return f"No item found with key: {item_key}"
    before = {field: item.get("data", {}).get(field) for field in fields}
    after_item = deepcopy(item)
    after_item.setdefault("data", {}).update(fields)
    after = {field: after_item.get("data", {}).get(field) for field in fields}
    lines = [f"Item: `{item_key}`", f"Before: {before}", f"After: {after}"]
    if dry_run:
        return format_action("Update Item Metadata", lines, dry_run=True)
    try:
        response: Any = zot.update_item(after_item)
    except Exception as exc:
        return f"Error updating item metadata: {exc}"
    lines.append(response_summary(response))
    return format_action("Update Item Metadata", lines, dry_run=False)


@mcp.tool(name="zotero_create_child_note", description="Create a child note under a Zotero parent item.")
def create_child_note(
    parent_item_key: str,
    note_text: str,
    tags: list[str] | None = None,
    dry_run: bool = True,
) -> str:
    if not note_text.strip():
        return "Provide note_text to create a child note."
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Create Child Note\n{block}"
    try:
        zot = get_zotero_client()
        parent: Any = zot.item(parent_item_key)
    except Exception as exc:
        return f"Error retrieving parent item: {exc}"
    if not parent:
        return f"No parent item found with key: {parent_item_key}"
    note = {
        "itemType": "note",
        "parentItem": parent_item_key,
        "note": note_text_to_html(note_text),
        "tags": [{"tag": tag} for tag in unique_strings(tags)],
    }
    lines = [f"Parent: `{parent_item_key}`", f"Tags: {unique_strings(tags)}", "", note_text]
    if dry_run:
        return format_action("Create Child Note", lines, dry_run=True)
    try:
        response: Any = zot.create_items([note])
    except Exception as exc:
        return f"Error creating child note: {exc}"
    lines.append(response_summary(response))
    return format_action("Create Child Note", lines, dry_run=False)


@mcp.tool(name="zotero_apply_organization_plan", description="Apply a batch of tag/collection/note operations with dry-run safety.")
def apply_organization_plan(plan: list[dict[str, Any]], dry_run: bool = True) -> str:
    if not plan:
        return "Plan is empty."
    block = write_guard(dry_run)
    if block:
        return f"# Blocked: Apply Organization Plan\n{block}"
    lines = [f"Operations: {len(plan)}"]
    results: list[str] = []
    report: list[dict[str, Any]] = []
    for index, operation in enumerate(plan, start=1):
        op_type = operation.get("type")
        item_key = operation.get("item_key")
        status = "ok"
        if not item_key and op_type != "create_collection":
            result = f"{index}. ERROR missing item_key"
            status = "error"
        elif op_type == "update_tags":
            result = update_item_tags(item_key, operation.get("tags"), operation.get("add_tags"), operation.get("remove_tags"), dry_run)
        elif op_type == "update_collections":
            result = update_item_collections(item_key, operation.get("collections"), operation.get("add_collections"), operation.get("remove_collections"), dry_run)
        elif op_type == "update_metadata":
            result = update_item_metadata(item_key, operation.get("fields", {}), dry_run)
        elif op_type == "create_child_note":
            result = create_child_note(item_key, str(operation.get("note_text", "")), operation.get("tags"), dry_run)
        elif op_type == "create_collection":
            result = create_collection(str(operation.get("name", "")), operation.get("parent_collection"), dry_run)
        else:
            result = f"{index}. ERROR unsupported operation type: {op_type}"
            status = "error"
        if result.startswith("Error") or " ERROR " in result or result.startswith("# Blocked"):
            status = "error"
        results.append(result)
        report.append({"index": index, "type": op_type, "item_key": item_key, "status": status})
    errors = sum(1 for item in report if item["status"] == "error")
    completed = len(report) - errors
    lines.extend([f"Completed: {completed}", f"Errors: {errors}"])
    if not dry_run:
        lines.append("Rollback: automatic rollback is not attempted; use the per-step report and rerun a corrective dry-run plan before applying fixes.")
    log_event("organization_plan", dry_run=dry_run, operations=len(plan), completed=completed, errors=errors)
    return "\n\n".join([
        format_action("Apply Organization Plan", lines, dry_run, data={"report": report}),
        *results,
    ])
