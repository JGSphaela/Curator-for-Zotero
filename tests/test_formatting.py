"""Comprehensive tests for zotero_curator.formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass

from zotero_curator.formatting import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_CHUNK_OVERLAP,
    MAX_CHUNK_CHARS,
    PROTECTED_ITEM_FIELDS,
    chunk_bounds,
    chunk_count,
    chunk_index_for_offset,
    clamp_int,
    collection_keys,
    creator_summary,
    format_action,
    format_item,
    format_item_list,
    format_item_summary,
    make_snippet,
    normalize_doi,
    normalize_whitespace,
    note_text_to_html,
    response_summary,
    set_item_collections,
    set_item_tags,
    strip_note_html,
    tag_names,
    tokenize_query,
    unique_strings,
)

# ---------------------------------------------------------------------------
# strip_note_html
# ---------------------------------------------------------------------------


class TestStripNoteHtml:
    def test_p_tags_removed(self) -> None:
        # </p> becomes \n, so trailing </p> produces a trailing newline
        assert strip_note_html("<p>Hello</p><p>World</p>") == "Hello\nWorld\n"

    def test_br_converted_to_newline(self) -> None:
        assert strip_note_html("Line1<br>Line2") == "Line1\nLine2"

    def test_strong_to_markdown_bold(self) -> None:
        assert strip_note_html("<strong>bold</strong>") == "**bold**"

    def test_em_to_markdown_italic(self) -> None:
        assert strip_note_html("<em>italic</em>") == "*italic*"

    def test_plain_text_unchanged(self) -> None:
        assert strip_note_html("Just text.") == "Just text."

    def test_mixed_tags(self) -> None:
        result = strip_note_html("<p><strong>A</strong> and <em>B</em></p>")
        assert result == "**A** and *B*\n"


# ---------------------------------------------------------------------------
# normalize_doi
# ---------------------------------------------------------------------------


class TestNormalizeDoi:
    def test_doi_org_url(self) -> None:
        assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"

    def test_dx_doi_org_url(self) -> None:
        assert normalize_doi("http://dx.doi.org/10.1234/test") == "10.1234/test"

    def test_doi_prefix(self) -> None:
        assert normalize_doi("doi: 10.5555/Test") == "10.5555/test"

    def test_bare_doi(self) -> None:
        assert normalize_doi("10.1000/simple") == "10.1000/simple"

    def test_trailing_dot_stripped(self) -> None:
        assert normalize_doi("10.1000/ABC.") == "10.1000/abc"

    def test_whitespace_stripped(self) -> None:
        assert normalize_doi("  10.1000/ws  ") == "10.1000/ws"

    def test_case_insensitive(self) -> None:
        assert normalize_doi("HTTPS://DOI.ORG/10.1000/X") == "10.1000/x"


# ---------------------------------------------------------------------------
# unique_strings
# ---------------------------------------------------------------------------


class TestUniqueStrings:
    def test_deduplication(self) -> None:
        assert unique_strings(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_whitespace_normalized(self) -> None:
        assert unique_strings([" a ", "a", " b "]) == ["a", "b"]

    def test_empty_filtered(self) -> None:
        assert unique_strings(["", "  ", "a"]) == ["a"]

    def test_none_returns_empty(self) -> None:
        assert unique_strings(None) == []

    def test_empty_list_returns_empty(self) -> None:
        assert unique_strings([]) == []

    def test_preserves_order(self) -> None:
        assert unique_strings(["c", "b", "a"]) == ["c", "b", "a"]


# ---------------------------------------------------------------------------
# tag_names / set_item_tags
# ---------------------------------------------------------------------------


class TestTagHelpers:
    def test_dict_tags(self) -> None:
        item = {"data": {"tags": [{"tag": "AI"}, {"tag": "NLP"}]}}
        assert tag_names(item) == ["AI", "NLP"]

    def test_string_tags(self) -> None:
        item = {"data": {"tags": ["AI", "NLP"]}}
        assert tag_names(item) == ["AI", "NLP"]

    def test_mixed_tags(self) -> None:
        item = {"data": {"tags": [{"tag": "AI"}, "Plain"]}}
        assert tag_names(item) == ["AI", "Plain"]

    def test_empty_tags(self) -> None:
        assert tag_names({"data": {"tags": []}}) == []

    def test_missing_data(self) -> None:
        assert tag_names({}) == []

    def test_set_creates_data_if_missing(self) -> None:
        item: dict = {}
        set_item_tags(item, ["New"])
        assert item["data"]["tags"] == [{"tag": "New"}]

    def test_set_deduplicates(self) -> None:
        item: dict = {"data": {}}
        set_item_tags(item, ["A", "A", "B"])
        assert tag_names(item) == ["A", "B"]


# ---------------------------------------------------------------------------
# collection_keys / set_item_collections
# ---------------------------------------------------------------------------


class TestCollectionHelpers:
    def test_normal(self) -> None:
        item = {"data": {"collections": ["C1", "C2"]}}
        assert collection_keys(item) == ["C1", "C2"]

    def test_missing_collections(self) -> None:
        assert collection_keys({"data": {}}) == []

    def test_missing_data(self) -> None:
        assert collection_keys({}) == []

    def test_none_collections_returns_empty(self) -> None:
        assert collection_keys({"data": {"collections": None}}) == []

    def test_set_creates_data_if_missing(self) -> None:
        item: dict = {}
        set_item_collections(item, ["C1"])
        assert item["data"]["collections"] == ["C1"]

    def test_set_deduplicates(self) -> None:
        item: dict = {"data": {}}
        set_item_collections(item, ["C1", "C1", "C2"])
        assert collection_keys(item) == ["C1", "C2"]


# ---------------------------------------------------------------------------
# note_text_to_html
# ---------------------------------------------------------------------------


class TestNoteTextToHtml:
    def test_empty_returns_empty(self) -> None:
        assert note_text_to_html("") == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert note_text_to_html("   \n  ") == ""

    def test_single_paragraph(self) -> None:
        assert note_text_to_html("Hello") == "<p>Hello</p>"

    def test_multiple_paragraphs(self) -> None:
        assert note_text_to_html("One\n\nTwo") == "<p>One</p><p>Two</p>"

    def test_html_entities_escaped(self) -> None:
        assert note_text_to_html("<script>") == "<p>&lt;script&gt;</p>"

    def test_blank_lines_filtered(self) -> None:
        result = note_text_to_html("A\n\n\nB")
        assert result == "<p>A</p><p>B</p>"


# ---------------------------------------------------------------------------
# clamp_int
# ---------------------------------------------------------------------------


class TestClampInt:
    def test_none_returns_default(self) -> None:
        assert clamp_int(None, 42, 0, 100) == 42

    def test_within_range(self) -> None:
        assert clamp_int(50, 42, 0, 100) == 50

    def test_below_minimum(self) -> None:
        assert clamp_int(-5, 42, 0, 100) == 0

    def test_above_maximum(self) -> None:
        assert clamp_int(200, 42, 0, 100) == 100

    def test_at_boundary(self) -> None:
        assert clamp_int(0, 42, 0, 100) == 0
        assert clamp_int(100, 42, 0, 100) == 100


# ---------------------------------------------------------------------------
# normalize_whitespace
# ---------------------------------------------------------------------------


class TestNormalizeWhitespace:
    def test_multiple_spaces(self) -> None:
        assert normalize_whitespace("a   b") == "a b"

    def test_tabs_and_newlines(self) -> None:
        assert normalize_whitespace("a\t\n b") == "a b"

    def test_leading_trailing_stripped(self) -> None:
        assert normalize_whitespace("  hello  ") == "hello"

    def test_empty(self) -> None:
        assert normalize_whitespace("") == ""

    def test_only_whitespace(self) -> None:
        assert normalize_whitespace("   ") == ""


# ---------------------------------------------------------------------------
# chunk_count / chunk_bounds / chunk_index_for_offset
# ---------------------------------------------------------------------------


class TestChunking:
    def test_zero_length(self) -> None:
        assert chunk_count(0, 100, 10) == 0

    def test_exact_one_chunk(self) -> None:
        assert chunk_count(100, 100, 10) == 1

    def test_one_extra_char(self) -> None:
        assert chunk_count(101, 100, 10) == 2

    def test_large_text(self) -> None:
        # 10000 chars, chunk 8000, overlap 500 -> step=7500
        # remaining=2000, 2000/7500=0.267, ceil=1, +1=2
        assert chunk_count(10000, 8000, 500) == 2

    def test_two_chunks(self) -> None:
        assert chunk_count(200, 100, 0) == 2

    def test_chunk_bounds_first(self) -> None:
        start, end = chunk_bounds(500, 1, 100, 10)
        assert start == 0
        assert end == 100

    def test_chunk_bounds_second(self) -> None:
        start, end = chunk_bounds(500, 2, 100, 10)
        assert start == 90
        assert end == 190

    def test_chunk_bounds_last_clamped(self) -> None:
        _start, end = chunk_bounds(250, 3, 100, 10)
        assert end == 250

    def test_chunk_index_for_offset_first(self) -> None:
        assert chunk_index_for_offset(0) == 1

    def test_chunk_index_for_offset_within_first(self) -> None:
        assert chunk_index_for_offset(100) == 1

    def test_chunk_index_for_offset_at_boundary(self) -> None:
        step = DEFAULT_CHUNK_CHARS - DEFAULT_CHUNK_OVERLAP
        assert chunk_index_for_offset(step) == 2


# ---------------------------------------------------------------------------
# make_snippet
# ---------------------------------------------------------------------------


class TestMakeSnippet:
    def test_start_of_text_no_prefix(self) -> None:
        result = make_snippet("hello world", 0, 100)
        assert not result.startswith("...")

    def test_middle_has_prefix_and_suffix(self) -> None:
        content = "a" * 1000
        result = make_snippet(content, 500, 50)
        assert result.startswith("...")
        assert result.endswith("...")

    def test_end_no_suffix(self) -> None:
        result = make_snippet("hello", 4, 100)
        assert not result.endswith("...")

    def test_short_text_no_ellipsis(self) -> None:
        result = make_snippet("hi", 1, 100)
        assert "..." not in result


# ---------------------------------------------------------------------------
# tokenize_query
# ---------------------------------------------------------------------------


class TestTokenizeQuery:
    def test_simple_words(self) -> None:
        assert tokenize_query("hello world") == ["hello", "world"]

    def test_hyphenated(self) -> None:
        assert tokenize_query("co-author") == ["co-author"]

    def test_underscore(self) -> None:
        assert tokenize_query("machine_learning") == ["machine_learning"]

    def test_single_char_excluded(self) -> None:
        # tokenize_query requires >= 2 chars: pattern [A-Za-z0-9][A-Za-z0-9_-]+
        result = tokenize_query("a bb c")
        assert result == ["bb"]

    def test_lowercase_normalized(self) -> None:
        assert tokenize_query("HELLO WORLD") == ["hello", "world"]


# ---------------------------------------------------------------------------
# creator_summary
# ---------------------------------------------------------------------------


class TestCreatorSummary:
    def test_first_last(self) -> None:
        data = {"creators": [{"firstName": "Ada", "lastName": "Lovelace"}]}
        assert creator_summary(data) == "Lovelace, Ada"

    def test_name_field(self) -> None:
        data = {"creators": [{"name": "University of Testing"}]}
        assert creator_summary(data) == "University of Testing"

    def test_et_al_truncation(self) -> None:
        data = {
            "creators": [
                {"firstName": "A", "lastName": "One"},
                {"firstName": "B", "lastName": "Two"},
                {"firstName": "C", "lastName": "Three"},
                {"firstName": "D", "lastName": "Four"},
            ]
        }
        result = creator_summary(data, limit=3)
        assert "et al." in result
        assert "Four" not in result

    def test_empty_creators(self) -> None:
        assert creator_summary({}) == "No authors"

    def test_mixed_formats(self) -> None:
        data = {
            "creators": [
                {"firstName": "Ada", "lastName": "Lovelace"},
                {"name": "Corp Inc"},
            ]
        }
        result = creator_summary(data)
        assert "Lovelace, Ada" in result
        assert "Corp Inc" in result


# ---------------------------------------------------------------------------
# format_item_summary
# ---------------------------------------------------------------------------


class TestFormatItemSummary:
    def test_article(self) -> None:
        item = {
            "key": "ABC123",
            "data": {
                "itemType": "journalArticle",
                "title": "Test Paper",
                "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                "date": "2024",
                "DOI": "10.1000/test",
            },
        }
        result = format_item_summary(item, index=1)
        assert "Test Paper" in result
        assert "journalArticle" in result
        assert "ABC123" in result
        assert "Lovelace, Ada" in result
        assert "10.1000/test" in result
        assert "2024" in result

    def test_note_type(self) -> None:
        item = {
            "key": "N1",
            "data": {"itemType": "note", "note": "<p>First line</p><p>Second</p>"},
        }
        result = format_item_summary(item)
        assert "First line" in result
        # Notes don't show authors
        assert "Authors" not in result

    def test_no_index(self) -> None:
        item = {"key": "K", "data": {"itemType": "book", "title": "B"}}
        result = format_item_summary(item, index=None)
        assert result.startswith("## B")

    def test_parent_item_shown(self) -> None:
        item = {
            "key": "K",
            "data": {
                "itemType": "attachment",
                "title": "Att",
                "parentItem": "PARENT",
            },
        }
        result = format_item_summary(item)
        assert "PARENT" in result

    def test_url_shown(self) -> None:
        item = {
            "key": "K",
            "data": {"itemType": "webpage", "title": "W", "url": "https://example.com"},
        }
        result = format_item_summary(item)
        assert "https://example.com" in result


# ---------------------------------------------------------------------------
# format_item
# ---------------------------------------------------------------------------


class TestFormatItemList:
    def test_detailed_markdown_preserves_full_item_metadata(self) -> None:
        item = {
            "key": "K",
            "data": {
                "itemType": "journalArticle",
                "title": "Deep Learning",
                "creators": [{"creatorType": "author", "firstName": "Yann", "lastName": "LeCun"}],
                "date": "2015",
                "publicationTitle": "Nature",
                "abstractNote": "A great paper.",
                "tags": [{"tag": "DL"}],
                "url": "https://example.com",
                "DOI": "10.1000/dl",
            },
        }
        result = format_item_list([item], title="DOI Match: 10.1000/dl", detailed=True)
        assert "# DOI Match: 10.1000/dl" in result
        assert "Publication: Nature" in result
        assert "### Abstract" in result
        assert "A great paper." in result
        assert "### Tags" in result
        assert "### Identifiers" in result
        assert "1. Deep Learning" not in result

    def test_detailed_json_keeps_single_valid_payload(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        item = {"key": "K", "data": {"itemType": "journalArticle", "title": "Deep Learning"}}
        parsed = json.loads(format_item_list([item], title="DOI Match", detailed=True))
        assert parsed["count"] == 1
        assert parsed["items"][0]["title"] == "Deep Learning"


class TestFormatItem:
    def test_article_full(self) -> None:
        item = {
            "key": "K",
            "data": {
                "itemType": "journalArticle",
                "title": "Deep Learning",
                "creators": [
                    {"creatorType": "author", "firstName": "Yann", "lastName": "LeCun"},
                    {"creatorType": "editor", "name": "Editor Corp"},
                ],
                "date": "2015",
                "publicationTitle": "Nature",
                "abstractNote": "A great paper.",
                "tags": [{"tag": "DL"}],
                "url": "https://example.com",
                "DOI": "10.1000/dl",
            },
        }
        result = format_item(item)
        assert "Deep Learning" in result
        assert "journalArticle" in result
        assert "LeCun, Yann" in result
        assert "Author:" in result
        assert "Editor:" in result
        assert "Nature" in result
        assert "A great paper." in result
        assert "DL" in result
        assert "10.1000/dl" in result
        assert "https://example.com" in result

    def test_note_formatting(self) -> None:
        item = {
            "key": "N1",
            "data": {
                "itemType": "note",
                "note": "<p>Note <strong>body</strong></p>",
                "parentItem": "PARENT",
                "tags": [{"tag": "T"}],
            },
        }
        result = format_item(item)
        assert "Note" in result
        assert "PARENT" in result
        assert "T" in result
        assert "Note **body**" in result

    def test_isbn_in_identifiers(self) -> None:
        item = {
            "key": "K",
            "data": {
                "itemType": "book",
                "title": "Book",
                "ISBN": "978-0-123456-78-9",
            },
        }
        result = format_item(item)
        assert "978-0-123456-78-9" in result


# ---------------------------------------------------------------------------
# response_summary
# ---------------------------------------------------------------------------


class TestResponseSummary:
    def test_successful_key(self) -> None:
        assert "successful=2" in response_summary({"successful": {"0": {}, "1": {}}})

    def test_failed_key(self) -> None:
        assert "failed=1" in response_summary({"failed": {"0": {}}})

    def test_unchanged_key(self) -> None:
        assert "unchanged=1" in response_summary({"unchanged": {"0": {}}})

    def test_success_key(self) -> None:
        assert "success=1" in response_summary({"success": {"0": {}}})

    def test_http_like_object(self) -> None:
        @dataclass
        class FakeResp:
            status_code: int = 200
            reason_phrase: str = "OK"

        assert response_summary(FakeResp()) == "HTTP 200 OK"

    def test_unknown_type(self) -> None:
        assert response_summary("unknown") == "write call completed"

    def test_empty_dict(self) -> None:
        assert response_summary({}) == "response=JSON object"


# ---------------------------------------------------------------------------
# format_action
# ---------------------------------------------------------------------------


class TestFormatAction:
    def test_markdown_dry_run(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "markdown")
        result = format_action("Test", ["line1"], dry_run=True)
        assert "Dry Run: Test" in result
        assert "No Zotero changes" in result
        assert "line1" in result

    def test_markdown_applied(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "markdown")
        result = format_action("Test", ["line1"], dry_run=False)
        assert "Applied: Test" in result
        assert "No Zotero changes" not in result

    def test_json_output(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        result = format_action("Test", ["line1"], dry_run=True)
        parsed = json.loads(result)
        assert parsed["title"] == "Test"
        assert parsed["dry_run"] is True

    def test_extra_data_included(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        result = format_action("Test", [], dry_run=False, data={"report": [1]})
        parsed = json.loads(result)
        assert parsed["report"] == [1]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_protected_fields_contains_key(self) -> None:
        assert "key" in PROTECTED_ITEM_FIELDS
        assert "version" in PROTECTED_ITEM_FIELDS
        assert "itemType" in PROTECTED_ITEM_FIELDS
        assert "collections" in PROTECTED_ITEM_FIELDS
        assert "tags" in PROTECTED_ITEM_FIELDS

    def test_chunk_defaults(self) -> None:
        assert DEFAULT_CHUNK_CHARS == 8000
        assert DEFAULT_CHUNK_OVERLAP == 500
        assert MAX_CHUNK_CHARS == 25000


class TestFormatItemJson:
    def test_article_json(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        item = {
            "key": "K",
            "data": {
                "itemType": "journalArticle",
                "title": "Deep Learning",
                "creators": [{"creatorType": "author", "firstName": "Yann", "lastName": "LeCun"}],
                "date": "2015",
                "DOI": "10.1000/dl",
                "tags": [{"tag": "DL"}],
            },
        }
        parsed = json.loads(format_item(item))
        assert parsed["key"] == "K"
        assert parsed["title"] == "Deep Learning"
        assert parsed["creators"]["author"] == ["LeCun, Yann"]
        assert parsed["identifiers"]["DOI"] == "10.1000/dl"
        assert parsed["tags"] == ["DL"]

    def test_note_json(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        item = {"key": "N1", "data": {"itemType": "note", "note": "<p>Hello</p>"}}
        parsed = json.loads(format_item(item))
        assert parsed["itemType"] == "note"
        assert parsed["note"] == "Hello\n"

    def test_minimal_json(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        item = {"key": "X", "data": {"itemType": "book"}}
        parsed = json.loads(format_item(item))
        assert parsed["key"] == "X"
        assert parsed["title"] == "Untitled"


class TestFormatItemSummaryJson:
    def test_summary_json_with_index(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        item = {"key": "K", "data": {"itemType": "book", "title": "B"}}
        parsed = json.loads(format_item_summary(item, index=1))
        assert parsed["index"] == 1
        assert parsed["key"] == "K"

    def test_summary_json_without_index(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
        item = {"key": "K", "data": {"itemType": "book", "title": "B"}}
        parsed = json.loads(format_item_summary(item))
        assert "index" not in parsed
        assert parsed["key"] == "K"
