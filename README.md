# Curator for Zotero

Curator for Zotero is a research-focused MCP server for Zotero. It lets AI coding and research assistants search a library, inspect metadata, read long attachments in manageable sections, export citations, and safely organize items with dry-run-first write tools.

This project is independently maintained and is based on the MIT-licensed [`kujenga/zotero-mcp`](https://github.com/kujenga/zotero-mcp). See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) and [LICENSE](LICENSE).

## Why Curator

The original Python MCP server required each client to know a repository-local virtual-environment path. Curator is a published Python package, so Codex, Claude Desktop, Cursor, Claude Code, and other clients can launch it with one stable command:

```bash
uvx --from zotero-curator zotero-curator serve
```

Curator adds long-document navigation, saved searches, optional PDF and semantic-search features, safe BibTeX workflows, arXiv import, central settings, diagnostics, and guarded organization tools.

## Quick start

Install [`uv`](https://docs.astral.sh/uv/), open Zotero, and enable:

> Zotero Settings → Advanced → Allow other applications on this computer to communicate with Zotero

Then configure and validate local mode:

```bash
uvx --from zotero-curator zotero-curator setup --local
uvx --from zotero-curator zotero-curator doctor
```

For GUI-launched macOS clients, use the absolute `uvx` path returned by:

```bash
command -v uvx
```

Common Homebrew paths are `/opt/homebrew/bin/uvx` on Apple Silicon and `/usr/local/bin/uvx` on Intel Macs.

## MCP client configuration

Claude Desktop, Cursor, and other JSON-style clients:

```json
{
  "mcpServers": {
    "zotero": {
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "zotero-curator", "zotero-curator", "serve"]
    }
  }
}
```

Codex:

```toml
[mcp_servers.zotero]
type = "stdio"
command = "/opt/homebrew/bin/uvx"
args = ["--from", "zotero-curator", "zotero-curator", "serve"]
startup_timeout_sec = 30
```

Replace `/opt/homebrew/bin/uvx` with your `command -v uvx` result.

Generate or install client configuration safely:

```bash
uvx --from zotero-curator zotero-curator mcp-config --uvx --format json
uvx --from zotero-curator zotero-curator mcp-config --uvx --format toml
uvx --from zotero-curator zotero-curator install-client --uvx
uvx --from zotero-curator zotero-curator install-client --uvx --apply
```

The installer backs up existing client configuration and defaults to dry-run mode.

## Documentation

Detailed, version-controlled documentation lives in [`docs/`](docs/README.md):

- [Client configuration](docs/client-config.md)
- [Settings and safety](docs/settings-and-safety.md)
- [Research workflows](docs/workflows.md)
- [Optional PDF and semantic extras](docs/optional-extras.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Claude Desktop MCPB](docs/mcpb.md)
- [Release process](docs/release.md)
- [Roadmap](docs/roadmap.md)

## Major capabilities

### Research and navigation

- Search by title, creator, year, tag, DOI, or indexed text.
- Inspect metadata, child notes, attachments, collections, tags, and saved searches.
- Read long documents by chunk, within-document search, heuristic outline, or section.
- Use optional page-aware PDF reads and local semantic search.

### Citation workflow

Curator exports selected Zotero items directly to managed BibTeX or BibLaTeX files and can validate LaTeX citations:

```bash
zotero-curator export-bibtex ITEMKEY1 ITEMKEY2 --out references.bib --mode auto
zotero-curator validate-citations --tex paper.tex --bib references.bib
```

`auto` prefers Better BibTeX when available for supported personal-library exports, then falls back to Zotero's exporter. Curator records the actual exporter, citation keys, generated cite command, and fallback reason.

### arXiv import

Preview an import:

```bash
uvx --from zotero-curator zotero-curator add-arxiv https://arxiv.org/abs/2410.03529
```

Real imports require Web API mode, a write-enabled API key, global write enablement, and `--apply`. See [Research workflows](docs/workflows.md).

### Guarded organization tools

Curator can create and rename collections, update tags and collection membership, patch selected metadata, create child notes, and apply multi-step organization plans.

All write tools default to `dry_run=true`. Real writes require:

1. Web API mode.
2. A Zotero API key with write permission.
3. `write_enabled = true` or `ZOTERO_WRITE_ENABLED=true`.
4. `dry_run=false` on the individual call.

Zotero's local API is treated as read-only because Local API v3 currently accepts only `GET` requests.

## Optional extras

Keep the base install small or request additional features:

```bash
uvx --from 'zotero-curator[pdf]' zotero-curator serve
uvx --from 'zotero-curator[semantic]' zotero-curator serve
uvx --from 'zotero-curator[all]' zotero-curator serve
```

The `pdf` extra enables page-aware stored-PDF reads and bookmark extraction. The `semantic` extra provides a local Chroma index with cross-process locking.

## Let an agent set it up

Copy this prompt into a local coding agent:

```text
Install Curator for Zotero for me by following this repo's AGENTS.md. Use the published uvx workflow and configure these MCP clients: CLIENTS_TO_CONFIGURE.
```

Replace `CLIENTS_TO_CONFIGURE` with the applications you use.

## Development

```bash
git clone https://github.com/JGSphaela/Curator-for-Zotero.git
cd Curator-for-Zotero
uv sync --extra dev
uv run zotero-curator doctor
uv run pytest
uv run ruff check .
```

The package exposes `zotero-curator` and the compatibility alias `zotero-mcp`.