from __future__ import annotations

import os
import time
from copy import deepcopy
from pathlib import Path

import pytest

from zotero_curator.arxiv import (
    arxiv_imported_pdf_attachment_item,
    arxiv_pdf_attachment_item,
    arxiv_pdf_filename,
    arxiv_record_to_zotero_item,
    first_success_key,
    https_arxiv_url,
    normalize_arxiv_id,
    parse_arxiv_feed,
)
from zotero_curator.formatting import (
    chunk_bounds,
    chunk_count,
    collection_keys,
    format_action,
    normalize_doi,
    note_text_to_html,
    set_item_collections,
    set_item_tags,
    tag_names,
    unique_strings,
)
from zotero_curator.semantic import (
    SemanticIndexBusyError,
    _pid_is_running,
    document_from_item,
    semantic_index_lock,
)
from zotero_curator.settings import env_flag, read_config_file, write_config

ARXIV_FEED = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:arxiv=\"http://arxiv.org/schemas/atom\">
  <entry>
    <id>http://arxiv.org/abs/2410.03529v1</id>
    <updated>2024-10-04T17:59:01Z</updated>
    <published>2024-10-04T17:59:01Z</published>
    <title>Example   Paper</title>
    <summary> A compact abstract. </summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Grace Hopper</name></author>
    <arxiv:doi>10.48550/arXiv.2410.03529</arxiv:doi>
    <arxiv:comment>12 pages</arxiv:comment>
    <link href=\"http://arxiv.org/abs/2410.03529v1\" rel=\"alternate\" type=\"text/html\"/>
    <link title=\"pdf\" href=\"http://arxiv.org/pdf/2410.03529v1\" rel=\"related\" type=\"application/pdf\"/>
    <category term=\"cs.AI\" />
  </entry>
