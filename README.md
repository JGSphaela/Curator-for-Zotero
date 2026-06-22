# Curator for Zotero

Curator for Zotero is a research-focused MCP server for Zotero. It lets AI coding and research assistants search your library, inspect metadata, read indexed attachment text in manageable chunks, navigate outlines/sections, and safely organize items with dry-run-first write tools.

This project is independently maintained and is based on the MIT-licensed [`kujenga/zotero-mcp`](https://github.com/kujenga/zotero-mcp). See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) and [LICENSE](LICENSE).

## Why this repo exists

The original Python MCP server was useful but awkward to configure across Codex, Claude Desktop, Cursor, Claude Code, and other clients because each app needed a hand-maintained virtualenv path. Curator fixes that by making the server a normal installable tool with one stable command:

```bash
zotero-curator serve
```

That command can be installed once with `uv tool install` or run without a persistent venv through `uvx`.

## Install

```bash
uv tool install zotero-curator
zotero-curator setup --local
zotero-curator doctor
```

Zero-install client command:

```bash
uvx --from zotero-curator zotero-curator serve
```

From a local checkout:

```bash
uv sync --extra dev
uv run zotero-curator doctor
uv run pytest
uv run ruff check .
```

## Zotero local API setup

1. Open Zotero.
2. Go to Settings → Advanced → Allow other applications on this computer to communicate with Zotero.
3. Run:

```bash
zotero-curator setup --local
zotero-curator doctor
```

Local mode uses library id `0` and does not require an API key.

## Web API setup

```bash
zotero-curator setup --web --library-id YOUR_LIBRARY_ID --api-key YOUR_API_KEY
```

For group libraries, add `--library-type group`.

## MCP client config

Claude/Cursor-style JSON:

```json
{
  "mcpServers": {
    "zotero": {
      "command": "zotero-curator",
      "args": ["serve"]
    }
  }
}
```

Codex TOML:

```toml
[mcp_servers.zotero]
command = "zotero-curator"
args = ["serve"]
```

Zero-install `uvx` TOML:

```toml
[mcp_servers.zotero]
command = "uvx"
args = ["--from", "zotero-curator", "zotero-curator", "serve"]
```

Generate config snippets:

```bash
zotero-curator mcp-config --format json
zotero-curator mcp-config --format toml
zotero-curator mcp-config --uvx --format toml
```

Release instructions are in [docs/release.md](docs/release.md). Claude Desktop MCPB bundle notes are in [docs/mcpb.md](docs/mcpb.md).

## Add arXiv papers

Curator can create a Zotero `preprint` item directly from an arXiv id, abstract URL, or PDF URL:

```bash
zotero-curator add-arxiv https://arxiv.org/abs/2410.03529
```

The command is dry-run-first. To apply it, enable writes globally and pass `--apply`:

```bash
zotero-curator setup --local --write-enabled
zotero-curator add-arxiv 2410.03529 --tag AI --collection COLLECTION_KEY --apply
```

This imports arXiv metadata first and stores the PDF as a Zotero file attachment by default. Use `--link-pdf` to attach only the arXiv PDF URL, `--no-pdf` to create only the metadata item, or `--pdf-mode {stored,linked,none}` for explicit control.

## Settings

Curator stores central settings in:

```text
~/.config/zotero-curator/config.toml
```

Example:

```toml
[zotero]
local = true
library_type = "user"
library_id = "0"
write_enabled = false
response_format = "markdown"
```

Environment variables override file settings:

| Variable | Purpose |
| --- | --- |
| `ZOTERO_LOCAL` | `true` for local API, `false` for Web API |
| `ZOTERO_LIBRARY_ID` | Zotero user/group library id |
| `ZOTERO_LIBRARY_TYPE` | `user` or `group` |
| `ZOTERO_API_KEY` | Zotero Web API key |
| `ZOTERO_WRITE_ENABLED` | Enable non-dry-run write tools |
| `ZOTERO_CURATOR_CONFIG` | Override settings file path |
| `ZOTERO_CURATOR_CONFIG_DIR` | Override settings directory |

## Tools

Read/navigation:

- `zotero_healthcheck`
- `zotero_diagnostics`
- `zotero_search_items`
- `zotero_find_item_by_doi`
- `zotero_item_metadata`
- `zotero_item_fulltext`
- `zotero_item_fulltext_info`
- `zotero_pdf_pages` (`pdf` extra)
- `zotero_pdf_outline` (`pdf` extra)
- `zotero_item_text_chunk`
- `zotero_item_search_text`
- `zotero_item_outline`
- `zotero_item_read_section`
- `zotero_item_children`
- `zotero_list_collections`
- `zotero_collection_items`
- `zotero_list_tags`
- `zotero_semantic_rebuild` (`semantic` extra)
- `zotero_semantic_search` (`semantic` extra)

Write/organization tools are dry-run-first and additionally require `write_enabled = true` for real changes:

- `zotero_write_status`
- `zotero_add_arxiv`
- `zotero_create_collection`
- `zotero_rename_collection`
- `zotero_delete_collection`
- `zotero_update_item_tags`
- `zotero_update_item_collections`
- `zotero_update_item_metadata`
- `zotero_create_child_note`
- `zotero_apply_organization_plan`

## Safety model

Write tools default to `dry_run=true`. Real write calls require both:

1. `write_enabled = true` in settings, or `ZOTERO_WRITE_ENABLED=true`.
2. The individual tool call sets `dry_run=false`.

This makes accidental library mutations much harder.

## Optional extras

The base install stays small. Heavy PDF and semantic dependencies are opt-in:

```bash
uv tool install 'zotero-curator[pdf]'
uv tool install 'zotero-curator[semantic]'
uv tool install 'zotero-curator[all]'
```

From a checkout:

```bash
uv pip install --python .venv/bin/python -e '.[pdf]'
uv pip install --python .venv/bin/python -e '.[semantic]'
```

The `pdf` extra enables page-aware PDF reads and bookmark extraction from stored Zotero attachments. The `semantic` extra stores a local Chroma index under the platform data directory shown by `zotero-curator doctor`; rebuild with `zotero_semantic_rebuild` after major library changes, then search with `zotero_semantic_search`. See [docs/optional-extras.md](docs/optional-extras.md) for storage and rebuild details.

## Runtime diagnostics

Curator writes structured JSONL runtime logs under the platform log directory shown by:

```bash
zotero-curator doctor
```

Set `response_format = "json"` in the central settings file, or set `ZOTERO_CURATOR_RESPONSE_FORMAT=json`, to make action-style write responses return structured JSON instead of Markdown. The `zotero_diagnostics` MCP tool reports resolved settings, log paths, and Zotero API reachability.

Batch organization plans include completed/error counts and a per-step report. Automatic rollback is intentionally not attempted; use the report to build and dry-run a corrective plan before applying fixes.

## Development status

Implemented:

- Python package with console scripts: `zotero-curator` and compatibility alias `zotero-mcp`.
- Central settings, diagnostics, and structured runtime logs.
- Client config generation for JSON and TOML MCP clients.
- Read/search/full-text tools.
- Dry-run-first write tools.
- arXiv preprint import from IDs, abstract URLs, and PDF URLs.
- Test and lint configuration.
- CI skeleton.

Next polish:

- PyPI trusted publishing and signed GitHub releases.
- Claude Desktop `.mcpb` packaging.
- Optional semantic index and PDF extraction extras.
- Richer structured JSON responses while keeping Markdown defaults.
