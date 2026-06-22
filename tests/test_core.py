from __future__ import annotations

from pathlib import Path

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
from zotero_curator.semantic import document_from_item
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

    def create_collections(self, payload: list[dict[str, str]]):
        self.created_collections.append(payload)
        return {"successful": {"0": {"key": "ABC123"}}}



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


def test_create_collection_payload(monkeypatch) -> None:
    from zotero_curator import server

    fake = FakeZotero()
    monkeypatch.setattr(server, "get_zotero_client", lambda: fake)
    monkeypatch.setattr(server, "write_guard", lambda dry_run: None)

    result = server.create_collection("Literature", parent_collection="PARENT", dry_run=False)

    assert fake.created_collections == [[{"name": "Literature", "parentCollection": "PARENT"}]]
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
