# Curator for Zotero

Curator for Zotero is a research-focused MCP server for Zotero. It lets AI coding and research assistants search your library, inspect metadata, read indexed attachment text in manageable chunks, navigate outlines/sections, and safely organize items with dry-run-first write tools.

This project is independently maintained and is based on the MIT-licensed [`kujenga/zotero-mcp`](https://github.com/kujenga/zotero-mcp). See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) and [LICENSE](LICENSE).

## Why this repo exists

The original Python MCP server was useful but awkward to configure across Codex, Claude Desktop, Cursor, Claude Code, and other clients because each app needed a hand-maintained virtualenv path. Curator fixes that by making the server a normal published Python tool that clients can launch with `uvx`:

```bash
uvx --from zotero-curator zotero-curator serve
```

That command lets each MCP client start its own stdio server process without knowing about a local checkout path, a repo-local `.venv`, or per-app shell setup.

## Recommended install: `uvx`

Install [`uv`](https://docs.astral.sh/uv/) once, then configure Curator through the published package:

```bash
uvx --from zotero-curator zotero-curator setup --local
uvx --from zotero-curator zotero-curator doctor
```

`uvx` keeps Python environments out of Claude/Codex/Cursor config files. It resolves and caches the published `zotero-curator` package, then runs the requested console command.

For GUI-launched clients on macOS, prefer the absolute `uvx` path from:

```bash
command -v uvx
```

Common Homebrew paths are `/opt/homebrew/bin/uvx` on Apple Silicon and `/usr/local/bin/uvx` on Intel macOS.

Optional persistent install:

```bash
uv tool install zotero-curator
zotero-curator setup --local
zotero-curator doctor
```

## Let an agent set it up

Copy this prompt into Codex, Claude Code, Cursor, or another local coding agent:

```text
Install Curator for Zotero for me by following this repo's AGENTS.md. Use the published uvx workflow and configure these MCP clients: CLIENTS_TO_CONFIGURE.
```

Replace `CLIENTS_TO_CONFIGURE` with the clients you use, for example `Claude Desktop and Codex`.

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
uvx --from zotero-curator zotero-curator setup --local
uvx --from zotero-curator zotero-curator doctor
```

Local mode uses library id `0` and does not require an API key.

## Web API setup

```bash
uvx --from zotero-curator zotero-curator setup --web --library-id YOUR_LIBRARY_ID --api-key YOUR_API_KEY
```

For group libraries, add `--library-type group`.

## MCP client config

Recommended `uvx` config for Claude Desktop, Cursor, and other JSON-style MCP clients:

```json
{
  "mcpServers": {
    "zotero": {
      "command": "/opt/homebrew/bin/uvx",
      "args": [
        "--from",
        "zotero-curator",
        "zotero-curator",
        "serve"
      ]
    }
  }
}
```

Replace `/opt/homebrew/bin/uvx` with the output of `command -v uvx` on your machine.

Recommended `uvx` config for Codex:

```toml
[mcp_servers.zotero]
type = "stdio"
command = "/opt/homebrew/bin/uvx"
args = ["--from", "zotero-curator", "zotero-curator", "serve"]
startup_timeout_sec = 30
```

If you prefer a pinned release, pin the package in the `--from` argument:

```toml
args = ["--from", "zotero-curator==0.1.0", "zotero-curator", "serve"]
```

Installed-tool fallback:

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

Generate config snippets:

```bash
uvx --from zotero-curator zotero-curator mcp-config --uvx --format json
uvx --from zotero-curator zotero-curator mcp-config --uvx --format toml
```

The `install-client` subcommand detects known MCP client config paths, backs up existing files, merges the `zotero` MCP server entry, and defaults to dry-run mode:

```bash
uvx --from zotero-curator zotero-curator install-client --uvx
uvx --from zotero-curator zotero-curator install-client --uvx --apply
```

Release instructions are in [docs/release.md](docs/release.md). Claude Desktop MCPB bundle notes are in [docs/mcpb.md](docs/mcpb.md).

## Add arXiv papers

Curator can create a Zotero `preprint` item directly from an arXiv id, abstract URL, or PDF URL:

```bash
uvx --from zotero-curator zotero-curator add-arxiv https://arxiv.org/abs/2410.03529
```

The command is dry-run-first. To apply it, configure Web API mode with a write-enabled API key, enable writes globally, and pass `--apply`:

```bash
uvx --from zotero-curator zotero-curator setup --web --library-id YOUR_LIBRARY_ID --api-key YOUR_WRITE_ENABLED_API_KEY --write-enabled
uvx --from zotero-curator zotero-curator add-arxiv 2410.03529 --tag AI --collection COLLECTION_KEY --apply
```

This imports arXiv metadata first and stores the PDF as a Zotero file attachment by default. Use `--link-pdf` to attach only the arXiv PDF URL, `--no-pdf` to create only the metadata item, or `--pdf-mode {stored,linked,none}` for explicit control.

## Safe LaTeX citation workflow

Curator can export selected Zotero items directly to a `.bib` file, so an LLM does not need to rewrite BibTeX text by hand.

From MCP, call `zotero_export_bibtex_file` with one or more Zotero item keys. The MCP tool writes only inside Curator's managed data directory, under `exports/`, and rejects path-like filenames such as `../references.bib`.

The `export_mode` argument controls the exporter:

- `auto` default: use Better BibTeX when its local JSON-RPC API is available and the selected personal-library items have BBT citation keys; otherwise fall back to Zotero's normal BibTeX export.
- `zotero`: always use Zotero's normal BibTeX export.
- `better-bibtex`: require Better BibTeX's `Better BibTeX` translator.
- `better-biblatex`: require Better BibTeX's `Better BibLaTeX` translator.

Better BibTeX export mode is currently supported for personal libraries. For group libraries, Curator uses Zotero export in `auto` mode and reports the Better BibTeX fallback reason. Explicit `better-bibtex` or `better-biblatex` group-library exports fail with a clear error because Curator stores Zotero's public group id, while Better BibTeX `item.export` may require Zotero's internal library id.

When Better BibTeX is used, Curator inherits BBT's configured export behavior rather than trying to reimplement it. That includes BBT citation-key resolution, the selected Better BibTeX/BibLaTeX translator, BBT export preferences and field handling, Unicode/LaTeX conversion behavior, and journal abbreviation behavior when configured in Better BibTeX.

The MCP/CLI response explicitly reports the actual backend and BBT metadata used, for example:

```text
Exporter: Better BibTeX
Used Better BibTeX: yes
Better BibTeX version: 9.0.36
Zotero version: 9.0.4

## Better BibTeX behavior applied
- Better BibTeX citation-key resolution
- Better BibTeX export preferences and field handling
- Better BibTeX Unicode/LaTeX conversion behavior
- Better BibTeX journal abbreviation behavior when configured
- Better BibTeX translator field mapping
```

or, after fallback/plain Zotero export:

```text
Exporter: zotero
Used Better BibTeX: no
```

The export creates three files:

- `references.bib`: BibTeX or BibLaTeX entries exported from Zotero/Better BibTeX.
- `references.keys.json`: exporter, whether BBT was used, BBT metadata/fallback reason when relevant, item keys, citation keys, and the generated LaTeX cite command.
- `references.cite.tex`: a ready-to-use `\cite{...}` snippet.

From the CLI:

```bash
zotero-curator export-bibtex ITEMKEY1 ITEMKEY2 --out references.bib --mode auto
```

Validate generated LaTeX against a `.bib` file:

```bash
zotero-curator validate-citations --tex paper.tex --bib references.bib
```

This reports missing citation keys, duplicate BibTeX keys, and unused BibTeX entries.

## Settings

Curator stores central settings in the platform config directory. Print the exact path with:

```bash
uvx --from zotero-curator zotero-curator setup-info
```

On macOS this is typically:

```text
~/Library/Application Support/zotero-curator/config.toml
```

On many Linux systems this is typically:

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
- `zotero_export_bibtex_file`
- `zotero_validate_latex_citations`
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
- `zotero_list_saved_searches`
- `zotero_saved_search_items` (local API only)
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

Write tools default to `dry_run=true`. Real write calls require all of the following:

1. Web API mode: `local = false`.
2. A Zotero API key with write access.
3. `write_enabled = true` in settings, or `ZOTERO_WRITE_ENABLED=true`.
4. The individual tool call sets `dry_run=false`.

The Zotero local API is treated as read-only by Curator because Zotero's Local API v3 documentation says: "Write requests are currently unsupported. Only `GET` is accepted." Local mode can be used for reads and dry-runs, but Curator blocks non-dry-run write tools before they call Zotero. This keeps the implementation aligned with the current API protocol and makes it easy to re-enable local writes later when Zotero adds support.

## Concurrency

Curator uses a cross-process directory-based lock (`SemanticIndexLock`) to serialize access to the optional semantic index. The lock is held during both `zotero_semantic_rebuild` and `zotero_semantic_search` operations.

If a Curator process crashes while holding the lock, the lock directory (`.index.lock`) persists. Curator detects stale locks older than 300 seconds and automatically cleans them up before acquiring a fresh lock, but only after verifying the owner PID is no longer running. The lock owner's PID and creation timestamp are written to `owner.txt` inside the lock directory for diagnostics.

Multiple concurrent MCP clients (e.g. Claude Desktop and Cursor) can safely run simultaneously. Read-only tools are lock-free. Write tools use dry-run-first semantics and require explicit `write_enabled = true` plus `dry_run = false`.

## Optional extras

The base install stays small. Heavy PDF and semantic dependencies are opt-in. For persistent installs:

```bash
uv tool install 'zotero-curator[pdf]'
uv tool install 'zotero-curator[semantic]'
uv tool install 'zotero-curator[all]'
```

For `uvx`-launched MCP clients, request the extra in the `--from` package:

```bash
uvx --from 'zotero-curator[pdf]' zotero-curator serve
uvx --from 'zotero-curator[semantic]' zotero-curator serve
uvx --from 'zotero-curator[all]' zotero-curator serve
```

From a checkout:

```bash
uv pip install --python .venv/bin/python -e '.[pdf]'
uv pip install --python .venv/bin/python -e '.[semantic]'
```

The `pdf` extra enables page-aware PDF reads and bookmark extraction from stored Zotero attachments. The `semantic` extra stores a local Chroma index under the platform data directory shown by `zotero-curator doctor`; rebuild with `zotero_semantic_rebuild` after major library changes, then search with `zotero_semantic_search`. Curator uses a cross-process lock around semantic rebuilds and searches, so concurrent MCP clients will return a clear "semantic index busy" message instead of mutating or querying the same Chroma store at the same time. See [docs/optional-extras.md](docs/optional-extras.md) for storage and rebuild details.

## Runtime diagnostics

Curator writes structured JSONL runtime logs under the platform log directory shown by:

```bash
uvx --from zotero-curator zotero-curator doctor
```

Set `response_format = "json"` in the central settings file, or set `ZOTERO_CURATOR_RESPONSE_FORMAT=json`, to make action-style write responses return structured JSON instead of Markdown. The `zotero_diagnostics` MCP tool reports resolved settings, log paths, and Zotero API reachability.

Batch organization plans include completed/error counts and a per-step report. Automatic rollback is intentionally not attempted; use the report to build and dry-run a corrective plan before applying fixes.

## Development status

Implemented:

- Python package with console scripts: `zotero-curator` and compatibility alias `zotero-mcp`.
- Central settings, diagnostics, and structured runtime logs.
- Client config generation for JSON and TOML MCP clients.
- Client config apply command (`install-client`) that safely injects the server entry into Claude Desktop and Cursor configs.
- Read/search/full-text tools.
- Dry-run-first write tools.
- arXiv preprint import from IDs, abstract URLs, and PDF URLs.
- Saved search listing and execution via the Zotero local API.
- Optional semantic index and PDF extraction extras.
- Richer structured JSON responses while keeping Markdown defaults.
- Cross-process semantic index lock with stale lock recovery.
- Test and lint configuration.
- CI skeleton.

Next polish:

- PyPI trusted publishing and signed GitHub releases.
- Claude Desktop `.mcpb` packaging.
