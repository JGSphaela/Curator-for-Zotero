# Agent installation guide

Use this guide when an AI coding agent or assistant installs Curator for Zotero for a user.

## Goal

Configure MCP clients to launch the published `zotero-curator` package through `uvx`, not through a repo-local virtual environment.

Preferred server command:

```bash
uvx --from zotero-curator zotero-curator serve
```

For GUI-launched macOS clients, use the absolute `uvx` path from:

```bash
command -v uvx
```

Common Homebrew paths are `/opt/homebrew/bin/uvx` on Apple Silicon and `/usr/local/bin/uvx` on Intel macOS.

## User setup checklist

1. Confirm `uvx` exists:

   ```bash
   command -v uvx
   ```

2. Ask the user to open Zotero and enable the local API:
   Zotero Settings → Advanced → Allow other applications on this computer to communicate with Zotero.

3. Write Curator's central settings:

   ```bash
   uvx --from zotero-curator zotero-curator setup --local
   ```

4. Validate connectivity:

   ```bash
   uvx --from zotero-curator zotero-curator doctor
   ```

5. Configure each MCP client to run the `uvx` command below. Do not create one virtualenv per client.

## Claude/Cursor JSON

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

Replace `/opt/homebrew/bin/uvx` with the user's `command -v uvx` output.

## Codex TOML

```toml
[mcp_servers.zotero]
type = "stdio"
command = "/opt/homebrew/bin/uvx"
args = ["--from", "zotero-curator", "zotero-curator", "serve"]
startup_timeout_sec = 30
```

Replace `/opt/homebrew/bin/uvx` with the user's `command -v uvx` output.

## Optional extras

If the user needs PDF or semantic-search extras, put the extra on the `--from` package:

```bash
uvx --from 'zotero-curator[pdf]' zotero-curator serve
uvx --from 'zotero-curator[semantic]' zotero-curator serve
uvx --from 'zotero-curator[all]' zotero-curator serve
```

## Settings location

Curator stores Zotero settings centrally, outside MCP client configs. Print the exact path with:

```bash
uvx --from zotero-curator zotero-curator setup-info
```

On macOS this is typically:

```text
~/Library/Application Support/zotero-curator/config.toml
```

## Safety rules for agents

- Prefer `uvx` over repo-local `.venv` paths in MCP client configs.
- Do not copy Zotero API keys into Claude/Codex/Cursor config unless the user explicitly asks for that deployment model.
- Preserve existing user config entries when editing MCP client config files.
- Back up config files before modifying them.
- Keep write tools disabled unless the user explicitly requests writes; real writes require both `write_enabled = true` and individual tool calls with `dry_run=false`.
- Use pinned packages such as `zotero-curator==0.1.0` when the user prefers reproducibility over auto-updating to the latest published release.
