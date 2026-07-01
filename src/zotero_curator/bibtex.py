"""BibTeX export and LaTeX citation validation helpers."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter

from zotero_curator.settings import CuratorConfig

DEFAULT_BIBTEX_FILENAME = "references.bib"
EXPORT_SUBDIR = "exports"
BBT_JSON_RPC_URL = "http://localhost:23119/better-bibtex/json-rpc"
BBT_TRANSLATORS = {
    "better-bibtex": "Better BibTeX",
    "better-biblatex": "Better BibLaTeX",
}
ExportMode = Literal["auto", "zotero", "better-bibtex", "better-biblatex"]
_SAFE_FILENAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,127}")
_BIBTEX_KEY_RE = re.compile(r"@\s*[A-Za-z]+\s*\{\s*([^,]+?)\s*,")
_CITE_COMMAND_RE = re.compile(r"\\(?P<command>[A-Za-z]*cite[A-Za-z]*|nocite)\*?")


class BetterBibtexUnavailableError(RuntimeError):
    """Raised when Better BibTeX JSON-RPC is unavailable or unusable."""


@dataclass(frozen=True)
class BibtexExportResult:
    """Files written by a BibTeX export."""

    bib_path: Path
    keys_path: Path
    cite_path: Path
    item_keys: list[str]
    citation_keys: list[str]
    exporter: str = "zotero"
    exporter_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CitationValidationReport:
    """Result of comparing LaTeX cite commands against BibTeX keys."""

    citation_keys: list[str]
    bibtex_keys: list[str]
    missing_keys: list[str]
    unused_bibtex_keys: list[str]
    duplicate_bibtex_keys: list[str]
    nocite_all: bool = False

    @property
    def ok(self) -> bool:
        return not self.missing_keys and not self.duplicate_bibtex_keys


def managed_export_dir(cfg: CuratorConfig) -> Path:
    """Return Curator's managed export directory."""

    data_dir = cfg.data_dir or Path.cwd() / ".zotero-curator"
    return data_dir / EXPORT_SUBDIR


def safe_export_filename(filename: str | None, suffix: str = ".bib") -> str:
    """Return a conservative export filename, rejecting paths and traversal."""

    value = (filename or DEFAULT_BIBTEX_FILENAME).strip()
    if not value:
        value = DEFAULT_BIBTEX_FILENAME
    path = Path(value)
    if path.is_absolute() or path.name != value or "/" in value or "\\" in value:
        raise ValueError("Export filename must be a filename only, not a path.")
    if value in {".", ".."} or ".." in path.parts:
        raise ValueError("Export filename must not contain parent directory traversal.")
    if not value.lower().endswith(suffix.lower()):
        value = f"{value}{suffix}"
    if not _SAFE_FILENAME_RE.fullmatch(value):
        raise ValueError(
            "Export filename may contain only letters, numbers, spaces, dots, underscores, and hyphens."
        )
    return value


def managed_export_path(cfg: CuratorConfig, filename: str | None, suffix: str = ".bib") -> Path:
    """Resolve a filename under the managed export directory."""

    export_dir = managed_export_dir(cfg).expanduser().resolve()
    path = (export_dir / safe_export_filename(filename, suffix=suffix)).resolve()
    if path.parent != export_dir:
        raise ValueError("Resolved export path escaped Curator's managed export directory.")
    return path


