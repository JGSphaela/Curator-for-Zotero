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
