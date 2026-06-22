"""arXiv import helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from zotero_curator.formatting import normalize_whitespace, unique_strings

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_ABS_URL = "https://arxiv.org/abs/{arxiv_id}"
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}.pdf"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


@dataclass(frozen=True)
class ArxivRecord:
    arxiv_id: str
    title: str
    authors: list[str]
    summary: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    categories: list[str]
    doi: str | None = None
    journal_ref: str | None = None
    comment: str | None = None


def normalize_arxiv_id(source: str) -> str:
    """Normalize an arXiv URL or identifier to the API id form."""
    value = source.strip()
    if not value:
        raise ValueError("Please provide an arXiv URL or identifier.")
    parsed = urlparse(value)
    if parsed.netloc:
        host = parsed.netloc.lower()
        if not host.endswith("arxiv.org"):
            raise ValueError(f"Not an arXiv URL: {source}")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"abs", "pdf", "html"}:
            value = parts[1]
        else:
            raise ValueError(f"Could not find an arXiv id in URL: {source}")
    value = value.removeprefix("arXiv:").removeprefix("arxiv:")
    value = value.removesuffix(".pdf")
    if not value:
        raise ValueError("Please provide an arXiv URL or identifier.")
    if not _looks_like_arxiv_id(value):
        raise ValueError(f"Could not parse arXiv id: {source}")
    return value


def _looks_like_arxiv_id(value: str) -> bool:
    import re

    modern = r"\d{4}\.\d{4,5}(?:v\d+)?"
    legacy = r"[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?"
    return re.fullmatch(f"(?:{modern})|(?:{legacy})", value) is not None


def fetch_arxiv_record(source: str, timeout: float = 20.0) -> ArxivRecord:
    arxiv_id = normalize_arxiv_id(source)
    url = f"{ARXIV_API_URL}?id_list={quote(arxiv_id)}&max_results=1"
    request = Request(url, headers={"User-Agent": "zotero-curator/0.1"})
    with urlopen(request, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8")
    return parse_arxiv_feed(xml_text, requested_id=arxiv_id)


def parse_arxiv_feed(xml_text: str, requested_id: str | None = None) -> ArxivRecord:
    root = ElementTree.fromstring(xml_text)
    entry = root.find(f"{ATOM_NS}entry")
    if entry is None:
        detail = f" for {requested_id}" if requested_id else ""
        raise ValueError(f"No arXiv record found{detail}.")
    entry_id = text_of(entry, f"{ATOM_NS}id")
    arxiv_id = normalize_arxiv_id(entry_id) if entry_id else requested_id
    if not arxiv_id:
        raise ValueError("arXiv response did not include an id.")
    title = normalize_whitespace(unescape(text_of(entry, f"{ATOM_NS}title")))
    summary = normalize_whitespace(unescape(text_of(entry, f"{ATOM_NS}summary")))
    authors = [normalize_whitespace(text_of(author, f"{ATOM_NS}name")) for author in entry.findall(f"{ATOM_NS}author")]
    categories = unique_strings(
        category.attrib.get("term", "") for category in entry.findall(f"{ATOM_NS}category")
    )
    pdf_url = ""
    abs_url = entry_id or ARXIV_ABS_URL.format(arxiv_id=arxiv_id)
    for link in entry.findall(f"{ATOM_NS}link"):
        href = link.attrib.get("href", "")
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = href
        elif link.attrib.get("rel") == "alternate" and href:
            abs_url = href
    if not pdf_url:
        pdf_url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    return ArxivRecord(
        arxiv_id=arxiv_id,
        title=title,
        authors=[author for author in authors if author],
        summary=summary,
        published=text_of(entry, f"{ATOM_NS}published"),
        updated=text_of(entry, f"{ATOM_NS}updated"),
        abs_url=abs_url,
        pdf_url=pdf_url,
        categories=categories,
        doi=optional_text(entry, f"{ARXIV_NS}doi"),
        journal_ref=optional_text(entry, f"{ARXIV_NS}journal_ref"),
        comment=optional_text(entry, f"{ARXIV_NS}comment"),
    )


def text_of(element: ElementTree.Element, path: str) -> str:
    found = element.find(path)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def optional_text(element: ElementTree.Element, path: str) -> str | None:
    text = text_of(element, path)
    return text or None


def arxiv_record_to_zotero_item(
    record: ArxivRecord,
    collections: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, object]:
    extra_lines = [f"arXiv: {record.arxiv_id}"]
    if record.journal_ref:
        extra_lines.append(f"Journal reference: {record.journal_ref}")
    if record.comment:
        extra_lines.append(f"Comment: {record.comment}")
    if record.categories:
        extra_lines.append(f"arXiv categories: {', '.join(record.categories)}")
    payload: dict[str, object] = {
        "itemType": "preprint",
        "title": record.title,
        "creators": [{"creatorType": "author", "name": author} for author in record.authors],
        "abstractNote": record.summary,
        "genre": "Preprint",
        "repository": "arXiv",
        "archive": "arXiv",
        "archiveID": record.arxiv_id,
        "date": date_only(record.published),
        "url": record.abs_url,
        "accessDate": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "libraryCatalog": "arXiv.org",
        "extra": "\n".join(extra_lines),
    }
    if record.doi:
        payload["DOI"] = record.doi
    collection_keys = unique_strings(collections or [])
    if collection_keys:
        payload["collections"] = collection_keys
    tag_names = unique_strings(tags or [])
    if tag_names:
        payload["tags"] = [{"tag": tag} for tag in tag_names]
    return payload


def arxiv_pdf_attachment_item(record: ArxivRecord, parent_key: str) -> dict[str, object]:
    return {
        "itemType": "attachment",
        "linkMode": "linked_url",
        "title": f"arXiv PDF: {record.arxiv_id}",
        "url": record.pdf_url,
        "contentType": "application/pdf",
        "parentItem": parent_key,
    }


def arxiv_imported_pdf_attachment_item(record: ArxivRecord, filename: str) -> dict[str, object]:
    return {
        "itemType": "attachment",
        "linkMode": "imported_file",
        "title": f"arXiv PDF: {record.arxiv_id}",
        "filename": filename,
        "contentType": "application/pdf",
    }


def arxiv_pdf_filename(record: ArxivRecord) -> str:
    safe_id = record.arxiv_id.replace("/", "_")
    return f"arxiv-{safe_id}.pdf"


def download_arxiv_pdf(
    record: ArxivRecord,
    directory: str | Path,
    timeout: float = 60.0,
    max_bytes: int = 100_000_000,
) -> Path:
    pdf_url = https_arxiv_url(record.pdf_url)
    destination = Path(directory) / arxiv_pdf_filename(record)
    request = Request(pdf_url, headers={"User-Agent": "zotero-curator/0.1"})
    total = 0
    first_chunk = b""
    with urlopen(request, timeout=timeout) as response, destination.open("wb") as handle:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError(f"arXiv PDF is too large: {length} bytes")
        while chunk := response.read(1024 * 1024):
            if not first_chunk:
                first_chunk = chunk[:1024]
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"arXiv PDF exceeded {max_bytes} bytes")
            handle.write(chunk)
    if b"%PDF" not in first_chunk:
        destination.unlink(missing_ok=True)
        raise ValueError("Downloaded arXiv response did not look like a PDF.")
    return destination


def https_arxiv_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("arxiv.org") or not parsed.path.startswith("/pdf/"):
        raise ValueError(f"Refusing to download non-arXiv PDF URL: {url}")
    return parsed._replace(scheme="https").geturl()


def date_only(value: str) -> str:
    return value[:10] if len(value) >= 10 else value


def first_success_key(response: object) -> str | None:
    if not isinstance(response, dict):
        return None
    successful = response.get("successful") or response.get("success")
    if not isinstance(successful, dict):
        return None
    for saved in successful.values():
        if isinstance(saved, str):
            return saved
        if isinstance(saved, dict):
            data = saved.get("data")
            if isinstance(data, dict) and isinstance(data.get("key"), str):
                return data["key"]
            if isinstance(saved.get("key"), str):
                return saved["key"]
    return None
