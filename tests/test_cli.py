"""Tests for zotero_curator.cli — argument parsing, config output, and entry points."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zotero_curator.cli import (
    _client_config_paths,
    _json_mcp_config,
    _server_config,
    _toml_mcp_config,
    build_parser,
    main,
)

# ---------------------------------------------------------------------------
# _server_config
# ---------------------------------------------------------------------------


class TestServerConfig:
    def test_default(self) -> None:
        cfg = _server_config("zotero-curator")
        assert cfg["command"] == "zotero-curator"
        assert cfg["args"] == ["serve"]

    def test_uvx(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "uvx" else None)
        cfg = _server_config("zotero-curator", uvx=True)
        assert cfg["command"] == "/usr/bin/uvx"
        assert cfg["args"] == ["--from", "zotero-curator", "zotero-curator", "serve"]


# ---------------------------------------------------------------------------
# _json_mcp_config / _toml_mcp_config
# ---------------------------------------------------------------------------


class TestMcpConfigOutput:
    def test_json_structure(self) -> None:
        result = _json_mcp_config("zotero-curator")
        parsed = json.loads(result)
        assert "mcpServers" in parsed
        assert "zotero" in parsed["mcpServers"]
        assert parsed["mcpServers"]["zotero"]["command"] == "zotero-curator"

    def test_json_uvx(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "uvx" else None)
        result = _json_mcp_config("zotero-curator", uvx=True)
        parsed = json.loads(result)
        assert parsed["mcpServers"]["zotero"]["command"] == "/usr/bin/uvx"

    def test_toml_contains_command(self) -> None:
        result = _toml_mcp_config("zotero-curator")
        assert "command = " in result
        assert "[mcp_servers.zotero]" in result

    def test_toml_uvx(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "uvx" else None)
        result = _toml_mcp_config("zotero-curator", uvx=True)
        assert "/usr/bin/uvx" in result


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_serve_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["serve"])
        assert args.transport == "stdio"

    def test_serve_sse(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["serve", "--transport", "sse"])
        assert args.transport == "sse"

    def test_setup_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.local is False  # not set explicitly
        assert args.web is False
        assert args.library_type == "user"
        assert args.write_enabled is False
        assert args.response_format == "markdown"

    def test_setup_web_mode(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup", "--web", "--library-id", "123", "--api-key", "k"])
        assert args.web is True
        assert args.library_id == "123"
        assert args.api_key == "k"

    def test_add_arxiv_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["add-arxiv", "2410.03529"])
        assert args.source == "2410.03529"
        assert args.pdf_mode == "stored"
        assert args.allow_duplicate is False
        assert args.apply is False

    def test_add_arxiv_no_pdf(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["add-arxiv", "2410.03529", "--no-pdf"])
        assert args.pdf_mode == "none"

    def test_add_arxiv_link_pdf(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["add-arxiv", "2410.03529", "--link-pdf"])
        assert args.pdf_mode == "linked"

    def test_mcp_config_format(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["mcp-config", "--format", "toml"])
        assert args.format == "toml"

    def test_doctor_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["doctor"])
        assert hasattr(args, "func")


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_args_defaults_to_serve(self) -> None:
        """main() with no args should try to start the serve subcommand."""
        # We can't actually run the server, so we mock cmd_serve
        with patch("zotero_curator.cli.cmd_serve", return_value=0) as mock_serve:
            result = main([])
            assert result == 0
            mock_serve.assert_called_once()
            args = mock_serve.call_args[0][0]
            assert args.transport == "stdio"

    def test_backward_compat_transport_flag(self) -> None:
        """`--transport stdio` without subcommand should insert 'serve'."""
        with patch("zotero_curator.cli.cmd_serve", return_value=0) as mock_serve:
            result = main(["--transport", "stdio"])
            assert result == 0
            args = mock_serve.call_args[0][0]
            assert args.transport == "stdio"

    def test_help_does_not_crash(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_unknown_command_shows_help(self) -> None:
        # When no func is set (e.g. no subcommand), main returns 2
        # But "serve" is always valid. Let's test an invalid subcommand.
        with pytest.raises(SystemExit):
            main(["unknown-subcommand"])

    def test_open_config(self, monkeypatch, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        monkeypatch.setenv("ZOTERO_CURATOR_CONFIG", str(path))
        with patch("builtins.print") as mock_print:
            result = main(["open-config"])
        assert result == 0
        mock_print.assert_called()
        printed_path = mock_print.call_args[0][0]
        assert str(path) in str(printed_path)


class TestClientConfigPaths:
    def test_linux_claude_desktop_uses_capitalized_config_dir(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("zotero_curator.cli.platform.system", lambda: "Linux")
        monkeypatch.setattr("zotero_curator.cli.Path.home", lambda: tmp_path)

        paths = _client_config_paths("claude-desktop")

        assert paths["claude-desktop"] == tmp_path / ".config" / "Claude" / "claude_desktop_config.json"


class TestInstallClient:
    def test_dry_run_default(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = tmp_path / "claude"
        config_dir.mkdir()
        config_file = config_dir / "claude_desktop_config.json"
        config_file.write_text('{"mcpServers": {}}')
        monkeypatch.setattr(
            "zotero_curator.cli._client_config_paths",
            lambda client: {"claude-desktop": config_file} if client in ("claude-desktop", "all") else {},
        )
        with patch("builtins.print") as mock_print:
            result = main(["install-client", "--client", "claude-desktop"])
        assert result == 0
        assert json.loads(config_file.read_text()) == {"mcpServers": {}}
        printed = "\n".join(str(c) for c in mock_print.call_args_list)
        assert "dry run" in printed.lower()

    def test_apply_writes_config(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = tmp_path / "cursor"
        config_dir.mkdir()
        config_file = config_dir / "mcp.json"
        existing = {"mcpServers": {"other": {"command": "x"}}}
        config_file.write_text(json.dumps(existing))
        monkeypatch.setattr(
            "zotero_curator.cli._client_config_paths",
            lambda client: {"cursor": config_file} if client in ("cursor", "all") else {},
        )
        result = main(["install-client", "--client", "cursor", "--apply"])
        assert result == 0
        written = json.loads(config_file.read_text())
        assert "zotero" in written["mcpServers"]
        assert written["mcpServers"]["other"]["command"] == "x"
        assert written["mcpServers"]["zotero"]["command"] == "zotero-curator"
        assert (config_file.with_suffix(".json.bak")).exists()

    def test_idempotent(self, monkeypatch, tmp_path: Path) -> None:
        from zotero_curator.cli import _server_config

        config_dir = tmp_path / "claude"
        config_dir.mkdir()
        config_file = config_dir / "claude_desktop_config.json"
        server_entry = _server_config("zotero-curator")
        config_file.write_text(json.dumps({"mcpServers": {"zotero": server_entry}}))
        monkeypatch.setattr(
            "zotero_curator.cli._client_config_paths",
            lambda client: {"claude-desktop": config_file},
        )
        with patch("builtins.print") as mock_print:
            result = main(["install-client", "--client", "claude-desktop"])
        assert result == 0
        printed = "\n".join(str(c) for c in mock_print.call_args_list)
        assert "already has this server entry" in printed

    def test_uvx_absolute_command(self, monkeypatch, tmp_path: Path) -> None:
        """--uvx with --command uses the provided absolute path."""
        config_dir = tmp_path / "claude"
        config_dir.mkdir()
        config_file = config_dir / "claude_desktop_config.json"
        config_file.write_text('{"mcpServers": {}}')
        monkeypatch.setattr(
            "zotero_curator.cli._client_config_paths",
            lambda client: {"claude-desktop": config_file} if client in ("claude-desktop", "all") else {},
        )
        result = main(["install-client", "--client", "claude-desktop", "--uvx", "--command", "/opt/homebrew/bin/uvx", "--apply"])
        assert result == 0
        written = json.loads(config_file.read_text())
        assert written["mcpServers"]["zotero"]["command"] == "/opt/homebrew/bin/uvx"
        assert written["mcpServers"]["zotero"]["args"] == ["--from", "zotero-curator", "zotero-curator", "serve"]

    def test_skip_returns_nonzero(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = tmp_path / "claude"
        config_dir.mkdir()
        config_file = config_dir / "claude_desktop_config.json"
        config_file.write_text("NOT VALID JSON{{{")
        monkeypatch.setattr(
            "zotero_curator.cli._client_config_paths",
            lambda client: {"claude-desktop": config_file} if client in ("claude-desktop", "all") else {},
        )
        result = main(["install-client", "--client", "claude-desktop", "--apply"])
        assert result == 1

    def test_uvx_not_found_fails(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = tmp_path / "claude"
        config_dir.mkdir()
        config_file = config_dir / "claude_desktop_config.json"
        config_file.write_text('{"mcpServers": {}}')
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setattr(
            "zotero_curator.cli._client_config_paths",
            lambda client: {"claude-desktop": config_file},
        )
        result = main(["install-client", "--client", "claude-desktop", "--uvx", "--apply"])
        assert result == 1