def normalize_item_keys(item_keys: list[str]) -> list[str]:
    """Normalize user-provided Zotero item keys while preserving order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_key in item_keys:
        key = str(raw_key).strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    if not normalized:
        raise ValueError("Please provide at least one Zotero item key.")
    return normalized


def bibtex_response_to_text(response: Any) -> str:
    """Convert Zotero/Pyzotero BibTeX responses into BibTeX text."""

    if isinstance(response, str):
        return response.strip()
    if isinstance(response, bytes):
        return response.decode("utf-8").strip()
    if isinstance(response, BibDatabase) or hasattr(response, "entries"):
        writer = BibTexWriter()
        writer.indent = "  "
        return writer.write(response).strip()
    raise TypeError(f"Unsupported BibTeX response type: {type(response).__name__}")


def bibtex_for_item(zot: Any, item_key: str) -> str:
    """Fetch one Zotero item as BibTeX text."""

    response = zot.item(item_key, format="bibtex")
    text = bibtex_response_to_text(response)
    if not text:
        raise ValueError(f"Zotero returned empty BibTeX for item key: {item_key}")
    return text


def bbt_json_rpc(method: str, params: list[Any] | None = None, timeout: float = 10.0) -> Any:
    """Call Better BibTeX's local JSON-RPC API."""

    payload = json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
    ).encode("utf-8")
    request = Request(
        BBT_JSON_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, HTTPError, URLError, json.JSONDecodeError) as exc:
        raise BetterBibtexUnavailableError(f"Better BibTeX JSON-RPC unavailable: {exc}") from exc
    if "error" in data:
        error = data["error"]
        message = error.get("message", error) if isinstance(error, dict) else error
        raise BetterBibtexUnavailableError(f"Better BibTeX JSON-RPC error: {message}")
    return data.get("result")


def bbt_ready() -> dict[str, Any]:
    """Return Better BibTeX readiness/version information."""

    result = bbt_json_rpc("api.ready", [])
    if not isinstance(result, dict) or not result.get("betterbibtex"):
        raise BetterBibtexUnavailableError("Better BibTeX did not return readiness information.")
    return result


def bbt_item_ids(item_keys: list[str], cfg: CuratorConfig) -> list[str]:
    """Return BBT item identifiers for personal-library citation-key lookup."""

    normalized = normalize_item_keys(item_keys)
    if cfg.library_type != "user":
        raise BetterBibtexUnavailableError(
            "Better BibTeX item.citationkey requires Zotero internal library IDs for groups."
        )
    return normalized


def bbt_personal_citation_keys(item_keys: list[str], cfg: CuratorConfig) -> tuple[list[str], list[str]]:
    """Resolve personal-library Zotero item keys to Better BibTeX citation keys."""

    normalized = normalize_item_keys(item_keys)
    ids = bbt_item_ids(normalized, cfg)
    result = bbt_json_rpc("item.citationkey", [ids])
    if not isinstance(result, dict):
        raise BetterBibtexUnavailableError("Better BibTeX returned an unexpected citation-key result.")
    citation_keys: list[str] = []
    missing: list[str] = []
    for item_key, bbt_id in zip(normalized, ids, strict=True):
        citekey = result.get(bbt_id)
        if not citekey:
            missing.append(item_key)
        else:
            citation_keys.append(str(citekey))
    if missing:
        raise BetterBibtexUnavailableError(
            "Better BibTeX has no citation key for item key(s): " + ", ".join(missing)
        )
    duplicate_keys = duplicate_values(citation_keys)
    if duplicate_keys:
        raise ValueError("Duplicate Better BibTeX citation keys: " + ", ".join(duplicate_keys))
    return citation_keys, normalized


