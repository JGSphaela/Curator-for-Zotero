# Roadmap

## Phase 1: package and setup foundation

- [x] Independent package name: `zotero-curator`.
- [x] Stable console scripts: `zotero-curator`, `zotero-mcp`.
- [x] Central settings under `~/.config/zotero-curator/config.toml`.
- [x] `setup`, `doctor`, `setup-info`, and `mcp-config` commands.
- [x] JSON and TOML MCP client snippets.

## Phase 2: feature parity with the useful fork work

- [x] Library search and item metadata.
- [x] DOI lookup.
- [x] Full-text dump, info, chunks, and within-document search.
- [x] Outline and section reading.
- [x] Child notes and attachments listing.
- [x] Collections and tags listing.
- [x] Dry-run-first item write tools.
- [x] Collection create/rename/delete tools.
- [x] Batch organization-plan tool.
- [x] Dry-run-first arXiv preprint import with stored PDF support.

## Phase 3: distribution polish

- [ ] PyPI trusted publishing.
- [ ] GitHub release workflow.
- [ ] Claude Desktop `.mcpb` bundle.
- [ ] Optional standalone binaries.

## Phase 4: research extras

- [x] Optional PDF text extraction fallback when Zotero indexed text is missing.
- [x] Optional semantic search with local embeddings/vector store.
- [x] Better citation export helpers: managed BibTeX file export plus citation-key validation.
- [x] Better BibTeX translator/key-style integration through optional JSON-RPC auto mode.
- [ ] DOI import with optional stored PDF discovery.
- [ ] Structured JSON output mode for automation-heavy agents.

## Phase 5: rewrite decision gate

A rewrite is only worth it if packaging polish does not solve the original cross-client setup problem. The current approach keeps Python for Zotero/PDF/semantic tooling and removes the venv-per-client pain through `uv tool install`, `uvx`, and generated MCP configs.
