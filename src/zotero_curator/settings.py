"""Configuration loading for Curator for Zotero."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - dependency is installed in normal package use
    def load_dotenv() -> bool:
        return False

try:
    from platformdirs import user_config_dir, user_data_dir, user_log_dir
except ModuleNotFoundError:  # pragma: no cover - dependency is installed in normal package use
    def user_config_dir(appname: str, appauthor: bool = False) -> str:
        return str(Path.home() / ".config" / appname)

    def user_data_dir(appname: str, appauthor: bool = False) -> str:
        return str(Path.home() / ".local" / "share" / appname)

    def user_log_dir(appname: str, appauthor: bool = False) -> str:
        return str(Path.home() / ".local" / "state" / appname / "logs")

APP_NAME = "zotero-curator"
TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}
SECRET_ENV = "ZOTERO_" + "API_KEY"


@dataclass(frozen=True)
class CuratorConfig:
    local: bool = True
    library_id: str = "0"
    library_type: str = "user"
    api_key: str | None = None
    write_enabled: bool = False
    response_format: str = "markdown"
    log_dir: Path | None = None
    data_dir: Path | None = None

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


def default_data_dir() -> Path:
    override = os.getenv("ZOTERO_CURATOR_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir(APP_NAME, appauthor=False))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUTHY:
        return True
    if normalized in FALSY:
        return False
    return default


def read_config_file(path: Path | None = None) -> dict[str, Any]:
    path = path or config_file()
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    zotero = data.get("zotero", {})
    return zotero if isinstance(zotero, dict) else {}


def load_config() -> CuratorConfig:
    load_dotenv()
    file_values = read_config_file()
    local = env_flag("ZOTERO_LOCAL", bool(file_values.get("local", True)))
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", str(file_values.get("library_type", "user")))
    library_id = os.getenv("ZOTERO_LIBRARY_ID", str(file_values.get("library_id", "0" if local else "")))
    api_key = os.getenv(SECRET_ENV) or file_values.get("api_key") or None
    write_enabled = env_flag("ZOTERO_WRITE_ENABLED", bool(file_values.get("write_enabled", False)))
    response_format = os.getenv("ZOTERO_CURATOR_RESPONSE_FORMAT", str(file_values.get("response_format", "markdown")))
    if local and not library_id:
        library_id = "0"
    return CuratorConfig(local, library_id, library_type, str(api_key) if api_key else None, write_enabled, response_format, default_log_dir(), default_data_dir())


def _toml_string(value: str) -> str:
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def write_config(*, local: bool = True, library_id: str | None = None, library_type: str = "user", api_key: str | None = None, write_enabled: bool = False, response_format: str = "markdown", path: Path | None = None) -> Path:
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if local:
        library_id = library_id or "0"
    lines = ["[zotero]", f"local = {str(local).lower()}", f"library_type = {_toml_string(library_type)}"]
    if library_id:
        lines.append(f"library_id = {_toml_string(library_id)}")
    if api_key:
        lines.append(f"api_key = {_toml_string(api_key)}")
    lines.append(f"write_enabled = {str(write_enabled).lower()}")
    lines.append(f"response_format = {_toml_string(response_format)}")
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
        f"Response format: {cfg.response_format}",
        f"Log dir: {cfg.log_dir}",
        f"Data dir: {cfg.data_dir}",
    ]
