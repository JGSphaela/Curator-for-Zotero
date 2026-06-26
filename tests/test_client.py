"""Tests for zotero_curator.client module."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from zotero_curator.client import AttachmentDetails, get_attachment_details, get_zotero_client
from zotero_curator.settings import write_config

# ---------------------------------------------------------------------------
# AttachmentDetails model
# ---------------------------------------------------------------------------


class TestAttachmentDetails:
    def test_basic(self) -> None:
        att = AttachmentDetails(key="ABC", content_type="application/pdf")
        assert att.key == "ABC"
        assert att.content_type == "application/pdf"

    def test_none_content_type(self) -> None:
        att = AttachmentDetails(key="ABC")
        assert att.content_type is None


# ---------------------------------------------------------------------------
# get_zotero_client
# ---------------------------------------------------------------------------


class TestGetZoteroClient:
    def test_web_no_key_raises(self, monkeypatch, tmp_path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        write_config(local=False, library_id="123", path=path)

        with pytest.raises(ValueError, match="Missing Zotero Web API"):
            get_zotero_client()

    def test_web_no_library_id_raises(self, monkeypatch, tmp_path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        # local=False, but library_id defaults to "" when not provided and not local
        write_config(local=False, path=path)

        with pytest.raises(ValueError, match="Missing Zotero Web API"):
            get_zotero_client()

    def test_local_mode_ok(self, monkeypatch, tmp_path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        write_config(local=True, path=path)

        # This should not raise — local mode doesn't need API key
        client = get_zotero_client()
        assert client is not None


# ---------------------------------------------------------------------------
# get_attachment_details
# ---------------------------------------------------------------------------


class TestGetAttachmentDetails:
    def _make_zot(self, children: list[dict[str, Any]] | None = None, exc: Exception | None = None):
        zot = MagicMock()
        if exc:
            zot.children.side_effect = exc
        else:
            zot.children.return_value = children or []
        return zot

    def test_prefers_pdf(self) -> None:
        zot = self._make_zot(children=[
            {"data": {"itemType": "attachment", "key": "H1", "contentType": "text/html"}},
            {"data": {"itemType": "attachment", "key": "P1", "contentType": "application/pdf"}},
        ])
        item = {"key": "ITEM", "data": {"key": "ITEM", "itemType": "journalArticle"}}
        result = get_attachment_details(zot, item)
        assert result is not None
        assert result.key == "P1"

    def test_html_over_other(self) -> None:
        zot = self._make_zot(children=[
            {"data": {"itemType": "attachment", "key": "X1", "contentType": "text/plain"}},
            {"data": {"itemType": "attachment", "key": "H1", "contentType": "text/html"}},
        ])
        item = {"key": "ITEM", "data": {"key": "ITEM", "itemType": "journalArticle"}}
        result = get_attachment_details(zot, item)
        assert result is not None
        assert result.key == "H1"

    def test_no_children_returns_none(self) -> None:
        zot = self._make_zot(children=[])
        item = {"key": "ITEM", "data": {"key": "ITEM", "itemType": "journalArticle"}}
        assert get_attachment_details(zot, item) is None

    def test_only_non_attachments(self) -> None:
        zot = self._make_zot(children=[
            {"data": {"itemType": "note", "key": "N1"}},
        ])
        item = {"key": "ITEM", "data": {"key": "ITEM", "itemType": "journalArticle"}}
        assert get_attachment_details(zot, item) is None

    def test_exception_returns_none(self) -> None:
        zot = self._make_zot(exc=RuntimeError("network error"))
        item = {"key": "ITEM", "data": {"key": "ITEM", "itemType": "journalArticle"}}
        assert get_attachment_details(zot, item) is None

    def test_direct_attachment_item(self) -> None:
        zot = self._make_zot()
        item = {
            "key": "ATT1",
            "data": {"key": "ATT1", "itemType": "attachment", "contentType": "application/pdf"},
        }
        result = get_attachment_details(zot, item)
        assert result is not None
        assert result.key == "ATT1"
        assert result.content_type == "application/pdf"

    def test_direct_attachment_no_key(self) -> None:
        zot = self._make_zot()
        item = {"data": {"itemType": "attachment", "contentType": "application/pdf"}}
        result = get_attachment_details(zot, item)
        assert result is None

    def test_tie_breaker_with_md5(self) -> None:
        zot = self._make_zot(children=[
            {"data": {"itemType": "attachment", "key": "P1", "contentType": "application/pdf", "md5": "aaa"}},
            {"data": {"itemType": "attachment", "key": "P2", "contentType": "application/pdf", "md5": "bbb"}},
        ])
        item = {"key": "ITEM", "data": {"key": "ITEM", "itemType": "journalArticle"}}
        result = get_attachment_details(zot, item)
        # Higher md5 sorts last in reverse, so "bbb" > "aaa"
        assert result is not None
        assert result.key == "P2"
