"""Tests for zotero_curator.runtime module."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from zotero_curator.runtime import configure_logging, log_event, runtime_diagnostics
from zotero_curator.settings import CuratorConfig


@pytest.fixture(autouse=True)
def _clean_logger():
    """Prevent FileHandler accumulation across tests."""
    yield
    logging.getLogger("zotero_curator").handlers.clear()

# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def test_creates_log_file(self, tmp_path: Path) -> None:
        cfg = CuratorConfig(log_dir=tmp_path)
        log_path = configure_logging(cfg)
        assert log_path == tmp_path / "curator.jsonl"
        assert log_path.parent.exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        cfg = CuratorConfig(log_dir=tmp_path)
        p1 = configure_logging(cfg)
        p2 = configure_logging(cfg)
        assert p1 == p2


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


class TestLogEvent:
    def test_writes_jsonl(self, tmp_path: Path) -> None:
        cfg = CuratorConfig(log_dir=tmp_path)
        configure_logging(cfg)
        log_event("test_event", key="value")
        log_path = tmp_path / "curator.jsonl"
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        last = json.loads(lines[-1])
        assert last["event"] == "test_event"
        assert last["key"] == "value"
        assert "ts" in last


# ---------------------------------------------------------------------------
# runtime_diagnostics
# ---------------------------------------------------------------------------


class TestRuntimeDiagnostics:
    def test_fields_present(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        data_dir = tmp_path / "data"
        log_dir.mkdir()
        data_dir.mkdir()
        cfg = CuratorConfig(
            local=True, library_id="0", library_type="user", write_enabled=False,
            response_format="markdown", log_dir=log_dir, data_dir=data_dir,
        )
        info = runtime_diagnostics(cfg)
        assert info["mode"] == "local Zotero API"
        assert info["library_type"] == "user"
        assert info["library_id"] == "0"
        assert info["api_key_set"] is False
        assert info["write_enabled"] is False
        assert info["response_format"] == "markdown"
        assert str(log_dir) in info["log_dir"]
        assert str(data_dir) in info["data_dir"]

    def test_api_key_set_true(self) -> None:
        cfg = CuratorConfig(api_key="secret")
        info = runtime_diagnostics(cfg)
        assert info["api_key_set"] is True
