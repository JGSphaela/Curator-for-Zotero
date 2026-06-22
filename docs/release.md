# Release process

Curator for Zotero publishes from Git tags through `.github/workflows/release.yml`.

## One-time PyPI setup

Create the `zotero-curator` project on PyPI, then add a trusted publisher with these values:

```text
Owner: JGSphaela
Repository: Curator-for-Zotero
Workflow: release.yml
Environment: pypi
```

The workflow requests `id-token: write`, so PyPI can authenticate the GitHub Actions run without storing an API token in repository secrets.

## Release checklist

1. Make sure `main` is green and clean locally:

   ```bash
   git checkout main
   git pull --ff-only
   uv pip install --python .venv/bin/python -e '.[dev]'
   .venv/bin/ruff check .
   .venv/bin/pytest
   uv build
   ```

2. Update the version in `pyproject.toml`.
3. Add a short release note entry in the GitHub release body after the workflow creates the release.
4. Commit the version bump:

   ```bash
   git add pyproject.toml uv.lock
   git commit -m "Release vX.Y.Z"
   git push
   ```

5. Create and push an annotated tag:

   ```bash
   git tag -a vX.Y.Z -m "Curator for Zotero vX.Y.Z"
   git push origin vX.Y.Z
   ```

6. Watch the release workflow finish.
7. Verify installation from PyPI:

   ```bash
   uv tool install zotero-curator
   zotero-curator --help
   zotero-curator doctor
   ```

For a fresh install test without replacing an existing tool, use:

```bash
uvx --from zotero-curator zotero-curator --help
```

## Rollback notes

PyPI files are immutable. If a bad release is published, yank the release on PyPI and publish a new patch version. Delete or edit the GitHub release only if the generated artifacts themselves are wrong.
