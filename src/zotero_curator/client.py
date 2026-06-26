"""Zotero client helpers."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from pydantic import BaseModel
from pyzotero import zotero

from zotero_curator.settings import CuratorConfig, load_config


class AttachmentDetails(BaseModel):
    key: str
    content_type: str | None = None


def get_zotero_client(config: CuratorConfig | None = None) -> zotero.Zotero:
    """Create a Pyzotero client from central settings and env overrides."""

    cfg = config or load_config()
    if not cfg.local and not all([cfg.library_id, cfg.api_key]):
        raise ValueError(
            "Missing Zotero Web API settings. Set the library id and API key, "
            "or run `zotero-curator setup --local`."
        )
    return zotero.Zotero(
        library_id=cfg.library_id,
        library_type=cfg.library_type,
        api_key=cfg.api_key,
        local=cfg.local,
    )


def local_api_get(path: str, config: CuratorConfig | None = None) -> Any:
    """Make a GET request to the Zotero Local API and return parsed JSON.

    Parameters
    ----------
    path:
        The library-relative path, e.g. ``"searches"`` or ``"searches/<key>/items"``.
        The function prepends ``/api/<library_type>s/<library_id>/`` automatically.
    config:
        Optional explicit config.  Falls back to ``load_config()``.
    """
    cfg = config or load_config()
    if not cfg.local:
        raise ValueError("local_api_get requires local Zotero mode")
    library_path = f"{cfg.library_type}s/{cfg.library_id}"
    url = f"http://localhost:23119/api/{library_path}/{path}"
    request = Request(url, headers={"User-Agent": "zotero-curator/0.1"})
    with urlopen(request, timeout=20.0) as response:
        data = response.read().decode("utf-8")
    return json.loads(data)


def get_attachment_details(
    zot: zotero.Zotero,
    item: dict[str, Any],
) -> AttachmentDetails | None:
    """Return the best attachment for a parent item or a direct attachment item."""

    data = item.get("data", {})
    item_type = data.get("itemType")

    if item_type == "attachment":
        key = data.get("key") or item.get("key")
        if key:
            return AttachmentDetails(key=key, content_type=data.get("contentType"))
        return None

    try:
        children: Any = zot.children(data.get("key") or item.get("key", ""))
    except Exception:
        return None

    candidates: list[tuple[int, str, str | None, str]] = []
    for child in children:
        child_data = child.get("data", {})
        if child_data.get("itemType") != "attachment":
            continue
        key = child_data.get("key") or child.get("key")
        if not key:
            continue
        content_type = child_data.get("contentType")
        priority = 0
        if content_type == "application/pdf":
            priority = 3
        elif content_type == "text/html":
            priority = 2
        elif content_type:
            priority = 1
        tie_breaker = str(child_data.get("md5") or child_data.get("title") or "")
        candidates.append((priority, key, content_type, tie_breaker))

    if not candidates:
        return None
    candidates.sort(key=lambda value: (value[0], value[3]), reverse=True)
    _, key, content_type, _ = candidates[0]
    return AttachmentDetails(key=key, content_type=content_type)
