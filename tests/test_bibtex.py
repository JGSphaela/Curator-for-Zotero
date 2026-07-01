from __future__ import annotations

from pathlib import Path

import pytest

from zotero_curator.bibtex import (
    BetterBibtexUnavailableError,
    bbt_citation_keys,
    bbt_export_items,
    bibtex_for_items,
    export_bibtex_file,
    extract_bibtex_keys,
    extract_latex_citation_keys,
    format_bibtex_export_result,
    latex_cite_command,
    managed_export_path,
    safe_export_filename,
    validate_latex_citations,
)
from zotero_curator.settings import CuratorConfig


class FakeZotero:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.entries = {
            "ABC123": "@article{lovelace1843notes,\n  title = {Notes},\n}\n",
            "DEF456": "@inproceedings{hopper1952compiler,\n  title = {Compiler},\n}\n",
        }

    def item(self, key: str, **kwargs: object) -> str:
        self.calls.append((key, kwargs))
        return self.entries[key]


def test_extract_bibtex_keys() -> None:
    text = """
@article{alpha2024,
  title = {A}
}

@inproceedings{beta-2025,
  title = {B}
}
"""
    assert extract_bibtex_keys(text) == ["alpha2024", "beta-2025"]


def test_safe_export_filename_rejects_paths() -> None:
    assert safe_export_filename("refs") == "refs.bib"
    assert safe_export_filename("refs.bib") == "refs.bib"
    with pytest.raises(ValueError, match="filename only"):
        safe_export_filename("../refs.bib")
    with pytest.raises(ValueError, match="filename only"):
        safe_export_filename("subdir/refs.bib")


def test_managed_export_path_stays_under_data_dir(tmp_path: Path) -> None:
    cfg = CuratorConfig(data_dir=tmp_path)
    assert managed_export_path(cfg, "refs.bib") == (tmp_path / "exports" / "refs.bib").resolve()


def test_export_bibtex_file_writes_bib_and_sidecars(tmp_path: Path) -> None:
    fake = FakeZotero()
    result = export_bibtex_file(
        zot=fake,
        item_keys=["abc123", "DEF456", "abc123"],
        bib_path=tmp_path / "references.bib",
    )

    assert fake.calls == [
        ("ABC123", {"format": "bibtex"}),
        ("DEF456", {"format": "bibtex"}),
    ]
    assert result.citation_keys == ["lovelace1843notes", "hopper1952compiler"]
    assert result.bib_path.read_text(encoding="utf-8").count("@") == 2
    assert result.keys_path.exists()
    assert result.cite_path.read_text(encoding="utf-8") == "\\cite{lovelace1843notes,hopper1952compiler}\n"


def test_export_bibtex_file_blocks_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "references.bib"
    path.write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_bibtex_file(zot=FakeZotero(), item_keys=["ABC123"], bib_path=path)


def test_latex_cite_command() -> None:
    assert latex_cite_command(["a", "b"]) == "\\cite{a,b}"


def test_extract_latex_citation_keys_handles_common_commands_and_comments() -> None:
    latex = r"""
This cites \cite{alpha,beta} and \parencite[see][12]{gamma}.
% \cite{commentedOut}
This is escaped \% not a comment \textcite{delta}.
\nocite{*}
"""
    keys, nocite_all = extract_latex_citation_keys(latex)
    assert keys == ["alpha", "beta", "gamma", "delta"]
    assert nocite_all is True


def test_validate_latex_citations_reports_missing_and_unused() -> None:
    report = validate_latex_citations(
        r"A \cite{alpha,missing}.",
        "@article{alpha, title={A}}\n@article{unused, title={U}}\n",
    )
    assert report.ok is False
    assert report.missing_keys == ["missing"]
    assert report.unused_bibtex_keys == ["unused"]


def test_validate_latex_citations_reports_duplicate_bib_keys() -> None:
    report = validate_latex_citations(
        r"A \cite{alpha}.",
        "@article{alpha, title={A}}\n@book{alpha, title={A2}}\n",
    )
    assert report.ok is False
    assert report.duplicate_bibtex_keys == ["alpha"]


def test_better_bibtex_citation_keys(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[object]]] = []

    def fake_rpc(method: str, params: list[object] | None = None, timeout: float = 10.0) -> object:
        calls.append((method, params or []))
        if method == "item.citationkey":
            return {"ABC123": "lovelace1843notes", "DEF456": "hopper1952compiler"}
        raise AssertionError(method)

    monkeypatch.setattr("zotero_curator.bibtex.bbt_json_rpc", fake_rpc)
    cfg = CuratorConfig(data_dir=tmp_path)

    citation_keys, item_keys = bbt_citation_keys(["abc123", "DEF456"], cfg)

    assert citation_keys == ["lovelace1843notes", "hopper1952compiler"]
    assert item_keys == ["ABC123", "DEF456"]
    assert calls == [("item.citationkey", [["ABC123", "DEF456"]])]


def test_better_bibtex_citation_keys_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "zotero_curator.bibtex.bbt_json_rpc",
        lambda method, params=None, timeout=10.0: {"ABC123": None},
    )
    cfg = CuratorConfig(data_dir=tmp_path)

    with pytest.raises(BetterBibtexUnavailableError, match="no citation key"):
        bbt_citation_keys(["ABC123"], cfg)


