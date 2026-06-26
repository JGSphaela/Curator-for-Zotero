"""Extended tests for zotero_curator.arxiv module."""

from __future__ import annotations

from xml.etree import ElementTree

import pytest

from zotero_curator.arxiv import (
    ArxivRecord,
    _looks_like_arxiv_id,
    arxiv_pdf_filename,
    arxiv_record_to_zotero_item,
    date_only,
    first_success_key,
    https_arxiv_url,
    normalize_arxiv_id,
    optional_text,
    parse_arxiv_feed,
    text_of,
)

FULL_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2410.03529v1</id>
    <updated>2024-10-04T17:59:01Z</updated>
    <published>2024-10-04T17:59:01Z</published>
    <title>Example Paper</title>
    <summary> A compact abstract. </summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Grace Hopper</name></author>
    <arxiv:doi>10.48550/arXiv.2410.03529</arxiv:doi>
    <arxiv:comment>12 pages</arxiv:comment>
    <arxiv:journal_ref>Nature 2024</arxiv:journal_ref>
    <link href="http://arxiv.org/abs/2410.03529v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2410.03529v1" rel="related" type="application/pdf"/>
    <category term="cs.AI" />
    <category term="cs.LG" />
  </entry>
</feed>
"""

MINIMAL_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <updated>2024-01-01T00:00:00Z</updated>
    <published>2024-01-01T00:00:00Z</published>
    <title>Minimal Paper</title>
    <summary>Abstract.</summary>
    <author><name>Author</name></author>
  </entry>
</feed>
"""


# ---------------------------------------------------------------------------
# normalize_arxiv_id
# ---------------------------------------------------------------------------


