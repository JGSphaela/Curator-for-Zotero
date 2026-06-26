"""Tests for server.py helper functions (write guard, headings, text extraction)."""

from __future__ import annotations

from pathlib import Path

from zotero_curator.server import (
    extract_headings,
    find_heading_matches,
    get_indexed_attachment_text,
    get_pdf_attachment_bytes,
    heading_score,
    iter_lines_with_offsets,
    section_end_offset,
    write_guard,
    zotero_backend_write_capable,
)
from zotero_curator.settings import CuratorConfig, write_config


def _configure(monkeypatch, tmp_path: Path, **kwargs) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
    write_config(path=path, **kwargs)


# ---------------------------------------------------------------------------
# zotero_backend_write_capable
# ---------------------------------------------------------------------------


class TestBackendWriteCapable:
    def test_local_returns_constant(self) -> None:
        cfg = CuratorConfig(local=True)
        assert zotero_backend_write_capable(cfg) is False

    def test_web_with_key(self) -> None:
        cfg = CuratorConfig(local=False, api_key="key")
        assert zotero_backend_write_capable(cfg) is True

    def test_web_no_key(self) -> None:
        cfg = CuratorConfig(local=False, api_key=None)
        assert zotero_backend_write_capable(cfg) is False

    def test_web_empty_key(self) -> None:
        cfg = CuratorConfig(local=False, api_key="")
        assert zotero_backend_write_capable(cfg) is False


# ---------------------------------------------------------------------------
# write_guard
# ---------------------------------------------------------------------------


class TestWriteGuard:
    def test_dry_run_always_allowed(self, monkeypatch, tmp_path: Path) -> None:
        _configure(monkeypatch, tmp_path, local=True)
        assert write_guard(dry_run=True) is None

    def test_local_blocks(self, monkeypatch, tmp_path: Path) -> None:
        _configure(monkeypatch, tmp_path, local=True, write_enabled=True)
        result = write_guard(dry_run=False)
        assert result is not None
        assert "Local API currently accepts only GET" in result

    def test_web_no_key_blocks(self, monkeypatch, tmp_path: Path) -> None:
        _configure(monkeypatch, tmp_path, local=False, library_id="1", write_enabled=True)
        result = write_guard(dry_run=False)
        assert result is not None
        assert "API key" in result

    def test_web_write_disabled_blocks(self, monkeypatch, tmp_path: Path) -> None:
        _configure(
            monkeypatch, tmp_path, local=False, library_id="1", api_key="k", write_enabled=False,
        )
        result = write_guard(dry_run=False)
        assert result is not None
        assert "write_enabled" in result

    def test_web_all_writes_allowed(self, monkeypatch, tmp_path: Path) -> None:
        _configure(
            monkeypatch, tmp_path, local=False, library_id="1", api_key="k", write_enabled=True,
        )
        assert write_guard(dry_run=False) is None


# ---------------------------------------------------------------------------
# iter_lines_with_offsets
# ---------------------------------------------------------------------------


class TestIterLinesWithOffsets:
    def test_simple(self) -> None:
        lines = iter_lines_with_offsets("hello\nworld")
        assert len(lines) == 2
        assert lines[0] == (0, "hello")
        assert lines[1] == (6, "world")

    def test_empty_lines_skipped(self) -> None:
        lines = iter_lines_with_offsets("a\n\nb")
        assert len(lines) == 2

    def test_leading_whitespace_offset(self) -> None:
        lines = iter_lines_with_offsets("  hello")
        assert lines[0][0] == 2  # offset of 'h' in '  hello'
        assert lines[0][1] == "hello"

    def test_tabs_normalized(self) -> None:
        lines = iter_lines_with_offsets("\tworld")
        assert lines[0][1] == "world"


# ---------------------------------------------------------------------------
# heading_score
# ---------------------------------------------------------------------------


