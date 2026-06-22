#!/usr/bin/env bash
set -euo pipefail

uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest
uv build
.venv/bin/zotero-curator --help >/dev/null