def bbt_group_citation_keys(item_keys: list[str], cfg: CuratorConfig) -> tuple[list[str], list[str]]:
    """Resolve group-library Zotero item keys via BBT search results.

    BBT's item.citationkey method expects Zotero's internal libraryID prefix for group items,
    while Curator stores the public Zotero API group id. Searching across BBT libraries lets us
    match results by the public group id embedded in Zotero item URIs.
    """

    normalized = normalize_item_keys(item_keys)
    group_id = str(cfg.library_id)
    citation_keys: list[str] = []
    missing: list[str] = []
    for item_key in normalized:
        result = bbt_json_rpc("item.search", [[["key", "is", item_key]]], timeout=10.0)
        if not isinstance(result, list):
            raise BetterBibtexUnavailableError("Better BibTeX returned an unexpected search result.")
        expected_suffix = f"/groups/{group_id}/items/{item_key}"
        citekey: str | None = None
        for item in result:
            if not isinstance(item, dict):
                continue
            zotero_id = str(item.get("id", ""))
            item_citekey = item.get("citekey") or item.get("citation-key")
            if zotero_id.endswith(expected_suffix) and item_citekey:
                citekey = str(item_citekey)
                break
        if citekey:
            citation_keys.append(citekey)
        else:
            missing.append(item_key)
    if missing:
        raise BetterBibtexUnavailableError(
            "Better BibTeX has no citation key for group item key(s): " + ", ".join(missing)
        )
    duplicate_keys = duplicate_values(citation_keys)
    if duplicate_keys:
        raise ValueError("Duplicate Better BibTeX citation keys: " + ", ".join(duplicate_keys))
    return citation_keys, normalized


def bbt_citation_keys(item_keys: list[str], cfg: CuratorConfig) -> tuple[list[str], list[str]]:
    """Resolve Zotero item keys to Better BibTeX citation keys."""

    if cfg.library_type == "user":
        return bbt_personal_citation_keys(item_keys, cfg)
    return bbt_group_citation_keys(item_keys, cfg)


def bbt_applied_features(export_mode: Literal["better-bibtex", "better-biblatex"]) -> list[str]:
    """Describe BBT behavior inherited by Curator's one-shot export."""

    features = [
        "Better BibTeX citation-key resolution",
        "Better BibTeX export preferences and field handling",
        "Better BibTeX Unicode/LaTeX conversion behavior",
        "Better BibTeX journal abbreviation behavior when configured",
    ]
    if export_mode == "better-biblatex":
        features.append("Better BibLaTeX translator field mapping")
    else:
        features.append("Better BibTeX translator field mapping")
    return features


def bbt_export_items(
    item_keys: list[str], cfg: CuratorConfig, export_mode: Literal["better-bibtex", "better-biblatex"]
) -> tuple[str, list[str], list[str], str, dict[str, Any]]:
    """Export items through Better BibTeX's configured translators."""

    bbt_info = bbt_ready()
    citation_keys, normalized = bbt_citation_keys(item_keys, cfg)
    translator = BBT_TRANSLATORS[export_mode]
    library_id: str | int | None = None
    if cfg.library_type != "user":
        library_id = cfg.library_id
    params: list[Any] = [citation_keys, translator]
    if library_id is not None:
        params.append(library_id)
    result = bbt_json_rpc("item.export", params)
    bibtex_text = bibtex_response_to_text(result)
    if not bibtex_text:
        raise BetterBibtexUnavailableError("Better BibTeX returned an empty export.")
    exported_keys = extract_bibtex_keys(bibtex_text)
    if not exported_keys:
        raise BetterBibtexUnavailableError("Better BibTeX export did not contain BibTeX entries.")
    duplicate_keys = duplicate_values(exported_keys)
    if duplicate_keys:
        raise ValueError("Duplicate BibTeX citation keys: " + ", ".join(duplicate_keys))
    metadata = {
        "used_better_bibtex": True,
        "better_bibtex": bbt_info,
        "translator": translator,
        "features_applied": bbt_applied_features(export_mode),
    }
    return bibtex_text.strip() + "\n", exported_keys, normalized, translator, metadata


def zotero_bibtex_for_items(zot: Any, item_keys: list[str]) -> tuple[str, list[str], list[str], str, dict[str, Any]]:
    """Fetch multiple Zotero items as combined BibTeX text and citation keys."""

    normalized_keys = normalize_item_keys(item_keys)
    chunks = [bibtex_for_item(zot, item_key) for item_key in normalized_keys]
    bibtex_text = "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip() + "\n"
    citation_keys = extract_bibtex_keys(bibtex_text)
    if not citation_keys:
        raise ValueError("No BibTeX entries were found in Zotero's export response.")
    duplicate_keys = duplicate_values(citation_keys)
    if duplicate_keys:
        raise ValueError("Duplicate BibTeX citation keys: " + ", ".join(duplicate_keys))
    metadata = {"used_better_bibtex": False, "translator": "zotero"}
    return bibtex_text, citation_keys, normalized_keys, "zotero", metadata