class TestNormalizeArxivId:
    def test_abs_url(self) -> None:
        assert normalize_arxiv_id("https://arxiv.org/abs/2410.03529v1") == "2410.03529v1"

    def test_pdf_url(self) -> None:
        assert normalize_arxiv_id("https://arxiv.org/pdf/2410.03529.pdf") == "2410.03529"

    def test_html_url(self) -> None:
        assert normalize_arxiv_id("https://arxiv.org/html/2410.03529v1") == "2410.03529v1"

    def test_bare_modern_id(self) -> None:
        assert normalize_arxiv_id("2410.03529") == "2410.03529"

    def test_bare_modern_id_with_version(self) -> None:
        assert normalize_arxiv_id("2410.03529v2") == "2410.03529v2"

    def test_legacy_id(self) -> None:
        assert normalize_arxiv_id("hep-th/9901001v2") == "hep-th/9901001v2"

    def test_arxiv_prefix_stripped(self) -> None:
        assert normalize_arxiv_id("arXiv:2410.03529") == "2410.03529"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="provide"):
            normalize_arxiv_id("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="provide"):
            normalize_arxiv_id("   ")

    def test_non_arxiv_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Not an arXiv URL"):
            normalize_arxiv_id("https://example.com/paper.pdf")

    def test_bad_url_path_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not find"):
            normalize_arxiv_id("https://arxiv.org/not-a-valid-path")

    def test_malformed_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse"):
            normalize_arxiv_id("not-a-valid-id!!")


# ---------------------------------------------------------------------------
# _looks_like_arxiv_id
# ---------------------------------------------------------------------------


class TestLooksLikeArxivId:
    @pytest.mark.parametrize(
        "value",
        ["2410.03529", "2410.03529v1", "2410.03529v12", "hep-th/9901001", "hep-th/9901001v2"],
    )
    def test_valid(self, value: str) -> None:
        assert _looks_like_arxiv_id(value) is True

    @pytest.mark.parametrize("value", ["", "abc", "123", "12.345", "not/valid", "http://x"])
    def test_invalid(self, value: str) -> None:
        assert _looks_like_arxiv_id(value) is False


# ---------------------------------------------------------------------------
# text_of / optional_text
# ---------------------------------------------------------------------------


class TestXmlHelpers:
    def test_text_of_found(self) -> None:
        elem = ElementTree.fromstring("<root><child>hello</child></root>")
        assert text_of(elem, "child") == "hello"

    def test_text_of_not_found(self) -> None:
        elem = ElementTree.fromstring("<root/>")
        assert text_of(elem, "child") == ""

    def test_text_of_empty(self) -> None:
        elem = ElementTree.fromstring("<root><child/></root>")
        assert text_of(elem, "child") == ""

    def test_optional_text_found(self) -> None:
        elem = ElementTree.fromstring("<root><child>val</child></root>")
        assert optional_text(elem, "child") == "val"

    def test_optional_text_missing(self) -> None:
        elem = ElementTree.fromstring("<root/>")
        assert optional_text(elem, "child") is None

    def test_optional_text_empty(self) -> None:
        elem = ElementTree.fromstring("<root><child/></root>")
        assert optional_text(elem, "child") is None


# ---------------------------------------------------------------------------
# date_only
# ---------------------------------------------------------------------------


class TestDateOnly:
    def test_full_iso(self) -> None:
        assert date_only("2024-10-04T17:59:01Z") == "2024-10-04"

    def test_date_only(self) -> None:
        assert date_only("2024-10-04") == "2024-10-04"

    def test_short_string(self) -> None:
        assert date_only("2024") == "2024"

    def test_empty(self) -> None:
        assert date_only("") == ""


# ---------------------------------------------------------------------------
# https_arxiv_url
# ---------------------------------------------------------------------------


class TestHttpsArxivUrl:
    def test_converts_http(self) -> None:
        result = https_arxiv_url("http://arxiv.org/pdf/2410.03529v1")
        assert result == "https://arxiv.org/pdf/2410.03529v1"

    def test_already_https(self) -> None:
        result = https_arxiv_url("https://arxiv.org/pdf/2410.03529v1")
        assert result == "https://arxiv.org/pdf/2410.03529v1"

    def test_rejects_non_arxiv(self) -> None:
        with pytest.raises(ValueError, match="Refusing"):
            https_arxiv_url("https://example.com/paper.pdf")

    def test_rejects_wrong_path(self) -> None:
        with pytest.raises(ValueError, match="Refusing"):
            https_arxiv_url("https://arxiv.org/abs/2410.03529")


# ---------------------------------------------------------------------------
# arxiv_pdf_filename
# ---------------------------------------------------------------------------


class TestArxivPdfFilename:
    def test_modern_id(self) -> None:
        record = ArxivRecord(
            arxiv_id="2410.03529v1", title="T", authors=[], summary="", published="",
            updated="", abs_url="", pdf_url="", categories=[],
        )
        assert arxiv_pdf_filename(record) == "arxiv-2410.03529v1.pdf"

    def test_legacy_id_slash_replaced(self) -> None:
        record = ArxivRecord(
            arxiv_id="hep-th/9901001", title="T", authors=[], summary="", published="",
            updated="", abs_url="", pdf_url="", categories=[],
        )
        assert arxiv_pdf_filename(record) == "arxiv-hep-th_9901001.pdf"


# ---------------------------------------------------------------------------
# parse_arxiv_feed
# ---------------------------------------------------------------------------


class TestParseArxivFeed:
    def test_full_record(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        assert record.arxiv_id == "2410.03529v1"
        assert record.title == "Example Paper"
        assert record.summary == "A compact abstract."
        assert record.authors == ["Ada Lovelace", "Grace Hopper"]
        assert record.doi == "10.48550/arXiv.2410.03529"
        assert record.comment == "12 pages"
        assert record.journal_ref == "Nature 2024"
        assert "cs.AI" in record.categories
        assert "cs.LG" in record.categories
        assert "pdf" in record.pdf_url
        assert "abs" in record.abs_url

    def test_minimal_record(self) -> None:
        record = parse_arxiv_feed(MINIMAL_FEED)
        assert record.arxiv_id == "2401.00001v1"
        assert record.doi is None
        assert record.comment is None
        assert record.journal_ref is None

    def test_no_entry_raises(self) -> None:
        empty_feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        with pytest.raises(ValueError, match="No arXiv record found"):
            parse_arxiv_feed(empty_feed)


# ---------------------------------------------------------------------------
# arxiv_record_to_zotero_item
# ---------------------------------------------------------------------------


class TestArxivRecordToZoteroItem:
    def test_creators_format(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record)
        assert item["creators"] == [
            {"creatorType": "author", "name": "Ada Lovelace"},
            {"creatorType": "author", "name": "Grace Hopper"},
        ]

    def test_doi_included_when_present(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record)
        assert "DOI" in item
        assert item["DOI"] == "10.48550/arXiv.2410.03529"

    def test_no_doi_when_absent(self) -> None:
        record = parse_arxiv_feed(MINIMAL_FEED)
        item = arxiv_record_to_zotero_item(record)
        assert "DOI" not in item

    def test_collections_deduped(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record, collections=["A", "A", "B"])
        assert item["collections"] == ["A", "B"]

    def test_no_collections_when_empty(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record, collections=[])
        assert "collections" not in item

    def test_tags_format(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record, tags=["AI", "ML"])
        assert item["tags"] == [{"tag": "AI"}, {"tag": "ML"}]

    def test_extra_includes_metadata(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record)
        extra = str(item["extra"])
        assert "arXiv: 2410.03529v1" in extra
        assert "Journal reference:" in extra
        assert "Comment:" in extra

    def test_item_type_is_preprint(self) -> None:
        record = parse_arxiv_feed(FULL_FEED)
        item = arxiv_record_to_zotero_item(record)
        assert item["itemType"] == "preprint"
        assert item["repository"] == "arXiv"
        assert item["archive"] == "arXiv"


# ---------------------------------------------------------------------------
# first_success_key
# ---------------------------------------------------------------------------


class TestFirstSuccessKey:
    def test_dict_with_key(self) -> None:
        assert first_success_key({"successful": {"0": {"key": "ABC"}}}) == "ABC"

    def test_string_value(self) -> None:
        assert first_success_key({"successful": {"0": "DEF"}}) == "DEF"

    def test_nested_data_key(self) -> None:
        resp = {"successful": {"0": {"data": {"key": "GHI"}}}}
        assert first_success_key(resp) == "GHI"

    def test_success_variant(self) -> None:
        assert first_success_key({"success": {"0": {"key": "JKL"}}}) == "JKL"

    def test_failure_returns_none(self) -> None:
        assert first_success_key({"failed": {}}) is None

    def test_empty_dict(self) -> None:
        assert first_success_key({}) is None

    def test_non_dict(self) -> None:
        assert first_success_key("string") is None
        assert first_success_key(None) is None
        assert first_success_key(42) is None

    def test_successful_not_dict(self) -> None:
        assert first_success_key({"successful": "not-a-dict"}) is None

    def test_no_key_in_saved(self) -> None:
        assert first_success_key({"successful": {"0": {"foo": "bar"}}}) is None
