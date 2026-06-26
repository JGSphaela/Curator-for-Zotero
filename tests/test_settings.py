"""Comprehensive tests for zotero_curator.settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from zotero_curator.settings import (
    CuratorConfig,
    _toml_string,
    config_dir,
    config_file,
    config_status_lines,
    default_data_dir,
    default_log_dir,
    env_flag,
    load_config,
    read_config_file,
    write_config,
)

# ---------------------------------------------------------------------------
# env_flag
# ---------------------------------------------------------------------------


class TestEnvFlag:
    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "on", "ON"])
    def test_truthy(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("TEST_FLAG", value)
        assert env_flag("TEST_FLAG") is True

    @pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", "OFF"])
    def test_falsy(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("TEST_FLAG", value)
        assert env_flag("TEST_FLAG", default=True) is False

    def test_unset_returns_default(self, monkeypatch) -> None:
        monkeypatch.delenv("TEST_FLAG", raising=False)
        assert env_flag("TEST_FLAG") is False
        assert env_flag("TEST_FLAG", default=True) is True

    def test_unknown_returns_default(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_FLAG", "maybe")
        assert env_flag("TEST_FLAG") is False
        assert env_flag("TEST_FLAG", default=True) is True

    def test_whitespace_handled(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_FLAG", "  true  ")
        assert env_flag("TEST_FLAG") is True


# ---------------------------------------------------------------------------
# config_file / config_dir overrides
# ---------------------------------------------------------------------------


class TestConfigPaths:
    def test_config_file_override(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", "/tmp/custom-config.toml")
        assert config_file() == Path("/tmp/custom-config.toml")

    def test_config_dir_override(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG_DIR", "/tmp/custom-dir")
        result = config_dir()
        assert result == Path("/tmp/custom-dir")
        # config_file should be within config_dir
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", "")
        monkeypatch.delenv("ZOTERO_CURATOR_CONFIG", raising=False)
        assert config_file().parent == result

    def test_default_log_dir_override(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_LOG_DIR", "/tmp/custom-logs")
        assert default_log_dir() == Path("/tmp/custom-logs")

    def test_default_data_dir_override(self, monkeypatch) -> None:
        monkeypatch.setenv("ZOTERO_CURATOR_DATA_DIR", "/tmp/custom-data")
        assert default_data_dir() == Path("/tmp/custom-data")


# ---------------------------------------------------------------------------
# _toml_string
# ---------------------------------------------------------------------------


class TestTomlString:
    def test_simple(self) -> None:
        assert _toml_string("hello") == '"hello"'

    def test_backslash_escaped(self) -> None:
        assert _toml_string("a\\b") == '"a\\\\b"'

    def test_quote_escaped(self) -> None:
        assert _toml_string('a"b') == '"a\\"b"'


# ---------------------------------------------------------------------------
# read_config_file
# ---------------------------------------------------------------------------


class TestReadConfigFile:
    def test_missing_file(self, tmp_path: Path) -> None:
        assert read_config_file(tmp_path / "nope.toml") == {}

    def test_non_zotero_section(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text("[other]\nfoo = 'bar'\n", encoding="utf-8")
        assert read_config_file(path) == {}

    def test_zotero_section(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(
            '[zotero]\nlocal = true\nlibrary_id = "123"\n',
            encoding="utf-8",
        )
        result = read_config_file(path)
        assert result["local"] is True
        assert result["library_id"] == "123"

    def test_non_dict_zotero_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text('zotero = "not a dict"\n', encoding="utf-8")
        assert read_config_file(path) == {}


# ---------------------------------------------------------------------------
# write_config
# ---------------------------------------------------------------------------


class TestWriteConfig:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "dir" / "config.toml"
        write_config(path=path)
        assert path.exists()

    def test_local_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_config(path=path)
        content = path.read_text()
        assert "local = true" in content
        assert 'library_type = "user"' in content
        assert "write_enabled = false" in content

    def test_web_mode_with_key(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_config(
            local=False, library_id="456", api_key="secret", write_enabled=True, path=path,
        )
        content = path.read_text()
        assert "local = false" in content
        assert "456" in content
        assert "secret" in content
        assert "write_enabled = true" in content

    def test_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_config(
            local=False,
            library_id="789",
            library_type="group",
            api_key="key123",
            write_enabled=True,
            response_format="json",
            path=path,
        )
        values = read_config_file(path)
        assert values["local"] is False
        assert values["library_id"] == "789"
        assert values["library_type"] == "group"
        assert values["api_key"] == "key123"
        assert values["write_enabled"] is True
        assert values["response_format"] == "json"


# ---------------------------------------------------------------------------
# config_status_lines
# ---------------------------------------------------------------------------


class TestConfigStatusLines:
    def test_contains_expected_fields(self, monkeypatch, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        write_config(local=True, path=path)
        cfg = load_config()
        lines = config_status_lines(cfg)
        text = "\n".join(lines)
        assert "Config file:" in text
        assert "Mode:" in text
        assert "Library:" in text
        assert "API key:" in text
        assert "Write tools:" in text
        assert "Response format:" in text
        assert "Log dir:" in text
        assert "Data dir:" in text


# ---------------------------------------------------------------------------
# CuratorConfig dataclass
# ---------------------------------------------------------------------------


class TestCuratorConfig:
    def test_defaults(self) -> None:
        cfg = CuratorConfig()
        assert cfg.local is True
        assert cfg.library_id == "0"
        assert cfg.library_type == "user"
        assert cfg.api_key is None
        assert cfg.write_enabled is False
        assert cfg.mode_label == "local Zotero API"

    def test_web_mode_label(self) -> None:
        cfg = CuratorConfig(local=False)
        assert cfg.mode_label == "Zotero Web API"

    def test_frozen(self) -> None:
        cfg = CuratorConfig()
        with pytest.raises(AttributeError):
            cfg.local = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_config with env overrides
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_env_overrides_file(self, monkeypatch, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        write_config(local=True, library_id="100", path=path)

        monkeypatch.setenv("ZOTERO_LOCAL", "false")
        monkeypatch.setenv("ZOTERO_LIBRARY_ID", "200")
        cfg = load_config()
        assert cfg.local is False
        assert cfg.library_id == "200"

    def test_local_default_library_id(self, monkeypatch, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        # Clear Zotero env vars so the config file values are actually tested
        monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
        monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
        monkeypatch.delenv("ZOTERO_LIBRARY_TYPE", raising=False)
        monkeypatch.delenv("ZOTERO_LOCAL", raising=False)
        write_config(local=True, path=path)
        cfg = load_config()
        assert cfg.library_id == "0"

    def test_api_key_from_env(self, monkeypatch, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        write_config(local=False, library_id="1", path=path)

        monkeypatch.setenv("ZOTERO_API_KEY", "env_key")
        cfg = load_config()
        assert cfg.api_key == "env_key"

    def test_api_key_from_file(self, monkeypatch, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
        write_config(local=False, library_id="1", api_key="file_key", path=path)
        cfg = load_config()
        assert cfg.api_key == "file_key"