def test_better_bibtex_export_items(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[object]]] = []

    def fake_rpc(method: str, params: list[object] | None = None, timeout: float = 10.0) -> object:
        calls.append((method, params or []))
        if method == "api.ready":
            return {"zotero": "9.0.4", "betterbibtex": "9.0.36"}
        if method == "item.citationkey":
            return {"ABC123": "lovelace1843notes"}
        if method == "item.export":
            assert params == [["lovelace1843notes"], "Better BibTeX"]
            return "@article{lovelace1843notes,\n  title = {Notes},\n}\n"
        raise AssertionError(method)

    monkeypatch.setattr("zotero_curator.bibtex.bbt_json_rpc", fake_rpc)
    cfg = CuratorConfig(data_dir=tmp_path)

    text, citation_keys, item_keys, exporter, metadata = bbt_export_items(
        ["ABC123"], cfg, "better-bibtex"
    )

    assert "@article{lovelace1843notes" in text
    assert citation_keys == ["lovelace1843notes"]
    assert item_keys == ["ABC123"]
    assert exporter == "Better BibTeX"
    assert metadata["used_better_bibtex"] is True
    assert metadata["better_bibtex"] == {"zotero": "9.0.4", "betterbibtex": "9.0.36"}
    assert "Better BibTeX citation-key resolution" in metadata["features_applied"]
    assert [call[0] for call in calls] == ["api.ready", "item.citationkey", "item.export"]


def test_better_biblatex_export_items(monkeypatch, tmp_path: Path) -> None:
    def fake_rpc(method: str, params: list[object] | None = None, timeout: float = 10.0) -> object:
        if method == "api.ready":
            return {"zotero": "9.0.4", "betterbibtex": "9.0.36"}
        if method == "item.citationkey":
            return {"ABC123": "lovelace1843notes"}
        if method == "item.export":
            assert params == [["lovelace1843notes"], "Better BibLaTeX"]
            return "@article{lovelace1843notes,\n  date = {1843},\n}\n"
        raise AssertionError(method)

    monkeypatch.setattr("zotero_curator.bibtex.bbt_json_rpc", fake_rpc)
    cfg = CuratorConfig(data_dir=tmp_path)

    text, citation_keys, item_keys, exporter, metadata = bbt_export_items(
        ["ABC123"], cfg, "better-biblatex"
    )

    assert "date = {1843}" in text
    assert citation_keys == ["lovelace1843notes"]
    assert item_keys == ["ABC123"]
    assert exporter == "Better BibLaTeX"
    assert metadata["used_better_bibtex"] is True
    assert "Better BibLaTeX translator field mapping" in metadata["features_applied"]


def test_export_result_explicitly_reports_whether_bbt_was_used(tmp_path: Path) -> None:
    fake = FakeZotero()
    zotero_result = export_bibtex_file(
        zot=fake,
        item_keys=["ABC123"],
        bib_path=tmp_path / "zotero.bib",
        export_mode="zotero",
    )
    assert "Used Better BibTeX: no" in format_bibtex_export_result(zotero_result)

    bbt_result = export_bibtex_file(
        zot=fake,
        item_keys=["ABC123"],
        bib_path=tmp_path / "bbt.bib",
        overwrite=True,
        export_mode="zotero",
    )
    object.__setattr__(bbt_result, "exporter", "Better BibTeX")
    assert "Used Better BibTeX: yes" in format_bibtex_export_result(bbt_result)


def test_auto_mode_prefers_better_bibtex(monkeypatch, tmp_path: Path) -> None:
    def fake_rpc(method: str, params: list[object] | None = None, timeout: float = 10.0) -> object:
        if method == "api.ready":
            return {"zotero": "9.0.4", "betterbibtex": "9.0.36"}
        if method == "item.citationkey":
            return {"ABC123": "lovelace1843notes"}
        if method == "item.export":
            return "@article{lovelace1843notes,\n  title = {Notes},\n}\n"
        raise AssertionError(method)

    monkeypatch.setattr("zotero_curator.bibtex.bbt_json_rpc", fake_rpc)
    cfg = CuratorConfig(data_dir=tmp_path)
    fake = FakeZotero()

    text, citation_keys, item_keys, exporter, metadata = bibtex_for_items(
        fake, ["ABC123"], cfg=cfg, export_mode="auto"
    )

    assert "lovelace1843notes" in text
    assert citation_keys == ["lovelace1843notes"]
    assert item_keys == ["ABC123"]
    assert exporter == "Better BibTeX"
    assert metadata["used_better_bibtex"] is True
    assert fake.calls == []


def test_auto_mode_falls_back_to_zotero(monkeypatch, tmp_path: Path) -> None:
    def fake_rpc(method: str, params: list[object] | None = None, timeout: float = 10.0) -> object:
        raise BetterBibtexUnavailableError("BBT unavailable")

    monkeypatch.setattr("zotero_curator.bibtex.bbt_json_rpc", fake_rpc)
    cfg = CuratorConfig(data_dir=tmp_path)
    fake = FakeZotero()

    text, citation_keys, item_keys, exporter, metadata = bibtex_for_items(
        fake, ["ABC123"], cfg=cfg, export_mode="auto"
    )

    assert "lovelace1843notes" in text
    assert citation_keys == ["lovelace1843notes"]
    assert item_keys == ["ABC123"]
    assert exporter == "zotero"
    assert metadata["used_better_bibtex"] is False
    assert metadata["better_bibtex_fallback_reason"] == "BBT unavailable"
    assert fake.calls == [("ABC123", {"format": "bibtex"})]