class TestHeadingScore:
    def test_short_line_zero(self) -> None:
        assert heading_score("ab") == 0

    def test_long_line_zero(self) -> None:
        assert heading_score("x" * 200) == 0

    def test_pure_digits_zero(self) -> None:
        assert heading_score("12345") == 0

    def test_chapter_prefix(self) -> None:
        assert heading_score("Chapter 1 Introduction") >= 5

    def test_numbered_section(self) -> None:
        assert heading_score("3.1 Methods") >= 4

    def test_dot_leader(self) -> None:
        assert heading_score("Conclusion... 42") >= 3

    def test_mostly_uppercase(self) -> None:
        assert heading_score("ABSTRACT OF THE PAPER") >= 2

    def test_short_title_case(self) -> None:
        score = heading_score("Introduction")
        assert score >= 1


# ---------------------------------------------------------------------------
# extract_headings
# ---------------------------------------------------------------------------


class TestExtractHeadings:
    def test_extracts_high_scoring_lines(self) -> None:
        content = "Chapter 1\n\nSome text\n\nChapter 2\n\nMore text"
        headings = extract_headings(content)
        titles = [h["title"] for h in headings]
        assert "Chapter 1" in titles
        assert "Chapter 2" in titles

    def test_dedupe_by_default(self) -> None:
        content = "Chapter 1\n\nText\n\nChapter 1"
        headings = extract_headings(content, dedupe=True)
        titles = [h["title"] for h in headings]
        assert titles.count("Chapter 1") == 1

    def test_no_dedupe(self) -> None:
        content = "Chapter 1\n\nText\n\nChapter 1"
        headings = extract_headings(content, dedupe=False)
        titles = [h["title"] for h in headings]
        assert titles.count("Chapter 1") == 2

    def test_limit_respected(self) -> None:
        lines = [f"Chapter {i}" for i in range(20)]
        content = "\n\n".join(lines)
        headings = extract_headings(content, limit=5)
        assert len(headings) <= 5

    def test_empty_content(self) -> None:
        assert extract_headings("") == []


# ---------------------------------------------------------------------------
# section_end_offset / find_heading_matches
# ---------------------------------------------------------------------------


class TestSectionHelpers:
    def test_section_end_offset_finds_next(self) -> None:
        headings = [
            {"title": "A", "offset": 0, "score": 5, "chunk": 1},
            {"title": "B", "offset": 100, "score": 5, "chunk": 1},
            {"title": "C", "offset": 200, "score": 5, "chunk": 1},
        ]
        assert section_end_offset(headings, 0, 999) == 100
        assert section_end_offset(headings, 100, 999) == 200

    def test_section_end_offset_uses_content_length(self) -> None:
        headings = [{"title": "A", "offset": 0, "score": 5, "chunk": 1}]
        assert section_end_offset(headings, 0, 500) == 500

    def test_find_heading_matches_substring(self) -> None:
        headings = [
            {"title": "Chapter 1: Introduction", "offset": 0, "score": 5, "chunk": 1},
            {"title": "Chapter 2: Methods", "offset": 100, "score": 5, "chunk": 1},
        ]
        matches = find_heading_matches(headings, "Introduction")
        assert len(matches) == 1
        assert matches[0]["offset"] == 0

    def test_find_heading_matches_token_subset(self) -> None:
        headings = [
            {"title": "Introduction to Deep Learning", "offset": 0, "score": 5, "chunk": 1},
        ]
        matches = find_heading_matches(headings, "deep learning")
        assert len(matches) == 1

    def test_find_heading_matches_no_match(self) -> None:
        headings = [
            {"title": "Chapter 1", "offset": 0, "score": 5, "chunk": 1},
        ]
        assert find_heading_matches(headings, "Conclusion") == []

    def test_find_heading_matches_empty_needle(self) -> None:
        headings = [{"title": "X", "offset": 0, "score": 5, "chunk": 1}]
        assert find_heading_matches(headings, "") == []
        assert find_heading_matches(headings, "   ") == []


