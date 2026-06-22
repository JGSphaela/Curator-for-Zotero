#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
bundle_dir="$root/build/mcpb/zotero-curator"
out_dir="$root/dist"

rm -rf "$bundle_dir"
mkdir -p "$bundle_dir" "$out_dir"
cp "$root/mcpb/manifest.json" "$bundle_dir/manifest.json"
cp "$root/pyproject.toml" "$bundle_dir/pyproject.toml"
cp "$root/README.md" "$bundle_dir/README.md"
cp "$root/LICENSE" "$bundle_dir/LICENSE"

npx --yes @anthropic-ai/mcpb validate "$bundle_dir/manifest.json"
npx --yes @anthropic-ai/mcpb pack "$bundle_dir" "$out_dir/zotero-curator.mcpb"
npx --yes @anthropic-ai/mcpb info "$out_dir/zotero-curator.mcpb"