def bibtex_for_items(
    zot: Any,
    item_keys: list[str],
    cfg: CuratorConfig | None = None,
    export_mode: ExportMode = "zotero",
) -> tuple[str, list[str], list[str], str, dict[str, Any]]:
    """Export items with plain Zotero or optional Better BibTeX support."""

    if export_mode == "zotero":
        return zotero_bibtex_for_items(zot, item_keys)
    if export_mode in BBT_TRANSLATORS:
        if cfg is None:
            raise ValueError("Better BibTeX export requires Curator configuration.")
        return bbt_export_items(item_keys, cfg, export_mode)
    if export_mode != "auto":
        raise ValueError(f"Unsupported BibTeX export mode: {export_mode}")
    if cfg is not None:
        try:
            return bbt_export_items(item_keys, cfg, "better-bibtex")
        except BetterBibtexUnavailableError as exc:
            bibtex_text, citation_keys, normalized_keys, exporter, metadata = zotero_bibtex_for_items(
                zot, item_keys
            )
            metadata["better_bibtex_fallback_reason"] = str(exc)
            return bibtex_text, citation_keys, normalized_keys, exporter, metadata
    return zotero_bibtex_for_items(zot, item_keys)


def duplicate_values(values: list[str]) -> list[str]:
    """Return duplicate values in first-seen order."""

    counts = Counter(values)
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if counts[value] > 1 and value not in seen:
            seen.add(value)
            duplicates.append(value)
    return duplicates


def extract_bibtex_keys(bibtex_text: str) -> list[str]:
    """Extract entry keys from BibTeX text."""

    return [match.group(1).strip() for match in _BIBTEX_KEY_RE.finditer(bibtex_text)]


def latex_cite_command(keys: list[str]) -> str:
    """Return a deterministic LaTeX cite command for exported keys."""

    if not keys:
        return ""
    return "\\cite{" + ",".join(keys) + "}"


