"""Runtime diagnostics and structured logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zotero_curator.settings import CuratorConfig, load_config

LOGGER_NAME = "zotero_curator"


def configure_logging(cfg: CuratorConfig | None = None) -> Path:
    """Configure append-only JSONL logging and return the log file path."""

    cfg = cfg or load_config()
    log_dir = cfg.log_dir or Path.cwd()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "curator.jsonl"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path for handler in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return log_path


def log_event(event: str, **fields: Any) -> None:
    """Write one structured JSON event if logging is configured."""

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        configure_logging()
    payload = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "event": event,
        **fields,
    }
    logger.info(json.dumps(payload, sort_keys=True, default=str))


def runtime_diagnostics(cfg: CuratorConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    return {
        "mode": cfg.mode_label,
        "library_type": cfg.library_type,
        "library_id": cfg.library_id,
        "api_key_set": bool(cfg.api_key),
        "write_enabled": cfg.write_enabled,
        "response_format": cfg.response_format,
        "log_dir": str(cfg.log_dir),
        "log_file": str((cfg.log_dir or Path.cwd()) / "curator.jsonl"),
        "data_dir": str(cfg.data_dir),
    }
