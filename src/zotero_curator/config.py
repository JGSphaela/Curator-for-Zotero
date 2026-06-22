"""Configuration loading for Curator for Zotero."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from platformdirs import user_config_dir, user_log_dir

APP_NAME = "zotero-curator"
TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CuratorConfig:
    """Resolved runtime configuration."""

    local: bool = True
    library_id: str = "0"
    library_type: str = "user"
    api_key: str | None = None
    write_enabled: bool = False
    log_dir: Path | None = None

    @property
    def mode_label(self) -> str:
        return "local Zotero API" if self.local else "Zotero Web API"


def config_dir() -> Path:
    override = os.getenv("ZOTERO_CURATOR_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir(APP_NAME, appauthor=False))


def config_file() -> Path:
    override = os.getenv("ZOTERO_CURATOR_CONFIG")
    if override:
        return Path(override).expanduser()
    return config_dir() / "config.toml"


def default_log_dir() -> Path:
    override = os.getenv("ZOTERO_CURATOR_LOG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_log_dir(APP_NAME, appauthor=False))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY


def read_config_file(path: Path | None = None) -> dict[str, Any]:
    path = path or config_file()
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    zotero = data.get("zotero", {})
    if not isinstance(zotero, dict):
        return {}
    return zotero


def load_config() -> CuratorConfig:
    """Load .env, TOML config, and environment variables.

    Precedence: environment variables > central config file > defaults.
    """

    load_dotenv()
    file_values = read_config_file()

    local = env_flag("ZOTERO_LOCAL", bool(file_values.get("local", True)))
    library_type = os.getenv(
        "ZOTERO_LIBRARY_TYPE", str(file_values.get("library_type", "user"))
    )
    library_id = os.getenv(
        "ZOTERO_LIBRARY_ID", str(file_values.get("library_id", "0" if local else ""))
    )
    api_key = os.getenv("ZOTERO_API_KEY") or file_values.get("api_key") or None
    write_enabled = env_flag(
        "ZOTERO_WRITE_ENABLED", bool(file_values.get("write_enabled", False))
    )

    if local and not library_id:
        library_id = "0"

    return CuratorConfig(
        local=local,
        library_id=library_id,
        library_type=library_type,
        api_key=str(api_key) if api_key else None,
        write_enabled=write_enabled,
        log_dir=default_log_dir(),
    )


def write_config(
    *,
    local: bool = True,
    library_id: str | None = None,
    library_type: str = "user",
    api_key: str | None = None,
    write_enabled: bool = False,
    path: Path | None = None,
) -> Path:
    """Write a central TOML config file and return its path."""

    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if local:
        library_id = library_id or "0"
    lines = ["[zotero]", f"local = {str(local).lower()}"]
    lines.append(f'library_type = "{library_type}"')
    if library_id:
        lines.append(f'library_id = "{library_id}"')
    if api_key:
        lines.append(f'api_key = "{api_key}"')
    lines.append(f"write_enabled = {str(write_enabled).lower()}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def config_status_lines(cfg: CuratorConfig | None = None) -> list[str]:
    cfg = cfg or load_config()
    return [
        f"Config file: {config_file()}",
        f"Mode: {cfg.mode_label}",
        f"Library: {cfg.library_type}/{cfg.library_id or '(unset)'}",
        f"API key: {'set' if cfg.api_key else 'not set'}",
        f"Write tools: {'enabled' if cfg.write_enabled else 'disabled'}",
        f"Log dir: {cfg.log_dir}",
    ]
