"""Tests for zotero_curator.cli — argument parsing, config output, and entry points."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from zotero_curator.cli import (
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

    def test_uvx(self) -> None:
        cfg = _server_config("zotero-curator", uvx=True)
        assert cfg["command"] == "uvx"
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

    def test_json_uvx(self) -> None:
        result = _json_mcp_config("cmd", uvx=True)
        parsed = json.loads(result)
        assert parsed["mcpServers"]["zotero"]["command"] == "uvx"

    def test_toml_contains_command(self) -> None:
        result = _toml_mcp_config("zotero-curator")
        assert "command = " in result
        assert "[mcp_servers.zotero]" in result

    def test_toml_uvx(self) -> None:
        result = _toml_mcp_config("cmd", uvx=True)
        assert "uvx" in result


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
    def test_no_args_defaults_to_serve(self, monkeypatch) -> None:
        """main() with no args should try to start the serve subcommand."""
        # We can't actually run the server, so we mock cmd_serve
        with patch("zotero_curator.cli.cmd_serve", return_value=0) as mock_serve:
            result = main([])
            assert result == 0
            mock_serve.assert_called_once()
            args = mock_serve.call_args[0][0]
            assert args.transport == "stdio"

    def test_backward_compat_transport_flag(self, monkeypatch) -> None:
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
