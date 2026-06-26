"""Formatting and text helpers for Zotero MCP responses."""

from __future__ import annotations

import json
import re
from html import escape
from math import ceil
from typing import Any

DEFAULT_CHUNK_CHARS = 8000
DEFAULT_CHUNK_OVERLAP = 500
MAX_CHUNK_CHARS = 25000
MAX_CONTEXT_CHARS = 2500
PROTECTED_ITEM_FIELDS = {
    "key",
    "version",
    "itemType",
    "collections",
    "tags",
    "relations",
    "dateAdded",
    "dateModified",
    "parentItem",
}


def strip_note_html(note: str) -> str:
    note = note.replace("<p>", "").replace("</p>", "\n").replace("<br>", "\n")
    note = note.replace("<strong>", "**").replace("</strong>", "**")
    return note.replace("<em>", "*").replace("</em>", "*")


def normalize_doi(doi: str) -> str:
    normalized = doi.strip()
    normalized = re.sub(
        r"^https?://(?:dx\.)?doi\.org/", "", normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.IGNORECASE)
    return normalized.strip().rstrip(".").lower()


def unique_strings(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def tag_names(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for tag in item.get("data", {}).get("tags", []):
        if isinstance(tag, dict) and tag.get("tag"):
            names.append(str(tag["tag"]))
        elif isinstance(tag, str):
            names.append(tag)
    return names


def set_item_tags(item: dict[str, Any], tags: list[str]) -> None:
    item.setdefault("data", {})["tags"] = [{"tag": tag} for tag in unique_strings(tags)]


def collection_keys(item: dict[str, Any]) -> list[str]:
    return list(item.get("data", {}).get("collections", []) or [])


def set_item_collections(item: dict[str, Any], collections: list[str]) -> None:
    item.setdefault("data", {})["collections"] = unique_strings(collections)


def note_text_to_html(text: str) -> str:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    if not paragraphs:
        return ""
    return "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)


def clamp_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    return max(minimum, min(value, maximum))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_count(text_length: int, chunk_chars: int, overlap_chars: int) -> int:
    if text_length <= 0:
        return 0
    step = max(1, chunk_chars - overlap_chars)
    return max(1, ceil(max(0, text_length - chunk_chars) / step) + 1)


def chunk_bounds(
    text_length: int, chunk_index: int, chunk_chars: int, overlap_chars: int
) -> tuple[int, int]:
    step = max(1, chunk_chars - overlap_chars)
    start = max(0, (chunk_index - 1) * step)
    end = min(text_length, start + chunk_chars)
    return start, end


def chunk_index_for_offset(
    offset: int,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    step = max(1, chunk_chars - overlap_chars)
    return max(1, offset // step + 1)


def make_snippet(content: str, center: int, context_chars: int) -> str:
    start = max(0, center - context_chars)
    end = min(len(content), center + context_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{normalize_whitespace(content[start:end])}{suffix}"


def tokenize_query(query: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]+", query)]


def creator_summary(data: dict[str, Any], limit: int = 3) -> str:
    creators: list[str] = []
    for creator in data.get("creators", [])[:limit]:
        if "firstName" in creator and "lastName" in creator:
            creators.append(f"{creator['lastName']}, {creator['firstName']}")
        elif "name" in creator:
            creators.append(creator["name"])
    if len(data.get("creators", [])) > limit:
        creators.append("et al.")
    return "; ".join(creators) if creators else "No authors"


def format_item_summary(item: dict[str, Any], index: int | None = None) -> str:
    if wants_json_response():
        d = _item_to_dict(item)
        if index is not None:
            d["index"] = index
        return json.dumps(d, indent=2, sort_keys=True, default=str)
    data = item.get("data", {})
    item_key = item.get("key") or data.get("key", "")
    item_type = data.get("itemType", "unknown")
    title = data.get("title", "Untitled")
    if item_type == "note":
        note_content = strip_note_html(data.get("note", ""))
        first_line = note_content.strip().split("\n", maxsplit=1)[0]
        title = first_line[:80] if first_line else "Note"
    prefix = f"{index}. " if index is not None else ""
    lines = [
        f"## {prefix}{title}",
        f"**Type**: {item_type} | **Key**: `{item_key}`",
    ]
    if date := data.get("date"):
        lines.append(f"**Date**: {date}")
    if item_type != "note":
        lines.append(f"**Authors**: {creator_summary(data)}")
    if doi := data.get("DOI"):
        lines.append(f"**DOI**: {doi}")
    if url := data.get("url"):
        lines.append(f"**URL**: {url}")
    if parent := data.get("parentItem"):
        lines.append(f"**Parent Item**: `{parent}`")
    return "\n".join(lines)


def _item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a Zotero item to a structured dict for JSON output."""
    data = item.get("data", {})
    item_key = item.get("key") or data.get("key", "")
    item_type = data.get("itemType", "unknown")

    creators_by_role: dict[str, list[str]] = {}
    for creator in data.get("creators", []):
        role = creator.get("creatorType", "contributor")
        if "firstName" in creator and "lastName" in creator:
            name = f"{creator['lastName']}, {creator['firstName']}"
        else:
            name = creator.get("name", "")
        if name:
            creators_by_role.setdefault(role, []).append(name)

    identifiers: dict[str, str] = {}
    for field in ("url", "DOI", "ISBN"):
        if value := data.get(field):
            identifiers[field] = value

    result: dict[str, Any] = {
        "key": item_key,
        "itemType": item_type,
        "title": data.get("title", "Untitled"),
    }
    if item_type == "note":
        result["note"] = strip_note_html(data.get("note", ""))
    else:
        result["date"] = data.get("date", "")
        result["creators"] = creators_by_role
        if pub := data.get("publicationTitle"):
            result["publicationTitle"] = pub
        if abstract := data.get("abstractNote"):
            result["abstract"] = abstract
    if tags := tag_names(item):
        result["tags"] = tags
    if identifiers:
        result["identifiers"] = identifiers
    if parent := data.get("parentItem"):
        result["parentItem"] = parent
    return result


def format_item(item: dict[str, Any]) -> str:
    if wants_json_response():
        return json.dumps(_item_to_dict(item), indent=2, sort_keys=True, default=str)
    data = item.get("data", {})
    item_key = item.get("key") or data.get("key", "")
    item_type = data.get("itemType", "unknown")
    if item_type == "note":
        note_content = strip_note_html(data.get("note", ""))
        formatted = ["## Note", f"Item Key: `{item_key}`"]
        if parent_item := data.get("parentItem"):
            formatted.append(f"Parent Item: `{parent_item}`")
        if tags := tag_names(item):
            formatted.append("\n### Tags\n" + ", ".join(f"`{tag}`" for tag in tags))
        formatted.append(f"\n### Note Content\n{note_content}")
        return "\n".join(formatted)

    formatted = [
        f"## {data.get('title', 'Untitled')}",
        f"Item Key: `{item_key}`",
        f"Type: {item_type}",
        f"Date: {data.get('date', 'No date')}",
    ]
    creators_by_role: dict[str, list[str]] = {}
    for creator in data.get("creators", []):
        role = creator.get("creatorType", "contributor")
        if "firstName" in creator and "lastName" in creator:
            name = f"{creator['lastName']}, {creator['firstName']}"
        else:
            name = creator.get("name", "")
        if name:
            creators_by_role.setdefault(role, []).append(name)
    for role, names in creators_by_role.items():
        formatted.append(f"{role.capitalize()}: {'; '.join(names)}")
    if publication := data.get("publicationTitle"):
        formatted.append(f"Publication: {publication}")
    if abstract := data.get("abstractNote"):
        formatted.append(f"\n### Abstract\n{abstract}")
    if tags := tag_names(item):
        formatted.append("\n### Tags\n" + ", ".join(f"`{tag}`" for tag in tags))
    identifiers = []
    for label, field in [("URL", "url"), ("DOI", "DOI"), ("ISBN", "ISBN")]:
        if value := data.get(field):
            identifiers.append(f"{label}: {value}")
    if identifiers:
        formatted.append("\n### Identifiers\n" + "\n".join(identifiers))
    return "\n".join(formatted)


def response_summary(response: Any) -> str:
    if isinstance(response, dict):
        parts = []
        for key in ["successful", "failed", "unchanged", "success", "failure"]:
            if key in response:
                parts.append(f"{key}={len(response[key])}")
        return ", ".join(parts) if parts else "response=JSON object"
    status_code = getattr(response, "status_code", None)
    reason = getattr(response, "reason_phrase", "")
    if status_code is not None:
        return f"HTTP {status_code}" + (f" {reason}" if reason else "")
    return "write call completed"


def wants_json_response() -> bool:
    try:
        from zotero_curator.settings import load_config

        return load_config().response_format == "json"
    except Exception:
        return False


def format_action(title: str, lines: list[str], dry_run: bool, data: dict[str, Any] | None = None) -> str:
    mode = "Dry Run" if dry_run else "Applied"
    payload = {"title": title, "mode": mode, "dry_run": dry_run, "lines": lines, **(data or {})}
    if wants_json_response():
        return json.dumps(payload, indent=2, sort_keys=True, default=str)
    prefix = [f"# {mode}: {title}"]
    if dry_run:
        prefix.append("No Zotero changes were made.")
    return "\n".join(prefix + lines)