# ---------------------------------------------------------------------------
# get_indexed_attachment_text
# ---------------------------------------------------------------------------


class TestGetIndexedAttachmentText:
    def _make_fake_zotero(self, items=None, fulltext=None, children=None):
        class Fake:
            def __init__(self):
                self._items = items or {}
                self._fulltext = fulltext or {}
                self._children = children or {}

            def item(self, key):
                return self._items.get(key)

            def fulltext_item(self, key):
                return self._fulltext.get(key)

            def children(self, key):
                return self._children.get(key, [])

        return Fake()

    def test_no_item(self) -> None:
        zot = self._make_fake_zotero()
        item, _att, _content, error = get_indexed_attachment_text(zot, "MISSING")
        assert item is None
        assert "No item found" in error

    def test_no_attachment(self) -> None:
        zot = self._make_fake_zotero(
            items={"K1": {"key": "K1", "data": {"key": "K1", "itemType": "book"}}},
            children={"K1": []},
        )
        item, att, _content, error = get_indexed_attachment_text(zot, "K1")
        assert item is not None
        assert att is None
        assert "No suitable attachment" in error

    def test_no_fulltext(self) -> None:
        zot = self._make_fake_zotero(
            items={"K1": {"key": "K1", "data": {"key": "K1", "itemType": "book"}}},
            children={
                "K1": [
                    {
                        "data": {
                            "itemType": "attachment",
                            "key": "ATT1",
                            "contentType": "application/pdf",
                        },
                        "key": "ATT1",
                    }
                ]
            },
            fulltext={},
        )
        _item, att, content, error = get_indexed_attachment_text(zot, "K1")
        assert att is not None
        assert content is None
        assert "indexed text is not available" in error

    def test_success(self) -> None:
        zot = self._make_fake_zotero(
            items={"K1": {"key": "K1", "data": {"key": "K1", "itemType": "book"}}},
            children={
                "K1": [
                    {
                        "data": {
                            "itemType": "attachment",
                            "key": "ATT1",
                            "contentType": "application/pdf",
                        },
                        "key": "ATT1",
                    }
                ]
            },
            fulltext={"ATT1": {"content": "Hello world"}},
        )
        _item, _att, content, error = get_indexed_attachment_text(zot, "K1")
        assert error is None
        assert content == "Hello world"


# ---------------------------------------------------------------------------
# get_pdf_attachment_bytes
# ---------------------------------------------------------------------------


class TestGetPdfAttachmentBytes:
    def _make_fake_zotero(self, items=None, children=None, file_data=None):
        class Fake:
            def __init__(self):
                self._items = items or {}
                self._children = children or {}
                self._file = file_data or {}

            def item(self, key):
                return self._items.get(key)

            def children(self, key):
                return self._children.get(key, [])

            def file(self, key):
                return self._file.get(key)

        return Fake()

    def test_no_item(self) -> None:
        zot = self._make_fake_zotero()
        item, _att, _data, error = get_pdf_attachment_bytes(zot, "MISSING")
        assert item is None
        assert "No item found" in error

    def test_no_attachment(self) -> None:
        zot = self._make_fake_zotero(
            items={"K1": {"key": "K1", "data": {"key": "K1", "itemType": "book"}}},
            children={"K1": []},
        )
        _item, att, _data, error = get_pdf_attachment_bytes(zot, "K1")
        assert att is None
        assert "No suitable attachment" in error

    def test_not_pdf(self) -> None:
        zot = self._make_fake_zotero(
            items={"K1": {"key": "K1", "data": {"key": "K1", "itemType": "book"}}},
            children={
                "K1": [
                    {
                        "data": {
                            "itemType": "attachment",
                            "key": "ATT1",
                            "contentType": "text/html",
                        },
                        "key": "ATT1",
                    }
                ]
            },
        )
        _item, _att, _data, error = get_pdf_attachment_bytes(zot, "K1")
        assert "not a PDF" in error
