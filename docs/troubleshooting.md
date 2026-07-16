# Troubleshooting

Start with:

```bash
uvx --from zotero-curator zotero-curator doctor
```

For MCP clients, also call `zotero_healthcheck` or `zotero_diagnostics`.

## `uvx` is not found

Install `uv`, then verify:

```bash
command -v uvx
```

GUI applications on macOS may not inherit your shell `PATH`. Put the absolute path returned by `command -v uvx` in the MCP client configuration. Common Homebrew paths are `/opt/homebrew/bin/uvx` on Apple Silicon and `/usr/local/bin/uvx` on Intel Macs.

## The MCP client cannot start Curator

Run the configured command directly:

```bash
uvx --from zotero-curator zotero-curator serve
```

Also verify the client config syntax using:

```bash
uvx --from zotero-curator zotero-curator mcp-config --uvx --format json
uvx --from zotero-curator zotero-curator mcp-config --uvx --format toml
```

The `install-client` command can detect and safely merge supported client configurations. It defaults to a dry run:

```bash
uvx --from zotero-curator zotero-curator install-client --uvx
uvx --from zotero-curator zotero-curator install-client --uvx --apply
```

## Curator cannot reach Zotero locally

Confirm all of the following:

1. Zotero is running.
2. Zotero Settings → Advanced → “Allow other applications on this computer to communicate with Zotero” is enabled.
3. Curator is configured for local mode:

```bash
uvx --from zotero-curator zotero-curator setup --local
```

Local mode uses library ID `0` and does not require an API key.

## Web API authentication fails

Reconfigure with the correct library ID and API key:

```bash
uvx --from zotero-curator zotero-curator setup --web \
  --library-id YOUR_LIBRARY_ID \
  --api-key YOUR_API_KEY
```

Add `--library-type group` for a group library. Real writes also require the key to have write permission and setup with `--write-enabled`.

## Write tools remain in dry-run mode

Real writes require Web API mode, a write-enabled key, global write enablement, and `dry_run=false` on the individual call. Zotero's local API is read-only for Curator write tools.

Inspect the resolved state with `zotero_write_status` or `doctor`.

## Full text is empty or unavailable

Curator's indexed-text tools use text already indexed by Zotero. They do not run OCR. Check that:

- the item has a PDF or HTML attachment;
- Zotero has indexed the attachment;
- the PDF contains selectable text rather than only scanned images.

Use `zotero_item_children` to inspect attachment keys and `zotero_item_fulltext_info` before requesting the whole text. With the `pdf` extra, page-aware extraction may provide better structure for stored PDFs, but image-only pages still require OCR outside Curator.

## PDF or semantic tools are missing

Install the corresponding extra:

```bash
uvx --from 'zotero-curator[pdf]' zotero-curator serve
uvx --from 'zotero-curator[semantic]' zotero-curator serve
uvx --from 'zotero-curator[all]' zotero-curator serve
```

The extra belongs on the package passed to `--from`.

## Semantic search says the index is busy

Another Curator process is rebuilding or searching the index. Retry after that operation finishes. Curator automatically removes stale locks older than 300 seconds only after verifying that the recorded owner process is no longer alive.

## Better BibTeX falls back to Zotero export

In `auto` mode, Curator falls back when Better BibTeX's local JSON-RPC API or usable citation keys are unavailable. The export response and `.keys.json` file include the reason.

Explicit Better BibTeX modes currently support personal libraries. Group-library exports use Zotero in `auto` mode because Better BibTeX may require Zotero's internal library ID rather than the public group ID stored by Curator.

## Citation validation reports missing keys

Check that the `.tex` file and `.bib` file are from the same export and that the generated `references.cite.tex` snippet was copied without editing the citation keys. The validator also reports duplicate keys and unused entries separately.

## Reporting a problem

Include:

- Curator version;
- operating system and Python/`uvx` version;
- local or Web API mode, without exposing the API key;
- relevant `doctor` or `zotero_diagnostics` output;
- the exact command or MCP tool call;
- the smallest reproducible error message.