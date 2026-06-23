# Client configuration

Curator is designed so MCP clients do not need to know anything about virtualenv paths. Configure clients to run a stable command and keep Zotero settings in Curator's central TOML file.

## Recommended installed-tool config

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

Codex:

```toml
[mcp_servers.zotero]
command = "zotero-curator"
args = ["serve"]
```

## Zero-install config

Use this when you do not want each coding app to manage a venv:

```json
{
  "mcpServers": {
    "zotero": {
      "command": "uvx",
      "args": ["--from", "zotero-curator", "zotero-curator", "serve"]
    }
  }
}
```

Codex:

```toml
[mcp_servers.zotero]
command = "uvx"
args = ["--from", "zotero-curator", "zotero-curator", "serve"]
```

## Generate snippets

```bash
zotero-curator mcp-config --format json
zotero-curator mcp-config --format toml
zotero-curator mcp-config --uvx --format toml
```

## Central settings

```bash
zotero-curator setup --local
zotero-curator setup-info
zotero-curator doctor
```

MCP clients should not store API keys or library configuration unless you intentionally choose that deployment model. Prefer the central settings file and environment overrides.

## Write-capable mode

Local API mode is read-only for Curator write tools. Zotero's Local API v3 documentation says: "Write requests are currently unsupported. Only `GET` is accepted." Local mode supports reads and dry-runs, but non-dry-run write tools require Web API mode with a Zotero API key that has write access:

```bash
zotero-curator setup --web --library-id YOUR_LIBRARY_ID --api-key YOUR_WRITE_ENABLED_API_KEY --write-enabled
zotero-curator doctor
```

For group libraries, add `--library-type group`.
