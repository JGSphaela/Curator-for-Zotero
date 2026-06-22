"""Optional PDF extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class OptionalPdfDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PdfPage:
    number: int
    text: str


def require_fitz():
    try:
        import fitz  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        raise OptionalPdfDependencyError(
            "PDF tools require the optional pdf extra. Install with `uv tool install 'zotero-curator[pdf]'` "
            "or `uv pip install -e '.[pdf]'` in a checkout."
        ) from exc
    return fitz


def open_pdf(pdf_bytes: bytes):
    fitz = require_fitz()
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def extract_pages(pdf_bytes: bytes, start_page: int = 1, end_page: int | None = None) -> list[PdfPage]:
    if start_page < 1:
        raise ValueError("start_page is 1-based and must be >= 1.")
    with open_pdf(pdf_bytes) as document:
        page_count = document.page_count
        end = min(end_page or start_page, page_count)
        if end < start_page:
            raise ValueError("end_page must be greater than or equal to start_page.")
        pages = []
        for index in range(start_page - 1, end):
            pages.append(PdfPage(number=index + 1, text=document[index].get_text("text")))
        return pages


def outline(pdf_bytes: bytes) -> list[dict[str, Any]]:
    with open_pdf(pdf_bytes) as document:
        return [
            {"level": level, "title": title, "page": page}
            for level, title, page in document.get_toc(simple=True)
        ]


def page_count(pdf_bytes: bytes) -> int:
    with open_pdf(pdf_bytes) as document:
        return int(document.page_count)
