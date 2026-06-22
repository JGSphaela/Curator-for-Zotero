# Claude Desktop MCPB bundle

Curator ships an MCP Bundle manifest under `mcpb/manifest.json`.

The bundle uses the MCPB v0.4 `uv` server type. It does not vendor a Python virtual environment. Instead, the manifest runs the same zero-install command used in normal MCP client configs:

```bash
uvx --from zotero-curator zotero-curator serve
```

This keeps the bundle small and lets users receive package updates through PyPI releases.

## Build the bundle

```bash
scripts/build-mcpb.sh
```

The script validates the manifest, creates `dist/zotero-curator.mcpb`, and prints bundle metadata.

## Install behavior

Opening `dist/zotero-curator.mcpb` in a host that supports MCPB should install the Curator server and run it through `uvx`.

Users still need to configure Zotero once:

```bash
zotero-curator setup --local
zotero-curator doctor
```

If they prefer central settings without a global install, they can run the same commands through `uvx`:

```bash
uvx --from zotero-curator zotero-curator setup --local
uvx --from zotero-curator zotero-curator doctor
```

## Update path

Publish a normal PyPI release, then rebuild and attach a new `.mcpb` file to the GitHub release. The bundle points to `uvx --from zotero-curator`, so fresh launches resolve the published package version available to `uvx`.

## Python/uv fallback

For MCP clients without MCPB support, use the generated JSON/TOML snippets in `docs/client-config.md`.