</feed>
"""


class FakeZotero:
    def __init__(self) -> None:
        self.created_collections: list[list[dict[str, str]]] = []
        self.updated_collections: list[dict[str, object]] = []
        self.deleted_collections: list[dict[str, object]] = []
        self.created_items: list[list[dict[str, object]]] = []
        self.updated_items: list[dict[str, object]] = []
        self.collections_by_key: dict[str, dict[str, object]] = {}
        self.items_by_key: dict[str, dict[str, object]] = {}

    def create_collections(self, payload: list[dict[str, str]]):
        self.created_collections.append(deepcopy(payload))
        return {"successful": {"0": {"key": "ABC123"}}}

    def collection(self, key: str):
        collection = self.collections_by_key.get(key)
        return deepcopy(collection) if collection else None

    def update_collection(self, collection: dict[str, object]):
        self.updated_collections.append(deepcopy(collection))
        return {"successful": {"0": collection.get("key", "COL123")}}

    def delete_collection(self, collection: dict[str, object]):
        self.deleted_collections.append(deepcopy(collection))
        return {"deleted": 1}

    def create_items(self, payload: list[dict[str, object]]):
        self.created_items.append(deepcopy(payload))
        return {"successful": {"0": {"key": "ITEM123"}}}

    def item(self, key: str):
        item = self.items_by_key.get(key)
        return deepcopy(item) if item else None

    def update_item(self, item: dict[str, object]):
        self.updated_items.append(deepcopy(item))
        return {"successful": {"0": item.get("key", "ITEM123")}}


def configure_web_writes(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
    write_config(
        local=False,
        library_id="123",
        api_key="secret",
        write_enabled=True,
        path=path,
    )



def test_normalize_doi() -> None:
    assert normalize_doi("https://doi.org/10.1000/ABC.") == "10.1000/abc"
    assert normalize_doi("doi: 10.5555/Test") == "10.5555/test"


def test_chunk_helpers() -> None:
    assert chunk_count(0, 100, 10) == 0
    assert chunk_count(100, 100, 10) == 1
    assert chunk_count(101, 100, 10) == 2
    assert chunk_bounds(250, 2, 100, 10) == (90, 190)


def test_unique_strings() -> None:
    assert unique_strings(["a", "", " a ", "b", "a"]) == ["a", "b"]


def test_tag_helpers() -> None:
    item = {"data": {"tags": [{"tag": "AI"}, {"tag": "Zotero"}]}}
    assert tag_names(item) == ["AI", "Zotero"]
    set_item_tags(item, ["New", "New", "Other"])
    assert tag_names(item) == ["New", "Other"]


def test_collection_helpers() -> None:
    item = {"data": {"collections": ["A"]}}
    assert collection_keys(item) == ["A"]
    set_item_collections(item, ["B", "B", "C"])
    assert collection_keys(item) == ["B", "C"]


def test_note_text_to_html() -> None:
    assert note_text_to_html("Hello\n\n<world>") == "<p>Hello</p><p>&lt;world&gt;</p>"


def test_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_config(
        local=False,
        library_id="123",
        library_type="group",
        api_key="secret",
        write_enabled=True,
        response_format="json",
        path=path,
    )
    values = read_config_file(path)
    assert values["local"] is False
    assert values["library_id"] == "123"
    assert values["library_type"] == "group"
    assert values["api_key"] == "secret"
    assert values["write_enabled"] is True
    assert values["response_format"] == "json"


def test_env_flag(monkeypatch) -> None:
    monkeypatch.setenv("FLAG", "yes")
    assert env_flag("FLAG") is True
    monkeypatch.setenv("FLAG", "no")
    assert env_flag("FLAG", True) is False
    monkeypatch.setenv("FLAG", "unknown")
    assert env_flag("FLAG", True) is True


def test_write_guard_allows_dry_run_in_local_mode(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
    write_config(local=True, write_enabled=True, path=path)

    from zotero_curator.server import write_guard

    assert write_guard(dry_run=True) is None


def test_local_api_writes_follow_current_zotero_protocol() -> None:
    from zotero_curator.server import LOCAL_API_WRITES_SUPPORTED

    # Zotero Local API v3 currently accepts GET only. Flip this when Zotero ships
    # local write support and Curator intentionally opts into it.
    assert LOCAL_API_WRITES_SUPPORTED is False


def test_write_guard_blocks_real_writes_in_local_mode(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
    write_config(local=True, write_enabled=True, path=path)

    from zotero_curator.server import write_guard

    blocked = write_guard(dry_run=False)
    assert blocked is not None
    assert "Local API currently accepts only GET" in blocked
    assert "Web API mode" in blocked


def test_write_guard_can_reenable_local_writes_when_zotero_supports_them(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
    write_config(local=True, write_enabled=True, path=path)

    import zotero_curator.server as server

    monkeypatch.setattr(server, "LOCAL_API_WRITES_SUPPORTED", True)

    assert server.write_guard(dry_run=False) is None


def test_write_guard_requires_web_api_key(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
    write_config(local=False, library_id="123", write_enabled=True, path=path)

    from zotero_curator.server import write_guard

    blocked = write_guard(dry_run=False)
    assert blocked is not None
    assert "API key" in blocked


def test_write_guard_allows_web_api_writes_when_enabled(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator.server import write_guard

    assert write_guard(dry_run=False) is None


def test_create_collection_uses_web_api_create_payload(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    result = server.create_collection("Literature", parent_collection="PARENT", dry_run=False)

    assert fake.created_collections == [[{"name": "Literature", "parentCollection": "PARENT"}]]
    assert "successful=1" in result


def test_rename_collection_uses_retrieved_editable_json(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    fake.collections_by_key["COL123"] = {
        "key": "COL123",
        "data": {"key": "COL123", "version": 7, "name": "Old", "parentCollection": False},
    }
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    result = server.rename_collection("COL123", "New", dry_run=False)

    assert fake.updated_collections == [
        {
            "key": "COL123",
            "data": {"key": "COL123", "version": 7, "name": "New", "parentCollection": False},
        }
    ]
    assert "successful=1" in result


def test_delete_collection_uses_retrieved_versioned_object(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    fake.collections_by_key["COL123"] = {
        "key": "COL123",
        "data": {"key": "COL123", "version": 7, "name": "Old", "parentCollection": False},
    }
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    result = server.delete_collection("COL123", dry_run=False)

    assert fake.deleted_collections == [
        {
            "key": "COL123",
            "data": {"key": "COL123", "version": 7, "name": "Old", "parentCollection": False},
        }
    ]
    assert "response=JSON object" in result


def test_update_item_tags_uses_web_api_editable_item_json(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    fake.items_by_key["ITEM123"] = {
        "key": "ITEM123",
        "data": {
            "key": "ITEM123",
            "version": 11,
            "itemType": "journalArticle",
            "title": "Paper",
            "tags": [{"tag": "Keep"}, {"tag": "Remove"}],
            "collections": ["COL1"],
        },
    }
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    result = server.update_item_tags(
        "ITEM123",
        add_tags=["Add", "Add"],
        remove_tags=["Remove"],
        dry_run=False,
    )

    assert fake.updated_items == [
        {
            "key": "ITEM123",
            "data": {
                "key": "ITEM123",
                "version": 11,
                "itemType": "journalArticle",
                "title": "Paper",
                "tags": [{"tag": "Keep"}, {"tag": "Add"}],
                "collections": ["COL1"],
            },
        }
    ]
    assert "successful=1" in result


def test_update_item_collections_uses_complete_collection_array(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    fake.items_by_key["ITEM123"] = {
        "key": "ITEM123",
        "data": {
            "key": "ITEM123",
            "version": 11,
            "itemType": "journalArticle",
            "title": "Paper",
            "tags": [],
            "collections": ["COL1", "COL2"],
        },
    }
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    result = server.update_item_collections(
        "ITEM123",
        add_collections=["COL3", "COL3"],
        remove_collections=["COL1"],
        dry_run=False,
    )

    assert fake.updated_items[0]["data"]["collections"] == ["COL2", "COL3"]
    assert fake.updated_items[0]["data"]["version"] == 11
    assert "successful=1" in result


def test_update_item_metadata_preserves_version_and_rejects_protected_fields(
    monkeypatch, tmp_path: Path
) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    fake.items_by_key["ITEM123"] = {
        "key": "ITEM123",
        "data": {
            "key": "ITEM123",
            "version": 11,
            "itemType": "journalArticle",
            "title": "Old",
            "abstractNote": "Before",
        },
    }
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    blocked = server.update_item_metadata("ITEM123", {"key": "OTHER"}, dry_run=False)
    result = server.update_item_metadata(
        "ITEM123",
        {"title": "New", "abstractNote": "After"},
        dry_run=False,
    )

    assert "protected fields" in blocked
    assert fake.updated_items == [
        {
            "key": "ITEM123",
            "data": {
                "key": "ITEM123",
                "version": 11,
                "itemType": "journalArticle",
                "title": "New",
                "abstractNote": "After",
            },
        }
    ]
    assert "successful=1" in result


def test_create_child_note_uses_web_api_item_create_payload(monkeypatch, tmp_path: Path) -> None:
    configure_web_writes(monkeypatch, tmp_path)

    from zotero_curator import server

    fake = FakeZotero()
    fake.items_by_key["PARENT"] = {
        "key": "PARENT",
        "data": {"key": "PARENT", "version": 3, "itemType": "journalArticle", "title": "Paper"},
    }
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)

    result = server.create_child_note("PARENT", "Hello\n\n<world>", tags=["Note"], dry_run=False)

    assert fake.created_items == [
        [
            {
                "itemType": "note",
                "parentItem": "PARENT",
                "note": "<p>Hello</p><p>&lt;world&gt;</p>",
                "tags": [{"tag": "Note"}],
            }
        ]
    ]
    assert "successful=1" in result


def test_arxiv_normalize_id() -> None:
    assert normalize_arxiv_id("https://arxiv.org/abs/2410.03529v1") == "2410.03529v1"
    assert normalize_arxiv_id("https://arxiv.org/pdf/2410.03529.pdf") == "2410.03529"
    assert normalize_arxiv_id("arXiv:hep-th/9901001v2") == "hep-th/9901001v2"


def test_arxiv_payloads() -> None:
    record = parse_arxiv_feed(ARXIV_FEED)
    item = arxiv_record_to_zotero_item(record, collections=["COL", "COL"], tags=["AI"])
    attachment = arxiv_pdf_attachment_item(record, "PARENT")
    imported_attachment = arxiv_imported_pdf_attachment_item(record, arxiv_pdf_filename(record))

    assert record.arxiv_id == "2410.03529v1"
    assert item["itemType"] == "preprint"
    assert item["title"] == "Example Paper"
    assert item["repository"] == "arXiv"
    assert item["archiveID"] == "2410.03529v1"
    assert item["collections"] == ["COL"]
    assert item["tags"] == [{"tag": "AI"}]
    assert attachment["itemType"] == "attachment"
    assert attachment["linkMode"] == "linked_url"
    assert attachment["parentItem"] == "PARENT"
    assert imported_attachment["linkMode"] == "imported_file"
    assert imported_attachment["filename"] == "arxiv-2410.03529v1.pdf"
    assert https_arxiv_url(record.pdf_url) == "https://arxiv.org/pdf/2410.03529v1"


def test_first_success_key() -> None:
    assert first_success_key({"successful": {"0": {"key": "ABC123"}}}) == "ABC123"
    assert first_success_key({"successful": {"0": "DEF456"}}) == "DEF456"
    assert first_success_key({"failed": {}}) is None


def test_json_action_response(monkeypatch) -> None:
    monkeypatch.setenv("ZOTERO_CURATOR_RESPONSE_FORMAT", "json")
    response = format_action("Test Action", ["one"], dry_run=True, data={"report": [{"status": "ok"}]})
    assert '"dry_run": true' in response
    assert '"report"' in response


def test_semantic_document_from_item() -> None:
    item = {
        "key": "ABC123",
        "data": {
            "key": "ABC123",
            "itemType": "journalArticle",
            "title": "Semantic Search for Zotero",
            "abstractNote": "Embeddings over citation metadata.",
            "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
        },
    }
    document = document_from_item(item)
    assert document is not None
    assert document.key == "ABC123"
    assert "Semantic Search" in document.text
    assert document.metadata["itemType"] == "journalArticle"


def test_semantic_index_lock_blocks_concurrent_access(tmp_path: Path) -> None:
    store = tmp_path / "semantic"

    with semantic_index_lock(store):
        assert (store / ".index.lock").is_dir()
        with pytest.raises(SemanticIndexBusyError), semantic_index_lock(store):
            pass

    assert not (store / ".index.lock").exists()


def test_semantic_index_lock_allows_later_access_after_release(tmp_path: Path) -> None:
    store = tmp_path / "semantic"

    with semantic_index_lock(store):
        pass

    with semantic_index_lock(store):
        assert (store / ".index.lock").is_dir()


def test_semantic_rebuild_reports_busy_lock(monkeypatch, tmp_path: Path) -> None:
    from zotero_curator import semantic, server

    monkeypatch.setattr(semantic, "semantic_store_dir", lambda: tmp_path / "semantic")
    monkeypatch.setattr(server, "get_zotero_client", lambda: object())
    monkeypatch.setattr(semantic, "require_semantic_dependencies", lambda: (object(), object()))

    with semantic.semantic_index_lock(tmp_path / "semantic"):
        result = server.semantic_rebuild()

    assert result.startswith("Semantic index busy:")


def test_semantic_search_reports_busy_lock(monkeypatch, tmp_path: Path) -> None:
    from zotero_curator import semantic, server

    monkeypatch.setattr(semantic, "semantic_store_dir", lambda: tmp_path / "semantic")
    monkeypatch.setattr(semantic, "require_semantic_dependencies", lambda: (object(), object()))

    with semantic.semantic_index_lock(tmp_path / "semantic"):
        result = server.semantic_search_items("query")

    assert result.startswith("Semantic index busy:")


class TestSemanticStaleLock:
    def test_stale_lock_cleaned_up(self, tmp_path: Path) -> None:
        """A lock older than stale_seconds with a dead PID is reclaimed."""
        store = tmp_path / "semantic"
        store.mkdir(parents=True)
        lock_dir = store / ".index.lock"
        lock_dir.mkdir()
        (lock_dir / "owner.txt").write_text(
            f"pid=99999\ncreated={time.time() - 600}\n",
            encoding="utf-8",
        )
        with semantic_index_lock(store, stale_seconds=300):
            assert (store / ".index.lock").is_dir()

    def test_stale_lock_with_live_pid_not_reclaimed(self, tmp_path: Path) -> None:
        """A stale lock whose owner PID is still running is NOT reclaimed."""
        store = tmp_path / "semantic"
        store.mkdir(parents=True)
        lock_dir = store / ".index.lock"
        lock_dir.mkdir()
        (lock_dir / "owner.txt").write_text(
            f"pid={os.getpid()}\ncreated={time.time() - 600}\n",
            encoding="utf-8",
        )
        with pytest.raises(SemanticIndexBusyError), semantic_index_lock(store, timeout_seconds=0.1, stale_seconds=300):
            pass

    def test_fresh_lock_not_reclaimed(self, tmp_path: Path) -> None:
        """A lock younger than stale_seconds is NOT removed."""
        store = tmp_path / "semantic"
        store.mkdir(parents=True)
        lock_dir = store / ".index.lock"
        lock_dir.mkdir()
        (lock_dir / "owner.txt").write_text(
            f"pid=99999\ncreated={time.time()}\n",
            encoding="utf-8",
        )
        with pytest.raises(SemanticIndexBusyError), semantic_index_lock(store, timeout_seconds=0.1, stale_seconds=300):
            pass

    def test_stale_lock_uses_mtime_fallback(self, tmp_path: Path) -> None:
        """When owner.txt is missing, mtime of the lock dir is used."""
        store = tmp_path / "semantic"
        store.mkdir(parents=True)
        lock_dir = store / ".index.lock"
        lock_dir.mkdir()
        old_time = time.time() - 600
        os.utime(lock_dir, (old_time, old_time))
        with semantic_index_lock(store, stale_seconds=300):
            pass

    def test_windows_pid_check_does_not_use_os_kill(self, monkeypatch) -> None:
        """Windows liveness probing must not call os.kill(pid, 0)."""
        from zotero_curator import semantic

        calls: list[tuple[int, int]] = []

        class FakeKernel32:
            def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
                assert access == 0x1000
                assert inherit is False
                assert pid == 1234
                return 1

            def GetExitCodeProcess(self, handle: int, exit_code) -> int:
                assert handle == 1
                exit_code._obj.value = 259
                return 1

            def CloseHandle(self, handle: int) -> int:
                assert handle == 1
                return 1

            def GetLastError(self) -> int:
                return 0

        monkeypatch.setattr(semantic.platform, "system", lambda: "Windows")
        monkeypatch.setattr(semantic.os, "kill", lambda pid, sig: calls.append((pid, sig)))
        monkeypatch.setattr(semantic.ctypes, "windll", type("FakeWindll", (), {"kernel32": FakeKernel32()})(), raising=False)

        assert _pid_is_running(1234) is True
        assert calls == []

    def test_windows_pid_check_unverifiable_on_access_failure(self, monkeypatch) -> None:
        """A failed Windows process open should not be treated as safely dead."""
        from zotero_curator import semantic

        class FakeKernel32:
            def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
                return 0

            def GetLastError(self) -> int:
                return 5

        monkeypatch.setattr(semantic.platform, "system", lambda: "Windows")
        monkeypatch.setattr(semantic.ctypes, "windll", type("FakeWindll", (), {"kernel32": FakeKernel32()})(), raising=False)

        assert _pid_is_running(1234) is None

    def test_windows_pid_check_false_for_invalid_parameter(self, monkeypatch) -> None:
        """Windows ERROR_INVALID_PARAMETER means the process id is gone."""
        from zotero_curator import semantic

        class FakeKernel32:
            def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
                return 0

            def GetLastError(self) -> int:
                return 87

        monkeypatch.setattr(semantic.platform, "system", lambda: "Windows")
        monkeypatch.setattr(semantic.ctypes, "windll", type("FakeWindll", (), {"kernel32": FakeKernel32()})(), raising=False)

        assert _pid_is_running(1234) is False
