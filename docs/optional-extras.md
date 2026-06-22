# Optional extras

Curator keeps the default package small. PDF parsing and embedding-backed semantic search are optional install extras.

## PDF extra

Install:

```bash
uv tool install 'zotero-curator[pdf]'
```

From a checkout:

```bash
uv pip install --python .venv/bin/python -e '.[pdf]'
```

Tools enabled by this extra:

- `zotero_pdf_pages`: extract page-aware text from a stored Zotero PDF attachment.
- `zotero_pdf_outline`: read PDF bookmarks/table of contents.

The tools use Zotero's local file endpoint to retrieve stored attachment bytes and do not need direct filesystem access to the Zotero storage directory.

## Semantic extra

Install:

```bash
uv tool install 'zotero-curator[semantic]'
```

From a checkout:

```bash
uv pip install --python .venv/bin/python -e '.[semantic]'
```

Tools enabled by this extra:

- `zotero_semantic_rebuild`: build or refresh a local Chroma index of Zotero item metadata.
- `zotero_semantic_search`: query the local semantic index.

The semantic index is stored under Curator's platform data directory. Show the resolved path with:

```bash
zotero-curator doctor
```

Override the storage location with:

```bash
export ZOTERO_CURATOR_DATA_DIR=/path/to/curator-data
```

## Rebuild and update workflow

After adding many Zotero items, changing abstracts/titles, or switching libraries, rebuild the index:

```text
Call the MCP tool `zotero_semantic_rebuild`.
```

Then search with:

```text
Call the MCP tool `zotero_semantic_search` with a natural-language query.
```

## All extras

```bash
uv tool install 'zotero-curator[all]'
```
