# Research workflows

Curator exposes Zotero through both MCP tools and focused CLI commands. This page collects the workflows that are too detailed for the project README.

## Add an arXiv paper

Preview an import:

```bash
uvx --from zotero-curator zotero-curator add-arxiv https://arxiv.org/abs/2410.03529
```

Real imports require Web API mode, a write-enabled API key, globally enabled writes, and `--apply`:

```bash
uvx --from zotero-curator zotero-curator setup --web \
  --library-id YOUR_LIBRARY_ID \
  --api-key YOUR_WRITE_ENABLED_API_KEY \
  --write-enabled

uvx --from zotero-curator zotero-curator add-arxiv 2410.03529 \
  --tag AI \
  --collection COLLECTION_KEY \
  --apply
```

The default stores the PDF as a Zotero attachment. Use `--link-pdf`, `--no-pdf`, or `--pdf-mode {stored,linked,none}` to choose another attachment mode.

## Read long documents

A typical MCP sequence is:

1. Find the item with `zotero_search_items` or `zotero_find_item_by_doi`.
2. Inspect size and attachment selection with `zotero_item_fulltext_info`.
3. Search inside the indexed text with `zotero_item_search_text`.
4. Read a bounded result with `zotero_item_text_chunk`.
5. Use `zotero_item_outline` and `zotero_item_read_section` when the indexed text preserves recognizable headings.

With the `pdf` extra, `zotero_pdf_pages` provides page-aware reads and `zotero_pdf_outline` reads PDF bookmarks or table-of-contents data when available.

## Export BibTeX safely

Call `zotero_export_bibtex_file` from MCP or use:

```bash
zotero-curator export-bibtex ITEMKEY1 ITEMKEY2 \
  --out references.bib \
  --mode auto
```

`auto` prefers Better BibTeX for supported personal-library exports when its local JSON-RPC API and citation keys are available, then falls back to Zotero's exporter. Other modes are `zotero`, `better-bibtex`, and `better-biblatex`.

Curator writes exports only inside its managed `exports/` data directory and rejects path-like filenames. A successful export creates:

- `references.bib`
- `references.keys.json`
- `references.cite.tex`

The metadata file records the selected exporter, citation keys, generated cite command, and Better BibTeX details or fallback reason.

## Validate LaTeX citations

```bash
zotero-curator validate-citations --tex paper.tex --bib references.bib
```

The validator reports missing citation keys, duplicate BibTeX keys, and unused entries. The equivalent MCP tool is `zotero_validate_latex_citations`.

## Navigate collections and saved searches

Use:

- `zotero_list_collections`
- `zotero_collection_items`
- `zotero_list_tags`
- `zotero_list_saved_searches`
- `zotero_saved_search_items`

Executing saved searches is available only through the Zotero local API.

## Organize the library

Organization tools cover collections, tags, selected metadata, and child notes. All write tools default to dry-run. Preview the proposed operation first, inspect the response, then repeat with `dry_run=false` only after enabling Web API writes.

For multi-step changes, `zotero_apply_organization_plan` reports each completed or failed step. Curator intentionally does not attempt automatic rollback; dry-run and apply a corrective plan instead.

See [Settings and safety](settings-and-safety.md) before enabling writes.