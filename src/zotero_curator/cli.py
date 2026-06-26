"""Command line interface for Curator for Zotero."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from zotero_curator.runtime import configure_logging, log_event
from zotero_curator.settings import config_file, config_status_lines, load_config, write_config


def _server_config(command: str, uvx: bool = False) -> dict[str, Any]:
    if uvx:
        uvx_cmd = command if command != "zotero-curator" else shutil.which("uvx") or "uvx"
        return {
            "command": uvx_cmd,
            "args": ["--from", "zotero-curator", "zotero-curator", "serve"],
        }
    return {"command": command, "args": ["serve"]}


def _json_mcp_config(command: str, uvx: bool = False) -> str:
    return json.dumps({"mcpServers": {"zotero": _server_config(command, uvx)}}, indent=2)


def _toml_mcp_config(command: str, uvx: bool = False) -> str:
    server = _server_config(command, uvx)
    args = ", ".join(json.dumps(arg) for arg in server["args"])
    return "\n".join(
        [
            "[mcp_servers.zotero]",
            f"command = {json.dumps(server['command'])}",
            f"args = [{args}]",
            "",
        ]
    )


def cmd_serve(args: argparse.Namespace) -> int:
    from zotero_curator.server import mcp

    cfg = load_config()
    log_path = configure_logging(cfg)
    log_event("server_start", transport=args.transport, log_file=str(log_path))
    mcp.run(args.transport)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    local = args.local or not args.web
    path = write_config(
        local=local,
        library_id=args.library_id,
        library_type=args.library_type,
        api_key=args.api_key,
        write_enabled=args.write_enabled,
        response_format=args.response_format,
    )
    print(f"Wrote settings: {path}")
    print("\nClaude/Cursor style JSON config:\n")
    print(_json_mcp_config(args.command, uvx=args.uvx))
    print("\nCodex TOML config:\n")
    print(_toml_mcp_config(args.command, uvx=args.uvx))
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    cfg = load_config()
    log_path = configure_logging(cfg)
    log_event("doctor_start", log_file=str(log_path))
    print("# Curator for Zotero Doctor")
    print(f"Python: {sys.version.split()[0]} ({platform.platform()})")
    print(f"Executable: {sys.executable}")
    print(f"uv: {shutil.which('uv') or 'not found'}")
    print()
    print("\n".join(config_status_lines(load_config())))
    print()
    try:
        from zotero_curator.client import get_zotero_client

        zot = get_zotero_client()
        items: Any = zot.items(limit=1)
    except Exception as exc:
        log_event("doctor_error", error_type=type(exc).__name__, error=str(exc))
        print("Zotero API: ERROR")
        print(f"{type(exc).__name__}: {exc}")
        print("Hint: open Zotero and enable the local API, or configure Web API credentials.")
        return 1
    log_event("doctor_ok", sample_count=len(items))
    print("Zotero API: OK")
    if items:
        data = items[0].get("data", {})
        print(f"Sample item: {data.get('title', 'Untitled')} (`{items[0].get('key')}`)")
    return 0


def cmd_setup_info(_: argparse.Namespace) -> int:
    print("# Setup Info")
    print("\n".join(config_status_lines(load_config())))
    print("\nConfig path:")
    print(config_file())
    return 0


def cmd_mcp_config(args: argparse.Namespace) -> int:
    if args.format == "toml":
        print(_toml_mcp_config(args.command, uvx=args.uvx))
    else:
        print(_json_mcp_config(args.command, uvx=args.uvx))
    return 0


def cmd_open_config(_: argparse.Namespace) -> int:
    print(config_file())
    return 0


def cmd_add_arxiv(args: argparse.Namespace) -> int:
    from zotero_curator.server import add_arxiv_paper

    print(
        add_arxiv_paper(
            source=args.source,
            collections=args.collection,
            tags=args.tag,
            pdf_mode=args.pdf_mode,
            allow_duplicate=args.allow_duplicate,
            dry_run=not args.apply,
        )
    )
    return 0


def _client_config_paths(client: str) -> dict[str, Path]:
    """Return {client_name: config_path} for known MCP clients."""
    is_macos = platform.system() == "Darwin"
    home = Path.home()
    paths: dict[str, Path] = {}
    if client in ("claude-desktop", "all"):
        if is_macos:
            paths["claude-desktop"] = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        else:
            paths["claude-desktop"] = home / ".config" / "claude" / "claude_desktop_config.json"
    if client in ("cursor", "all"):
        paths["cursor"] = home / ".cursor" / "mcp.json"
    return paths


def cmd_install_client(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    targets = _client_config_paths(args.client)
    if not targets:
        print("No client config paths found for the requested client(s).")
        return 1

    server_entry = _server_config(args.command, uvx=args.uvx)
    actions: list[str] = []
    skipped = 0

    for name, path in targets.items():
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                actions.append(f"SKIP {name}: cannot read {path} ({exc})")
                skipped += 1
                continue
            if existing.get("mcpServers", {}).get("zotero") == server_entry:
                actions.append(f"OK {name}: {path} already has this server entry")
                continue

        merged = dict(existing)
        mcp = dict(merged.get("mcpServers", {}))
        mcp["zotero"] = server_entry
        merged["mcpServers"] = mcp

        if dry_run:
            actions.append(f"DRY RUN {name}: would write {path}")
            actions.append(f"  Server entry: {json.dumps(server_entry)}")
        else:
            if path.exists():
                backup = path.with_suffix(".json.bak")
                shutil.copy2(path, backup)
                actions.append(f"BACKUP {name}: {backup}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
                f.write("\n")
            actions.append(f"APPLIED {name}: wrote {path}")

    print("# install-client")
    print(f"Mode: {'dry run' if dry_run else 'apply'}")
    print()
    for action in actions:
        print(action)
    return 1 if skipped else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zotero-curator",
        description="Research-focused MCP server and setup helper for Zotero.",
    )
    subparsers = parser.add_subparsers(dest="command_name")

    serve = subparsers.add_parser("serve", help="Run the MCP server.")
    serve.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    serve.set_defaults(func=cmd_serve)

    setup = subparsers.add_parser("setup", help="Write central settings and print MCP configs.")
    mode = setup.add_mutually_exclusive_group()
    mode.add_argument("--local", action="store_true", help="Use Zotero local API. Default.")
    mode.add_argument("--web", action="store_true", help="Use Zotero Web API.")
    setup.add_argument("--library-id", help="Zotero library id. Local mode defaults to 0.")
    setup.add_argument("--library-type", default="user", choices=["user", "group"])
    setup.add_argument("--api-key", help="Zotero Web API key.")
    setup.add_argument("--write-enabled", action="store_true", help="Enable write tools globally.")
    setup.add_argument("--response-format", default="markdown", choices=["markdown", "json"])
    setup.add_argument("--command", default="zotero-curator", help="Command clients should run.")
    setup.add_argument("--uvx", action="store_true", help="Print zero-install uvx configs.")
    setup.set_defaults(func=cmd_setup)

    doctor = subparsers.add_parser("doctor", help="Validate install and Zotero connectivity.")
    doctor.set_defaults(func=cmd_doctor)

    setup_info = subparsers.add_parser("setup-info", help="Print resolved settings paths/status.")
    setup_info.set_defaults(func=cmd_setup_info)

    mcp_config = subparsers.add_parser("mcp-config", help="Print MCP client config only.")
    mcp_config.add_argument("--format", choices=["json", "toml"], default="json")
    mcp_config.add_argument("--command", default="zotero-curator")
    mcp_config.add_argument("--uvx", action="store_true")
    mcp_config.set_defaults(func=cmd_mcp_config)

    open_config = subparsers.add_parser("open-config", help="Print settings file path.")
    open_config.set_defaults(func=cmd_open_config)

    add_arxiv = subparsers.add_parser("add-arxiv", help="Add an arXiv preprint to Zotero.")
    add_arxiv.add_argument("source", help="arXiv id, abstract URL, or PDF URL.")
    add_arxiv.add_argument("--collection", action="append", help="Collection key to add the item to. Repeatable.")
    add_arxiv.add_argument("--tag", action="append", help="Tag to assign to the item. Repeatable.")
    add_arxiv.add_argument(
        "--pdf-mode",
        choices=["stored", "linked", "none"],
        default="stored",
        help="How to attach the arXiv PDF. Default: stored.",
    )
    add_arxiv.add_argument("--no-pdf", action="store_const", const="none", dest="pdf_mode", help="Shortcut for --pdf-mode none.")
    add_arxiv.add_argument("--link-pdf", action="store_const", const="linked", dest="pdf_mode", help="Shortcut for --pdf-mode linked.")
    add_arxiv.add_argument("--allow-duplicate", action="store_true", help="Create even if a possible arXiv match already exists.")
    add_arxiv.add_argument("--apply", action="store_true", help="Apply the write. Default is a dry run.")
    add_arxiv.set_defaults(func=cmd_add_arxiv)

    install_client = subparsers.add_parser(
        "install-client",
        help="Detect known MCP client configs and merge the zotero server entry.",
    )
    install_client.add_argument(
        "--client",
        choices=["claude-desktop", "cursor", "all"],
        default="all",
        help="Which client config to target. Default: all.",
    )
    install_client.add_argument("--command", default="zotero-curator", help="Command clients should run.")
    install_client.add_argument("--uvx", action="store_true", help="Use uvx launch config.")
    install_client.add_argument("--apply", action="store_true", help="Apply changes. Default is dry run.")
    install_client.set_defaults(func=cmd_install_client)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        raw_args = ["serve"]
    # Backward-compatible MCP configs may run `zotero-curator --transport stdio`.
    if raw_args[0].startswith("--"):
        raw_args.insert(0, "serve")
    args = parser.parse_args(raw_args)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