def write_bibtex_export(
    *,
    bibtex_text: str,
    citation_keys: list[str],
    item_keys: list[str],
    bib_path: Path,
    overwrite: bool = False,
    exporter: str = "zotero",
    exporter_metadata: dict[str, Any] | None = None,
) -> BibtexExportResult:
    """Write BibTeX plus key/cite sidecars to disk."""

    keys_path = bib_path.with_suffix(".keys.json")
    cite_path = bib_path.with_suffix(".cite.tex")
    export_paths = [bib_path, keys_path, cite_path]
    existing_paths = [path for path in export_paths if path.exists()]
    if existing_paths and not overwrite:
        existing = ", ".join(str(path) for path in existing_paths)
        raise FileExistsError(f"Export file(s) already exist: {existing}")

    bib_path.parent.mkdir(parents=True, exist_ok=True)
    bib_path.write_text(bibtex_text, encoding="utf-8")
    keys_payload = {
        "bib_file": str(bib_path),
        "exporter": exporter,
        "used_better_bibtex": bool(
            exporter_metadata and exporter_metadata.get("used_better_bibtex")
        ),
        "item_keys": item_keys,
        "citation_keys": citation_keys,
        "latex_cite": latex_cite_command(citation_keys),
    }
    if exporter_metadata:
        keys_payload["exporter_metadata"] = exporter_metadata
    keys_path.write_text(json.dumps(keys_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cite_path.write_text(latex_cite_command(citation_keys) + "\n", encoding="utf-8")
    return BibtexExportResult(
        bib_path=bib_path,
        keys_path=keys_path,
        cite_path=cite_path,
        item_keys=item_keys,
        citation_keys=citation_keys,
        exporter=exporter,
        exporter_metadata=exporter_metadata,
    )


def export_bibtex_file(
    *,
    zot: Any,
    item_keys: list[str],
    bib_path: Path,
    overwrite: bool = False,
    cfg: CuratorConfig | None = None,
    export_mode: ExportMode = "auto",
) -> BibtexExportResult:
    """Fetch Zotero items and write a BibTeX export file."""

    bibtex_text, citation_keys, normalized_keys, exporter, exporter_metadata = bibtex_for_items(
        zot, item_keys, cfg=cfg, export_mode=export_mode
    )
    return write_bibtex_export(
        bibtex_text=bibtex_text,
        citation_keys=citation_keys,
        item_keys=normalized_keys,
        bib_path=bib_path,
        overwrite=overwrite,
        exporter=exporter,
        exporter_metadata=exporter_metadata,
    )


def export_bibtex_managed_file(
    *,
    zot: Any,
    item_keys: list[str],
    cfg: CuratorConfig,
    filename: str | None = DEFAULT_BIBTEX_FILENAME,
    overwrite: bool = False,
    export_mode: ExportMode = "auto",
) -> BibtexExportResult:
    """Export BibTeX into Curator's managed export directory."""

    return export_bibtex_file(
        zot=zot,
        item_keys=item_keys,
        bib_path=managed_export_path(cfg, filename, suffix=".bib"),
        overwrite=overwrite,
        cfg=cfg,
        export_mode=export_mode,
    )


def strip_latex_comments(text: str) -> str:
    """Remove unescaped LaTeX comments before citation scanning."""

    cleaned: list[str] = []
    for line in text.splitlines():
        cut_at: int | None = None
        for index, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                cut_at = index
                break
        cleaned.append(line[:cut_at] if cut_at is not None else line)
    return "\n".join(cleaned)


def skip_latex_whitespace(text: str, pos: int) -> int:
    """Return the next non-whitespace position."""

    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def skip_latex_optional_arguments(text: str, pos: int) -> int:
    """Skip simple LaTeX optional arguments after a cite command or cite group."""

    while True:
        pos = skip_latex_whitespace(text, pos)
        if pos >= len(text) or text[pos] != "[":
            return pos
        end = text.find("]", pos + 1)
        if end == -1:
            return pos
        pos = end + 1


def read_latex_braced_argument(text: str, pos: int) -> tuple[str | None, int]:
    """Read a simple braced LaTeX argument starting near pos."""

    pos = skip_latex_whitespace(text, pos)
    if pos >= len(text) or text[pos] != "{":
        return None, pos
    end = text.find("}", pos + 1)
    if end == -1:
        return None, pos
    return text[pos + 1 : end], end + 1


def append_latex_citation_keys(raw_keys: str, keys: list[str]) -> bool:
    """Append comma-separated citation keys and return whether nocite-all was present."""

    nocite_all = False
    for raw_key in raw_keys.split(","):
        key = raw_key.strip()
        if not key:
            continue
        if key == "*":
            nocite_all = True
            continue
        keys.append(key)
    return nocite_all


def extract_latex_citation_keys(latex_text: str) -> tuple[list[str], bool]:
    """Extract citation keys from common LaTeX, natbib, and biblatex cite commands."""

    cleaned = strip_latex_comments(latex_text)
    keys: list[str] = []
    nocite_all = False
    for match in _CITE_COMMAND_RE.finditer(cleaned):
        command = match.group("command").lower()
        is_multicite = command.endswith("s") and command != "nocite"
        pos = match.end()
        while True:
            pos = skip_latex_optional_arguments(cleaned, pos)
            raw_keys, next_pos = read_latex_braced_argument(cleaned, pos)
            if raw_keys is None:
                break
            nocite_all = append_latex_citation_keys(raw_keys, keys) or nocite_all
            pos = next_pos
            if not is_multicite:
                break
    return keys, nocite_all


def validate_latex_citations(latex_text: str, bibtex_text: str) -> CitationValidationReport:
    """Validate that all LaTeX citation keys exist in a BibTeX file."""

    citation_keys, nocite_all = extract_latex_citation_keys(latex_text)
    bibtex_keys = extract_bibtex_keys(bibtex_text)
    bibtex_key_set = set(bibtex_keys)
    citation_key_set = set(citation_keys)
    missing = [key for key in dict.fromkeys(citation_keys) if key not in bibtex_key_set]
    unused = [] if nocite_all else [key for key in bibtex_keys if key not in citation_key_set]
    return CitationValidationReport(
        citation_keys=list(dict.fromkeys(citation_keys)),
        bibtex_keys=bibtex_keys,
        missing_keys=missing,
        unused_bibtex_keys=unused,
        duplicate_bibtex_keys=duplicate_values(bibtex_keys),
        nocite_all=nocite_all,
    )


def format_bibtex_export_result(result: BibtexExportResult) -> str:
    """Format a BibTeX export result for an MCP or CLI response."""

    keys = "\n".join(f"- `{key}`" for key in result.citation_keys)
    metadata = result.exporter_metadata or {}
    used_bbt = bool(metadata.get("used_better_bibtex")) or result.exporter.startswith("Better Bib")
    lines = [
        "# BibTeX Export Complete",
        f"Wrote {len(result.item_keys)} item(s).",
        f"Exporter: {result.exporter}",
        f"Used Better BibTeX: {'yes' if used_bbt else 'no'}",
    ]
    bbt_info = metadata.get("better_bibtex")
    if bbt_info and isinstance(bbt_info, dict):
        lines.append(f"Better BibTeX version: {bbt_info.get('betterbibtex', 'unknown')}")
        lines.append(f"Zotero version: {bbt_info.get('zotero', 'unknown')}")
    if fallback_reason := metadata.get("better_bibtex_fallback_reason"):
        lines.append(f"Better BibTeX fallback reason: {fallback_reason}")
    if features := metadata.get("features_applied"):
        lines.append("")
        lines.append("## Better BibTeX behavior applied")
        lines.extend(f"- {feature}" for feature in features)
    lines.extend(
        [
            "",
            f"BibTeX file: `{result.bib_path}`",
            f"Citation key manifest: `{result.keys_path}`",
            f"LaTeX cite snippet: `{result.cite_path}`",
            "",
            "## Citation Keys",
            keys,
            "",
            "## LaTeX",
            "```latex",
            latex_cite_command(result.citation_keys),
            "```",
        ]
    )
    return "\n".join(lines)


def format_validation_report(report: CitationValidationReport) -> str:
    """Format a citation validation report."""

    lines = ["# Citation Validation", f"Status: {'OK' if report.ok else 'ERROR'}"]
    lines.append(f"Citation keys found in LaTeX: {len(report.citation_keys)}")
    lines.append(f"BibTeX entries found: {len(report.bibtex_keys)}")
    if report.nocite_all:
        lines.append("Detected `\\nocite{*}`; unused BibTeX entries are not reported.")
    if report.missing_keys:
        lines.append("")
        lines.append("## Missing citation keys")
        lines.extend(f"- `{key}`" for key in report.missing_keys)
    if report.duplicate_bibtex_keys:
        lines.append("")
        lines.append("## Duplicate BibTeX keys")
        lines.extend(f"- `{key}`" for key in report.duplicate_bibtex_keys)
    if report.unused_bibtex_keys:
        lines.append("")
        lines.append("## Unused BibTeX keys")
        lines.extend(f"- `{key}`" for key in report.unused_bibtex_keys)
    if report.ok:
        lines.append("")
        lines.append("All LaTeX citation keys are present in the BibTeX file.")
    return "\n".join(lines)
