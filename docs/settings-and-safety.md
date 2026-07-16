# Settings and safety

Curator keeps Zotero credentials and behavior in one central settings file rather than duplicating them across MCP client configurations.

## Locate the settings file

```bash
uvx --from zotero-curator zotero-curator setup-info
```

Typical locations:

- macOS: `~/Library/Application Support/zotero-curator/config.toml`
- Linux: `~/.config/zotero-curator/config.toml`

Example local configuration:

```toml
[zotero]
local = true
library_type = "user"
library_id = "0"
write_enabled = false
response_format = "markdown"
```

## Environment overrides

| Variable | Purpose |
| --- | --- |
| `ZOTERO_LOCAL` | `true` for local API, `false` for Web API |
| `ZOTERO_LIBRARY_ID` | Zotero user or group library ID |
| `ZOTERO_LIBRARY_TYPE` | `user` or `group` |
| `ZOTERO_API_KEY` | Zotero Web API key |
| `ZOTERO_WRITE_ENABLED` | Enable non-dry-run write tools |
| `ZOTERO_CURATOR_RESPONSE_FORMAT` | `markdown` or `json` action responses |
| `ZOTERO_CURATOR_CONFIG` | Override the settings file path |
| `ZOTERO_CURATOR_CONFIG_DIR` | Override the settings directory |
| `ZOTERO_CURATOR_DATA_DIR` | Override managed data and semantic-index storage |

Environment variables take precedence over the settings file.

## Write safety model

Write tools default to `dry_run=true`. A real write requires all four conditions:

1. Web API mode (`local = false`).
2. A Zotero API key with write permission.
3. `write_enabled = true` or `ZOTERO_WRITE_ENABLED=true`.
4. The individual tool call sets `dry_run=false`.

Curator treats Zotero Local API v3 as read-only because it currently accepts only `GET` requests. Local mode supports reads and dry-runs, but Curator blocks real write operations before calling Zotero.

Check resolved write status with `zotero_write_status` or:

```bash
uvx --from zotero-curator zotero-curator doctor
```

## Diagnostics and logs

`zotero_healthcheck` tests basic configuration and API reachability. `zotero_diagnostics` also reports resolved paths and runtime details.

The CLI equivalent is:

```bash
uvx --from zotero-curator zotero-curator doctor
```

Curator writes structured JSONL runtime logs under the platform log directory printed by `doctor`.

## Response formats

Markdown is the default. Set this in the TOML file:

```toml
response_format = "json"
```

or export:

```bash
export ZOTERO_CURATOR_RESPONSE_FORMAT=json
```

Structured responses are especially useful for action-style write tools and automation.

## Concurrent clients

Read-only tools are lock-free. The optional semantic index uses a cross-process directory lock during rebuilds and searches, preventing multiple MCP clients from mutating or querying the same Chroma index concurrently.

A stale lock is eligible for cleanup after 300 seconds, but only after Curator verifies that the recorded owner process is no longer running. Owner metadata is stored in `.index.lock/owner.txt` for diagnostics.