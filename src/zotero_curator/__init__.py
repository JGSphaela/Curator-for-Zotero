"""Curator for Zotero."""

__all__ = ["mcp"]
__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "mcp":
        from zotero_curator.server import mcp

        return mcp
    raise AttributeError(name)
