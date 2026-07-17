from __future__ import annotations

from collections import defaultdict
from enum import Enum
from pathlib import Path
import json
import os
import re
import shutil
import sys
import subprocess
import threading
import time
import webbrowser
import zipfile
import xml.etree.ElementTree as ET
import tkinter as tk
import tkinter.filedialog as fd
from tkinter import messagebox, ttk
import customtkinter as ctk
from PIL import Image

import build_errors_warnings_report
import merge_master_xml
import make_html_statistics
import patch
import update_start_from_xml
from build_errors_warnings_report import _SHARED_PLACEHOLDER_JPEG

# Non-greedy inner; Creo files may contain multiple <DESCRIPTION> blocks — the first
# is sometimes legacy/comment junk; we pick the best candidate after cleaning.
DESCRIPTION_BLOCK_RE = re.compile(
    r"<DESCRIPTION>\s*(.*?)\s*</DESCRIPTION>",
    re.DOTALL | re.IGNORECASE,
)
XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Top-level Creo model filenames (same patterns as ``_scan_models_non_recursive``).
_CREO_MODEL_TOPLEVEL_RE = re.compile(r".*\.(prt|asm|drw)(\.\d+)?$", re.IGNORECASE)
_CREO_MODEL_EXT_PATTERNS: dict[str, str] = {
    "prt": r".*\.prt(\.\d+)?$",
    "asm": r".*\.asm(\.\d+)?$",
    "drw": r".*\.drw(\.\d+)?$",
}
_CREO_MODEL_EXTENSIONS_ALL = ("prt", "asm", "drw")
# Windows FindFirstFile-style globs — avoid listing every file in a large working folder.
_CREO_MODEL_GLOBS: dict[str, tuple[str, ...]] = {
    "prt": ("*.prt", "*.prt.*"),
    "asm": ("*.asm", "*.asm.*"),
    "drw": ("*.drw", "*.drw.*"),
}
_MODELCHECK_OUTPUT_GLOBS: tuple[str, ...] = (
    "*.p.xml",
    "*.a.xml",
    "*.d.xml",
    "*.p.html",
    "*.a.html",
    "*.d.html",
)
_JPEG_OUTPUT_GLOBS: tuple[str, ...] = ("*.jpg",)
_START_TEMPLATE_KINDS: tuple[tuple[str, str], ...] = (
    ("prt", "Part..."),
    ("asm", "Assembly..."),
    ("drw", "Drawing..."),
)
_START_TEMPLATE_DEST_NAMES: dict[str, str] = {
    "prt": "part_template.prt",
    "asm": "assembly_template.asm",
    "drw": "drawing_template.drw",
}
_START_TEMPLATE_XML_NAMES: dict[str, str] = {
    "prt": "part_template.p.xml",
    "asm": "assembly_template.a.xml",
    "drw": "drawing_template.d.xml",
}
_TEMPLATE_KIND_LABELS: dict[str, str] = {
    "prt": "part",
    "asm": "assembly",
    "drw": "drawing",
}
# ModelCHECK detail outputs under templates\ removed when Scan Templates finishes (Next >).
# Runner scripts (creo-batch-*.ps1) are removed separately — not via this suffix list.
_TEMPLATE_SCAN_DETAIL_SUFFIXES = (".html", ".js", ".png", ".css")

# Chunk .dxc files: working_dir / f"{base}-1.dxc", "-2.dxc", ...
CREO_BATCH_BASE = "creo-batch"  # legacy; new runs use task-specific bases below
BATCH_DXC_BASE_MODELCHECK = "modelcheck-batch"
BATCH_DXC_BASE_PART_THUMBNAILS = "part-thumbnails-batch"
BATCH_DXC_BASE_ASSEMBLY_THUMBNAILS = "assembly-thumbnails-batch"
BATCH_DXC_BASE_DRAWING_THUMBNAILS = "drawing-thumbnails-batch"
BATCH_DXC_BASE_SCAN_TEMPLATES = "scan-templates-batch"
BATCH_DXC_CHUNK_BASES = (
    CREO_BATCH_BASE,
    BATCH_DXC_BASE_MODELCHECK,
    BATCH_DXC_BASE_PART_THUMBNAILS,
    BATCH_DXC_BASE_ASSEMBLY_THUMBNAILS,
    BATCH_DXC_BASE_DRAWING_THUMBNAILS,
)


def _batch_dxc_base_for_task_kind(task_kind: str) -> str:
    """Unique .dxc filename prefix per batch task (avoids cross-phase progress races)."""
    return {
        "modelcheck": BATCH_DXC_BASE_MODELCHECK,
        "jpeg3d_part": BATCH_DXC_BASE_PART_THUMBNAILS,
        "jpeg3d_asm": BATCH_DXC_BASE_ASSEMBLY_THUMBNAILS,
        "jpeg2d": BATCH_DXC_BASE_DRAWING_THUMBNAILS,
        "jpeg3d": BATCH_DXC_BASE_PART_THUMBNAILS,
    }.get(task_kind, CREO_BATCH_BASE)
# Models per chunk in each .dxc (default 10). User can change via Settings → Batch settings...
CREO_BATCH_CHUNK_SIZE_DEFAULT = 10
CREO_BATCH_CHUNK_SIZE_MIN = 1
CREO_BATCH_CHUNK_SIZE_MAX = 100
# GO writes a task-specific driver next to the chunk .dxc files (legacy name cleaned on GO).
CREO_BATCH_RUNNER_LEGACY_BASENAME = "creo-batch-run.ps1"
CREO_BATCH_RUNNER_MODELCHECK_BASENAME = "creo-batch-modelcheck.ps1"
CREO_BATCH_RUNNER_JPEG_3D_BASENAME = "creo-batch-jpeg3d.ps1"
CREO_BATCH_RUNNER_JPEG_2D_BASENAME = "creo-batch-jpeg2d.ps1"
CREO_BATCH_RUNNER_SCAN_TEMPLATES_BASENAME = "creo-batch-scan-templates.ps1"
PURGE_CACHE_PS1_BASENAME = "purge_cache.ps1"
CREO_BATCH_RUNNER_BASENAMES = (
    CREO_BATCH_RUNNER_LEGACY_BASENAME,
    CREO_BATCH_RUNNER_MODELCHECK_BASENAME,
    CREO_BATCH_RUNNER_JPEG_3D_BASENAME,
    CREO_BATCH_RUNNER_JPEG_2D_BASENAME,
    CREO_BATCH_RUNNER_SCAN_TEMPLATES_BASENAME,
)
# Generated runner: max time to wait for the expected output files of one chunk, in seconds.
BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT = 120
BATCH_OUTPUT_WAIT_TIMEOUT_MIN = 60
# After all expected outputs for a chunk appear, brief settle when xtop already exited.
BATCH_OUTPUT_SETTLE_SEC = 5
# After kill.bat (end of chunk or pre-launch cleanup), pause before the next ptcdbatch launch.
BATCH_POST_KILL_SETTLE_SEC = 3
# xtop.exe: fixed wait for first appearance after ptcdbatch launch (XTOP NEVER STARTED).
BATCH_XTOP_START_WAIT_SEC = 60
# xtop.exe: after it exits mid-chunk, wait this long for a restart (XTOP GONE); Settings → Batch settings…
BATCH_XTOP_DEAD_CHECKS = 2
BATCH_XTOP_GONE_TIMEOUT_SEC_DEFAULT = 20
BATCH_XTOP_GONE_TIMEOUT_SEC_MIN = 5
# Wizard polls the batch folder until chunk .dxc files are gone (runner deletes them when done).
WIZARD_BATCH_DXC_POLL_MS = 3000
# Faster poll while a batch run is active (chunk .dxc remain or runner process alive).
WIZARD_BATCH_ACTIVE_POLL_MS = 800
# Re-check soon after the runner process exits (last chunk .dxc cleanup).
WIZARD_BATCH_RUNNER_EXIT_POLL_MS = 250
# Paint 100% before thumbnail chain only; ModelCHECK shows 100% immediately when runner + .dxc are done.
WIZARD_BATCH_FINISH_PAINT_MS = 0
WIZARD_BATCH_THUMBNAIL_PHASE_PAINT_MS = 600
# Automatic mode: keep batch-complete progress at 100% visible before advancing.
WIZARD_BATCH_AUTO_ADVANCE_HOLD_MS = 1500
# After the scan-templates runner exits, keep polling for template .xml before failing.
SCAN_BATCH_RUNNER_EXIT_GRACE_SEC = 15
BATCH_TIMEOUT_LOG_PREFIX = "creo-batch-timeouts-"
BATCH_STOP_FLAG_BASENAME = "creo-batch-stop.requested"
BATCH_PAUSE_FLAG_BASENAME = "creo-batch-pause.requested"
# Written by the runner only while it is actually held (safe gap); UI polls this.
BATCH_PAUSE_ACTIVE_BASENAME = "creo-batch-pause.active"
# Runner polls this often while paused (between chunks / before kill).
BATCH_PAUSE_POLL_MS = 1000
# Written by the generated runner when all chunks finish (works even when PowerShell -NoExit keeps the window open).
BATCH_RUN_COMPLETE_FLAG_SUFFIX = "-run.complete"
# After writing the stop flag, wait briefly for the runner to exit before force-killing.
BATCH_STOP_COOPERATIVE_WAIT_SEC = 2.0
# Modal dialogs: match wizard primary/secondary buttons (CTk default can look disabled/gray
# when a modal opens while the main window still shows Waiting… disabled buttons).
_DIALOG_BTN_PRIMARY_KW = {
    "fg_color": "#3B8ED0",
    "hover_color": "#36719F",
    "text_color": "#FFFFFF",
}
_DIALOG_BTN_SECONDARY_KW = {
    "fg_color": "#ECECEC",
    "hover_color": "#DDDDDD",
    "text_color": "#111111",
    "border_width": 1,
    "border_color": "#8F98A3",
}
_BATCH_TIMEOUT_LOG_HEADER = "Models timed out:"
_THUMBNAIL_PART_SUFFIX = ".part.jpg"
_THUMBNAIL_ASSEMBLY_SUFFIX = ".assembly.jpg"
_THUMBNAIL_MODEL_SUFFIX = ".model.jpg"  # legacy fallback
_THUMBNAIL_DRAWING_SUFFIX = ".drawing.jpg"
_WIZARD_THUMBNAILS_PHASE_PART = "jpeg3d_part"
_WIZARD_THUMBNAILS_PHASE_ASSEMBLY = "jpeg3d_asm"
_WIZARD_THUMBNAILS_PHASE_2D = "jpeg2d"
_WIZARD_THUMBNAILS_PHASE_ORDER = {
    _WIZARD_THUMBNAILS_PHASE_PART: 0,
    _WIZARD_THUMBNAILS_PHASE_ASSEMBLY: 1,
    _WIZARD_THUMBNAILS_PHASE_2D: 2,
}
_THUMBNAIL_JPEG_TASK_KINDS = frozenset(
    {"jpeg3d_part", "jpeg3d_asm", "jpeg2d", "jpeg3d"}
)
# Chunk ETA on ModelCHECK / JPEG 3D: show after this many chunks finish (depends on total).
WIZARD_BATCH_ETA_MIN_CHUNKS_DEFAULT = 2
WIZARD_BATCH_ETA_MIN_CHUNKS_SMALL = 1
WIZARD_BATCH_ETA_SMALL_BATCH_MAX_CHUNKS = 2
WIZARD_BATCH_ETA_ESTIMATING_SUFFIX = " · Estimating time…"


class FailedBatchGoChoice(Enum):
    """When a failure log lists models still missing output."""
    BATCH_ALL_PENDING = "batch_all_pending"
    FAILED_ONE_PER_MODEL = "failed_one_per_model"
    FAILED_NORMAL_CHUNK = "failed_normal_chunk"


WIZARD_AUTOMATIC_MODE_MESSAGE = (
    "Automatic Mode — runs each batch in sequence when the previous step finishes "
    "(Scan Templates → ModelCHECK → Thumbnails → Report)."
)
AUTOMATIC_MODE_DEFAULT = True
DEBUG_MODE_DEFAULT = False
SCAN_PARTS_DEFAULT = True
SCAN_ASSEMBLIES_DEFAULT = True
SCAN_DRAWINGS_DEFAULT = True
_RECENT_SCANS_MAX = 10
# When no Creo loadpoint / no .ttd list yet, File → New uses this default task (filename + UI label).
DEFAULT_MODELCHECK_TTD = "modelcheck.ttd"
DEFAULT_MODELCHECK_DISPLAY = "ModelCHECK"
JPEG_3D_DISPLAY = "Thumbnails"
SCAN_TEMPLATES_DISPLAY = "Scan Templates"
CREATE_REPORT_DISPLAY = "Create Report"
SCAN_TEMPLATES_DXC_BASENAME = "templates.dxc"
SCAN_TEMPLATES_CHUNK_SIZE = 1
JPEG_2D_PLOT_TTD = "plot_jpeg_a-size.ttd"
JPEG_2D_PLOT_DISPLAY = "JPEG 2D Export to file, A Paper Size"
JPEG_3D_TTD = "solid-raster_write_jpg.ttd"
TASK_COMBOBOX_FONT = ("Segoe UI", 11)
_START_OVER_REMOVE_DIR_NAMES = frozenset({"modchk", "templates"})
_START_OVER_FILE_SUFFIXES = frozenset(
    {
        ".ps1",
        ".dxc",
        ".xml",
        ".html",
        ".js",
        ".jpg",
        ".png",
        ".log",
        ".css",
        ".json",
        ".crc",
        ".txt",
        ".out",
        ".tmp",
    }
)
_REPORT_ZIP_FOLDER_NAME = "report"
_REPORT_ZIP_LAUNCHER_BASENAME = "Open Report.bat"
_REPORT_ZIP_EXTRA_DIRS = ("modchk", "templates")
_REPORT_ZIP_ASSET_SUFFIXES = frozenset(
    {".html", ".js", ".jpg", ".jpeg", ".png", ".css", ".gif", ".svg"}
)
_WINDOWS_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
WIZARD_STEP_SETUP = 0
WIZARD_STEP_SCAN = 1
WIZARD_STEP_MODELCHECK = 2
WIZARD_STEP_JPEG_3D = 3
WIZARD_STEP_REPORT = 4
WIZARD_STEP_COUNT = 5
WIZARD_STEPPER_LABELS = ("Setup", "Templates", "ModelCHECK", "Thumbnails", "Report")
WIZARD_STEPPER_FONT_SIZE = 14


def _creo_model_name_pattern(extensions: tuple[str, ...]) -> re.Pattern[str]:
    inner = "|".join(re.escape(ext) for ext in extensions)
    return re.compile(rf".*\.({inner})(\.\d+)?$", re.IGNORECASE)


def _app_bundle_dir() -> Path:
    """Sidecar files live beside main.exe (dev: beside main.py), not under PyInstaller _MEI temp."""
    if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _read_app_version() -> str:
    """App version string from the ``version`` file next to the executable / main.py."""
    try:
        text = (_app_bundle_dir() / "version").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text.splitlines()[0].strip() if text else ""


def _default_app_settings_path() -> Path:
    """``app_settings.json`` next to the app: only used to persist current form fields for the next run."""
    return _app_bundle_dir() / "app_settings.json"


def _safe_report_zip_stem(folder_name: str) -> str:
    """Filesystem-safe stem for ``{name}-report.zip`` from a working-directory folder name."""
    stem = _WINDOWS_INVALID_FILENAME_CHARS.sub("_", (folder_name or "").strip()).rstrip(". ")
    return stem or "report"


def _report_zip_basename(working_dir: Path) -> str:
    return f"{_safe_report_zip_stem(working_dir.name)}-report.zip"


def _is_report_zip_top_level_file(path: Path) -> bool:
    if path.name.casefold() == "statistics.html":
        return False
    if path.suffix.casefold() in _REPORT_ZIP_ASSET_SUFFIXES:
        return True
    return _CREO_MODEL_TOPLEVEL_RE.match(path.name) is not None


def _collect_report_zip_asset_paths(working_dir: Path) -> list[Path]:
    """Top-level report assets in ``working_dir`` (``index.html``, report siblings, Creo models)."""
    index_path = working_dir / "index.html"
    if not index_path.is_file():
        return []
    assets: list[Path] = []
    try:
        for entry in working_dir.iterdir():
            if not entry.is_file():
                continue
            if not _is_report_zip_top_level_file(entry):
                continue
            assets.append(entry)
    except OSError:
        return []
    if index_path not in assets:
        return []
    assets.sort(key=lambda p: p.name.casefold())
    return assets


def _collect_report_zip_dir_entries(working_dir: Path, dir_name: str) -> list[tuple[Path, str]]:
    """Files under ``working_dir/dir_name`` as ``(path, arcname under report/)``."""
    root = working_dir / dir_name
    if not root.is_dir():
        return []
    entries: list[tuple[Path, str]] = []
    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            entries.append((path, f"{dir_name}/{rel}"))
    except OSError:
        return []
    entries.sort(key=lambda item: item[1].casefold())
    return entries


def _open_report_bat_text() -> str:
    return '@echo off\r\nstart "" "%~dp0report\\index.html"\r\n'


def build_report_zip(working_dir: Path, zip_path: Path | None = None) -> Path:
    """Write ``{folder}-report.zip`` with ``report\\`` assets and ``Open Report.bat``."""
    working_dir = working_dir.expanduser().resolve()
    assets = _collect_report_zip_asset_paths(working_dir)
    if not assets:
        raise FileNotFoundError(f"index.html not found in:\n{working_dir}")
    if zip_path is None:
        zip_path = working_dir / _report_zip_basename(working_dir)
    else:
        zip_path = zip_path.expanduser().resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    report_prefix = f"{_REPORT_ZIP_FOLDER_NAME}/"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for asset in assets:
            zf.write(asset, arcname=report_prefix + asset.name)
        for dir_name in _REPORT_ZIP_EXTRA_DIRS:
            for path, rel_arc in _collect_report_zip_dir_entries(working_dir, dir_name):
                zf.write(path, arcname=report_prefix + rel_arc)
        zf.writestr(_REPORT_ZIP_LAUNCHER_BASENAME, _open_report_bat_text())
    return zip_path


def _normalize_chunk_size(value: object) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return CREO_BATCH_CHUNK_SIZE_DEFAULT
    return max(CREO_BATCH_CHUNK_SIZE_MIN, min(CREO_BATCH_CHUNK_SIZE_MAX, n))


def _batch_timeout_log_path(log_dir: Path, task_kind: str) -> Path:
    return log_dir / f"{BATCH_TIMEOUT_LOG_PREFIX}{task_kind}.txt"


def _resolve_batch_timeout_log_path(log_dir: Path, task_kind: str) -> Path | None:
    """Path to the failure log for a batch step (fixed name, then legacy timestamped name)."""
    if not log_dir.is_dir():
        return None
    fixed = _batch_timeout_log_path(log_dir, task_kind)
    if fixed.is_file():
        return fixed
    return _latest_legacy_batch_timeout_log(log_dir, task_kind)


def _creo_model_base_name(name: str) -> str:
    """``part.prt.2`` → ``part.prt``; ``part.p.xml`` → ``part.prt`` (no revision suffix)."""
    stripped = (name or "").strip()
    m = re.match(r"^(.*\.(?:prt|asm|drw))(?:\.\d+)?$", stripped, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m_xml = re.match(r"^(.*)\.(p|a|d)\.xml$", stripped, flags=re.IGNORECASE)
    if m_xml:
        letter = m_xml.group(2).lower()
        ext = {"p": "prt", "a": "asm", "d": "drw"}[letter]
        return f"{m_xml.group(1)}.{ext}"
    return stripped


def _modelcheck_expected_output_basenames(model_path: Path) -> list[str]:
    """ModelCHECK batch: XML plus HTML (``stem.p.xml`` and ``stem.p.html``, etc.)."""
    name = model_path.name
    m_ver = re.match(r"^(.*)\.(\d+)$", name)
    if m_ver:
        name = m_ver.group(1)
    m_ext = re.match(r"^(.*)\.(prt|asm|drw)$", name, flags=re.IGNORECASE)
    if not m_ext:
        return []
    stem, letter = m_ext.group(1), m_ext.group(2).lower()[0]
    return [f"{stem}.{letter}.xml", f"{stem}.{letter}.html"]


def _glob_toplevel_file_names(
    directory: Path, globs: tuple[str, ...]
) -> tuple[str, ...]:
    """Top-level file names matching ``globs`` only (not a full directory listing)."""
    names: list[str] = []
    seen: set[str] = set()
    for pattern in globs:
        try:
            for path in directory.glob(pattern):
                try:
                    if not path.is_file():
                        continue
                except OSError:
                    continue
                name = path.name
                if name in seen:
                    continue
                seen.add(name)
                names.append(name)
        except OSError:
            continue
    return tuple(names)


def _creo_model_globs(extensions: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for ext in extensions:
        out.extend(_CREO_MODEL_GLOBS.get(ext, ()))
    return tuple(out)


def _task_output_globs(task_kind: str) -> tuple[str, ...]:
    if task_kind == "modelcheck":
        return _MODELCHECK_OUTPUT_GLOBS
    if task_kind in ("jpeg3d_part", "jpeg3d_asm", "jpeg2d", "jpeg3d"):
        return _JPEG_OUTPUT_GLOBS
    return ()


def _directory_has_matching_file(
    directory: Path,
    pattern: re.Pattern[str],
    *,
    globs: tuple[str, ...] | None = None,
) -> bool:
    """True when any top-level file matches ``pattern`` (stops at the first hit)."""
    if globs:
        for name in _glob_toplevel_file_names(directory, globs):
            if pattern.match(name):
                return True
        return False
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False) and pattern.match(entry.name):
                    return True
    except OSError:
        return False
    return False


def _working_dir_has_output_basename(
    working_dir: Path,
    basename: str,
    *,
    names_cf: frozenset[str] | None = None,
) -> bool:
    """True when ``basename`` exists as a top-level file (case-insensitive name match)."""
    if not basename:
        return False
    if names_cf is not None:
        return basename.casefold() in names_cf
    if (working_dir / basename).is_file():
        return True
    # Windows paths are case-insensitive; avoid scanning huge folders per model.
    if sys.platform == "win32":
        return False
    key = basename.casefold()
    try:
        for entry in working_dir.iterdir():
            if entry.is_file() and entry.name.casefold() == key:
                return True
    except OSError:
        pass
    return False


def _parse_batch_timeout_log(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    models: list[str] = []
    seen: set[str] = set()
    past_header = False
    header_cf = _BATCH_TIMEOUT_LOG_HEADER.casefold()
    header_merged_re = re.compile(
        r"^Models timed out:\s*(.+)$", re.IGNORECASE
    )
    for line in text.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        if not past_header:
            if stripped.casefold() == header_cf:
                past_header = True
                continue
            merged = header_merged_re.match(stripped)
            if merged:
                past_header = True
                stripped = merged.group(1).strip()
                if not stripped:
                    continue
            else:
                continue
        base = _creo_model_base_name(stripped)
        key = base.casefold()
        if base and key not in seen:
            seen.add(key)
            models.append(base)
    return models


def _latest_legacy_batch_timeout_log(log_dir: Path, task_kind: str) -> Path | None:
    """Oldest runners used ``creo-batch-timeouts-{kind}-HHmmss.txt``."""
    if not log_dir.is_dir():
        return None
    prefix = f"{BATCH_TIMEOUT_LOG_PREFIX}{task_kind}-"
    candidates: list[Path] = []
    try:
        for path in log_dir.iterdir():
            if not path.is_file():
                continue
            name = path.name
            if not name.startswith(prefix) or not name.endswith(".txt"):
                continue
            candidates.append(path)
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _read_batch_failed_models(log_dir: Path, task_kind: str) -> list[str]:
    if not log_dir.is_dir():
        return []
    fixed = _batch_timeout_log_path(log_dir, task_kind)
    if fixed.is_file():
        models = _parse_batch_timeout_log(fixed)
        if models:
            return models
    legacy = _latest_legacy_batch_timeout_log(log_dir, task_kind)
    if legacy is None:
        return []
    return _parse_batch_timeout_log(legacy)


_JPEG_THUMBNAIL_FAILURE_TASK_KINDS = ("jpeg3d_part", "jpeg3d_asm", "jpeg2d", "jpeg3d")


def _read_jpeg_thumbnail_failed_models(log_dir: Path) -> list[str]:
    """Union of failed models from all thumbnail phase timeout logs (deduped, stable order)."""
    models: list[str] = []
    for kind in _JPEG_THUMBNAIL_FAILURE_TASK_KINDS:
        for model in _read_batch_failed_models(log_dir, kind):
            if model not in models:
                models.append(model)
    return models


def _append_batch_timeout_log_models(
    log_dir: Path, task_kind: str, model_names: list[str]
) -> None:
    """Append model base names to the timeout log (deduped); used for dialog skips and recovery."""
    if not model_names:
        return
    log_path = _batch_timeout_log_path(log_dir, task_kind)
    existing = {
        _creo_model_base_name(m).casefold()
        for m in _read_batch_failed_models(log_dir, task_kind)
    }
    to_add: list[str] = []
    for name in model_names:
        base = _creo_model_base_name(name)
        key = base.casefold()
        if base and key not in existing:
            existing.add(key)
            to_add.append(base)
    if not to_add:
        return
    header_lines = [
        f"Task: {task_kind}",
        f"Started: {time.strftime('%H:%M:%S')}",
        f"Log file: {log_path}",
        "",
        _BATCH_TIMEOUT_LOG_HEADER,
        "",
    ]
    body = "\n".join(to_add) + "\n"
    for attempt in range(8):
        try:
            if log_path.is_file():
                with log_path.open("rb") as fh:
                    raw = fh.read()
                prefix = b""
                if raw and raw[-1:] not in (b"\n", b"\r"):
                    prefix = b"\n"
                with log_path.open("ab") as fh:
                    if prefix:
                        fh.write(prefix)
                    fh.write(body.encode("utf-8"))
            else:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    "\n".join(header_lines) + "\n" + body,
                    encoding="utf-8",
                    newline="\n",
                )
            return
        except OSError:
            if attempt >= 7:
                return
            time.sleep(0.25)


def _is_batch_timeout_log_name(name: str) -> bool:
    n = name.casefold()
    return n.startswith(BATCH_TIMEOUT_LOG_PREFIX.casefold()) and n.endswith(".txt")


_START_OVER_BATCH_STATUS_EXACT_NAMES_CF = frozenset(
    name.casefold()
    for name in (
        BATCH_STOP_FLAG_BASENAME,
        BATCH_PAUSE_FLAG_BASENAME,
        BATCH_PAUSE_ACTIVE_BASENAME,
    )
)


def _is_start_over_batch_status_file(name: str) -> bool:
    """Batch runner flags, run-complete markers, and Creo ``.pvz`` status files."""
    n = name.casefold()
    if n in _START_OVER_BATCH_STATUS_EXACT_NAMES_CF:
        return True
    if n.endswith(BATCH_RUN_COMPLETE_FLAG_SUFFIX.casefold()):
        return True
    return n.endswith(".pvz")


def _remove_batch_status_files_in_directory(directory: Path) -> list[str]:
    """Remove batch status/flag files (Start over only); return unlink error lines."""
    errors: list[str] = []
    if not directory.is_dir():
        return errors
    try:
        for entry in directory.iterdir():
            if not entry.is_file() or not _is_start_over_batch_status_file(entry.name):
                continue
            try:
                entry.unlink()
            except OSError as exc:
                errors.append(f"{entry}\n{exc}")
    except OSError as exc:
        errors.append(f"{directory}\n{exc}")
    return errors


def _remove_batch_timeout_logs_in_directory(directory: Path) -> list[str]:
    """Remove ``creo-batch-timeouts-*.txt`` failure logs (Start over only); return unlink error lines."""
    errors: list[str] = []
    if not directory.is_dir():
        return errors
    try:
        for entry in directory.iterdir():
            if not entry.is_file() or not _is_batch_timeout_log_name(entry.name):
                continue
            try:
                entry.unlink()
            except OSError as exc:
                errors.append(f"{entry}\n{exc}")
    except OSError as exc:
        errors.append(f"{directory}\n{exc}")
    return errors


def _remove_batch_timeout_log_for_task(log_dir: Path, task_kind: str) -> None:
    """Remove one phase timeout log before a new batch run on that task."""
    path = _batch_timeout_log_path(log_dir, task_kind)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    legacy = _latest_legacy_batch_timeout_log(log_dir, task_kind)
    if legacy is not None and legacy.is_file() and legacy != path:
        try:
            legacy.unlink()
        except OSError:
            pass


def _paths_for_timed_out_candidates(
    latest_files: list[Path], candidates: list[str]
) -> list[Path]:
    by_base: dict[str, Path] = {}
    for path in latest_files:
        by_base[_creo_model_base_name(path.name).casefold()] = path
    result: list[Path] = []
    seen: set[str] = set()
    for name in candidates:
        key = _creo_model_base_name(name).casefold()
        if not key or key in seen:
            continue
        path = by_base.get(key)
        if path is not None:
            seen.add(key)
            result.append(path)
    return result


def _is_thumbnail_placeholder_name(name: str) -> bool:
    return name.casefold() == _SHARED_PLACEHOLDER_JPEG.casefold()


def _is_plain_batch_jpg_name(name: str) -> bool:
    """True for Creo batch ``stem.jpg`` outputs (not renamed thumbs or placeholder)."""
    low = name.casefold()
    if not low.endswith(".jpg"):
        return False
    if _is_thumbnail_placeholder_name(name):
        return False
    renamed_suffixes = (
        _THUMBNAIL_PART_SUFFIX,
        _THUMBNAIL_ASSEMBLY_SUFFIX,
        _THUMBNAIL_MODEL_SUFFIX,
        _THUMBNAIL_DRAWING_SUFFIX,
    )
    return not any(low.endswith(suffix) for suffix in renamed_suffixes)


def _rename_plain_jpgs_in_directory(directory: Path, *, middle: str) -> list[str]:
    """Rename each top-level plain ``*.jpg`` to ``*.{middle}.jpg`` (keeps placeholder)."""
    errors: list[str] = []
    if not directory.is_dir():
        return errors
    suffix = f".{middle}.jpg"
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        return [f"{directory}\n{exc}"]
    for entry in entries:
        if not entry.is_file() or not _is_plain_batch_jpg_name(entry.name):
            continue
        stem = entry.name[:-4]
        dest = directory / f"{stem}{suffix}"
        try:
            if dest.is_file():
                dest.unlink()
            entry.rename(dest)
        except OSError as exc:
            errors.append(f"{entry}\n{exc}")
    return errors


def _directory_has_thumbnail_suffix(directory: Path, middle: str) -> bool:
    marker = f".{middle}.jpg"
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.name.casefold().endswith(marker):
                return True
    except OSError:
        pass
    return False


def _jpeg_thumbnail_stem(model_name: str) -> str | None:
    m_ext = re.match(r"^(.*)\.(prt|asm|drw)(?:\.\d+)?$", model_name, flags=re.IGNORECASE)
    return m_ext.group(1) if m_ext else None


def _jpeg_model_extension(model_name: str) -> str | None:
    m_ext = re.match(r"^.*\.(prt|asm|drw)(?:\.\d+)?$", model_name, flags=re.IGNORECASE)
    return m_ext.group(1).lower() if m_ext else None


def _jpeg_output_candidates(model_name: str, task_kind: str) -> tuple[str, ...]:
    """Expected thumbnail basenames for a model/task (plain + renamed)."""
    stem = _jpeg_thumbnail_stem(model_name)
    if stem is None:
        return ()
    if task_kind == "jpeg3d_part":
        return (
            f"{stem}.jpg",
            f"{stem}{_THUMBNAIL_PART_SUFFIX}",
            f"{stem}{_THUMBNAIL_MODEL_SUFFIX}",
        )
    if task_kind == "jpeg3d_asm":
        return (
            f"{stem}.jpg",
            f"{stem}{_THUMBNAIL_ASSEMBLY_SUFFIX}",
            f"{stem}{_THUMBNAIL_MODEL_SUFFIX}",
        )
    if task_kind == "jpeg2d":
        return (f"{stem}.jpg", f"{stem}{_THUMBNAIL_DRAWING_SUFFIX}")
    if task_kind == "jpeg3d":
        ext = _jpeg_model_extension(model_name)
        if ext == "prt":
            return _jpeg_output_candidates(model_name, "jpeg3d_part")
        if ext == "asm":
            return _jpeg_output_candidates(model_name, "jpeg3d_asm")
    return ()


def _jpeg_part_output_exists(
    working_dir: Path,
    model_name: str,
    *,
    names_cf: frozenset[str] | None = None,
) -> bool:
    for name in _jpeg_output_candidates(model_name, "jpeg3d_part"):
        if _working_dir_has_output_basename(working_dir, name, names_cf=names_cf):
            return True
    return False


def _jpeg_assembly_output_exists(
    working_dir: Path,
    model_name: str,
    *,
    names_cf: frozenset[str] | None = None,
) -> bool:
    for name in _jpeg_output_candidates(model_name, "jpeg3d_asm"):
        if _working_dir_has_output_basename(working_dir, name, names_cf=names_cf):
            return True
    return False


def _jpeg_drawing_output_exists(
    working_dir: Path,
    model_name: str,
    *,
    names_cf: frozenset[str] | None = None,
) -> bool:
    for name in _jpeg_output_candidates(model_name, "jpeg2d"):
        if _working_dir_has_output_basename(working_dir, name, names_cf=names_cf):
            return True
    return False


def _jpeg_thumbnail_output_exists(
    working_dir: Path,
    model_name: str,
    task_kind: str,
    *,
    names_cf: frozenset[str] | None = None,
) -> bool:
    """True when the expected renamed thumbnail for this model/task exists."""
    if task_kind == "jpeg3d_part":
        return _jpeg_part_output_exists(working_dir, model_name, names_cf=names_cf)
    if task_kind == "jpeg3d_asm":
        return _jpeg_assembly_output_exists(working_dir, model_name, names_cf=names_cf)
    if task_kind == "jpeg2d":
        return _jpeg_drawing_output_exists(working_dir, model_name, names_cf=names_cf)
    if task_kind == "jpeg3d":
        ext = _jpeg_model_extension(model_name)
        if ext == "prt":
            return _jpeg_part_output_exists(working_dir, model_name, names_cf=names_cf)
        if ext == "asm":
            return _jpeg_assembly_output_exists(working_dir, model_name, names_cf=names_cf)
    return False


def _batch_eta_min_chunks_done(total_chunks: int) -> int:
    if total_chunks <= WIZARD_BATCH_ETA_SMALL_BATCH_MAX_CHUNKS:
        return WIZARD_BATCH_ETA_MIN_CHUNKS_SMALL
    return WIZARD_BATCH_ETA_MIN_CHUNKS_DEFAULT


def _format_batch_eta_remaining(seconds: float) -> str:
    total_minutes = max(1, int(round(max(0.0, seconds) / 60)))
    if total_minutes < 60:
        if total_minutes == 1:
            return "~1 min remaining"
        return f"~{total_minutes} min remaining"
    hours = total_minutes // 60
    mins = total_minutes % 60
    if mins == 0:
        hr = "1hr" if hours == 1 else f"{hours}hr"
        return f"~{hr} remaining"
    hr = "1hr" if hours == 1 else f"{hours}hr"
    return f"~{hr} {mins}min remaining"


def _batch_progress_eta_suffix(
    watch: dict[str, object],
    *,
    done: int,
    remaining: int,
    initial: int,
) -> str:
    step = watch.get("step")
    if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
        return ""
    if remaining <= 0 or initial <= 0:
        watch.pop("eta_at_done", None)
        watch.pop("eta_suffix", None)
        return ""
    if done <= 0 or done < _batch_eta_min_chunks_done(initial):
        watch.pop("eta_at_done", None)
        watch.pop("eta_suffix", None)
        return WIZARD_BATCH_ETA_ESTIMATING_SUFFIX
    cached_done = watch.get("eta_at_done")
    cached_suffix = watch.get("eta_suffix")
    if (
        isinstance(cached_done, int)
        and cached_done == done
        and isinstance(cached_suffix, str)
        and cached_suffix
    ):
        return cached_suffix
    started = watch.get("started_at")
    if not isinstance(started, (int, float)):
        return WIZARD_BATCH_ETA_ESTIMATING_SUFFIX
    elapsed = max(1.0, time.time() - float(started))
    eta_sec = (elapsed / done) * remaining
    suffix = " · " + _format_batch_eta_remaining(eta_sec)
    watch["eta_at_done"] = done
    watch["eta_suffix"] = suffix
    return suffix


def _normalize_output_timeout_sec(value: object) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT
    if n < BATCH_OUTPUT_WAIT_TIMEOUT_MIN:
        return BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT
    return n


def _normalize_xtop_gone_timeout_sec(value: object) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return BATCH_XTOP_GONE_TIMEOUT_SEC_DEFAULT
    if n < BATCH_XTOP_GONE_TIMEOUT_SEC_MIN:
        return BATCH_XTOP_GONE_TIMEOUT_SEC_DEFAULT
    return n


def _xtop_is_running() -> bool:
    """True when Creo ``xtop.exe`` is running (Windows)."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq xtop.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "xtop.exe" in (result.stdout or "").casefold()


def _normalize_xtop_timeout_sec(value: object) -> int:
    """Legacy key ``xtop_timeout_sec`` in app_settings.json."""
    return _normalize_xtop_gone_timeout_sec(value)


def _normalize_automatic_mode(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _normalize_scan_type_flag(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _filter_scan_extensions(
    extensions: tuple[str, ...],
    *,
    scan_parts: bool,
    scan_assemblies: bool,
    scan_drawings: bool,
) -> tuple[str, ...]:
    allowed: set[str] = set()
    if scan_parts:
        allowed.add("prt")
    if scan_assemblies:
        allowed.add("asm")
    if scan_drawings:
        allowed.add("drw")
    return tuple(ext for ext in extensions if ext in allowed)


def _normalize_recent_scans(value: object) -> list[str]:
    """Up to ``_RECENT_SCANS_MAX`` full working-directory paths (most recent first)."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        path = item.strip()
        if not path:
            continue
        key = path.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
        if len(out) >= _RECENT_SCANS_MAX:
            break
    return out


def _prepend_recent_scan(recent: list[str], working_dir: str) -> list[str]:
    path = working_dir.strip()
    if not path:
        return list(recent)
    key = path.casefold()
    rest = [p for p in recent if p.strip().casefold() != key]
    return [path, *rest[: _RECENT_SCANS_MAX - 1]]


def _format_recent_scan_menu_label(index: int, path: str, *, max_len: int = 52) -> str:
    """Menu label: ``1. C:/PTC/XMA3/.../Widget_Asm`` (full path when short enough)."""
    prefix = f"{index}. "
    trimmed = path.strip()
    if not trimmed:
        return prefix.rstrip()
    try:
        resolved = Path(trimmed).expanduser()
        folder = (resolved.name or trimmed).replace("\\", "/")
        display = str(resolved).replace("\\", "/")
    except (OSError, ValueError):
        folder = trimmed.replace("\\", "/")
        display = folder
    full = f"{prefix}{display}"
    if len(full) <= max_len:
        return full
    parts = [p for p in display.split("/") if p]
    if len(parts) >= 2 and len(parts[0]) == 2 and parts[0][1] == ":":
        start = "/".join(parts[: min(3, len(parts) - 1)])
    elif parts:
        start = parts[0]
    else:
        start = display[:12]
    middle = f"{start}/.../{folder}"
    candidate = f"{prefix}{middle}"
    if len(candidate) <= max_len:
        return candidate
    budget = max_len - len(prefix) - len("/.../") - len(folder)
    if budget < 4:
        return f"{prefix}.../{folder}"[:max_len]
    return f"{prefix}{start[:budget]}/.../{folder}"[:max_len]


def _canonical_app_settings(data: dict[str, object]) -> dict[str, object]:
    """Keys persisted in app_settings.json (task selection is not stored)."""
    out: dict[str, object] = {
        "working_directory": str(data.get("working_directory") or ""),
        "recent_scans": _normalize_recent_scans(data.get("recent_scans")),
        "creo_loadpoint": str(data.get("creo_loadpoint") or ""),
        "chunk_size": _normalize_chunk_size(
            data.get("chunk_size", CREO_BATCH_CHUNK_SIZE_DEFAULT)
        ),
        "output_timeout_sec": _normalize_output_timeout_sec(
            data.get("output_timeout_sec", BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT)
        ),
        "xtop_timeout_sec": _normalize_xtop_gone_timeout_sec(
            data.get("xtop_timeout_sec", BATCH_XTOP_GONE_TIMEOUT_SEC_DEFAULT)
        ),
        "automatic_mode": _normalize_automatic_mode(
            data.get("automatic_mode", AUTOMATIC_MODE_DEFAULT)
        ),
        "debug_mode": _normalize_automatic_mode(
            data.get("debug_mode", DEBUG_MODE_DEFAULT)
        ),
        "scan_parts": _normalize_scan_type_flag(
            data.get("scan_parts"), default=SCAN_PARTS_DEFAULT
        ),
        "scan_assemblies": _normalize_scan_type_flag(
            data.get("scan_assemblies"), default=SCAN_ASSEMBLIES_DEFAULT
        ),
        "scan_drawings": _normalize_scan_type_flag(
            data.get("scan_drawings"), default=SCAN_DRAWINGS_DEFAULT
        ),
    }
    if not (
        out["scan_parts"] or out["scan_assemblies"] or out["scan_drawings"]
    ):
        out["scan_parts"] = SCAN_PARTS_DEFAULT
        out["scan_assemblies"] = SCAN_ASSEMBLIES_DEFAULT
        out["scan_drawings"] = SCAN_DRAWINGS_DEFAULT
    return out


def _toplevel_effective_size(widget: tk.Misc) -> tuple[int, int]:
    """Best-effort width/height for CTk windows (often 1x1 until after first paint)."""
    widget.update_idletasks()
    return (
        max(widget.winfo_width(), widget.winfo_reqwidth()),
        max(widget.winfo_height(), widget.winfo_reqheight()),
    )


def _center_toplevel_on_parent(toplevel: tk.Misc, parent: tk.Misc) -> None:
    """Place *toplevel* centered over *parent* (call after widgets are laid out)."""
    toplevel.update_idletasks()
    parent.update_idletasks()
    tw, th = _toplevel_effective_size(toplevel)
    pw, ph = _toplevel_effective_size(parent)
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    x = px + max(0, (pw - tw) // 2)
    y = py + max(0, (ph - th) // 2)
    toplevel.geometry(f"+{x}+{y}")


def _schedule_center_toplevel_on_parent(toplevel: tk.Misc, parent: tk.Misc) -> None:
    """Center now and again after layout (CTk often reports 1x1 until first paint)."""

    def place() -> None:
        try:
            if toplevel.winfo_exists():
                _center_toplevel_on_parent(toplevel, parent)
        except tk.TclError:
            pass

    place()
    try:
        toplevel.after_idle(place)
        toplevel.after(50, place)
    except tk.TclError:
        pass


def _xml_attr_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )


def _dxc_path_str(path: Path) -> str:
    """Absolute path for Creo .dxc XML (forward slashes)."""
    return path.resolve().as_posix()


def _clean_templates_dir_scan_detail_files(templates_dir: Path) -> list[str]:
    """Remove ModelCHECK detail files from templates\\; keep Creo models, .xml, and runner .ps1."""
    errors: list[str] = []
    runner_names = {name.casefold() for name in CREO_BATCH_RUNNER_BASENAMES}
    try:
        if not templates_dir.is_dir():
            return errors
        for entry in templates_dir.iterdir():
            if not entry.is_file():
                continue
            if entry.name.casefold() in runner_names:
                continue
            if entry.name.casefold().endswith(_TEMPLATE_SCAN_DETAIL_SUFFIXES):
                try:
                    entry.unlink()
                except OSError as exc:
                    errors.append(f"{entry}\n{exc}")
    except OSError as exc:
        errors.append(f"{templates_dir}\n{exc}")
    return errors


def _sort_scan_template_models(paths: list[Path]) -> list[Path]:
    """Scan Templates order: part, then assembly, then drawing."""
    rank = {"prt": 0, "asm": 1, "drw": 2}

    def _key(path: Path) -> tuple[int, str]:
        match = re.search(r"\.(prt|asm|drw)(?:\.\d+)?$", path.name, flags=re.IGNORECASE)
        ext = match.group(1).lower() if match else ""
        return (rank.get(ext, 3), path.name.lower())

    return sorted(paths, key=_key)


# Not passed to Creo as <ConfigFile> (dev scripts, batch artifacts, etc.).
_MODELCHECK_CONFIG_SKIP_SUFFIXES = frozenset(
    {".ps1", ".bat", ".dxc", ".py", ".md", ".json", ".html", ".xml"}
)


def _creo_loadpoint_has_parametric_dir(loadpoint: str) -> bool:
    """True if ``loadpoint`` looks like a Creo install root (contains ``Parametric`` as a directory)."""
    s = (loadpoint or "").strip().rstrip("\\/")
    if not s:
        return False
    return (Path(s) / "Parametric").is_dir()


def _working_directory_exists_as_dir(working_directory: str) -> bool:
    """True if the path resolves to an existing directory (for Save / Report / settings file)."""
    s = (working_directory or "").strip()
    if not s:
        return False
    try:
        return Path(s).expanduser().resolve().is_dir()
    except OSError:
        return False


def _working_directory_ok_for_go(working_directory: str) -> bool:
    """Existing folder, or a missing leaf whose parent is an existing folder (GO will mkdir the leaf)."""
    s = (working_directory or "").strip()
    if not s:
        return False
    try:
        p = Path(s).expanduser()
        if p.is_dir():
            return True
        if p.exists():
            return False
        return p.parent.is_dir()
    except OSError:
        return False


def _path_contains_spaces(path: str) -> bool:
    """True if *path* contains whitespace (batch runner does not support spaced paths)."""
    return " " in (path or "").strip()


def _summary_report_inputs_ok(working_directory: str) -> bool:
    """True when ModelCHECK result XML exists and bundled report assets exist."""
    if not _working_directory_exists_as_dir(working_directory):
        return False
    try:
        wd = Path(working_directory.strip()).expanduser().resolve()
    except OSError:
        return False
    try:
        has_xml = False
        for entry in wd.iterdir():
            if not entry.is_file():
                continue
            low = entry.name.lower()
            if low.endswith((".p.xml", ".a.xml", ".d.xml")):
                has_xml = True
                break
        if not has_xml:
            return False
    except OSError:
        return False
    bundle = _app_bundle_dir()
    return (bundle / "model_checks.xml").is_file() and (bundle / "report_template.html.j2").is_file()


class CreoDistributedBatchMakerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self._install_dialog_parent()

        self.title("PDSVISION Cad Assessment Tool")
        self.geometry("584x460")
        self._wizard_step = WIZARD_STEP_SETUP
        self._wizard_step_outcome: dict[int, str] = {}
        self._wizard_step_failed_models: dict[int, list[str]] = {}
        self._wizard_thumbnails_part_phase_done = False
        self._wizard_thumbnails_assembly_phase_done = False
        self._wizard_thumbnails_drawing_phase_done = False
        self._wizard_thumbnails_go_phase: str | None = None
        self._wizard_thumbnails_go_phase_owned_by_on_go = False
        self._pending_template_sources: dict[str, Path] = {}
        self.resizable(False, False)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Keep a tiny PIL image around to establish Pillow usage
        # and provide an easy place to swap in a real icon later.
        self._placeholder_image = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        self._settings_path = _default_app_settings_path()
        # After Save As or Open: File → Save / Exit also update this path (same JSON as app_settings).
        self._paired_settings_json_path: Path | None = None
        self._config_dir = _app_bundle_dir() / "config"
        self._config_templates_dir = self._config_dir / "templates"
        self._chunk_size = CREO_BATCH_CHUNK_SIZE_DEFAULT
        self._output_timeout_sec = BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT
        self._xtop_gone_timeout_sec = BATCH_XTOP_GONE_TIMEOUT_SEC_DEFAULT
        self._automatic_mode = AUTOMATIC_MODE_DEFAULT
        self._automatic_mode_var = tk.BooleanVar(master=self, value=AUTOMATIC_MODE_DEFAULT)
        self._debug_mode = DEBUG_MODE_DEFAULT
        self._debug_mode_var = tk.BooleanVar(master=self, value=DEBUG_MODE_DEFAULT)
        self._scan_parts = SCAN_PARTS_DEFAULT
        self._scan_assemblies = SCAN_ASSEMBLIES_DEFAULT
        self._scan_drawings = SCAN_DRAWINGS_DEFAULT
        self._automatic_wizard_chain_job: str | None = None
        self._automatic_wizard_paused = False
        self._wizard_report_auto_create_done = False
        self._skip_timed_out_prompt_on_go = False
        self._session_failed_batch_go_choice: FailedBatchGoChoice | None = None
        self._go_in_progress = False
        self._recent_scans: list[str] = []
        self._file_menu_recent_scans_index: int | None = None
        self._configuration_menu: tk.Menu | None = None
        self._menubar: tk.Menu | None = None
        self._settings_options = [
            "Model Checks...",
            "Config.pro...",
            "Angles...",
            "GMC...",
            "Modelcheck Config...",
            "Start...",
            "Designers...",
            "Holes...",
            "Inch Settings...",
            "Metric Settings...",
            "Sheetmetal Thickness...",
            "View scales...",
            "Open configurations...",
        ]
        self._wizard_batch_failed_log_path: Path | None = None
        self._wizard_report_modelcheck_failed_log_path: Path | None = None
        self._wizard_report_thumbnails_failed_log_path: Path | None = None
        self._refresh_action_buttons_job: str | None = None
        self._activate_refresh_job: str | None = None
        self._post_batch_task_refresh_job: str | None = None
        self._wizard_batch_watch: dict[str, object] | None = None
        self._wizard_batch_watch_job: str | None = None
        self._wizard_batch_go_snapshot: dict[str, object] | None = None
        # Top-level listings keyed by resolved folder path (working dir, templates, …).
        self._wd_file_listing_cache: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {}
        self._wd_file_listing_lock = threading.Lock()
        self._wizard_batch_status_job: str | None = None
        self._wizard_batch_status_cache: dict[str, object] | None = None
        self._wizard_batch_status_gen = 0
        self._suppress_task_var_refresh = False
        self._batch_runner_process: subprocess.Popen | None = None
        self._last_create_report_available = False
        self._modal_dialog_depth = 0
        self._report_job_running = False
        self._report_processing_dialog: ctk.CTkToplevel | None = None
        self._report_processing_anim_job: str | None = None
        self._post_map_refresh_done = False
        self._suppress_settings_autosave = False
        self._settings_config_relative: dict[str, str] = {
            "Model Checks...": "templates/checks.mch",
            "Config.pro...": "config.pro",
            "Angles...": "angles.txt",
            "GMC...": "config.gmc",
            "Modelcheck Config...": "config_init.mc",
            "Start...": "start.mcs",
            "Designers...": "designers.txt",
            "Holes...": "holes.txt",
            "Inch Settings...": "inch.mcn",
            "Metric Settings...": "mm.mcn",
            "Sheetmetal Thickness...": "thick.txt",
            "View scales...": "view_scale.txt",
        }

        self._build_ui()
        self._build_menu_bar()
        # Load last saved app_settings.json after the window exists.
        self.after(0, self._load_settings)
        # CTkButton.configure(state=...) can be invoked during _load_settings before
        # the toplevel has been mapped, in which case the visual state does not
        # repaint until the user interacts. Force one more refresh once the window
        # is actually on screen so action buttons reflect the loaded settings.
        self.bind("<Map>", self._on_first_window_map, add="+")
        # Re-evaluate GO / Report when returning to this app
        # (e.g. batch runner deleted chunk .dxc, or files changed in Explorer).
        self.bind("<Activate>", self._on_app_activate, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _is_scan_templates_task(self, task_display: str) -> bool:
        return (task_display or "").strip() == SCAN_TEMPLATES_DISPLAY

    def _is_create_report_task(self, task_display: str) -> bool:
        return (task_display or "").strip() == CREATE_REPORT_DISPLAY

    def _is_modelcheck_task(self, task_display: str) -> bool:
        if self._is_scan_templates_task(task_display):
            return True
        filename = self._task_filename_from_ui(task_display)
        if not filename:
            return False
        return Path(filename).stem.lower() == "modelcheck"

    def _is_regular_modelcheck_task(self, task_display: str) -> bool:
        """ModelCHECK .ttd batch (not Scan Templates)."""
        return self._is_modelcheck_task(task_display) and not self._is_scan_templates_task(
            task_display
        )

    def _update_start_from_template_xml_if_present(self) -> tuple[bool, str, str]:
        """Refresh config\\start.mcs when template scan XML exists.

        Returns (ok, error_message, status_note). status_note is updated or skipped.
        """
        skipped = "Template extraction: skipped"
        updated = "Template extraction: updated"
        cleared = "Template extraction: cleared"
        error = "Template extraction: error"
        if self._wizard_step_outcome.get(WIZARD_STEP_SCAN) == "skipped":
            ok, err = self._clear_start_mcs()
            if not ok:
                return False, err, ""
            return True, "", cleared
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            return True, "", skipped
        templates_dir = Path(wd) / "templates"
        part_xml = templates_dir / "part_template.p.xml"
        asm_xml = templates_dir / "assembly_template.a.xml"
        drw_xml = templates_dir / "drawing_template.d.xml"
        part_path = part_xml if part_xml.is_file() and self._scan_parts else None
        asm_path = asm_xml if asm_xml.is_file() and self._scan_assemblies else None
        drw_path = drw_xml if drw_xml.is_file() and self._scan_drawings else None
        mcs_path = _app_bundle_dir() / "config" / "start.mcs"
        try:
            update_start_from_xml.update_start(
                mcs_path.resolve(),
                part_xml_path=part_path,
                asm_xml_path=asm_path,
                drw_xml_path=drw_path,
            )
        except (FileNotFoundError, OSError, ET.ParseError):
            return False, error, ""
        if not part_path and not asm_path and not drw_path:
            return True, "", cleared
        return True, "", updated

    def _clear_start_mcs(self) -> tuple[bool, str]:
        """Reset bundled ``config\\start.mcs`` template blocks (anchor lines only)."""
        mcs_path = (_app_bundle_dir() / "config" / "start.mcs").resolve()
        try:
            update_start_from_xml.clear_start_template_blocks(mcs_path)
        except (FileNotFoundError, OSError, ET.ParseError) as exc:
            return False, str(exc)
        return True, ""

    def _sync_start_for_modelcheck_go(self) -> tuple[bool, str, str]:
        """Apply template XML to start.mcs only after Scan Templates completed (not Skip)."""
        cleared = "Template extraction: cleared"
        if self._wizard_step_outcome.get(WIZARD_STEP_SCAN) != "done":
            ok, err = self._clear_start_mcs()
            if not ok:
                return False, err, ""
            return True, "", cleared
        return self._update_start_from_template_xml_if_present()

    def _apply_start_after_template_scan(self) -> None:
        """Merge template scan XML into start.mcs when Scan Templates batch completes."""
        ok, err, _note = self._update_start_from_template_xml_if_present()
        if not ok:
            messagebox.showwarning(
                "Scan Templates",
                "Could not update config\\start.mcs from template XML:\n\n" + err,
            )

    def _effective_ttd_filename(self, task_display: str) -> str:
        if self._is_scan_templates_task(task_display):
            return DEFAULT_MODELCHECK_TTD
        return self._task_filename_from_ui(task_display)

    def _modelcheck_config_dir_for_task(self, task_display: str) -> Path | None:
        if self._is_scan_templates_task(task_display):
            return self._config_templates_dir
        if self._is_modelcheck_task(task_display):
            return self._config_dir
        return None

    def _batch_dir_for_task(self, working_dir: Path, task_display: str) -> Path:
        if self._is_scan_templates_task(task_display):
            return working_dir / "templates"
        return working_dir

    def _batch_runner_basename_for_task(self, task_display: str) -> str:
        if self._is_scan_templates_task(task_display):
            return CREO_BATCH_RUNNER_SCAN_TEMPLATES_BASENAME
        if self._is_jpeg_2d_plot_task(task_display):
            return CREO_BATCH_RUNNER_JPEG_2D_BASENAME
        if self._is_jpeg_3d_task(task_display):
            return CREO_BATCH_RUNNER_JPEG_3D_BASENAME
        return CREO_BATCH_RUNNER_MODELCHECK_BASENAME

    def _templates_dir_has_creo_models(self, working_dir_str: str | None = None) -> bool:
        wd = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not wd:
            return False
        templates = Path(wd) / "templates"
        if templates.is_dir():
            if self._working_directory_has_creo_models(
                str(templates), extensions=self._enabled_scan_extensions()
            ):
                return True
        return bool(self._pending_template_sources)

    def _templates_dir_has_scan_xml(self, working_dir_str: str | None = None) -> bool:
        """True when a prior Scan Templates run left ModelCHECK XML in templates\\."""
        wd = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not wd:
            return False
        templates_dir = Path(wd) / "templates"
        if not templates_dir.is_dir():
            return False
        for kind in ("prt", "asm", "drw"):
            if not self._scan_kind_enabled(kind):
                continue
            xml_name = _START_TEMPLATE_XML_NAMES.get(kind)
            if xml_name and (templates_dir / xml_name).is_file():
                return True
        return False

    def _default_task_display(self, display_values: list[str]) -> str:
        if not display_values:
            return ""
        if self._templates_dir_has_scan_xml():
            modelcheck = self._task_display_for_ttd_filename(DEFAULT_MODELCHECK_TTD)
            if modelcheck and modelcheck in display_values:
                return modelcheck
        return display_values[0]

    def _drawing_thumbnails_applicable(self) -> bool:
        """True when the Creo loadpoint provides the JPEG 2D plot task (drawing thumbnails)."""
        return bool(self._task_display_for_ttd_filename(JPEG_2D_PLOT_TTD))

    def _invalidate_working_dir_file_cache(self) -> None:
        """Drop cached working-folder listings (call after GO, rename, or folder change)."""
        with self._wd_file_listing_lock:
            self._wd_file_listing_cache.clear()
        self._wizard_batch_status_cache = None
        self._wizard_batch_status_gen += 1

    def _working_dir_cache_key(self, working_dir: Path) -> str:
        try:
            return str(working_dir.expanduser().resolve())
        except OSError:
            return str(working_dir)

    def _working_dir_model_names(
        self, working_dir: Path, extensions: tuple[str, ...]
    ) -> tuple[str, ...]:
        """Top-level Creo model names for ``extensions`` only (glob, not full folder list)."""
        ext_key = ",".join(extensions)
        key = f"{self._working_dir_cache_key(working_dir)}|m|{ext_key}"
        with self._wd_file_listing_lock:
            cached = self._wd_file_listing_cache.get(key)
            if cached is not None:
                return cached[0]
        globs = _creo_model_globs(extensions)
        raw = _glob_toplevel_file_names(working_dir, globs)
        regexes = [
            re.compile(_CREO_MODEL_EXT_PATTERNS[ext], re.IGNORECASE)
            for ext in extensions
            if ext in _CREO_MODEL_EXT_PATTERNS
        ]
        names = tuple(
            name for name in raw if any(rx.match(name) for rx in regexes)
        )
        names_cf = frozenset(n.casefold() for n in names)
        with self._wd_file_listing_lock:
            self._wd_file_listing_cache[key] = (names, names_cf)
        return names

    def _working_dir_output_names_cf(
        self, working_dir: Path, task_kind: str
    ) -> frozenset[str]:
        """Basenames of expected outputs for ``task_kind`` only (glob, not full folder list)."""
        key = f"{self._working_dir_cache_key(working_dir)}|o|{task_kind}"
        with self._wd_file_listing_lock:
            cached = self._wd_file_listing_cache.get(key)
            if cached is not None:
                return cached[1]
        globs = _task_output_globs(task_kind)
        names = _glob_toplevel_file_names(working_dir, globs) if globs else ()
        names_cf = frozenset(n.casefold() for n in names)
        with self._wd_file_listing_lock:
            self._wd_file_listing_cache[key] = (names, names_cf)
        return names_cf

    def _working_directory_has_jpg_files(self, working_dir_str: str | None = None) -> bool:
        """True when at least one in-scope model has a thumbnail output on disk."""
        return self._working_directory_has_thumbnail_files(working_dir_str)

    def _working_directory_has_thumbnail_files(self, working_dir_str: str | None = None) -> bool:
        """True when any applicable thumbnail pass already has at least one output file."""
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s:
            return False
        try:
            d = Path(s).expanduser()
            if not d.is_dir():
                return False
        except OSError:
            return False
        for phase in (
            _WIZARD_THUMBNAILS_PHASE_PART,
            _WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
            _WIZARD_THUMBNAILS_PHASE_2D,
        ):
            if not self._wizard_thumbnails_phase_applicable(phase, s):
                continue
            extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
            if not extensions:
                continue
            latest = self._scan_models_non_recursive(d, extensions=extensions)
            paths = self._get_latest_model_files(latest)
            if not paths:
                continue
            pending = self._filter_models_missing_task_output(
                paths,
                d,
                self._wizard_thumbnails_phase_runner_task_kind(phase),
            )
            if len(pending) < len(paths):
                return True
        return False

    def _wizard_thumbnails_phase_applicable(
        self, phase: str, working_dir_str: str | None = None
    ) -> bool:
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            return self._wizard_thumbnails_needs_part_phase(working_dir_str)
        if phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            return self._wizard_thumbnails_needs_assembly_phase(working_dir_str)
        if phase == _WIZARD_THUMBNAILS_PHASE_2D:
            return (
                self._wizard_thumbnails_needs_drawing_phase(working_dir_str)
                and self._drawing_thumbnails_applicable()
            )
        return False

    def _working_directory_thumbnails_complete(self, working_dir_str: str | None = None) -> bool:
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s:
            return False
        try:
            d = Path(s).expanduser()
            if not d.is_dir():
                return False
        except OSError:
            return False
        any_applicable = False
        for phase in (
            _WIZARD_THUMBNAILS_PHASE_PART,
            _WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
            _WIZARD_THUMBNAILS_PHASE_2D,
        ):
            if not self._wizard_thumbnails_phase_applicable(phase, s):
                continue
            any_applicable = True
            if self._wizard_thumbnails_phase_has_pending(d, phase):
                return False
        return any_applicable

    def _wizard_thumbnails_phase_model_counts(
        self, working_dir: Path, phase: str
    ) -> tuple[int, int]:
        """Return (total models, pending models) for one thumbnail sub-phase."""
        wd_str = str(working_dir)
        if not self._wizard_thumbnails_phase_applicable(phase, wd_str):
            return 0, 0
        extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
        if not extensions:
            return 0, 0
        try:
            wd = working_dir.expanduser().resolve()
        except OSError:
            return 0, 0
        if not wd.is_dir():
            return 0, 0
        latest = self._scan_models_non_recursive(wd, extensions=extensions)
        paths = self._get_latest_model_files(latest)
        if not paths:
            return 0, 0
        pending = self._filter_models_missing_task_output(
            paths,
            wd,
            self._wizard_thumbnails_phase_runner_task_kind(phase),
        )
        return len(paths), len(pending)

    def _wizard_thumbnails_phase_has_models(self, phase: str) -> bool:
        """True when this thumbnail sub-phase has at least one in-scope model."""
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return False
        try:
            wd = Path(wd_str).expanduser().resolve()
            if not wd.is_dir():
                return False
        except OSError:
            return False
        total, _ = self._wizard_thumbnails_phase_model_counts(wd, phase)
        return total > 0

    def _wizard_thumbnails_phase_pending_are_known_failures(
        self, working_dir: Path, phase: str, pending: list[Path]
    ) -> bool:
        """True when every still-missing model for this pass is listed in its failure log."""
        if not pending:
            return True
        task_kind = self._wizard_thumbnails_phase_runner_task_kind(phase)
        logged = {
            _creo_model_base_name(m).casefold()
            for m in _read_batch_failed_models(working_dir, task_kind)
        }
        if not logged:
            return False
        for path in pending:
            if _creo_model_base_name(path.name).casefold() not in logged:
                return False
        return True

    def _wizard_thumbnails_phase_pending_paths(
        self, working_dir: Path, phase: str
    ) -> list[Path]:
        if not self._wizard_thumbnails_phase_applicable(phase, str(working_dir)):
            return []
        extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
        if not extensions:
            return []
        latest = self._scan_models_non_recursive(working_dir, extensions=extensions)
        paths = self._get_latest_model_files(latest)
        if not paths:
            return []
        return self._filter_models_missing_task_output(
            paths,
            working_dir,
            self._wizard_thumbnails_phase_runner_task_kind(phase),
        )

    def _wizard_thumbnails_phase_disk_progress(
        self, phase_key: str, title: str
    ) -> tuple[float, str] | None:
        """Progress for one thumbnail pass from files on disk (ignores session flags)."""
        short = self._wizard_thumbnails_phase_short_title(title)
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return None
        try:
            wd = Path(wd_str).expanduser().resolve()
            if not wd.is_dir():
                return None
        except OSError:
            return None
        if not self._wizard_thumbnails_phase_applicable(phase_key, wd_str):
            return None
        extensions = self._wizard_thumbnails_phase_scan_extensions(phase_key)
        if not extensions:
            return None
        latest = self._scan_models_non_recursive(wd, extensions=extensions)
        paths = self._get_latest_model_files(latest)
        total = len(paths)
        if total <= 0:
            return None
        pending = self._filter_models_missing_task_output(
            paths,
            wd,
            self._wizard_thumbnails_phase_runner_task_kind(phase_key),
        )
        pending_count = len(pending)
        if pending_count <= 0:
            return 1.0, f"{short} finished."
        # Pass already ran: remaining models are only recorded failures → show 100%.
        # Thumbnails > will show the failed-models dialog and retry them.
        if self._wizard_thumbnails_phase_pending_are_known_failures(
            wd, phase_key, pending
        ):
            return 1.0, f"{short} finished."
        done_count = total - pending_count
        if done_count > 0:
            models_word = "model" if total == 1 else "models"
            return (
                done_count / total,
                f"{short} — {done_count} of {total} {models_word} complete.",
            )
        return 0.0, f"{short} — waiting to start"

    def _sync_wizard_thumbnails_phase_done_from_disk(self) -> None:
        """Mark thumbnail sub-phases done when outputs already exist (prior run / skip path)."""
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return
        try:
            wd = Path(wd_str).expanduser()
            if not wd.is_dir():
                return
        except OSError:
            return
        if self._wizard_thumbnails_phase_applicable(_WIZARD_THUMBNAILS_PHASE_PART, wd_str):
            if not self._wizard_thumbnails_phase_has_pending(wd, _WIZARD_THUMBNAILS_PHASE_PART):
                self._wizard_thumbnails_part_phase_done = True
        if self._wizard_thumbnails_phase_applicable(_WIZARD_THUMBNAILS_PHASE_ASSEMBLY, wd_str):
            if not self._wizard_thumbnails_phase_has_pending(
                wd, _WIZARD_THUMBNAILS_PHASE_ASSEMBLY
            ):
                self._wizard_thumbnails_assembly_phase_done = True
        if self._wizard_thumbnails_phase_applicable(_WIZARD_THUMBNAILS_PHASE_2D, wd_str):
            if not self._wizard_thumbnails_phase_has_pending(wd, _WIZARD_THUMBNAILS_PHASE_2D):
                self._wizard_thumbnails_drawing_phase_done = True

    def _wizard_thumbnails_needs_part_phase(self, working_dir_str: str | None = None) -> bool:
        if not self._scan_parts:
            return False
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        return bool(s) and self._working_directory_has_creo_models(s, extensions=("prt",))

    def _wizard_thumbnails_needs_assembly_phase(self, working_dir_str: str | None = None) -> bool:
        if not self._scan_assemblies:
            return False
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        return bool(s) and self._working_directory_has_creo_models(s, extensions=("asm",))

    def _wizard_thumbnails_needs_drawing_phase(self, working_dir_str: str | None = None) -> bool:
        if not self._scan_drawings:
            return False
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        return bool(s) and self._working_directory_has_creo_models(s, extensions=("drw",))

    @staticmethod
    def _wizard_thumbnails_phase_runner_task_kind(phase: str) -> str:
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            return "jpeg3d_part"
        if phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            return "jpeg3d_asm"
        return "jpeg2d"

    def _wizard_thumbnails_phase_scan_extensions(self, phase: str) -> tuple[str, ...]:
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            base = ("prt",)
        elif phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            base = ("asm",)
        else:
            base = ("drw",)
        return _filter_scan_extensions(
            base,
            scan_parts=self._scan_parts,
            scan_assemblies=self._scan_assemblies,
            scan_drawings=self._scan_drawings,
        )

    @staticmethod
    def _wizard_thumbnails_phase_rename_middle(phase: str) -> str:
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            return "part"
        if phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            return "assembly"
        return "drawing"

    def _wizard_thumbnails_next_pending_phase(self, working_dir: Path) -> str | None:
        """First thumbnail sub-phase that still has models missing output."""
        wd_str = str(working_dir)
        if self._wizard_thumbnails_needs_part_phase(wd_str):
            extensions = self._wizard_thumbnails_phase_scan_extensions(
                _WIZARD_THUMBNAILS_PHASE_PART
            )
            if extensions:
                latest = self._scan_models_non_recursive(working_dir, extensions=extensions)
                paths = self._get_latest_model_files(latest)
                pending = self._filter_models_missing_task_output(
                    paths, working_dir, "jpeg3d_part"
                )
                if pending:
                    return _WIZARD_THUMBNAILS_PHASE_PART
        if self._wizard_thumbnails_needs_assembly_phase(wd_str):
            extensions = self._wizard_thumbnails_phase_scan_extensions(
                _WIZARD_THUMBNAILS_PHASE_ASSEMBLY
            )
            if extensions:
                latest = self._scan_models_non_recursive(working_dir, extensions=extensions)
                paths = self._get_latest_model_files(latest)
                pending = self._filter_models_missing_task_output(
                    paths, working_dir, "jpeg3d_asm"
                )
                if pending:
                    return _WIZARD_THUMBNAILS_PHASE_ASSEMBLY
        if self._wizard_thumbnails_needs_drawing_phase(wd_str) and self._drawing_thumbnails_applicable():
            extensions = self._wizard_thumbnails_phase_scan_extensions(
                _WIZARD_THUMBNAILS_PHASE_2D
            )
            if extensions:
                latest = self._scan_models_non_recursive(working_dir, extensions=extensions)
                paths = self._get_latest_model_files(latest)
                pending = self._filter_models_missing_task_output(
                    paths, working_dir, "jpeg2d"
                )
                if pending:
                    return _WIZARD_THUMBNAILS_PHASE_2D
        return None

    def _wizard_thumbnails_mark_phase_done(self, phase: str) -> None:
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            self._wizard_thumbnails_part_phase_done = True
        elif phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            self._wizard_thumbnails_assembly_phase_done = True
        elif phase == _WIZARD_THUMBNAILS_PHASE_2D:
            self._wizard_thumbnails_drawing_phase_done = True

    def _wizard_thumbnails_reset_phases_from(self, phase: str) -> None:
        """Clear session phase-done flag for the pass being (re)started."""
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            self._wizard_thumbnails_part_phase_done = False
        elif phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            self._wizard_thumbnails_assembly_phase_done = False
            self._wizard_thumbnails_drawing_phase_done = False
        elif phase == _WIZARD_THUMBNAILS_PHASE_2D:
            self._wizard_thumbnails_drawing_phase_done = False

    def _wizard_thumbnails_next_subphase_for_auto(
        self, *, after_phase: str | None = None
    ) -> str | None:
        """Next thumbnail pass with pending work.

        When ``after_phase`` is set (end of a finished pass), only consider passes
        **after** that one so leftover part failures do not restart the part pass
        and block assembly/drawing.
        """
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return None
        try:
            wd = Path(wd_str).expanduser().resolve()
            if not wd.is_dir():
                return None
        except OSError:
            return None
        min_order = -1
        if after_phase is not None:
            min_order = _WIZARD_THUMBNAILS_PHASE_ORDER.get(str(after_phase), -1)
        for phase in (
            _WIZARD_THUMBNAILS_PHASE_PART,
            _WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
            _WIZARD_THUMBNAILS_PHASE_2D,
        ):
            if _WIZARD_THUMBNAILS_PHASE_ORDER.get(phase, -1) <= min_order:
                continue
            if not self._wizard_thumbnails_phase_applicable(phase, wd_str):
                continue
            if self._wizard_thumbnails_phase_has_pending(wd, phase):
                return phase
        return None

    def _wizard_thumbnails_phase_is_done(self, phase: str) -> bool:
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            return self._wizard_thumbnails_part_phase_done
        if phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            return self._wizard_thumbnails_assembly_phase_done
        if phase == _WIZARD_THUMBNAILS_PHASE_2D:
            return self._wizard_thumbnails_drawing_phase_done
        return False

    def _wizard_thumbnails_phase_session_active(self, phase_key: str) -> bool:
        """True when a batch GO for this thumbnail sub-phase is running or finishing."""
        if self._wizard_thumbnails_phase_is_done(phase_key):
            return False
        if self._wizard_thumbnails_go_phase == phase_key:
            return True
        step = WIZARD_STEP_JPEG_3D
        if not self._wizard_batch_session_active_for_step(step):
            return False
        snap = self._wizard_batch_go_snapshot_for_step(step)
        if snap is not None and snap.get("thumbnails_phase") == phase_key:
            return True
        watch = self._wizard_batch_watch
        return (
            watch is not None
            and watch.get("step") == step
            and watch.get("thumbnails_phase") == phase_key
        )

    @staticmethod
    def _wizard_thumbnails_phase_short_title(title: str) -> str:
        short = title.split("(", 1)[0].strip()
        return short or title

    def _wizard_thumbnails_sync_active_phase_ui(self, phase: str) -> None:
        """Align thumbnail progress rows with the pass starting (part / assembly / drawing)."""
        if self._wizard_thumbnails_go_phase is None:
            self._wizard_thumbnails_go_phase = phase
            self._wizard_thumbnails_go_phase_owned_by_on_go = True
        snap = self._wizard_batch_go_snapshot_for_step(WIZARD_STEP_JPEG_3D)
        if snap is not None:
            snap["thumbnails_phase"] = phase
            snap["batch_dxc_base"] = _batch_dxc_base_for_task_kind(
                self._wizard_thumbnails_phase_runner_task_kind(phase)
            )
        self._refresh_wizard_step_batch_progress(WIZARD_STEP_JPEG_3D)
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def _wizard_thumbnails_watch_ready_unprocessed(self, step: int) -> bool:
        """True when the batch watcher sees a finished run but has not marked the phase done yet."""
        watch = self._wizard_batch_watch
        if watch is None or watch.get("step") != step:
            return False
        if not self._wizard_batch_outputs_ready(watch):
            return False
        phase = watch.get("thumbnails_phase", _WIZARD_THUMBNAILS_PHASE_PART)
        return not self._wizard_thumbnails_phase_is_done(str(phase))

    def _wizard_thumbnails_chain_next_subphase_auto(
        self, *, after_phase: str | None = None
    ) -> bool:
        """Start the next thumbnail sub-phase batch; skip empty passes. True if a batch started."""
        while True:
            next_phase = self._wizard_thumbnails_next_subphase_for_auto(
                after_phase=after_phase
            )
            if next_phase is None:
                return False
            if self._wizard_thumbnails_start_subphase_batch(next_phase):
                return True
            self._wizard_thumbnails_mark_phase_done(next_phase)
            after_phase = next_phase

    def _wizard_thumbnails_phase_has_pending(self, working_dir: Path, phase: str) -> bool:
        """True when models for one sub-phase still lack that phase's thumbnail output."""
        if phase == _WIZARD_THUMBNAILS_PHASE_2D and not self._drawing_thumbnails_applicable():
            return False
        extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
        if not extensions:
            return False
        latest = self._scan_models_non_recursive(working_dir, extensions=extensions)
        paths = self._get_latest_model_files(latest)
        pending = self._filter_models_missing_task_output(
            paths,
            working_dir,
            self._wizard_thumbnails_phase_runner_task_kind(phase),
        )
        return bool(pending)

    def _wizard_jpeg_2d_display(self) -> str:
        return (
            self._task_display_for_ttd_filename(JPEG_2D_PLOT_TTD)
            or JPEG_2D_PLOT_DISPLAY
        )

    def _working_directory_index_html_path(self, working_dir_str: str | None = None) -> Path | None:
        """Path to index.html in the working directory, or None if missing."""
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s:
            return None
        try:
            path = Path(s).expanduser() / "index.html"
            return path if path.is_file() else None
        except OSError:
            return None

    def _wizard_should_auto_create_report(self) -> bool:
        """Automatic mode: one auto Create Report per visit to the report step."""
        if self._wizard_report_auto_create_done:
            return False
        wd = (self.working_directory.get() or "").strip()
        return _summary_report_inputs_ok(wd)

    def _create_report_task_available(self, working_dir_str: str | None = None) -> bool:
        wd = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            return False
        return self._working_directory_has_modelcheck_xml(wd) and self._working_directory_has_jpg_files(
            wd
        )

    def _go_model_source_ready(self, working_dir_str: str, task_display: str) -> bool:
        if self._is_create_report_task(task_display):
            return False
        if self._is_scan_templates_task(task_display):
            return self._templates_dir_has_creo_models(working_dir_str)
        return self._working_directory_has_creo_models(
            working_dir_str,
            extensions=self._model_scan_extensions_for_task(task_display),
        )

    def _is_jpeg_3d_task(self, task_display: str) -> bool:
        display = (task_display or "").strip().casefold()
        if display == JPEG_3D_DISPLAY.casefold():
            return True
        filename = self._task_filename_from_ui(task_display)
        if not filename:
            return False
        if filename.lower() == JPEG_3D_TTD.lower():
            return True
        if "jpeg" in display and "3d" in display:
            return True
        stem = Path(filename).stem.casefold()
        return "jpeg" in stem and "3d" in stem

    def _is_jpeg_2d_plot_task(self, task_display: str) -> bool:
        filename = self._task_filename_from_ui(task_display)
        if not filename:
            return False
        return filename.lower() == JPEG_2D_PLOT_TTD.lower()

    def _is_jpeg_export_task(self, task_display: str) -> bool:
        return self._is_jpeg_3d_task(task_display) or self._is_jpeg_2d_plot_task(task_display)

    def _enabled_scan_extensions(self) -> tuple[str, ...]:
        return _filter_scan_extensions(
            _CREO_MODEL_EXTENSIONS_ALL,
            scan_parts=self._scan_parts,
            scan_assemblies=self._scan_assemblies,
            scan_drawings=self._scan_drawings,
        )

    def _enabled_scan_types_label(self) -> str:
        exts = self._enabled_scan_extensions()
        if not exts:
            return ".prt, .asm, or .drw"
        return "/".join(f".{ext}" for ext in exts)

    def _model_scan_extensions_for_task(self, task_display: str) -> tuple[str, ...]:
        if self._is_jpeg_2d_plot_task(task_display):
            task_exts: tuple[str, ...] = ("drw",)
        elif self._is_jpeg_3d_task(task_display):
            task_exts = ("prt", "asm")
        else:
            task_exts = _CREO_MODEL_EXTENSIONS_ALL
        return _filter_scan_extensions(
            task_exts,
            scan_parts=self._scan_parts,
            scan_assemblies=self._scan_assemblies,
            scan_drawings=self._scan_drawings,
        )

    def _model_scan_types_label(self, task_display: str) -> str:
        return "/".join(f".{ext}" for ext in self._model_scan_extensions_for_task(task_display))

    def _runner_task_kind(self, task_display: str) -> str:
        if self._is_modelcheck_task(task_display):
            return "modelcheck"
        if self._is_jpeg_2d_plot_task(task_display):
            return "jpeg2d"
        return "jpeg3d"

    def _task_filename_from_ui(self, task_display: str) -> str:
        key = (task_display or "").strip()
        fn = self._task_display_to_filename.get(key, "")
        if fn:
            return fn
        if key.casefold() == JPEG_3D_DISPLAY.casefold():
            for mapped_fn in self._task_display_to_filename.values():
                if (mapped_fn or "").lower() == JPEG_3D_TTD.lower():
                    return mapped_fn
            return JPEG_3D_TTD
        return ""

    def _task_display_for_ttd_filename(self, ttd_filename: str) -> str | None:
        want = (ttd_filename or "").strip().lower()
        if not want:
            return None
        for display, fn in self._task_display_to_filename.items():
            if (fn or "").strip().lower() == want:
                return display
        return None

    def _maybe_advance_to_create_report_task(self) -> None:
        """Refresh task metadata only; wizard steps advance via Next, one step at a time."""
        if not self._create_report_task_available():
            return
        self._update_create_report_task_list(advance_from_jpeg=False)

    def _update_create_report_task_list(self, *, advance_from_jpeg: bool = False) -> None:
        """Rebuild task maps when Create Report eligibility changes (no wizard auto-advance)."""
        available = self._create_report_task_available()
        if available == self._last_create_report_available:
            return
        self._last_create_report_available = available
        self._refresh_task_options()

    def _cancel_post_batch_task_refresh(self) -> None:
        jid = self._post_batch_task_refresh_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._post_batch_task_refresh_job = None

    def _schedule_post_batch_task_refresh(self) -> None:
        """Poll for new batch outputs so Create Report appears without restarting."""
        self._cancel_post_batch_task_refresh()
        poll_remaining = {"count": 120}

        def tick() -> None:
            self._post_batch_task_refresh_job = None
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            if self._modal_dialog_depth > 0:
                self._post_batch_task_refresh_job = self.after(1000, tick)
                return
            if self._batch_run_active_for_heavy_ui_polls():
                self._post_batch_task_refresh_job = self.after(3000, tick)
                return
            self._update_create_report_task_list(advance_from_jpeg=False)
            poll_remaining["count"] -= 1
            if poll_remaining["count"] <= 0 or self._create_report_task_available():
                return
            self._post_batch_task_refresh_job = self.after(3000, tick)

        self._post_batch_task_refresh_job = self.after(3000, tick)

    def _advance_task_after_open_batch(self, from_task_display: str) -> None:
        """Legacy hook; wizard advances only when the user clicks Next."""
        del from_task_display

    def _wizard_advance_one_step_after_batch(self) -> None:
        """Advance exactly one wizard step after the user clicks Next on a finished batch."""
        step = self._wizard_step
        if step == WIZARD_STEP_SCAN and self._wizard_scan_step_has_failed():
            return
        self._cancel_wizard_batch_output_watch()
        self._close_batch_runner_window()
        if step == WIZARD_STEP_SCAN:
            templates_dir = self._start_templates_dir()
            if templates_dir is not None and not self._debug_mode:
                cleanup_errors = _clean_templates_dir_scan_detail_files(templates_dir)
                if cleanup_errors:
                    messagebox.showwarning(
                        "Scan Templates",
                        "Some template detail files could not be removed:\n\n"
                        + "\n\n".join(cleanup_errors),
                    )
                self._remove_batch_runner_scripts(templates_dir)
            kinds: list[str] = []
            if templates_dir is not None:
                kinds = self._scanned_template_kind_labels(templates_dir)
            self._write_template_scan_session_for_working_dir("done", kinds)
            self._wizard_step_outcome[WIZARD_STEP_SCAN] = "done"
            self._set_wizard_step(WIZARD_STEP_MODELCHECK)
        elif step == WIZARD_STEP_MODELCHECK:
            self._wizard_step_outcome[WIZARD_STEP_MODELCHECK] = "done"
            self._set_wizard_step(WIZARD_STEP_JPEG_3D)
        elif step == WIZARD_STEP_JPEG_3D:
            self._wizard_step_outcome[WIZARD_STEP_JPEG_3D] = "done"
            self._set_wizard_step(WIZARD_STEP_REPORT)
            self._update_create_report_task_list(advance_from_jpeg=False)

    def _clean_description_inner(self, inner: str) -> str:
        """Remove XML comments and junk; collapse to a single display line."""
        text = inner
        # Strip <!-- ... --> repeatedly (handles nested/overlapping poorly; run until stable)
        for _ in range(20):
            new_text = XML_COMMENT_RE.sub("", text)
            if new_text == text:
                break
            text = new_text
        # Drop common Creo/comment artifacts left inside the tag
        text = re.sub(r"^[\s\-:>]+", "", text)
        text = re.sub(r"[\s\-:>]+$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _description_looks_usable(self, text: str) -> bool:
        if not text or len(text) > 200:
            return False
        if "-->" in text or "<!--" in text or text.strip().startswith("--"):
            return False
        if "<" in text or ">" in text:
            return False
        return True

    @staticmethod
    def _xml_local_name(tag: str) -> str:
        if tag.startswith("{"):
            return tag.split("}", 1)[-1]
        return tag

    def _description_from_ttd_element(self, ttd: ET.Element) -> str | None:
        """Creo .ttd files are XML: <TTD><DESCRIPTION>...</DESCRIPTION>...</TTD>."""
        for child in ttd:
            if self._xml_local_name(child.tag) != "DESCRIPTION":
                continue
            text = (child.text or "").strip()
            if text:
                return re.sub(r"\s+", " ", text)
        for el in ttd.iter():
            if self._xml_local_name(el.tag) == "DESCRIPTION":
                text = (el.text or "").strip()
                if text:
                    return re.sub(r"\s+", " ", text)
        return None

    def _read_ttd_description(self, ttd_path: Path) -> str:
        try:
            raw = ttd_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ttd_path.name

        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return self._read_ttd_description_regex_fallback(ttd_path, raw)

        ttd_el = root
        if self._xml_local_name(root.tag) != "TTD":
            ttd_el = next(
                (el for el in root.iter() if self._xml_local_name(el.tag) == "TTD"),
                root,
            )

        desc = self._description_from_ttd_element(ttd_el)
        if desc:
            return desc

        return self._read_ttd_description_regex_fallback(ttd_path, raw)

    def _read_ttd_description_regex_fallback(self, ttd_path: Path, raw: str) -> str:
        """Non-XML or unusual files: best-effort regex (may be noisy)."""
        blocks = DESCRIPTION_BLOCK_RE.findall(raw)
        if not blocks:
            return ttd_path.name

        cleaned = [self._clean_description_inner(b) for b in blocks]
        for c in cleaned:
            if self._description_looks_usable(c):
                return c
        for c in cleaned:
            if c:
                return c
        return ttd_path.name

    @staticmethod
    def _unique_task_labels(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """pairs: (filename, description). Returns (filename, unique dropdown label)."""
        desc_counts: dict[str, int] = {}
        for _fn, disp in pairs:
            desc_counts[disp] = desc_counts.get(disp, 0) + 1
        out: list[tuple[str, str]] = []
        for fn, disp in pairs:
            if desc_counts.get(disp, 0) > 1:
                label = f"{disp} ({fn})"
            else:
                label = disp
            out.append((fn, label))
        return out

    def _build_ttk_styles(self) -> None:
        # Popdown list is a separate Listbox; match closed-field font (ttk style alone does not).
        self.option_add("*TCombobox*Listbox*Font", TASK_COMBOBOX_FONT)
        style = ttk.Style(self)
        style.configure(
            "Task.TCombobox",
            fieldbackground="#FFFFFF",
            background="#D2D5DA",
            foreground="#1F1F1F",
            bordercolor="#8F98A3",
            lightcolor="#8F98A3",
            darkcolor="#8F98A3",
            arrowsize=14,
            padding=2,
            font=TASK_COMBOBOX_FONT,
        )

    def _timeout_task_step_label(self, task_kind: str) -> str:
        if task_kind == "modelcheck":
            return "ModelCHECK"
        if task_kind == "jpeg3d_part":
            return "Part thumbnails"
        if task_kind == "jpeg3d_asm":
            return "Assembly thumbnails"
        if task_kind == "jpeg2d":
            return "Drawing thumbnails (2D JPEG)"
        if task_kind == "jpeg3d":
            return "3D thumbnails"
        return task_kind

    def _model_still_missing_task_output(
        self,
        working_dir: Path,
        model_name: str,
        task_kind: str,
        *,
        names_cf: frozenset[str] | None = None,
    ) -> bool:
        model_path = working_dir / model_name
        if task_kind == "modelcheck":
            for out in _modelcheck_expected_output_basenames(model_path):
                if not _working_dir_has_output_basename(
                    working_dir, out, names_cf=names_cf
                ):
                    return True
            return False
        if task_kind in ("jpeg3d_part", "jpeg3d_asm", "jpeg2d", "jpeg3d"):
            return not _jpeg_thumbnail_output_exists(
                working_dir, model_name, task_kind, names_cf=names_cf
            )
        return True

    def _filter_models_missing_task_output(
        self,
        latest_files: list[Path],
        working_dir: Path,
        task_kind: str,
    ) -> list[Path]:
        """Models in the working folder that still lack this step's expected output."""
        if not latest_files:
            return []
        names_cf = self._working_dir_output_names_cf(working_dir, task_kind)
        return [
            p
            for p in latest_files
            if self._model_still_missing_task_output(
                working_dir,
                p.name,
                task_kind,
                names_cf=names_cf,
            )
        ]

    def _batch_paths_by_model_base(self, latest_files: list[Path]) -> dict[str, Path]:
        by_base: dict[str, Path] = {}
        for path in latest_files:
            by_base[_creo_model_base_name(path.name).casefold()] = path
        return by_base

    def _timed_out_models_still_in_batch(
        self,
        batch_dir: Path,
        task_kind: str,
        latest_files: list[Path],
        *,
        working_dir: Path,
    ) -> list[str]:
        logged = _read_batch_failed_models(batch_dir, task_kind)
        if not logged:
            return []
        batch_by_base = self._batch_paths_by_model_base(latest_files)
        names_cf = self._working_dir_output_names_cf(working_dir, task_kind)
        candidates: list[str] = []
        seen: set[str] = set()
        for logged_name in logged:
            base = _creo_model_base_name(logged_name).casefold()
            if base in seen or base not in batch_by_base:
                continue
            batch_path = batch_by_base[base]
            if not self._model_still_missing_task_output(
                working_dir,
                batch_path.name,
                task_kind,
                names_cf=names_cf,
            ):
                continue
            seen.add(base)
            candidates.append(_creo_model_base_name(logged_name))
        return candidates

    def _ask_failed_batch_go_choice(self, message: str) -> FailedBatchGoChoice | None:
        anchor = self
        dialog = ctk.CTkToplevel(anchor)
        dialog.withdraw()
        dialog.title("Failed models")
        dialog.resizable(False, False)
        dialog.transient(anchor)

        result: dict[str, FailedBatchGoChoice | None] = {"value": None}

        def close(choice: FailedBatchGoChoice | None) -> None:
            result["value"] = choice
            dialog.destroy()

        ctk.CTkLabel(dialog, text=message, justify="left", wraplength=440).pack(
            anchor="w", padx=16, pady=(16, 12)
        )
        btn_col = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_col.pack(anchor="e", padx=16, pady=(0, 16))
        buttons: list[ctk.CTkButton] = []
        for label, choice, primary in (
            ("Retry failed only (one model per batch)", FailedBatchGoChoice.FAILED_ONE_PER_MODEL, True),
            ("Retry failed only (normal chunking)", FailedBatchGoChoice.FAILED_NORMAL_CHUNK, False),
            ("Batch all still missing (normal chunking)", FailedBatchGoChoice.BATCH_ALL_PENDING, False),
        ):
            btn = self._mk_dialog_button(
                btn_col,
                text=label,
                width=280,
                primary=primary,
                command=lambda c=choice: close(c),
            )
            btn.pack(anchor="e", pady=(0, 6))
            buttons.append(btn)
        cancel_btn = self._mk_dialog_button(
            btn_col, text="Cancel", width=88, primary=False, command=lambda: close(None)
        )
        cancel_btn.pack(anchor="e", pady=(4, 0))
        buttons.append(cancel_btn)
        dialog.bind("<Escape>", lambda _e: close(None))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(None))

        self._run_modal_toplevel_wait(
            dialog, anchor=anchor, focus_widget=buttons[0], repaints=tuple(buttons)
        )
        return result["value"]

    def _clear_batch_failure_log_for_task(self, batch_dir: Path, task_kind: str) -> None:
        """Remove this phase's failure log before a new batch run (one task only)."""
        _remove_batch_timeout_log_for_task(batch_dir, task_kind)
        if task_kind == "modelcheck":
            self._wizard_step_failed_models.pop(WIZARD_STEP_MODELCHECK, None)

    def _clear_step_failure_logs(self, step: int, batch_dir: Path | None) -> None:
        """Clear timeout failure logs for a wizard batch step (e.g. after Stop)."""
        if batch_dir is None:
            return
        if step == WIZARD_STEP_MODELCHECK:
            self._clear_batch_failure_log_for_task(batch_dir, "modelcheck")
        elif step == WIZARD_STEP_JPEG_3D:
            for kind in _JPEG_THUMBNAIL_FAILURE_TASK_KINDS:
                self._clear_batch_failure_log_for_task(batch_dir, kind)

    def _resolve_batch_go_models(
        self,
        latest_files: list[Path],
        batch_dir: Path,
        working_dir: Path,
        task_kind: str,
    ) -> tuple[list[Path], bool, int | None, bool]:
        """Build model list and chunk override for GO.

        Returns (paths, continue_go, chunk_size_override, failed_retry).
        """
        silent = self._skip_timed_out_prompt_on_go
        if silent:
            self._skip_timed_out_prompt_on_go = False

        pending = self._filter_models_missing_task_output(
            latest_files, working_dir, task_kind
        )
        failed_candidates = self._timed_out_models_still_in_batch(
            batch_dir, task_kind, latest_files, working_dir=working_dir
        )

        if failed_candidates:
            choice: FailedBatchGoChoice | None = None
            if silent and self._session_failed_batch_go_choice is not None:
                choice = self._session_failed_batch_go_choice
            else:
                # Manual GO, or automatic with no remembered choice — always ask.
                silent = False
                step_label = self._timeout_task_step_label(task_kind)
                log_name = f"{BATCH_TIMEOUT_LOG_PREFIX}{task_kind}.txt"
                remember = ""
                if self._session_failed_batch_go_choice is not None:
                    remember = (
                        "\n\nYour last retry choice this session is remembered for "
                        "Automatic mode on later steps until you pick again here."
                    )
                message = (
                    f"The last {step_label} run recorded {len(failed_candidates)} failed "
                    f"model(s) still missing output ({len(pending)} total still need output).\n\n"
                    f"See {log_name} in the working folder for the full list.\n\n"
                    "Retry failed only (one model per batch) — one `.dxc` per failed model.\n"
                    "Retry failed only (normal chunking) — failed models only, using batch "
                    "chunk size from Settings.\n"
                    "Batch all still missing — every model without output, using batch chunk "
                    "size from Settings.\n\n"
                    "Cancel — do not start the batch."
                    f"{remember}"
                )
                choice = self._ask_failed_batch_go_choice(message)
            if choice is None:
                return pending, False, None, False
            self._session_failed_batch_go_choice = choice
            if choice == FailedBatchGoChoice.BATCH_ALL_PENDING:
                return pending, True, None, False
            retry_paths = _paths_for_timed_out_candidates(latest_files, failed_candidates)
            if not retry_paths:
                return [], False, None, False
            if choice == FailedBatchGoChoice.FAILED_ONE_PER_MODEL:
                return retry_paths, True, 1, True
            return retry_paths, True, None, True

        return pending, True, None, False

    def _run_modal_toplevel_wait(
        self,
        dialog: ctk.CTkToplevel,
        *,
        anchor: tk.Misc | None = None,
        focus_widget: tk.Misc | None = None,
        repaints: tuple[ctk.CTkButton, ...] = (),
    ) -> None:
        """Show a CTk dialog modally (grab, focus, wait) so it stays in front on Windows."""
        parent = anchor if anchor is not None else self

        self._modal_dialog_depth += 1
        try:
            dialog.update_idletasks()
            if not dialog.winfo_exists():
                return
            _schedule_center_toplevel_on_parent(dialog, parent)
            dialog.deiconify()
            if repaints:
                self._repaint_dialog_buttons(dialog, *repaints)
            try:
                dialog.attributes("-topmost", True)
                dialog.update_idletasks()
                dialog.lift()
                dialog.grab_set()
                if focus_widget is not None:
                    try:
                        if focus_widget.winfo_exists():
                            focus_widget.focus_set()
                    except tk.TclError:
                        dialog.focus_force()
                else:
                    dialog.focus_force()
            except tk.TclError:
                pass
            finally:
                try:
                    if dialog.winfo_exists():
                        dialog.attributes("-topmost", False)
                except tk.TclError:
                    pass
            _schedule_center_toplevel_on_parent(dialog, parent)
            dialog.wait_window()
        finally:
            try:
                if dialog.winfo_exists():
                    dialog.grab_release()
            except tk.TclError:
                pass
            self._modal_dialog_depth = max(0, self._modal_dialog_depth - 1)
            if parent is self:

                def _repaint_action_buttons() -> None:
                    try:
                        if self.winfo_exists():
                            self._refresh_action_buttons_run()
                            self.update_idletasks()
                    except tk.TclError:
                        pass

                self.after_idle(_repaint_action_buttons)

    def _set_wizard_go_button_busy(self, busy: bool) -> None:
        nxt = getattr(self, "wizard_next_button", None)
        if nxt is None:
            return
        if busy:
            try:
                nxt.configure(state="disabled")
            except tk.TclError:
                pass
            return
        self._refresh_wizard_footer()

    def _wizard_jpeg_3d_display(self) -> str:
        return JPEG_3D_DISPLAY

    def _wizard_modelcheck_display(self) -> str:
        return (
            self._task_display_for_ttd_filename(DEFAULT_MODELCHECK_TTD)
            or DEFAULT_MODELCHECK_DISPLAY
        )

    def _wizard_task_display_for_step(self, step: int) -> str:
        if step == WIZARD_STEP_SCAN:
            return SCAN_TEMPLATES_DISPLAY
        if step == WIZARD_STEP_MODELCHECK:
            return self._wizard_modelcheck_display()
        if step == WIZARD_STEP_JPEG_3D:
            return self._wizard_jpeg_3d_display()
        if step == WIZARD_STEP_REPORT:
            return CREATE_REPORT_DISPLAY
        return ""

    def _wizard_step_title(self, step: int) -> str:
        titles = {
            WIZARD_STEP_SETUP: "Setup",
            WIZARD_STEP_SCAN: "Scan Templates",
            WIZARD_STEP_MODELCHECK: self._wizard_modelcheck_display(),
            WIZARD_STEP_JPEG_3D: self._wizard_jpeg_3d_display(),
            WIZARD_STEP_REPORT: "Create Report",
        }
        return titles.get(step, "")

    def _wizard_step_intro(self, step: int) -> str:
        if step == WIZARD_STEP_SETUP:
            return (
                "Choose the working folder for your models and batch outputs, "
                "and your Creo loadpoint."
            )
        if step == WIZARD_STEP_SCAN:
            return (
                "Optional: upload templates for model types enabled in Scan settings, then run "
                "ModelCHECK on them to seed configs. Assembly and drawing rows appear when "
                ".asm or .drw files are in the working folder (or a template is already set). "
                "At least one template is required to scan."
            )
        if step == WIZARD_STEP_MODELCHECK:
            return (
                "Run ModelCHECK on models in the working directory. "
                "Outputs (XML, HTML, etc.) are written to the working folder."
            )
        if step == WIZARD_STEP_JPEG_3D:
            return (
                "Part thumbnails, then assembly thumbnails, then drawing thumbnails when .drw "
                "files are present. Each pass renames batch output to "
                "*.part.jpg, *.assembly.jpg, and *.drawing.jpg. Passes with no matching "
                "models are skipped."
            )
        if step == WIZARD_STEP_REPORT:
            return (
                "Build master.xml from ModelCHECK results and generate the Model Quality Report."
            )
        return ""

    def _wizard_setup_valid(self) -> bool:
        wd = (self.working_directory.get() or "").strip()
        lp = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        if not wd or not _working_directory_ok_for_go(wd):
            return False
        if _path_contains_spaces(wd):
            return False
        if not lp or not _creo_loadpoint_has_parametric_dir(lp):
            return False
        ptc = Path(lp) / "Parametric" / "bin" / "ptcdbatch.bat"
        kill = _app_bundle_dir() / "kill.bat"
        return ptc.is_file() and kill.is_file()

    def _scan_kind_enabled(self, kind: str) -> bool:
        if kind == "prt":
            return self._scan_parts
        if kind == "asm":
            return self._scan_assemblies
        if kind == "drw":
            return self._scan_drawings
        return True

    def _clear_template_artifacts_for_kind(self, kind: str) -> None:
        self._pending_template_sources.pop(kind, None)
        for path in self._template_scan_artifact_paths(kind):
            try:
                path.unlink()
            except OSError:
                pass

    def _clear_templates_for_disabled_scan_types(self) -> None:
        """Remove template picks and files for model types turned off in Scan settings."""
        changed = False
        for kind in ("prt", "asm", "drw"):
            if self._scan_kind_enabled(kind):
                continue
            if self._template_has_selection(kind):
                self._clear_template_artifacts_for_kind(kind)
                changed = True
        if changed:
            self._update_start_from_template_xml_if_present()

    def _template_dest_path(self, kind: str) -> Path | None:
        dest_dir = self._start_templates_dir()
        if dest_dir is None:
            return None
        dest_name = _START_TEMPLATE_DEST_NAMES.get(kind)
        if not dest_name:
            return None
        return dest_dir / dest_name

    def _template_is_set(self, kind: str) -> bool:
        dest = self._template_dest_path(kind)
        return dest is not None and dest.is_file()

    def _template_has_selection(self, kind: str) -> bool:
        return kind in self._pending_template_sources or self._template_is_set(kind)

    def _materialize_pending_templates(self) -> tuple[bool, str]:
        """Copy Browse selections into ``working_dir\\templates`` (Scan Templates GO only)."""
        if not self._pending_template_sources:
            return True, ""
        dest_dir = self._start_templates_dir()
        if dest_dir is None:
            return False, "Working directory is not set."
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"Could not create templates folder:\n{dest_dir.resolve()}\n\n{exc}"
        for kind, source in list(self._pending_template_sources.items()):
            if not self._scan_kind_enabled(kind):
                self._pending_template_sources.pop(kind, None)
                continue
            dest = self._template_dest_path(kind)
            if dest is None:
                continue
            try:
                shutil.copy2(source, dest)
            except OSError as exc:
                return (
                    False,
                    f"Could not copy template:\n{source}\n\n→\n\n{dest.resolve()}\n\n{exc}",
                )
            self._pending_template_sources.pop(kind, None)
        return True, ""

    def _wizard_template_kind_visible(self, kind: str) -> bool:
        """Show a template row only for enabled scan types; asm/drw when WD has that type or set."""
        if not self._scan_kind_enabled(kind):
            return False
        if kind == "prt":
            return True
        if self._template_has_selection(kind):
            return True
        if kind == "asm":
            return self._working_directory_has_creo_models(extensions=("asm",))
        if kind == "drw":
            return self._working_directory_has_creo_models(extensions=("drw",))
        return True

    def _refresh_wizard_template_row_visibility(self) -> None:
        rows = getattr(self, "_wizard_template_rows", None)
        if not rows:
            return
        for kind in ("prt", "asm", "drw"):
            row = rows.get(kind)
            if row is not None:
                row.pack_forget()
        for kind in ("prt", "asm", "drw"):
            row = rows.get(kind)
            if row is not None and self._wizard_template_kind_visible(kind):
                row.pack(fill="x", pady=3)

    def _template_stem_and_letter(self, kind: str) -> tuple[str, str] | None:
        dest_name = _START_TEMPLATE_DEST_NAMES.get(kind)
        if not dest_name:
            return None
        m = re.match(r"^(.*)\.(prt|asm|drw)$", dest_name, flags=re.IGNORECASE)
        if not m:
            return None
        return m.group(1), m.group(2).lower()[0]

    def _template_scan_artifact_paths(self, kind: str) -> list[Path]:
        """Model file and ModelCHECK outputs (xml, html, js) for one template kind."""
        info = self._template_stem_and_letter(kind)
        dest_dir = self._start_templates_dir()
        if info is None or dest_dir is None or not dest_dir.is_dir():
            return []
        stem, letter = info
        ext = {"p": "prt", "a": "asm", "d": "drw"}[letter]
        paths: list[Path] = []
        seen: set[Path] = set()

        def add(path: Path) -> None:
            resolved = path.resolve()
            if resolved not in seen and path.is_file():
                seen.add(resolved)
                paths.append(path)

        dest = dest_dir / _START_TEMPLATE_DEST_NAMES[kind]
        add(dest)
        xml_name = _START_TEMPLATE_XML_NAMES.get(kind)
        if xml_name:
            add(dest_dir / xml_name)
        rev_re = re.compile(rf"^{re.escape(stem)}\.{re.escape(ext)}\.\d+$", flags=re.IGNORECASE)
        html_re = re.compile(rf"^{re.escape(stem)}\.{re.escape(letter)}\.html$", flags=re.IGNORECASE)
        stem_fold = stem.casefold()
        try:
            for entry in dest_dir.iterdir():
                if not entry.is_file():
                    continue
                name = entry.name
                if rev_re.match(name) or html_re.match(name):
                    add(entry)
                    continue
                name_low = name.casefold()
                if name_low.endswith(".js") and name_low.startswith(stem_fold):
                    add(entry)
        except OSError:
            pass
        return paths

    def _on_wizard_clear_template(self, kind: str) -> None:
        if self._wizard_batch_waiting_on_step(WIZARD_STEP_SCAN):
            return
        had_pending = kind in self._pending_template_sources
        self._pending_template_sources.pop(kind, None)
        paths = self._template_scan_artifact_paths(kind)
        if not paths and not had_pending:
            return
        errors: list[str] = []
        for path in paths:
            try:
                path.unlink()
            except OSError as exc:
                errors.append(f"{path}\n{exc}")
        self._update_start_from_template_xml_if_present()
        self._refresh_task_options()
        self._refresh_wizard_template_status()
        self._refresh_wizard_footer()
        if errors:
            messagebox.showwarning(
                "Remove template",
                "Some files could not be removed:\n\n" + "\n\n".join(errors),
            )

    def _templates_upload_count(self) -> int:
        return sum(
            1
            for kind, _ in _START_TEMPLATE_KINDS
            if self._scan_kind_enabled(kind) and self._template_has_selection(kind)
        )

    def _discard_working_templates_on_skip(self) -> None:
        """Skip Scan Templates: no JSON; drop pending picks; remove folder unless scan XML exists."""
        self._pending_template_sources.clear()
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            return
        try:
            make_html_statistics.clear_template_scan_session(wd)
        except OSError:
            pass
        if self._templates_dir_has_scan_xml(wd):
            return
        templates_dir = Path(wd).expanduser() / "templates"
        if not templates_dir.is_dir():
            return
        try:
            shutil.rmtree(templates_dir)
        except OSError:
            pass

    def _prepare_wizard_scan_step_for_rescan(self) -> None:
        """Allow Scan Templates > again after the user returns from a later wizard step."""
        self._wizard_step_outcome.pop(WIZARD_STEP_SCAN, None)

    def _set_wizard_step(self, step: int) -> None:
        step = max(WIZARD_STEP_SETUP, min(WIZARD_STEP_COUNT - 1, step))
        prev = self._wizard_step
        if step != self._wizard_step:
            self._cancel_wizard_batch_output_watch()
        if step == WIZARD_STEP_SCAN and prev > WIZARD_STEP_SCAN:
            self._prepare_wizard_scan_step_for_rescan()
        sync_thumbs = False
        if step == WIZARD_STEP_JPEG_3D and prev != WIZARD_STEP_JPEG_3D:
            self._wizard_thumbnails_part_phase_done = False
            self._wizard_thumbnails_assembly_phase_done = False
            self._wizard_thumbnails_drawing_phase_done = False
            self._wizard_thumbnails_go_phase = None
            sync_thumbs = True
        if step == WIZARD_STEP_REPORT and prev != WIZARD_STEP_REPORT:
            self._wizard_report_auto_create_done = False
        self._wizard_step = step
        # Cheap task label on enter — do not scan for next pending thumbnail phase here.
        if step == WIZARD_STEP_JPEG_3D:
            task_display = self._wizard_jpeg_3d_display()
        else:
            task_display = self._wizard_task_display_for_step(step)
        self._suppress_task_var_refresh = True
        try:
            if task_display:
                self.task.set(task_display)
        finally:
            self._suppress_task_var_refresh = False
        self._refresh_configuration_menu()
        self._refresh_wizard_ui()
        if sync_thumbs:
            self._schedule_sync_wizard_thumbnails_phase_done_from_disk()

    def _schedule_sync_wizard_thumbnails_phase_done_from_disk(self) -> None:
        """Mark finished thumbnail passes off the UI thread (large folders)."""
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return
        try:
            wd = Path(wd_str).expanduser()
            if not wd.is_dir():
                return
        except OSError:
            return

        def work() -> None:
            try:
                part = False
                asm = False
                drawing = False
                if self._wizard_thumbnails_phase_applicable(
                    _WIZARD_THUMBNAILS_PHASE_PART, wd_str
                ):
                    part = not self._wizard_thumbnails_phase_has_pending(
                        wd, _WIZARD_THUMBNAILS_PHASE_PART
                    )
                if self._wizard_thumbnails_phase_applicable(
                    _WIZARD_THUMBNAILS_PHASE_ASSEMBLY, wd_str
                ):
                    asm = not self._wizard_thumbnails_phase_has_pending(
                        wd, _WIZARD_THUMBNAILS_PHASE_ASSEMBLY
                    )
                if self._wizard_thumbnails_phase_applicable(
                    _WIZARD_THUMBNAILS_PHASE_2D, wd_str
                ):
                    drawing = not self._wizard_thumbnails_phase_has_pending(
                        wd, _WIZARD_THUMBNAILS_PHASE_2D
                    )
            except OSError:
                return

            def apply() -> None:
                if self._wizard_step != WIZARD_STEP_JPEG_3D:
                    return
                self._wizard_thumbnails_part_phase_done = part
                self._wizard_thumbnails_assembly_phase_done = asm
                self._wizard_thumbnails_drawing_phase_done = drawing
                self._refresh_wizard_footer()

            try:
                self.after(0, apply)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _wizard_batch_go_snapshot_for_step(self, step: int) -> dict[str, object] | None:
        snap = self._wizard_batch_go_snapshot
        if snap is not None and snap.get("step") == step:
            return snap
        return None

    def _wizard_batch_dir_for_step(self, step: int) -> tuple[Path | None, bool]:
        """Batch folder and whether this step uses Scan Templates (templates.dxc)."""
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return None, False
        try:
            working_dir = Path(wd_str).expanduser().resolve()
        except OSError:
            return None, False
        task_display = self._wizard_task_display_for_step(step)
        if not task_display or self._is_create_report_task(task_display):
            return None, False
        scan_templates = self._is_scan_templates_task(task_display)
        batch_dir = self._batch_dir_for_task(working_dir, task_display)
        return batch_dir, scan_templates

    def _wizard_batch_dxc_context_for_step(self, step: int) -> tuple[Path | None, bool]:
        """Batch folder and scan-templates flag; prefer the active watch folder when set."""
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            batch_dir = watch.get("batch_dir")
            if isinstance(batch_dir, Path):
                return batch_dir, bool(watch.get("scan_templates"))
        return self._wizard_batch_dir_for_step(step)

    def _wizard_step_has_remaining_dxc(self, step: int) -> bool:
        batch_dir, scan_templates = self._wizard_batch_dxc_context_for_step(step)
        if batch_dir is None:
            return False
        base = self._batch_dxc_base_for_step(step)
        return self._batch_dxc_files_exist(batch_dir, scan_templates, base)

    @staticmethod
    def _watch_batch_dxc_base(watch: dict[str, object] | None) -> str:
        if watch is not None:
            base = watch.get("batch_dxc_base")
            if isinstance(base, str) and base:
                return base
        return CREO_BATCH_BASE

    def _batch_dxc_base_for_step(
        self, step: int, *, thumbnails_phase: str | None = None
    ) -> str:
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            return self._watch_batch_dxc_base(watch)
        snap = self._wizard_batch_go_snapshot_for_step(step)
        if snap is not None:
            base = snap.get("batch_dxc_base")
            if isinstance(base, str) and base:
                return base
        if step == WIZARD_STEP_MODELCHECK:
            return BATCH_DXC_BASE_MODELCHECK
        if step == WIZARD_STEP_JPEG_3D:
            phase = thumbnails_phase
            if phase is None and snap is not None:
                phase = snap.get("thumbnails_phase")
            if phase is None and watch is not None and watch.get("step") == step:
                phase = watch.get("thumbnails_phase")
            if isinstance(phase, str):
                return _batch_dxc_base_for_task_kind(
                    self._wizard_thumbnails_phase_runner_task_kind(phase)
                )
            return BATCH_DXC_BASE_PART_THUMBNAILS
        if step == WIZARD_STEP_SCAN:
            return BATCH_DXC_BASE_SCAN_TEMPLATES
        return CREO_BATCH_BASE

    @staticmethod
    def _any_batch_chunk_dxc_exist(batch_dir: Path, *, scan_templates: bool) -> bool:
        if scan_templates:
            return CreoDistributedBatchMakerApp._batch_dxc_files_exist(
                batch_dir, True
            )
        for base in BATCH_DXC_CHUNK_BASES:
            if CreoDistributedBatchMakerApp._batch_dxc_files_exist(
                batch_dir, False, base
            ):
                return True
        return False

    def _wizard_step_pending_models(self, step: int) -> list[Path]:
        """Models on this wizard step that still lack required output files."""
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return []
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return []
        try:
            working_dir = Path(wd_str).expanduser()
        except OSError:
            return []
        if not working_dir.is_dir():
            return []
        if step == WIZARD_STEP_JPEG_3D:
            pending: list[Path] = []
            for phase, kind in (
                (_WIZARD_THUMBNAILS_PHASE_PART, "jpeg3d_part"),
                (_WIZARD_THUMBNAILS_PHASE_ASSEMBLY, "jpeg3d_asm"),
                (_WIZARD_THUMBNAILS_PHASE_2D, "jpeg2d"),
            ):
                if kind == "jpeg2d" and not self._drawing_thumbnails_applicable():
                    continue
                extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
                if not extensions:
                    continue
                scanned = self._scan_models_non_recursive(working_dir, extensions=extensions)
                latest = self._get_latest_model_files(scanned)
                for path in self._filter_models_missing_task_output(
                    latest, working_dir, kind
                ):
                    if path not in pending:
                        pending.append(path)
            return pending
        task_display = self._wizard_task_display_for_step(step)
        if not task_display:
            return []
        latest = self._latest_models_for_task(working_dir, task_display)
        return self._filter_models_missing_task_output(
            latest, working_dir, self._runner_task_kind(task_display)
        )

    def _wizard_step_has_pending_outputs(self, step: int) -> bool:
        return bool(self._wizard_step_pending_models(step))

    def _wizard_batch_runner_finished_for_step(self, step: int) -> bool:
        """True when the latest batch run on this step finished (runner idle, .dxc gone)."""
        watch = self._wizard_batch_watch
        if watch is None or watch.get("step") != step:
            return False
        if self._wizard_batch_finish_pending(watch, step):
            return False
        return self._wizard_batch_pass_complete(watch)

    def _wizard_thumbnails_all_phases_attempted(self) -> bool:
        """True when each applicable thumbnail pass (part, assembly, drawing) has finished a batch run."""
        wd_str = (self.working_directory.get() or "").strip()
        if self._wizard_thumbnails_needs_part_phase(wd_str):
            if not self._wizard_thumbnails_part_phase_done:
                return False
        if self._wizard_thumbnails_needs_assembly_phase(wd_str):
            if not self._wizard_thumbnails_assembly_phase_done:
                return False
        if self._wizard_thumbnails_needs_drawing_phase(wd_str) and self._drawing_thumbnails_applicable():
            if not self._wizard_thumbnails_drawing_phase_done:
                return False
        return True

    def _wizard_batch_ready_for_auto_advance(self, step: int) -> bool:
        """Automatic mode: advance after this step's batch run finished (even if outputs remain)."""
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return False
        if not self._wizard_batch_session_active_for_step(step):
            return False
        watch = self._wizard_batch_watch
        if watch is None or watch.get("step") != step:
            return False
        if not watch.get("batch_post_ready_done"):
            return False
        if self._automatic_mode and not self._wizard_batch_auto_advance_hold_elapsed(watch):
            return False
        if not self._wizard_batch_pass_complete(watch):
            return False
        if step == WIZARD_STEP_JPEG_3D:
            if self._wizard_thumbnails_will_chain_after_batch(watch):
                return False
            if not self._wizard_thumbnails_all_phases_attempted():
                return False
        return True

    def _wizard_batch_compute_outputs_complete(self, step: int) -> bool:
        """True when ModelCHECK/Thumbnails required outputs exist (may scan once)."""
        if step == WIZARD_STEP_JPEG_3D:
            if self._wizard_step_has_pending_outputs(step):
                return False
            return self._working_directory_thumbnails_complete()
        if step == WIZARD_STEP_MODELCHECK:
            if self._wizard_step_has_pending_outputs(step):
                return False
            watch = self._wizard_batch_watch
            if watch is not None and watch.get("step") == step:
                return self._wizard_batch_outputs_ready(watch)
            return True
        return False

    def _wizard_batch_ready_for_next(self, step: int) -> bool:
        """True when this step's required outputs are complete and Next should show."""
        if self._wizard_step_has_remaining_dxc(step):
            return False
        if self._wizard_batch_waiting_on_step(step):
            return False
        if step == WIZARD_STEP_SCAN:
            watch = self._wizard_batch_watch
            if watch is not None and watch.get("step") == step:
                return self._wizard_batch_outputs_ready(watch)
            return False
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            wd = (self.working_directory.get() or "").strip()
            cache = self._wizard_batch_status_cache
            if (
                isinstance(cache, dict)
                and cache.get("step") == step
                and cache.get("wd") == wd
                and "outputs_complete" in cache
            ):
                return bool(cache.get("outputs_complete"))
            # Skip/idle: do not census every UI refresh. After a finished run, scan once and cache.
            if not (
                self._wizard_batch_runner_finished_for_step(step)
                or self._wizard_step_outcome.get(step) == "done"
            ):
                return False
            complete = self._wizard_batch_compute_outputs_complete(step)
            if not isinstance(cache, dict) or cache.get("step") != step or cache.get("wd") != wd:
                cache = {"step": step, "wd": wd}
            cache["outputs_complete"] = complete
            self._wizard_batch_status_cache = cache
            return complete
        return self._wizard_batch_step_already_complete(step)

    def _wizard_thumbnails_will_chain_after_batch(self, watch: dict[str, object]) -> bool:
        """True when the batch watcher will rename JPEGs and start the next thumbnail pass."""
        cached = watch.get("_will_chain")
        if isinstance(cached, bool):
            return cached
        if watch.get("step") != WIZARD_STEP_JPEG_3D:
            watch["_will_chain"] = False
            return False
        if not self._wizard_batch_outputs_ready(watch):
            return False
        phase = watch.get("thumbnails_phase", _WIZARD_THUMBNAILS_PHASE_PART)
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            watch["_will_chain"] = False
            return False
        try:
            wd = Path(wd_str).expanduser().resolve()
        except OSError:
            watch["_will_chain"] = False
            return False
        result = False
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            if self._wizard_thumbnails_phase_has_pending(wd, _WIZARD_THUMBNAILS_PHASE_ASSEMBLY):
                result = True
            elif self._wizard_thumbnails_phase_has_pending(wd, _WIZARD_THUMBNAILS_PHASE_2D):
                result = True
        elif phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            if self._wizard_thumbnails_phase_has_pending(wd, _WIZARD_THUMBNAILS_PHASE_2D):
                result = True
        watch["_will_chain"] = result
        return result

    def _wizard_thumbnails_batch_settling(self, watch: dict[str, object]) -> bool:
        """True after a thumbnail batch finishes but before rename / next pass / Next >."""
        if watch.get("step") != WIZARD_STEP_JPEG_3D:
            return False
        if not self._wizard_batch_outputs_ready(watch):
            return False
        # Hold the UI until post-ready rename/chain runs — no per-tick folder census.
        return bool(watch.get("batch_finish_painted")) and not bool(
            watch.get("batch_post_ready_done")
        )

    def _wizard_footer_next_enabled(self) -> bool:
        """True when the footer Next / step GO button would be enabled."""
        step = self._wizard_step
        if self._wizard_batch_waiting_on_step(step):
            return False
        if step == WIZARD_STEP_SETUP:
            return self._wizard_setup_valid()
        if step == WIZARD_STEP_SCAN:
            watch = self._wizard_batch_watch
            scan_failed = (
                watch is not None
                and watch.get("step") == WIZARD_STEP_SCAN
                and watch.get("scan_failed")
            )
            if scan_failed:
                return self._templates_upload_count() > 0 and self._go_fields_valid()
            if self._wizard_scan_show_next_after_batch(step):
                return True
            return self._templates_upload_count() > 0 and self._go_fields_valid()
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            if self._wizard_batch_ready_for_next(step):
                return True
            return self._go_fields_valid()
        if step == WIZARD_STEP_REPORT:
            wd = (self.working_directory.get() or "").strip()
            return _summary_report_inputs_ok(wd) and not self._report_job_running
        return False

    @staticmethod
    def _scan_templates_dxc_base(batch_dxc_base: str) -> str:
        if batch_dxc_base == CREO_BATCH_BASE:
            return BATCH_DXC_BASE_SCAN_TEMPLATES
        return batch_dxc_base

    @staticmethod
    def _batch_dxc_files_exist(
        batch_dir: Path,
        scan_templates: bool,
        batch_dxc_base: str = CREO_BATCH_BASE,
    ) -> bool:
        try:
            if scan_templates:
                base = CreoDistributedBatchMakerApp._scan_templates_dxc_base(
                    batch_dxc_base
                )
                if (batch_dir / SCAN_TEMPLATES_DXC_BASENAME).is_file():
                    return True
                return any(batch_dir.glob(f"{base}-*.dxc"))
            return any(batch_dir.glob(f"{batch_dxc_base}-*.dxc"))
        except OSError:
            return False

    @staticmethod
    def _batch_dxc_count(
        batch_dir: Path,
        scan_templates: bool,
        batch_dxc_base: str = CREO_BATCH_BASE,
    ) -> int:
        try:
            if scan_templates:
                base = CreoDistributedBatchMakerApp._scan_templates_dxc_base(
                    batch_dxc_base
                )
                count = len(list(batch_dir.glob(f"{base}-*.dxc")))
                if (batch_dir / SCAN_TEMPLATES_DXC_BASENAME).is_file():
                    count += 1
                return count
            return len(list(batch_dir.glob(f"{batch_dxc_base}-*.dxc")))
        except OSError:
            return 0

    def _batch_runner_process_alive(self) -> bool:
        proc = self._batch_runner_process
        return proc is not None and proc.poll() is None

    def _wizard_batch_session_active_for_step(self, step: int) -> bool:
        """True when this session started a batch on ``step`` (not leftover .dxc alone)."""
        if self._wizard_batch_go_snapshot_for_step(step) is not None:
            return True
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            return True
        if self._batch_runner_process_alive() and step == self._wizard_step:
            batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
            base = self._batch_dxc_base_for_step(step)
            if batch_dir is not None and self._batch_dxc_files_exist(
                batch_dir, scan_templates, base
            ):
                return True
        return False

    def _wizard_batch_in_progress_for_step(self, step: int) -> bool:
        """Active session batch on ``step`` with chunk .dxc files still present."""
        watch = self._wizard_batch_watch
        if (
            watch is not None
            and watch.get("step") == step
            and self._wizard_batch_pass_complete(watch)
            and watch.get("batch_finish_painted")
        ):
            return False
        if not self._wizard_batch_session_active_for_step(step):
            return False
        batch_dir, scan_templates = self._wizard_batch_dxc_context_for_step(step)
        if batch_dir is None:
            batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return False
        base = self._batch_dxc_base_for_step(step)
        return self._batch_dxc_files_exist(batch_dir, scan_templates, base)

    def _ensure_wizard_batch_watch(self, step: int) -> dict[str, object] | None:
        """Keep or recreate batch watch state while chunk .dxc files remain."""
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            return watch
        if not self._wizard_batch_session_active_for_step(step):
            return watch
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        base = self._batch_dxc_base_for_step(step)
        if batch_dir is None or not self._batch_dxc_files_exist(
            batch_dir, scan_templates, base
        ):
            return watch
        snap = self._wizard_batch_go_snapshot_for_step(step)
        remaining = self._batch_dxc_count(batch_dir, scan_templates, base)
        initial = remaining
        if snap is not None:
            snap_initial = snap.get("initial_dxc_count")
            if isinstance(snap_initial, int) and snap_initial > 0:
                initial = max(snap_initial, remaining)
        started = snap.get("started_at") if snap is not None else time.time()
        if not isinstance(started, (int, float)):
            started = time.time()
        batch_dxc_base = (
            snap.get("batch_dxc_base") if snap is not None else base
        )
        if not isinstance(batch_dxc_base, str) or not batch_dxc_base:
            batch_dxc_base = base
        watch = {
            "step": step,
            "batch_dir": batch_dir,
            "scan_templates": scan_templates,
            "batch_dxc_base": batch_dxc_base,
            "had_dxc": True,
            "initial_dxc_count": initial,
            "started_at": started,
            "thumbnails_phase": snap.get("thumbnails_phase") if snap is not None else None,
        }
        self._wizard_batch_watch = watch
        if self._wizard_batch_watch_job is None:
            self._wizard_batch_watch_job = self.after(
                0, self._tick_wizard_batch_output_watch
            )
        return watch

    def _restore_wizard_batch_watch_from_session(self, step: int) -> dict[str, object] | None:
        """Recreate batch watch after .dxc is gone but template XML is still pending."""
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            return watch
        if not self._wizard_batch_session_active_for_step(step):
            return watch
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return watch
        base = self._batch_dxc_base_for_step(step)
        if self._batch_dxc_files_exist(batch_dir, scan_templates, base):
            return self._ensure_wizard_batch_watch(step)
        snap = self._wizard_batch_go_snapshot_for_step(step)
        if snap is None:
            return watch
        started = snap.get("started_at")
        if not isinstance(started, (int, float)):
            started = time.time()
        initial = snap.get("initial_dxc_count")
        if not isinstance(initial, int) or initial <= 0:
            initial = 1
        batch_dxc_base = snap.get("batch_dxc_base")
        if not isinstance(batch_dxc_base, str) or not batch_dxc_base:
            batch_dxc_base = base
        watch = {
            "step": step,
            "batch_dir": batch_dir,
            "scan_templates": scan_templates,
            "batch_dxc_base": batch_dxc_base,
            "had_dxc": True,
            "initial_dxc_count": initial,
            "started_at": started,
            "thumbnails_phase": snap.get("thumbnails_phase"),
        }
        self._wizard_batch_watch = watch
        return watch

    def _clear_wizard_batch_go_snapshot(self, step: int | None = None) -> None:
        snap = self._wizard_batch_go_snapshot
        if snap is None:
            return
        if step is None or snap.get("step") == step:
            self._wizard_batch_go_snapshot = None

    @staticmethod
    def _batch_run_complete_flag_path(batch_dir: Path, batch_dxc_base: str) -> Path:
        return batch_dir / f"{batch_dxc_base}{BATCH_RUN_COMPLETE_FLAG_SUFFIX}"

    @staticmethod
    def _cleanup_batch_run_complete_flags(
        batch_dir: Path, *, batch_dxc_base: str | None = None
    ) -> None:
        try:
            if not batch_dir.is_dir():
                return
            bases = (
                [batch_dxc_base]
                if batch_dxc_base
                else list(BATCH_DXC_CHUNK_BASES)
            )
            for base in bases:
                flag = batch_dir / f"{base}{BATCH_RUN_COMPLETE_FLAG_SUFFIX}"
                if flag.is_file():
                    flag.unlink()
        except OSError:
            pass

    def _batch_run_active_for_heavy_ui_polls(self) -> bool:
        """True while a ModelCHECK or thumbnails batch is in progress (skip full-folder scans)."""
        return self._wizard_batch_waiting_on_step(WIZARD_STEP_MODELCHECK) or (
            self._wizard_batch_waiting_on_step(WIZARD_STEP_JPEG_3D)
        )

    def _wizard_batch_cache_thumbnail_phase_flags(
        self,
        watch: dict[str, object],
        *,
        working_dir_str: str,
        drawing_task_ok: bool,
    ) -> None:
        """Store which thumbnail progress rows apply (fixed for this GO; no per-tick iterdir)."""
        watch["thumbnails_show_part"] = bool(
            working_dir_str and self._wizard_thumbnails_needs_part_phase(working_dir_str)
        )
        watch["thumbnails_show_asm"] = bool(
            working_dir_str
            and self._wizard_thumbnails_needs_assembly_phase(working_dir_str)
        )
        watch["thumbnails_show_drawing"] = bool(
            working_dir_str
            and drawing_task_ok
            and self._wizard_thumbnails_needs_drawing_phase(working_dir_str)
        )

    def _wizard_batch_sync_progress_snapshot(self, watch: dict[str, object]) -> None:
        """One chunk .dxc glob and pass-complete check per UI tick (shared by progress UI)."""
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return
        scan_templates = bool(watch.get("scan_templates"))
        batch_dxc_base = self._watch_batch_dxc_base(watch)
        pass_complete = bool(watch.get("batch_chunks_complete")) or self._wizard_batch_pass_complete(
            watch
        )
        if pass_complete:
            remaining = 0
        else:
            remaining = self._batch_dxc_count(batch_dir, scan_templates, batch_dxc_base)
        watch["_progress_pass_complete"] = pass_complete
        watch["_progress_remaining_dxc"] = remaining

    def _wizard_batch_runner_idle(self, watch: dict[str, object]) -> bool:
        """True when the batch runner script finished (process exited or run-complete flag)."""
        batch_dir = watch.get("batch_dir")
        if isinstance(batch_dir, Path):
            base = self._watch_batch_dxc_base(watch)
            if self._batch_run_complete_flag_path(batch_dir, base).is_file():
                watch["runner_exit_polled"] = True
                return True
            # Scan Templates + Debug (-NoExit): chunks and template XML can be done
            # while the PowerShell window is still open — treat as idle so Next > appears.
            if bool(watch.get("scan_templates")) and self._wizard_scan_outputs_complete(
                batch_dir
            ):
                if not self._batch_dxc_files_exist(batch_dir, True, base):
                    watch["runner_exit_polled"] = True
                    return True
        proc = self._batch_runner_process
        if proc is None:
            return bool(watch.get("runner_exit_polled"))
        if proc.poll() is not None:
            watch["runner_exit_polled"] = True
            return True
        return False

    def _wizard_batch_pass_complete(self, watch: dict[str, object]) -> bool:
        """True when runner finished and every chunk .dxc for this pass is gone."""
        if not watch.get("had_dxc"):
            return False
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return False
        scan_templates = bool(watch.get("scan_templates"))
        batch_dxc_base = self._watch_batch_dxc_base(watch)
        if self._batch_dxc_files_exist(batch_dir, scan_templates, batch_dxc_base):
            if (
                not scan_templates
                and self._wizard_batch_runner_idle(watch)
                and not watch.get("orphan_dxc_cleaned")
            ):
                self._wizard_batch_cleanup_orphan_dxc_after_runner(watch)
                if not self._batch_dxc_files_exist(batch_dir, scan_templates, batch_dxc_base):
                    return True
            return False
        if scan_templates:
            return self._wizard_batch_runner_idle(watch) and self._wizard_scan_outputs_complete(
                batch_dir
            )
        return self._wizard_batch_runner_idle(watch)

    def _wizard_batch_runner_session_finished(self, watch: dict[str, object]) -> bool:
        """Alias for pass complete (runner idle + no chunk .dxc)."""
        return self._wizard_batch_pass_complete(watch)

    def _wizard_batch_finish_pending(self, watch: dict[str, object], step: int) -> bool:
        """True while 100% must stay visible before rename / chain / auto-advance."""
        if not self._wizard_batch_pass_complete(watch):
            return False
        if not watch.get("batch_finish_painted"):
            return True
        if not watch.get("batch_post_ready_done"):
            return True
        if (
            self._automatic_mode
            and watch.get("batch_complete_shown_at") is not None
            and not self._wizard_batch_auto_advance_hold_elapsed(watch)
        ):
            return True
        if step == WIZARD_STEP_JPEG_3D and self._wizard_thumbnails_batch_settling(watch):
            return True
        return False

    def _wizard_batch_paint_pass_complete(self, watch: dict[str, object]) -> None:
        """Paint 100% immediately when runner finished and chunk .dxc files are gone."""
        if watch.get("batch_finish_painted"):
            return
        watch["batch_finish_painted"] = True
        watch["batch_chunks_complete"] = True
        step = watch.get("step")
        if isinstance(step, int):
            if self._automatic_mode and step in (
                WIZARD_STEP_SCAN,
                WIZARD_STEP_MODELCHECK,
                WIZARD_STEP_JPEG_3D,
            ):
                will_chain = (
                    step == WIZARD_STEP_JPEG_3D
                    and self._wizard_thumbnails_will_chain_after_batch(watch)
                )
                if not will_chain:
                    self._wizard_batch_mark_complete_for_auto_advance(watch)
            self._refresh_wizard_step_batch_progress(step)
            try:
                self.update_idletasks()
            except tk.TclError:
                pass

    def _wizard_batch_cleanup_orphan_dxc_after_runner(self, watch: dict[str, object]) -> None:
        if watch.get("orphan_dxc_cleaned"):
            return
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path) or bool(watch.get("scan_templates")):
            return
        base = self._watch_batch_dxc_base(watch)
        if self._batch_dxc_files_exist(batch_dir, False, base):
            self._cleanup_leftover_batch_dxc(
                batch_dir, scan_templates=False, batch_dxc_base=base
            )
        watch["orphan_dxc_cleaned"] = True

    def _wizard_batch_progress_info(self, watch: dict[str, object] | None) -> tuple[float, str] | None:
        if watch is None or not watch.get("had_dxc"):
            return None
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return None
        scan_templates = bool(watch.get("scan_templates"))
        batch_dxc_base = self._watch_batch_dxc_base(watch)
        initial = watch.get("initial_dxc_count")
        if not isinstance(initial, int) or initial <= 0:
            return None
        cached_remaining = watch.get("_progress_remaining_dxc")
        if isinstance(cached_remaining, int):
            remaining = cached_remaining
        else:
            remaining = self._batch_dxc_count(batch_dir, scan_templates, batch_dxc_base)
            if (
                watch.get("batch_chunks_complete")
                or self._wizard_batch_pass_complete(watch)
            ):
                remaining = 0
        done = max(0, initial - remaining)
        phase = watch.get("thumbnails_phase")
        if phase == _WIZARD_THUMBNAILS_PHASE_PART:
            single_running = "Part thumbnails running…"
            single_finished = "Part thumbnails finished."
        elif phase == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
            single_running = "Assembly thumbnails running…"
            single_finished = "Assembly thumbnails finished."
        elif phase == _WIZARD_THUMBNAILS_PHASE_2D:
            single_running = "Drawing thumbnails running…"
            single_finished = "Drawing thumbnails finished."
        else:
            single_running = "Batch running…"
            single_finished = "Batch finished."
        if scan_templates:
            if remaining:
                return 0.0, "Template scan running…"
            return 1.0, "Template scan finished."
        if initial == 1:
            if remaining:
                return 0.0, single_running
            return 1.0, single_finished
        if remaining == 0:
            if phase in (
                _WIZARD_THUMBNAILS_PHASE_PART,
                _WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
                _WIZARD_THUMBNAILS_PHASE_2D,
            ):
                return 1.0, single_finished
            return 1.0, f"Batch progress: {initial} of {initial} chunks complete."
        fraction = done / initial
        chunks_word = "chunks" if initial != 1 else "chunk"
        if phase in (
            _WIZARD_THUMBNAILS_PHASE_PART,
            _WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
            _WIZARD_THUMBNAILS_PHASE_2D,
        ):
            text = f"{single_running.rstrip('…')} — {done} of {initial} {chunks_word} complete."
        else:
            text = f"Batch progress: {done} of {initial} {chunks_word} complete."
        text += _batch_progress_eta_suffix(
            watch, done=done, remaining=remaining, initial=initial
        )
        return fraction, text

    def _wizard_step_shows_batch_progress(self, step: int) -> bool:
        if step not in (WIZARD_STEP_SCAN, WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return False
        if self._wizard_batch_in_progress_for_step(step):
            return True
        if self._wizard_batch_waiting_on_step(step):
            return True
        watch = self._wizard_batch_watch
        if step == WIZARD_STEP_SCAN:
            if watch is not None and watch.get("step") == WIZARD_STEP_SCAN and watch.get(
                "scan_failed"
            ):
                return True
            if self._wizard_scan_show_next_after_batch(step):
                return True
        elif self._wizard_batch_ready_for_next(step):
            return True
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            if self._wizard_batch_runner_finished_for_step(step):
                return True
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            if not self._wizard_batch_waiting_on_step(step):
                batch_dir, _ = self._wizard_batch_dir_for_step(step)
                if batch_dir is not None and self._wizard_failed_models_for_step(step, batch_dir):
                    return True
        return False

    def _wizard_batch_progress_info_for_step(self, step: int) -> tuple[float, str] | None:
        watch = self._wizard_batch_watch
        if watch is None or watch.get("step") != step:
            watch = self._ensure_wizard_batch_watch(step)
        if watch is not None and watch.get("step") == step:
            if self._wizard_batch_waiting_on_step(step):
                # While Waiting… use chunk/.dxc progress only — never a full model census.
                return self._wizard_batch_progress_info(watch)
            if self._wizard_batch_outputs_ready(watch):
                info = self._wizard_batch_progress_info(watch)
                if info is not None:
                    return info
        if (
            step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D)
            and self._wizard_batch_runner_finished_for_step(step)
        ):
            pending = self._wizard_step_pending_models(step)
            if pending:
                n = len(pending)
                word = "model" if n == 1 else "models"
                return 1.0, f"Last batch run finished — {n} {word} still need output."
        if watch is not None and watch.get("step") == step:
            info = self._wizard_batch_progress_info(watch)
            if info is not None:
                return info
        if step == WIZARD_STEP_SCAN:
            if not self._wizard_scan_show_next_after_batch(step):
                return None
        elif not self._wizard_batch_ready_for_next(step):
            return None
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return None
        if scan_templates:
            return 1.0, "Template scan finished."
        return 1.0, "Batch finished."

    def _refresh_wizard_step_batch_progress(self, step: int) -> None:
        if self._wizard_batch_in_progress_for_step(step):
            self._ensure_wizard_batch_watch(step)
        watch = self._wizard_batch_watch
        if (
            watch is not None
            and watch.get("step") == step
            and watch.get("had_dxc")
            and self._wizard_batch_waiting_on_step(step)
            and "_progress_remaining_dxc" not in watch
        ):
            self._wizard_batch_sync_progress_snapshot(watch)
        for frame_attr in (
            "wizard_scan_progress_frame",
            "wizard_batch_progress_frame",
            "wizard_jpeg_part_progress_frame",
            "wizard_jpeg_assembly_progress_frame",
            "wizard_jpeg_drawing_progress_frame",
        ):
            frame = getattr(self, frame_attr, None)
            if frame is not None:
                frame.pack_forget()
        if step == WIZARD_STEP_JPEG_3D:
            self._refresh_wizard_jpeg_thumbnails_progress()
            return
        rows = (
            (
                WIZARD_STEP_SCAN,
                getattr(self, "wizard_scan_progress_frame", None),
                getattr(self, "wizard_scan_progress_label", None),
                getattr(self, "wizard_scan_progress_bar", None),
            ),
            (
                WIZARD_STEP_MODELCHECK,
                getattr(self, "wizard_batch_progress_frame", None),
                getattr(self, "wizard_batch_progress_label", None),
                getattr(self, "wizard_batch_progress_bar", None),
            ),
        )
        if not self._wizard_step_shows_batch_progress(step):
            return
        frame = label = bar = None
        if step == WIZARD_STEP_SCAN:
            frame = getattr(self, "wizard_scan_progress_frame", None)
            label = getattr(self, "wizard_scan_progress_label", None)
            bar = getattr(self, "wizard_scan_progress_bar", None)
        elif step == WIZARD_STEP_MODELCHECK:
            frame = getattr(self, "wizard_batch_progress_frame", None)
            label = getattr(self, "wizard_batch_progress_label", None)
            bar = getattr(self, "wizard_batch_progress_bar", None)
        if frame is None or label is None or bar is None:
            return
        watch = self._wizard_batch_watch
        if (
            step == WIZARD_STEP_SCAN
            and watch is not None
            and watch.get("step") == WIZARD_STEP_SCAN
            and watch.get("scan_failed")
        ):
            if self._automatic_mode:
                fail_text = (
                    "Template scan failed — automatic mode stopped. "
                    "Check the batch log, then use Scan Templates > to try again."
                )
            else:
                fail_text = (
                    "Template scan failed. "
                    "Check the batch log, then use Scan Templates > to try again."
                )
            label.configure(text=fail_text, text_color="#C62828")
            bar.set(0)
            frame.pack(anchor="w", fill="x", pady=(8, 0))
            return
        info = self._wizard_batch_progress_info_for_step(step)
        failures_only = False
        if info is None and step == WIZARD_STEP_MODELCHECK:
            batch_dir, _ = self._wizard_batch_dir_for_step(step)
            if batch_dir is not None and self._wizard_failed_models_for_step(step, batch_dir):
                failures_only = True
        if info is None and not failures_only:
            wait_text = "Waiting for batch to finish…"
            watch = self._wizard_batch_watch
            if (
                step == WIZARD_STEP_MODELCHECK
                and watch is not None
                and watch.get("step") == step
            ):
                wait_text += WIZARD_BATCH_ETA_ESTIMATING_SUFFIX
            label.configure(text=wait_text, text_color="#666666")
            bar.set(0)
        else:
            if failures_only:
                fraction, text = 1.0, ""
            else:
                fraction, text = info  # type: ignore[misc]
            finished = fraction >= 1.0
            still_pending = "still need output" in text
            label.configure(
                text=text,
                text_color=(
                    "#2E7D32" if finished and text and not still_pending else "#111111"
                ),
            )
            bar.set(fraction)
        frame.pack(anchor="w", fill="x", pady=(8, 0))
        if step == WIZARD_STEP_MODELCHECK:
            batch_dir, _ = self._wizard_batch_dxc_context_for_step(step)
            self._refresh_wizard_batch_automatic_label(step)
            if not self._wizard_batch_waiting_on_step(step):
                self._refresh_wizard_batch_failed_label(step, batch_dir)

    def _apply_wizard_progress_row(
        self,
        *,
        frame,
        label,
        bar,
        info: tuple[float, str] | None,
        waiting: bool,
        pending_text: str = "",
    ) -> None:
        if frame is None or label is None or bar is None:
            return
        if info is not None:
            fraction, text = info
            finished = fraction >= 1.0
            label.configure(
                text=text,
                text_color="#2E7D32" if finished and text else "#111111",
            )
            bar.set(fraction)
            frame.pack(anchor="w", fill="x", pady=(8, 0))
            return
        if waiting:
            text = "Waiting for batch to finish…" + WIZARD_BATCH_ETA_ESTIMATING_SUFFIX
            label.configure(text=text, text_color="#666666")
            bar.set(0)
            frame.pack(anchor="w", fill="x", pady=(8, 0))
            return
        if pending_text:
            label.configure(text=pending_text, text_color="#666666")
            bar.set(0)
            frame.pack(anchor="w", fill="x", pady=(8, 0))

    def _refresh_wizard_jpeg_thumbnails_progress(self) -> None:
        step = WIZARD_STEP_JPEG_3D
        if not self._wizard_step_shows_batch_progress(step):
            return
        watch = self._wizard_batch_watch
        waiting = self._wizard_batch_waiting_on_step(step)
        # Prefer GO/watch row flags so Waiting… ticks never re-scan for "has models".
        if watch is not None and watch.get("step") == step and (
            "thumbnails_show_part" in watch
            or "thumbnails_show_asm" in watch
            or "thumbnails_show_drawing" in watch
        ):
            needs_part = bool(watch.get("thumbnails_show_part"))
            needs_asm = bool(watch.get("thumbnails_show_asm"))
            needs_drawing = bool(watch.get("thumbnails_show_drawing"))
        else:
            needs_part = self._wizard_thumbnails_phase_has_models(_WIZARD_THUMBNAILS_PHASE_PART)
            needs_asm = self._wizard_thumbnails_phase_has_models(
                _WIZARD_THUMBNAILS_PHASE_ASSEMBLY
            )
            needs_drawing = self._wizard_thumbnails_phase_has_models(
                _WIZARD_THUMBNAILS_PHASE_2D
            )
        progress_info_once = (
            self._wizard_batch_progress_info(watch)
            if watch is not None and watch.get("had_dxc")
            else None
        )

        def _phase_row(
            *,
            show: bool,
            title: str,
            phase_key: str,
            frame_attr: str,
            label_attr: str,
            bar_attr: str,
        ) -> None:
            frame = getattr(self, frame_attr, None)
            if not show:
                if frame is not None:
                    frame.pack_forget()
                return
            short = self._wizard_thumbnails_phase_short_title(title)
            watch = self._wizard_batch_watch
            phase = watch.get("thumbnails_phase") if watch is not None else None
            active_this_phase = (
                watch is not None
                and watch.get("step") == step
                and phase == phase_key
            )
            waiting_this = active_this_phase and waiting
            if active_this_phase and (waiting_this or progress_info_once is not None):
                info = progress_info_once
                if info is None and waiting_this:
                    info = (0.0, f"{short} running…")
            elif waiting:
                # Inactive rows during a run: session flags only — no disk census.
                if phase_key == _WIZARD_THUMBNAILS_PHASE_PART:
                    done = self._wizard_thumbnails_part_phase_done
                elif phase_key == _WIZARD_THUMBNAILS_PHASE_ASSEMBLY:
                    done = self._wizard_thumbnails_assembly_phase_done
                else:
                    done = self._wizard_thumbnails_drawing_phase_done
                if done:
                    info = (1.0, f"{short} finished.")
                else:
                    info = (0.0, f"{short} — waiting to start")
            else:
                info = self._wizard_thumbnails_phase_disk_progress(phase_key, title)
            if info is None:
                if frame is not None:
                    frame.pack_forget()
                return
            self._apply_wizard_progress_row(
                frame=frame,
                label=getattr(self, label_attr, None),
                bar=getattr(self, bar_attr, None),
                info=info,
                waiting=False,
                pending_text="",
            )

        _phase_row(
            show=needs_part,
            title="Part thumbnails (3D raster)",
            phase_key=_WIZARD_THUMBNAILS_PHASE_PART,
            frame_attr="wizard_jpeg_part_progress_frame",
            label_attr="wizard_jpeg_part_progress_label",
            bar_attr="wizard_jpeg_part_progress_bar",
        )
        _phase_row(
            show=needs_asm,
            title="Assembly thumbnails (3D raster)",
            phase_key=_WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
            frame_attr="wizard_jpeg_assembly_progress_frame",
            label_attr="wizard_jpeg_assembly_progress_label",
            bar_attr="wizard_jpeg_assembly_progress_bar",
        )
        _phase_row(
            show=needs_drawing,
            title="Drawing thumbnails (2D JPEG)",
            phase_key=_WIZARD_THUMBNAILS_PHASE_2D,
            frame_attr="wizard_jpeg_drawing_progress_frame",
            label_attr="wizard_jpeg_drawing_progress_label",
            bar_attr="wizard_jpeg_drawing_progress_bar",
        )

        batch_dir, _ = self._wizard_batch_dxc_context_for_step(step)
        self._refresh_wizard_batch_automatic_label(step)
        if not waiting:
            self._refresh_wizard_batch_failed_label(step, batch_dir)

    def _wizard_automatic_mode_progress_note(self, step: int) -> str:
        if not self._automatic_mode:
            return ""
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return ""
        return WIZARD_AUTOMATIC_MODE_MESSAGE

    def _refresh_wizard_batch_automatic_label(self, step: int) -> None:
        label = getattr(self, "wizard_batch_automatic_label", None)
        if label is None:
            return
        note = self._wizard_automatic_mode_progress_note(step)
        if note and self._wizard_step_shows_batch_progress(step):
            label.configure(text=note, text_color="#1565C0")
            label.pack(anchor="w", pady=(4, 0))
        else:
            label.configure(text="")
            label.pack_forget()

    def _wizard_thumbnails_latest_models(self, working_dir: Path) -> list[Path]:
        """Top-level models included in any applicable thumbnail pass."""
        seen: set[Path] = set()
        out: list[Path] = []
        for phase in (
            _WIZARD_THUMBNAILS_PHASE_PART,
            _WIZARD_THUMBNAILS_PHASE_ASSEMBLY,
            _WIZARD_THUMBNAILS_PHASE_2D,
        ):
            if phase == _WIZARD_THUMBNAILS_PHASE_2D and not self._drawing_thumbnails_applicable():
                continue
            extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
            if not extensions:
                continue
            scanned = self._scan_models_non_recursive(working_dir, extensions=extensions)
            for path in self._get_latest_model_files(scanned):
                if path not in seen:
                    seen.add(path)
                    out.append(path)
        return out

    def _wizard_thumbnails_task_display_to_run(self) -> str:
        """Pick 3D or 2D batch task for the next thumbnail sub-phase."""
        wd = (self.working_directory.get() or "").strip()
        try:
            d = Path(wd).expanduser().resolve() if wd else None
        except OSError:
            d = None
        if d is not None and d.is_dir():
            phase = self._wizard_thumbnails_next_pending_phase(d)
            if phase == _WIZARD_THUMBNAILS_PHASE_2D:
                return self._wizard_jpeg_2d_display()
        return self._wizard_jpeg_3d_display()

    def _record_pending_thumbnail_failures_for_phase(
        self, working_dir: Path, phase: str
    ) -> None:
        """Write models still missing this pass's thumbnail into that phase's failure log.

        The Failed (N) line only reads timeout log files. Runner timeouts are recorded
        there automatically; this also records models that finished the pass chunks but
        still have no output (so part failures stay visible after chaining to drawings).
        """
        extensions = self._wizard_thumbnails_phase_scan_extensions(phase)
        if not extensions:
            return
        task_kind = self._wizard_thumbnails_phase_runner_task_kind(phase)
        latest = self._scan_models_non_recursive(working_dir, extensions=extensions)
        paths = self._get_latest_model_files(latest)
        pending = self._filter_models_missing_task_output(paths, working_dir, task_kind)
        if not pending:
            return
        _append_batch_timeout_log_models(
            working_dir, task_kind, [p.name for p in pending]
        )

    def _wizard_thumbnails_after_phase_complete(self, watch: dict[str, object]) -> bool:
        """Rename batch JPGs; chain the next thumbnail sub-phase. True = step not fully done."""
        phase = watch.get("thumbnails_phase", _WIZARD_THUMBNAILS_PHASE_PART)
        wd_str = (self.working_directory.get() or "").strip()
        if not wd_str:
            return False
        wd = Path(wd_str).expanduser().resolve()
        middle = self._wizard_thumbnails_phase_rename_middle(str(phase))

        if phase in (_WIZARD_THUMBNAILS_PHASE_PART, _WIZARD_THUMBNAILS_PHASE_ASSEMBLY, _WIZARD_THUMBNAILS_PHASE_2D):
            errors = _rename_plain_jpgs_in_directory(wd, middle=middle)
            self._invalidate_working_dir_file_cache()
            if errors:
                messagebox.showwarning(
                    "Thumbnails",
                    "Some thumbnail files could not be renamed:\n\n" + "\n\n".join(errors),
                )
        self._record_pending_thumbnail_failures_for_phase(wd, str(phase))
        self._wizard_thumbnails_mark_phase_done(str(phase))
        # Always advance to a *later* pass (assembly/drawing). Do not restart this
        # pass for leftover failures — that is what manual Thumbnails > is for.
        return self._wizard_thumbnails_chain_next_subphase_auto(after_phase=str(phase))

    def _wizard_thumbnails_start_subphase_batch(self, phase: str) -> bool:
        if phase == _WIZARD_THUMBNAILS_PHASE_2D:
            task_display = self._wizard_jpeg_2d_display()
            if not task_display:
                messagebox.showwarning(
                    "Thumbnails",
                    "JPEG 2D plot task is not available from the Creo loadpoint.",
                )
                return False
        else:
            task_display = self._wizard_jpeg_3d_display()
        if not self._go_fields_valid():
            return False
        self._wizard_thumbnails_go_phase = phase
        self.task.set(task_display)
        self._cancel_wizard_batch_output_watch(clear_go_snapshot=False)
        self._wizard_thumbnails_sync_active_phase_ui(phase)
        self._close_batch_runner_window()
        if self._automatic_mode:
            self._skip_timed_out_prompt_on_go = True
        try:
            self._on_go()
        finally:
            self._wizard_thumbnails_go_phase = None
        watch = self._wizard_batch_watch
        return (
            watch is not None
            and watch.get("step") == WIZARD_STEP_JPEG_3D
            and watch.get("thumbnails_phase") == phase
        )

    def _wizard_thumbnails_start_drawing_batch(self) -> bool:
        return self._wizard_thumbnails_start_subphase_batch(_WIZARD_THUMBNAILS_PHASE_2D)

    def _wizard_scan_outputs_complete(self, templates_dir: Path) -> bool:
        """True when every uploaded template has its ModelCHECK .xml in templates\\."""
        if not templates_dir.is_dir():
            return False
        expected_any = False
        for kind, dest_name in _START_TEMPLATE_DEST_NAMES.items():
            if not self._scan_kind_enabled(kind):
                continue
            dest = templates_dir / dest_name
            if not dest.is_file():
                continue
            expected_any = True
            xml_name = _START_TEMPLATE_XML_NAMES.get(kind)
            if xml_name and not (templates_dir / xml_name).is_file():
                return False
        return expected_any

    def _scanned_template_kind_labels(self, templates_dir: Path) -> list[str]:
        """Uploaded templates that finished with ModelCHECK .xml (part/assembly/drawing labels)."""
        if not templates_dir.is_dir():
            return []
        found: list[str] = []
        for kind, dest_name in _START_TEMPLATE_DEST_NAMES.items():
            if not self._scan_kind_enabled(kind):
                continue
            if not (templates_dir / dest_name).is_file():
                continue
            xml_name = _START_TEMPLATE_XML_NAMES.get(kind)
            if xml_name and (templates_dir / xml_name).is_file():
                label = _TEMPLATE_KIND_LABELS.get(kind)
                if label:
                    found.append(label)
        return found

    def _write_template_scan_session_for_working_dir(
        self, outcome: str, kinds: list[str] | None = None
    ) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            return
        try:
            make_html_statistics.write_template_scan_session(wd, outcome, kinds)
        except OSError:
            pass

    def _wizard_scan_step_has_failed(self) -> bool:
        watch = self._wizard_batch_watch
        return (
            watch is not None
            and watch.get("step") == WIZARD_STEP_SCAN
            and bool(watch.get("scan_failed"))
        )

    def _on_wizard_scan_batch_failed(self, watch: dict[str, object]) -> None:
        """Pause auto-advance when template scan did not succeed (checkbox unchanged)."""
        watch["scan_failed"] = True
        self._cancel_automatic_wizard_chain()
        self._wizard_step_outcome.pop(WIZARD_STEP_SCAN, None)
        if watch.get("scan_failed_notified"):
            return
        watch["scan_failed_notified"] = True
        log_hint = ""
        batch_dir = watch.get("batch_dir")
        if isinstance(batch_dir, Path):
            log_stem = Path(CREO_BATCH_RUNNER_SCAN_TEMPLATES_BASENAME).stem
            log_path = batch_dir / f"{log_stem}.log"
            if log_path.is_file():
                log_hint = f"\n\nSee log:\n{log_path}"
        if self._automatic_mode:
            fail_body = (
                "Template scan did not complete. Auto-advance is paused until you continue manually.\n\n"
                "The Automatic mode checkbox in Settings is not changed.\n\n"
                "Fix the issue and use Scan Templates > to try again."
            )
        else:
            fail_body = (
                "Template scan did not complete.\n\n"
                "Fix the issue and use Scan Templates > to try again, or use Back to change templates."
            )
        messagebox.showerror("Scan Templates failed", fail_body + log_hint)

    def _wizard_scan_batch_failed(self, watch: dict[str, object]) -> bool:
        """True when the scan runner finished but template .xml outputs are still missing."""
        if not watch.get("scan_templates"):
            return False
        if watch.get("scan_failed"):
            return True
        if not watch.get("had_dxc"):
            return False
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return False
        if self._batch_dxc_files_exist(batch_dir, True):
            return False
        if self._wizard_scan_outputs_complete(batch_dir):
            watch.pop("runner_exited_at", None)
            return False
        # Debug (-NoExit) keeps PowerShell open; prefer run-complete flag, then process exit.
        runner_finished = self._wizard_batch_runner_idle(watch)
        if not runner_finished:
            return False
        exited_at = watch.get("runner_exited_at")
        if exited_at is None:
            watch["runner_exited_at"] = time.time()
            return False
        if time.time() - float(exited_at) < SCAN_BATCH_RUNNER_EXIT_GRACE_SEC:
            return False
        watch["scan_failed"] = True
        return True

    def _wizard_batch_outputs_ready(self, watch: dict[str, object]) -> bool:
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return False
        scan_templates = bool(watch.get("scan_templates"))
        if not scan_templates and self._wizard_batch_pass_complete(watch):
            return True
        batch_dxc_base = self._watch_batch_dxc_base(watch)
        has_dxc = self._batch_dxc_files_exist(batch_dir, scan_templates, batch_dxc_base)
        if has_dxc:
            watch["had_dxc"] = True
            count = self._batch_dxc_count(batch_dir, scan_templates, batch_dxc_base)
            initial = watch.get("initial_dxc_count")
            if not isinstance(initial, int) or count > initial:
                watch["initial_dxc_count"] = count
            return False
        if not watch.get("had_dxc"):
            return False
        if scan_templates:
            if watch.get("scan_failed"):
                return False
            return self._wizard_scan_outputs_complete(batch_dir)
        return True

    def _wizard_batch_poll_interval_ms(self, watch: dict[str, object]) -> int:
        """Shorter interval while a batch is running; quick ticks after batch completes."""
        if watch.get("batch_complete_shown_at") is not None:
            return 100
        if self._wizard_batch_pass_complete(watch) and not watch.get("batch_post_ready_done"):
            return WIZARD_BATCH_RUNNER_EXIT_POLL_MS
        proc = self._batch_runner_process
        if proc is not None and proc.poll() is None:
            return WIZARD_BATCH_ACTIVE_POLL_MS
        batch_dir = watch.get("batch_dir")
        if isinstance(batch_dir, Path):
            scan_templates = bool(watch.get("scan_templates"))
            base = self._watch_batch_dxc_base(watch)
            if self._batch_dxc_files_exist(batch_dir, scan_templates, base):
                return WIZARD_BATCH_ACTIVE_POLL_MS
        return WIZARD_BATCH_DXC_POLL_MS

    def _wizard_batch_auto_advance_hold_elapsed(self, watch: dict[str, object]) -> bool:
        """True once batch-complete progress (100%) has been visible long enough."""
        since = watch.get("batch_complete_shown_at")
        if not isinstance(since, (int, float)):
            return False
        return (time.time() - float(since)) * 1000 >= WIZARD_BATCH_AUTO_ADVANCE_HOLD_MS

    @staticmethod
    def _wizard_batch_mark_complete_for_auto_advance(watch: dict[str, object]) -> None:
        if watch.get("batch_complete_shown_at") is None:
            watch["batch_complete_shown_at"] = time.time()

    def _wizard_batch_completion_hold_active(self, step: int) -> bool:
        """Automatic mode: brief pause at 100% before advancing to the next wizard step."""
        if not self._automatic_mode:
            return False
        watch = self._wizard_batch_watch
        if watch is None or watch.get("step") != step:
            return False
        if step not in (WIZARD_STEP_SCAN, WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return False
        if watch.get("batch_complete_shown_at") is None:
            return False
        if step == WIZARD_STEP_JPEG_3D and self._wizard_thumbnails_batch_settling(watch):
            return False
        return not self._wizard_batch_auto_advance_hold_elapsed(watch)

    def _cancel_wizard_batch_output_watch(self, *, clear_go_snapshot: bool = True) -> None:
        jid = self._wizard_batch_watch_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._wizard_batch_watch_job = None
        self._wizard_batch_watch = None
        if clear_go_snapshot:
            self._wizard_batch_go_snapshot = None

    def _start_wizard_batch_output_watch(
        self,
        step: int,
        batch_dir: Path,
        scan_templates: bool,
        *,
        launched_dxc_count: int = 0,
        thumbnails_phase: str | None = None,
        batch_dxc_base: str | None = None,
    ) -> None:
        self._cancel_wizard_batch_output_watch(clear_go_snapshot=False)
        if step == WIZARD_STEP_MODELCHECK:
            self._wizard_step_failed_models.pop(step, None)
        if batch_dxc_base is None:
            if scan_templates:
                batch_dxc_base = BATCH_DXC_BASE_SCAN_TEMPLATES
            elif step == WIZARD_STEP_MODELCHECK:
                batch_dxc_base = BATCH_DXC_BASE_MODELCHECK
            elif step == WIZARD_STEP_JPEG_3D and isinstance(thumbnails_phase, str):
                batch_dxc_base = _batch_dxc_base_for_task_kind(
                    self._wizard_thumbnails_phase_runner_task_kind(thumbnails_phase)
                )
            else:
                batch_dxc_base = CREO_BATCH_BASE
        file_had_dxc = self._batch_dxc_files_exist(
            batch_dir, scan_templates, batch_dxc_base
        )
        file_dxc_count = self._batch_dxc_count(
            batch_dir, scan_templates, batch_dxc_base
        )
        if launched_dxc_count > 0:
            had_dxc = file_had_dxc or True
            initial_dxc_count = max(file_dxc_count, launched_dxc_count)
        else:
            had_dxc = file_had_dxc
            initial_dxc_count = file_dxc_count
        self._wizard_batch_watch = {
            "step": step,
            "batch_dir": batch_dir,
            "scan_templates": scan_templates,
            "batch_dxc_base": batch_dxc_base,
            "had_dxc": had_dxc,
            "initial_dxc_count": initial_dxc_count,
            "started_at": time.time(),
            "thumbnails_phase": thumbnails_phase,
        }
        if step == WIZARD_STEP_JPEG_3D:
            wd_str = (self.working_directory.get() or "").strip()
            drawing_task_ok = bool(self._task_display_for_ttd_filename(JPEG_2D_PLOT_TTD))
            self._wizard_batch_cache_thumbnail_phase_flags(
                self._wizard_batch_watch,
                working_dir_str=wd_str,
                drawing_task_ok=drawing_task_ok,
            )
        self._wizard_batch_go_snapshot = {
            "step": step,
            "batch_dir": batch_dir,
            "scan_templates": scan_templates,
            "batch_dxc_base": batch_dxc_base,
            "initial_dxc_count": initial_dxc_count,
            "started_at": self._wizard_batch_watch["started_at"],
            "thumbnails_phase": thumbnails_phase,
        }
        self._tick_wizard_batch_output_watch()

    def _wizard_batch_post_ready_delay_ms(self, watch: dict[str, object]) -> int:
        if (
            watch.get("step") == WIZARD_STEP_JPEG_3D
            and self._wizard_thumbnails_will_chain_after_batch(watch)
        ):
            return WIZARD_BATCH_THUMBNAIL_PHASE_PAINT_MS
        return 0

    def _wizard_batch_finish_post_ready(self) -> None:
        """Rename / chain / auto-advance after batch-complete progress was painted at 100%."""
        self._wizard_batch_watch_job = None
        watch = self._wizard_batch_watch
        if watch is None or not watch.get("batch_finish_painted"):
            return
        if watch.get("batch_post_ready_done"):
            return
        watch["batch_post_ready_done"] = True
        self._invalidate_working_dir_file_cache()
        thumbnails_continuing = False
        step = watch.get("step")
        if step == WIZARD_STEP_JPEG_3D:
            self._wizard_capture_failed_models_after_batch(watch)
            thumbnails_continuing = self._wizard_thumbnails_after_phase_complete(watch)
            watch = self._wizard_batch_watch
        else:
            self._wizard_capture_failed_models_after_batch(watch)
        if (
            watch is not None
            and not thumbnails_continuing
            and self._automatic_mode
            and step in (
                WIZARD_STEP_SCAN,
                WIZARD_STEP_MODELCHECK,
                WIZARD_STEP_JPEG_3D,
            )
        ):
            self._wizard_batch_mark_complete_for_auto_advance(watch)
        step = watch.get("step") if watch is not None else None
        if isinstance(step, int):
            self._refresh_wizard_step_batch_progress(step)
            self._refresh_wizard_footer()
            if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
                batch_dir, _ = self._wizard_batch_dxc_context_for_step(step)
                self._refresh_wizard_batch_failed_label(step, batch_dir)
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        if watch is None:
            return
        if not thumbnails_continuing:
            step = watch.get("step")
            if step == WIZARD_STEP_SCAN and self._wizard_scan_step_has_failed():
                return
            if step == WIZARD_STEP_SCAN and not watch.get("start_applied"):
                watch["start_applied"] = True
                self._apply_start_after_template_scan()
            if step == WIZARD_STEP_JPEG_3D:
                self._update_create_report_task_list(advance_from_jpeg=False)
            if self._automatic_mode and step in (
                WIZARD_STEP_SCAN,
                WIZARD_STEP_MODELCHECK,
                WIZARD_STEP_JPEG_3D,
            ):
                if not self._wizard_batch_auto_advance_hold_elapsed(watch):
                    self._wizard_batch_watch_job = self.after(
                        100, self._tick_wizard_batch_output_watch
                    )
                    return
                self._schedule_automatic_wizard_advance()
            return
        new_watch = self._wizard_batch_watch
        if new_watch is not None:
            poll_ms = self._wizard_batch_poll_interval_ms(new_watch)
            self._wizard_batch_watch_job = self.after(
                poll_ms, self._tick_wizard_batch_output_watch
            )

    def _tick_wizard_batch_output_watch(self) -> None:
        self._wizard_batch_watch_job = None
        watch = self._wizard_batch_watch
        if watch is None and self._wizard_batch_session_active_for_step(self._wizard_step):
            batch_dir, scan_templates = self._wizard_batch_dir_for_step(self._wizard_step)
            base = self._batch_dxc_base_for_step(self._wizard_step)
            if batch_dir is not None and self._batch_dxc_files_exist(
                batch_dir, scan_templates, base
            ):
                watch = self._ensure_wizard_batch_watch(self._wizard_step)
            else:
                watch = self._restore_wizard_batch_watch_from_session(self._wizard_step)
        if watch is None:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self._modal_dialog_depth > 0:
            self._refresh_wizard_ui()
            self._wizard_batch_watch_job = self.after(1000, self._tick_wizard_batch_output_watch)
            return
        step = watch.get("step")
        if isinstance(step, int):
            self._ensure_wizard_batch_watch(step)
            watch = self._wizard_batch_watch
            if watch is None:
                return
        proc = self._batch_runner_process
        if proc is not None and proc.poll() is not None and not watch.get(
            "runner_exit_polled"
        ):
            watch["runner_exit_polled"] = True
        if self._wizard_scan_batch_failed(watch):
            if watch.get("scan_failed"):
                self._on_wizard_scan_batch_failed(watch)
                self._refresh_wizard_ui()
                return
            self._refresh_wizard_ui()
            self._wizard_batch_watch_job = self.after(
                WIZARD_BATCH_DXC_POLL_MS, self._tick_wizard_batch_output_watch
            )
            return
        if watch.get("had_dxc"):
            self._wizard_batch_sync_progress_snapshot(watch)
        ready = bool(watch.get("_progress_pass_complete"))
        if ready:
            if not watch.get("batch_finish_painted"):
                self._wizard_batch_paint_pass_complete(watch)
            if not watch.get("batch_post_ready_done"):
                self._wizard_batch_watch_job = self.after(
                    self._wizard_batch_post_ready_delay_ms(watch),
                    self._wizard_batch_finish_post_ready,
                )
                return
            step = watch.get("step")
            if self._automatic_mode and step in (
                WIZARD_STEP_SCAN,
                WIZARD_STEP_MODELCHECK,
                WIZARD_STEP_JPEG_3D,
            ):
                if isinstance(step, int):
                    self._refresh_wizard_step_batch_progress(step)
                if not self._wizard_batch_auto_advance_hold_elapsed(watch):
                    self._wizard_batch_watch_job = self.after(
                        100, self._tick_wizard_batch_output_watch
                    )
                    return
                self._schedule_automatic_wizard_advance()
            return
        poll_ms = self._wizard_batch_poll_interval_ms(watch)
        step = watch.get("step")
        if isinstance(step, int):
            self._refresh_wizard_step_batch_progress(step)
        else:
            self._refresh_wizard_ui()
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        self._wizard_batch_watch_job = self.after(
            poll_ms, self._tick_wizard_batch_output_watch
        )

    def _cancel_automatic_wizard_chain(self) -> None:
        jid = self._automatic_wizard_chain_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._automatic_wizard_chain_job = None

    def _schedule_automatic_wizard_advance(self) -> None:
        """Automatic mode: timer that clicks Next > / GO when each step is ready."""
        if not self._automatic_mode or self._automatic_wizard_paused:
            return
        jid = self._automatic_wizard_chain_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._automatic_wizard_chain_job = self.after(
            300, self._tick_automatic_wizard_advance
        )

    def _tick_automatic_wizard_advance(self) -> None:
        """Same actions as the footer Next > button, on a short timer."""
        self._automatic_wizard_chain_job = None
        if not self._automatic_mode or self._automatic_wizard_paused:
            return
        if self._modal_dialog_depth > 0:
            self._schedule_automatic_wizard_advance()
            return

        step = self._wizard_step
        if step == WIZARD_STEP_SCAN and self._wizard_scan_step_has_failed():
            return

        if self._wizard_batch_waiting_on_step(step) or self._go_in_progress:
            self._schedule_automatic_wizard_advance()
            return

        if step == WIZARD_STEP_REPORT:
            if not self._report_job_running and self._wizard_should_auto_create_report():
                self._on_wizard_next(from_auto=True)
            return

        if self._wizard_footer_next_enabled():
            self._on_wizard_next(from_auto=True)

        if step in (
            WIZARD_STEP_SCAN,
            WIZARD_STEP_MODELCHECK,
            WIZARD_STEP_JPEG_3D,
            WIZARD_STEP_REPORT,
        ):
            self._schedule_automatic_wizard_advance()

    def _maybe_schedule_automatic_advance(self) -> None:
        """Start the auto timer when the footer would enable Next > or GO."""
        if (
            not self._automatic_mode
            or self._automatic_wizard_paused
            or self._automatic_wizard_chain_job is not None
        ):
            return
        if self._go_in_progress or self._modal_dialog_depth > 0:
            return
        step = self._wizard_step
        if self._wizard_batch_waiting_on_step(step):
            return
        if step == WIZARD_STEP_SCAN and self._wizard_scan_show_next_after_batch(step):
            self._schedule_automatic_wizard_advance()
        elif step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D, WIZARD_STEP_REPORT):
            if self._wizard_footer_next_enabled():
                self._schedule_automatic_wizard_advance()

    def _wizard_batch_step_already_complete(self, step: int) -> bool:
        """True only when this step's batch already finished earlier in this session."""
        if self._wizard_step_outcome.get(step) != "done":
            return False
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return False
        return not self._any_batch_chunk_dxc_exist(batch_dir, scan_templates=scan_templates)

    def _wizard_batch_waiting_on_step(self, step: int) -> bool:
        if self._wizard_batch_completion_hold_active(step):
            return True
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            if step == WIZARD_STEP_SCAN and self._wizard_scan_step_has_failed():
                return False
            if self._wizard_batch_finish_pending(watch, step):
                return True
            if self._wizard_step_has_remaining_dxc(step):
                return True
            if not self._wizard_batch_outputs_ready(watch):
                return True
            if step == WIZARD_STEP_JPEG_3D and self._wizard_thumbnails_batch_settling(watch):
                return True
            return False
        return self._wizard_batch_in_progress_for_step(step)

    def _wizard_capture_failed_models_after_batch(self, watch: dict[str, object]) -> None:
        step = watch.get("step")
        if step != WIZARD_STEP_MODELCHECK:
            return
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return
        task_display = self.task.get() or ""
        if not task_display:
            return
        task_kind = self._runner_task_kind(task_display)
        self._wizard_step_failed_models[step] = _read_batch_failed_models(
            batch_dir, task_kind
        )

    def _wizard_failed_models_still_missing(
        self, log_dir: Path, task_kind: str
    ) -> list[str]:
        """Models from a failure log that still lack this task's output on disk."""
        logged = _read_batch_failed_models(log_dir, task_kind)
        if not logged:
            return []
        still: list[str] = []
        seen: set[str] = set()
        for name in logged:
            base = _creo_model_base_name(name)
            key = base.casefold()
            if not key or key in seen:
                continue
            if not self._model_still_missing_task_output(log_dir, base, task_kind):
                continue
            seen.add(key)
            still.append(base)
        return still

    def _wizard_failed_models_for_step(self, step: int, log_dir: Path) -> list[str]:
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return []
        if step == WIZARD_STEP_JPEG_3D:
            models: list[str] = []
            seen: set[str] = set()
            for kind in _JPEG_THUMBNAIL_FAILURE_TASK_KINDS:
                for name in self._wizard_failed_models_still_missing(log_dir, kind):
                    key = name.casefold()
                    if key in seen:
                        continue
                    seen.add(key)
                    models.append(name)
            return models
        if self._wizard_batch_waiting_on_step(step):
            task_display = self._wizard_task_display_for_step(step)
            if not task_display:
                return []
            task_kind = self._runner_task_kind(task_display)
            return self._wizard_failed_models_still_missing(log_dir, task_kind)
        task_display = self._wizard_task_display_for_step(step)
        if not task_display:
            return []
        task_kind = self._runner_task_kind(task_display)
        models = self._wizard_failed_models_still_missing(log_dir, task_kind)
        self._wizard_step_failed_models[step] = models
        return models

    def _write_combined_thumbnail_failure_review(self, log_dir: Path) -> Path | None:
        """Build a short review file listing failed models from every thumbnail phase."""
        sections: list[str] = []
        total = 0
        labels = {
            "jpeg3d_part": "Part thumbnails",
            "jpeg3d_asm": "Assembly thumbnails",
            "jpeg2d": "Drawing thumbnails",
            "jpeg3d": "3D thumbnails (legacy)",
        }
        for kind in _JPEG_THUMBNAIL_FAILURE_TASK_KINDS:
            still = self._wizard_failed_models_still_missing(log_dir, kind)
            if not still:
                continue
            total += len(still)
            label = labels.get(kind, kind)
            log_name = f"{BATCH_TIMEOUT_LOG_PREFIX}{kind}.txt"
            sections.append(f"{label} ({len(still)}) — see also {log_name}:")
            sections.extend(f"  {name}" for name in still)
            sections.append("")
        if not sections:
            return None
        out = log_dir / f"{BATCH_TIMEOUT_LOG_PREFIX}thumbnails.txt"
        text = (
            "Thumbnail failures still missing output\n"
            f"Total: {total}\n\n"
            + "\n".join(sections)
        )
        try:
            out.write_text(text, encoding="utf-8")
        except OSError:
            return None
        return out

    def _resolve_wizard_batch_failed_log_path(self, step: int, log_dir: Path) -> Path | None:
        if step == WIZARD_STEP_JPEG_3D:
            combined = self._write_combined_thumbnail_failure_review(log_dir)
            if combined is not None:
                return combined
            for kind in _JPEG_THUMBNAIL_FAILURE_TASK_KINDS:
                models = self._wizard_failed_models_still_missing(log_dir, kind)
                if not models:
                    continue
                path = _resolve_batch_timeout_log_path(log_dir, kind)
                if path is not None:
                    return path
            return _resolve_batch_timeout_log_path(log_dir, "jpeg3d_part")
        task_display = self._wizard_task_display_for_step(step)
        if not task_display:
            return None
        task_kind = self._runner_task_kind(task_display)
        return _resolve_batch_timeout_log_path(log_dir, task_kind)

    def _refresh_wizard_batch_failed_label(self, step: int, log_dir: Path | None) -> None:
        frame = getattr(self, "wizard_batch_failed_frame", None)
        if frame is None:
            return
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D) or log_dir is None:
            self._wizard_batch_failed_log_path = None
            frame.pack_forget()
            return
        failed = self._wizard_failed_models_for_step(step, log_dir)
        if not failed:
            self._wizard_batch_failed_log_path = None
            frame.pack_forget()
            return
        log_path = self._resolve_wizard_batch_failed_log_path(step, log_dir)
        self._wizard_batch_failed_log_path = log_path
        prefix = getattr(self, "wizard_batch_failed_prefix", None)
        if prefix is not None:
            prefix.configure(text=f"Failed ({len(failed)}): Click ")
        frame.pack(anchor="w", pady=(4, 0))

    def _open_batch_failed_log_path(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            messagebox.showwarning(
                "Failed models",
                "The failure log file was not found in the working directory.",
            )
            return
        try:
            self._open_file_in_notepad(path)
        except OSError as exc:
            messagebox.showerror("Failed models", f"Could not open:\n{path}\n\n{exc}")

    def _on_wizard_open_batch_failed_log(self) -> None:
        self._open_batch_failed_log_path(self._wizard_batch_failed_log_path)

    def _on_wizard_open_report_modelcheck_failed_log(self) -> None:
        self._open_batch_failed_log_path(self._wizard_report_modelcheck_failed_log_path)

    def _on_wizard_open_report_thumbnails_failed_log(self) -> None:
        self._open_batch_failed_log_path(self._wizard_report_thumbnails_failed_log_path)

    def _wizard_batch_failure_summary(self, step: int) -> tuple[int, Path | None]:
        """Failed model count and timeout log path for a finished batch step."""
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return 0, None
        if self._wizard_step_outcome.get(step) == "skipped":
            return 0, None
        batch_dir, _ = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return 0, None
        failed = self._wizard_failed_models_for_step(step, batch_dir)
        if not failed:
            return 0, None
        return len(failed), self._resolve_wizard_batch_failed_log_path(step, batch_dir)

    def _refresh_wizard_report_failure_row(
        self,
        step: int,
        *,
        frame,
        prefix_label,
        step_name: str,
        log_path_attr: str,
    ) -> None:
        count, log_path = self._wizard_batch_failure_summary(step)
        setattr(self, log_path_attr, log_path)
        if count <= 0:
            frame.pack_forget()
            return
        prefix_label.configure(text=f"{step_name} failed ({count}): Click ")
        frame.pack(anchor="w", pady=(4, 0))

    def _refresh_wizard_report_batch_failures(self) -> None:
        mc_frame = getattr(self, "wizard_report_modelcheck_failed_frame", None)
        mc_prefix = getattr(self, "wizard_report_modelcheck_failed_prefix", None)
        th_frame = getattr(self, "wizard_report_thumbnails_failed_frame", None)
        th_prefix = getattr(self, "wizard_report_thumbnails_failed_prefix", None)
        if mc_frame is None or mc_prefix is None or th_frame is None or th_prefix is None:
            return
        self._refresh_wizard_report_failure_row(
            WIZARD_STEP_MODELCHECK,
            frame=mc_frame,
            prefix_label=mc_prefix,
            step_name="ModelCHECK",
            log_path_attr="_wizard_report_modelcheck_failed_log_path",
        )
        self._refresh_wizard_report_failure_row(
            WIZARD_STEP_JPEG_3D,
            frame=th_frame,
            prefix_label=th_prefix,
            step_name="Thumbnails",
            log_path_attr="_wizard_report_thumbnails_failed_log_path",
        )

    def _wizard_scan_show_next_after_batch(self, step: int) -> bool:
        """True when Scan Templates finished in this session (show Next >, not re-scan)."""
        if step != WIZARD_STEP_SCAN or self._wizard_scan_step_has_failed():
            return False
        if self._wizard_step_has_remaining_dxc(step):
            return False
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None or not scan_templates:
            return False
        if not self._wizard_scan_outputs_complete(batch_dir):
            return False
        return self._wizard_batch_session_active_for_step(step)

    def _wizard_batch_primary_action_label(self, step: int) -> str:
        if step == WIZARD_STEP_SCAN:
            return "Scan Templates >"
        if step == WIZARD_STEP_MODELCHECK:
            return "Run ModelCHECK >"
        if step == WIZARD_STEP_JPEG_3D:
            return "Thumbnails >"
        return "Next >"

    def _on_wizard_back(self) -> None:
        if self._wizard_step <= WIZARD_STEP_SETUP:
            return
        if self._wizard_batch_waiting_on_step(self._wizard_step):
            return
        self._automatic_wizard_paused = True
        self._cancel_automatic_wizard_chain()
        self._cancel_wizard_batch_output_watch()
        self._set_wizard_step(self._wizard_step - 1)

    def _on_wizard_skip_step(self) -> None:
        step = self._wizard_step
        self._automatic_wizard_paused = False
        self._cancel_automatic_wizard_chain()
        self._cancel_wizard_batch_output_watch()
        self._close_batch_runner_window()
        if step == WIZARD_STEP_SCAN:
            ok, err = self._clear_start_mcs()
            if not ok:
                messagebox.showwarning(
                    "Scan Templates",
                    "Could not reset config\\start.mcs:\n\n" + err,
                )
                return
            if self._warn_wizard_working_directory_missing_models():
                return
            self._discard_working_templates_on_skip()
            self._wizard_step_outcome[WIZARD_STEP_SCAN] = "skipped"
            self._set_wizard_step(WIZARD_STEP_MODELCHECK)
        elif step == WIZARD_STEP_MODELCHECK:
            self._wizard_step_outcome[WIZARD_STEP_MODELCHECK] = "skipped"
            self._set_wizard_step(WIZARD_STEP_JPEG_3D)
        elif step == WIZARD_STEP_JPEG_3D:
            self._wizard_step_outcome[WIZARD_STEP_JPEG_3D] = "skipped"
            self._set_wizard_step(WIZARD_STEP_REPORT)
            self._update_create_report_task_list(advance_from_jpeg=False)

    def _on_wizard_next(self, *, from_auto: bool = False) -> None:
        if from_auto and self._automatic_wizard_paused:
            return
        if not from_auto:
            self._automatic_wizard_paused = False
        step = self._wizard_step
        if step == WIZARD_STEP_SETUP:
            if not self._wizard_setup_valid():
                wd = (self.working_directory.get() or "").strip()
                if not wd:
                    messagebox.showwarning(
                        "Missing Working Directory", "Please enter a working directory."
                    )
                    return
                if not _working_directory_ok_for_go(wd):
                    messagebox.showwarning(
                        "Working directory",
                        "Working directory must be an existing folder, or a new folder name "
                        "under an existing folder.",
                    )
                    return
                if _path_contains_spaces(wd):
                    self._warn_if_working_directory_has_spaces()
                    return
                lp = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
                if not lp:
                    messagebox.showwarning("Missing Creo Loadpoint", "Please enter a Creo loadpoint.")
                    return
                if not _creo_loadpoint_has_parametric_dir(lp):
                    self._warn_if_creo_loadpoint_missing_parametric()
                    return
                messagebox.showerror(
                    "Setup",
                    "Could not find ptcdbatch.bat under the loadpoint or kill.bat next to the app.",
                )
                return
            self._persist_working_directory_and_loadpoint()
            if self._warn_wizard_working_directory_missing_models():
                return
            self._refresh_task_options()
            self._set_wizard_step(WIZARD_STEP_SCAN)
            return
        if step == WIZARD_STEP_SCAN:
            if self._wizard_batch_waiting_on_step(step):
                return
            if self._wizard_scan_show_next_after_batch(step):
                self._wizard_advance_one_step_after_batch()
                return
            if self._go_in_progress:
                return
            if from_auto:
                self._skip_timed_out_prompt_on_go = True
            self._on_go()
            return
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            if self._wizard_batch_waiting_on_step(step):
                return
            if self._wizard_batch_ready_for_next(step):
                self._wizard_advance_one_step_after_batch()
                return
            if from_auto:
                if step == WIZARD_STEP_JPEG_3D:
                    self._on_wizard_automatic_thumbnails()
                    return
                if step == WIZARD_STEP_MODELCHECK and self._wizard_batch_runner_finished_for_step(step):
                    if self._wizard_batch_ready_for_auto_advance(step):
                        self._wizard_advance_one_step_after_batch()
                    return
                if self._wizard_batch_ready_for_auto_advance(step):
                    self._wizard_advance_one_step_after_batch()
                    return
            if self._go_in_progress:
                return
            if step == WIZARD_STEP_JPEG_3D:
                self.task.set(self._wizard_thumbnails_task_display_to_run())
            if from_auto:
                self._skip_timed_out_prompt_on_go = True
            self._on_go()
            return
        if step == WIZARD_STEP_REPORT:
            self._on_write_summary_report()

    def _on_wizard_automatic_thumbnails(self) -> None:
        """Automatic mode on Thumbnails: chain part → assembly → drawing; never restart an finished pass."""
        step = WIZARD_STEP_JPEG_3D
        if self._wizard_batch_waiting_on_step(step) or self._go_in_progress:
            return
        if self._wizard_batch_ready_for_next(step):
            self._wizard_advance_one_step_after_batch()
            return
        if self._wizard_thumbnails_watch_ready_unprocessed(step):
            return
        if not self._wizard_thumbnails_all_phases_attempted():
            self._skip_timed_out_prompt_on_go = True
            self._wizard_thumbnails_chain_next_subphase_auto()
            return
        if self._wizard_batch_ready_for_auto_advance(step):
            self._wizard_advance_one_step_after_batch()

    def _on_wizard_open_report(self) -> None:
        path = self._working_directory_index_html_path()
        if path is None:
            messagebox.showwarning(
                "Open Report",
                "index.html was not found in the working directory.",
            )
            return
        try:
            webbrowser.open(path.as_uri())
        except OSError as exc:
            messagebox.showerror(
                "Open Failed",
                f"Could not open report in browser.\n\n{exc}",
            )

    def _on_wizard_browse_template(self, kind: str) -> None:
        if self._wizard_batch_waiting_on_step(WIZARD_STEP_SCAN):
            return
        labels = {k: label.rstrip(".") for k, label in _START_TEMPLATE_KINDS}
        if not self._scan_kind_enabled(kind):
            title = labels.get(kind, "Template")
            messagebox.showinfo(
                "Scan settings",
                f"{title} is not available because that model type is turned off in "
                "Settings → Scan settings…",
            )
            return
        title = labels.get(kind, "Template")
        wd = (self.working_directory.get() or "").strip()
        if not wd or not Path(wd).is_dir():
            messagebox.showwarning(
                "Template",
                "Set a working directory on the Setup step before choosing a template.",
            )
            return
        selected = fd.askopenfilename(
            title=title,
            initialdir=wd,
            filetypes=[
                (f"Creo {kind} files", f"*.{kind};*.{kind}.*"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        source = Path(selected)
        if not source.is_file():
            messagebox.showerror("Template", f"File not found:\n{source}")
            return
        if not self._creo_model_filename_matches(source.name, kind):
            messagebox.showerror(
                "Template",
                f"Select a Creo {kind} file (*.{kind} or *.{kind}.*).",
            )
            return
        dest_dir = self._start_templates_dir()
        if dest_dir is None:
            messagebox.showwarning(
                "Template",
                "Set a working directory on the Setup step before choosing a template.",
            )
            return
        self._pending_template_sources[kind] = source.resolve()
        self._refresh_task_options()
        self._refresh_wizard_template_status()
        self._refresh_wizard_footer()

    def _refresh_wizard_ui(self) -> None:
        self._refresh_wizard_stepper()
        self._refresh_wizard_step_panels()
        self._refresh_wizard_footer()
        self._refresh_menu_bar_state()

    def _refresh_wizard_stepper(self) -> None:
        frame = getattr(self, "wizard_stepper_frame", None)
        if frame is None:
            return
        for widget in frame.winfo_children():
            widget.destroy()
        current = self._wizard_step
        for idx, label in enumerate(WIZARD_STEPPER_LABELS):
            if idx > 0:
                ctk.CTkLabel(
                    frame,
                    text="—",
                    font=ctk.CTkFont(size=WIZARD_STEPPER_FONT_SIZE),
                    text_color="#888888",
                ).pack(side="left", padx=6)
            outcome = self._wizard_step_outcome.get(idx, "")
            if idx < current:
                if outcome == "skipped":
                    mark = "—"
                    color = "#888888"
                else:
                    mark = "✓"
                    color = "#2E7D32"
            elif idx == current:
                mark = str(idx + 1)
                color = "#3B8ED0"
            else:
                mark = str(idx + 1)
                color = "#AAAAAA"
            step_text = f"{mark} {label}"
            ctk.CTkLabel(
                frame,
                text=step_text,
                font=ctk.CTkFont(
                    size=WIZARD_STEPPER_FONT_SIZE,
                    weight="bold" if idx == current else "normal",
                ),
                text_color=color,
            ).pack(side="left", padx=4)

    def _refresh_wizard_step_panels(self) -> None:
        step = self._wizard_step
        panels = (
            getattr(self, "wizard_setup_frame", None),
            getattr(self, "wizard_scan_frame", None),
            getattr(self, "wizard_batch_frame", None),
            getattr(self, "wizard_batch_frame", None),
            getattr(self, "wizard_report_frame", None),
        )
        for panel in {p for p in panels if p is not None}:
            panel.pack_forget()
        title = getattr(self, "wizard_step_title_label", None)
        intro = getattr(self, "wizard_step_intro_label", None)
        if title is not None:
            title.configure(text=self._wizard_step_title(step))
        if intro is not None:
            intro.configure(text=self._wizard_step_intro(step))
        if step == WIZARD_STEP_SETUP and getattr(self, "wizard_setup_frame", None):
            self.wizard_setup_frame.pack(fill="both", expand=True)
            self._refresh_wizard_setup_status()
        elif step == WIZARD_STEP_SCAN and getattr(self, "wizard_scan_frame", None):
            self.wizard_scan_frame.pack(fill="both", expand=True)
            self._refresh_wizard_template_status()
        elif step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D) and getattr(
            self, "wizard_batch_frame", None
        ):
            self.wizard_batch_frame.pack(fill="both", expand=True)
            self._refresh_wizard_batch_status()
        elif step == WIZARD_STEP_REPORT and getattr(self, "wizard_report_frame", None):
            self.wizard_report_frame.pack(fill="both", expand=True)
            self._refresh_wizard_report_status()

    def _refresh_wizard_setup_status(self) -> None:
        label = getattr(self, "wizard_setup_status_label", None)
        if label is None:
            return
        wd = (self.working_directory.get() or "").strip()
        if self._working_directory_index_html_path(wd):
            label.configure(
                text="Report (index.html) found in the working directory.",
                text_color="#2E7D32",
            )
            if not label.winfo_ismapped():
                label.pack(anchor="w", pady=(8, 0))
            return
        if (
            wd
            and _working_directory_exists_as_dir(wd)
            and not self._wizard_working_directory_has_models(wd)
        ):
            label.configure(
                text=(
                    "No Creo models (.prt, .asm, .drw) found in this folder — "
                    "add models before continuing."
                ),
                text_color="#C62828",
            )
            if not label.winfo_ismapped():
                label.pack(anchor="w", pady=(8, 0))
            return
        label.pack_forget()

    def _refresh_wizard_template_row_controls(self) -> None:
        """Enable or disable Browse and × on visible template rows."""
        waiting = self._wizard_batch_waiting_on_step(WIZARD_STEP_SCAN)
        browse_buttons = getattr(self, "_wizard_template_browse_buttons", {})
        clear_buttons = getattr(self, "_wizard_template_clear_buttons", {})
        for kind in ("prt", "asm", "drw"):
            if not self._wizard_template_kind_visible(kind):
                continue
            browse = browse_buttons.get(kind)
            if browse is not None:
                browse.configure(state="disabled" if waiting else "normal")
            clear_btn = clear_buttons.get(kind)
            if clear_btn is None:
                continue
            dest = self._template_dest_path(kind)
            if dest is not None and dest.is_file():
                clear_btn.pack(side="right", padx=(0, 4))
                clear_btn.configure(state="disabled" if waiting else "normal")
            else:
                clear_btn.pack_forget()

    def _refresh_wizard_template_status(self) -> None:
        labels = getattr(self, "_wizard_template_status_labels", None)
        if not labels:
            return
        self._refresh_wizard_template_row_visibility()
        if not self._wizard_batch_waiting_on_step(WIZARD_STEP_SCAN):
            for kind, label in labels.items():
                if not self._wizard_template_kind_visible(kind):
                    continue
                dest = self._template_dest_path(kind)
                pending = self._pending_template_sources.get(kind)
                if dest is not None and dest.is_file():
                    label.configure(text=f"Set ({dest.name})", text_color="#2E7D32")
                elif pending is not None:
                    label.configure(
                        text=f"Selected ({pending.name}) — runs on Scan Templates >",
                        text_color="#111111",
                    )
                else:
                    label.configure(text="Not set", text_color="#666666")
            count = self._templates_upload_count()
            summary = getattr(self, "wizard_scan_summary_label", None)
            if summary is not None:
                has_scan = self._templates_dir_has_scan_xml()
                if has_scan:
                    summary.configure(
                        text="Template scan complete.",
                        text_color="#2E7D32",
                    )
                elif count:
                    summary.configure(
                        text=f"{count} template file(s) ready — use Scan Templates > to continue.",
                        text_color="#111111",
                    )
                else:
                    summary.configure(
                        text="No templates uploaded yet — skip this step or browse below.",
                        text_color="#666666",
                    )
        self._refresh_wizard_template_row_controls()
        self._refresh_wizard_step_batch_progress(WIZARD_STEP_SCAN)

    def _scan_templates_skip_allowed(self) -> bool:
        """Skip when no templates uploaded, or scan XML already exists from a prior run."""
        if self._templates_upload_count() == 0:
            return True
        return self._templates_dir_has_scan_xml()

    def _wizard_step_skip_allowed(self, step: int) -> bool:
        if self._wizard_batch_waiting_on_step(step):
            return False
        if step == WIZARD_STEP_SCAN:
            if self._wizard_batch_ready_for_next(step):
                return False
            return self._scan_templates_skip_allowed()
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return True
        return False

    def _latest_models_for_task(self, working_dir: Path, task_display: str) -> list[Path]:
        """Same model list GO uses: top-level only, latest revision per base name."""
        scanned = self._scan_models_non_recursive(
            working_dir,
            extensions=self._model_scan_extensions_for_task(task_display),
        )
        return self._get_latest_model_files(scanned)

    def _format_batch_model_count_message(
        self,
        latest_files: list[Path],
        pending_files: list[Path],
        _task_display: str,
    ) -> str:
        if not latest_files:
            return "No models to batch in the working directory yet."
        total = len(latest_files)
        pending = len(pending_files)
        if pending <= 0:
            models_word = "model" if total == 1 else "models"
            return f"All {total} {models_word} already have output for this step."
        if pending == total:
            models_word = "model" if pending == 1 else "models"
            return f"{pending} {models_word} will be batched (none have output yet)."
        return (
            f"{pending} of {total} models still need output and will be batched "
            f"({total - pending} already complete)."
        )

    def _refresh_wizard_batch_status(self) -> None:
        label = getattr(self, "wizard_batch_status_label", None)
        if label is None:
            return
        step = self._wizard_step
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            self._refresh_wizard_step_batch_progress(step)
        if self._wizard_batch_waiting_on_step(step):
            return
        wd = (self.working_directory.get() or "").strip()
        cache = self._wizard_batch_status_cache
        if (
            isinstance(cache, dict)
            and cache.get("step") == step
            and cache.get("wd") == wd
            and isinstance(cache.get("text"), str)
        ):
            label.configure(
                text=str(cache["text"]),
                text_color=str(cache.get("color") or "#666666"),
            )
            batch_dir, _ = self._wizard_batch_dir_for_step(step)
            if batch_dir is not None:
                self._refresh_wizard_batch_failed_label(step, batch_dir)
            return
        label.configure(text="Checking models…", text_color="#666666")
        job = self._wizard_batch_status_job
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._wizard_batch_status_job = None
        self._wizard_batch_status_gen += 1
        gen = self._wizard_batch_status_gen
        task_display = self._wizard_task_display_for_step(step)
        threading.Thread(
            target=self._wizard_batch_status_worker,
            args=(step, wd, task_display, gen),
            daemon=True,
        ).start()

    def _wizard_batch_status_worker(
        self, step: int, wd: str, task_display: str, gen: int
    ) -> None:
        """Scan models off the UI thread; marshal result back with ``after``."""
        result: dict[str, object]
        try:
            if not wd:
                result = {
                    "text": "Set the working directory on the Setup step.",
                    "color": "#666666",
                    "outputs_complete": False,
                    "working_dir": None,
                }
            else:
                working_dir = Path(wd).expanduser()
                if not working_dir.is_dir() and not working_dir.parent.is_dir():
                    result = {
                        "text": "Working directory is not ready.",
                        "color": "#666666",
                        "outputs_complete": False,
                        "working_dir": None,
                    }
                elif working_dir.is_dir():
                    if step == WIZARD_STEP_JPEG_3D:
                        latest_files = self._wizard_thumbnails_latest_models(working_dir)
                        pending_files = self._wizard_step_pending_models(step)
                    else:
                        latest_files = self._latest_models_for_task(
                            working_dir, task_display
                        )
                        task_kind = self._runner_task_kind(task_display)
                        pending_files = self._filter_models_missing_task_output(
                            latest_files, working_dir, task_kind
                        )
                    lines: list[str] = [
                        self._format_batch_model_count_message(
                            latest_files, pending_files, task_display
                        )
                    ]
                    ok = bool(latest_files)
                    if step == WIZARD_STEP_MODELCHECK:
                        has_xml = self._working_directory_has_modelcheck_xml(wd)
                        lines.append(
                            "ModelCHECK XML found."
                            if has_xml
                            else "ModelCHECK XML not found yet."
                        )
                        ok = ok or has_xml or bool(pending_files)
                    elif step == WIZARD_STEP_JPEG_3D:
                        has_thumbs = self._working_directory_has_thumbnail_files(wd)
                        lines.append(
                            "Thumbnail files found."
                            if has_thumbs
                            else "Thumbnail files not found yet."
                        )
                        ok = ok or has_thumbs or bool(pending_files)
                    outputs_complete = not bool(pending_files) and (
                        step != WIZARD_STEP_JPEG_3D
                        or self._working_directory_thumbnails_complete(wd)
                    )
                    result = {
                        "text": "\n".join(lines),
                        "color": "#2E7D32" if ok else "#666666",
                        "outputs_complete": outputs_complete,
                        "working_dir": working_dir,
                    }
                else:
                    result = {
                        "text": "Working folder will be created when you run this step.",
                        "color": "#111111",
                        "outputs_complete": False,
                        "working_dir": None,
                    }
        except OSError:
            result = {
                "text": "Could not scan the working directory.",
                "color": "#666666",
                "outputs_complete": False,
                "working_dir": None,
            }
        try:
            self.after(
                0,
                lambda s=step, w=wd, g=gen, r=result: self._apply_wizard_batch_status_result(
                    s, w, g, r
                ),
            )
        except tk.TclError:
            pass

    def _apply_wizard_batch_status_result(
        self,
        step: int,
        wd: str,
        gen: int,
        result: dict[str, object],
    ) -> None:
        if gen != self._wizard_batch_status_gen or self._wizard_step != step:
            return
        label = getattr(self, "wizard_batch_status_label", None)
        if label is None:
            return
        if self._wizard_batch_waiting_on_step(step):
            return
        text = str(result.get("text") or "")
        color = str(result.get("color") or "#666666")
        label.configure(text=text, text_color=color)
        self._wizard_batch_status_cache = {
            "step": step,
            "wd": wd,
            "text": text,
            "color": color,
            "outputs_complete": bool(result.get("outputs_complete")),
        }
        working_dir = result.get("working_dir")
        if isinstance(working_dir, Path):
            self._refresh_wizard_batch_failed_label(step, working_dir)
        self._refresh_wizard_footer()

    def _refresh_wizard_batch_status_heavy(self, step: int) -> None:
        """Compatibility entry: schedule the same background status scan."""
        self._wizard_batch_status_job = None
        if self._wizard_step != step:
            return
        wd = (self.working_directory.get() or "").strip()
        self._wizard_batch_status_gen += 1
        gen = self._wizard_batch_status_gen
        task_display = self._wizard_task_display_for_step(step)
        threading.Thread(
            target=self._wizard_batch_status_worker,
            args=(step, wd, task_display, gen),
            daemon=True,
        ).start()

    def _refresh_wizard_report_status(self) -> None:
        label = getattr(self, "wizard_report_status_label", None)
        if label is None:
            return
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            label.configure(text="Working directory is not ready.", text_color="#666666")
            return
        has_xml = self._working_directory_has_modelcheck_xml(wd)
        has_thumbs = self._working_directory_has_thumbnail_files(wd)
        has_index = self._working_directory_index_html_path(wd) is not None
        lines: list[str] = []
        lines.append("ModelCHECK XML found." if has_xml else "ModelCHECK XML not found yet.")
        lines.append(
            "Thumbnail files found." if has_thumbs else "Thumbnail files not found yet."
        )
        lines.append("Report (index.html) found." if has_index else "Report (index.html) not found yet.")
        if self._automatic_mode and self._report_job_running:
            lines.append("Automatic mode — creating the report…")
        bundle = _app_bundle_dir()
        if not (bundle / "model_checks.xml").is_file():
            lines.append("Missing model_checks.xml next to the app.")
        if not (bundle / "report_template.html.j2").is_file():
            lines.append("Missing report_template.html.j2 next to the app.")
        ok = _summary_report_inputs_ok(wd) or has_index
        label.configure(
            text="\n".join(lines),
            text_color="#2E7D32" if ok else "#666666",
        )
        self._refresh_wizard_report_batch_failures()

    def _refresh_wizard_footer(self) -> None:
        back = getattr(self, "wizard_back_button", None)
        skip = getattr(self, "wizard_skip_button", None)
        open_rpt = getattr(self, "wizard_open_report_button", None)
        nxt = getattr(self, "wizard_next_button", None)
        if back is None or skip is None or nxt is None:
            return
        step = self._wizard_step
        batch_waiting = self._wizard_batch_waiting_on_step(step)
        if step > WIZARD_STEP_SETUP:
            back.pack(side="left")
            back.configure(state="disabled" if batch_waiting else "normal")
        else:
            back.pack_forget()
        if self._wizard_step_skip_allowed(step):
            skip.pack(side="left", padx=(0, 12))
            skip.configure(state="normal")
        else:
            skip.pack_forget()
        wd = (self.working_directory.get() or "").strip()
        if step == WIZARD_STEP_SETUP:
            nxt.configure(text="Next >", state="normal" if self._wizard_setup_valid() else "disabled")
        elif step == WIZARD_STEP_SCAN:
            watch = self._wizard_batch_watch
            scan_failed = (
                watch is not None
                and watch.get("step") == WIZARD_STEP_SCAN
                and watch.get("scan_failed")
            )
            if scan_failed:
                can_scan = self._templates_upload_count() > 0 and self._go_fields_valid()
                nxt.configure(
                    text="Scan Templates >",
                    state="normal" if can_scan else "disabled",
                )
            elif self._wizard_batch_waiting_on_step(step):
                nxt.configure(text="Waiting…", state="disabled")
            elif self._wizard_scan_show_next_after_batch(step):
                nxt.configure(text="Next >", state="normal")
            else:
                can_scan = self._templates_upload_count() > 0 and self._go_fields_valid()
                nxt.configure(
                    text="Scan Templates >",
                    state="normal" if can_scan else "disabled",
                )
        elif step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            if self._wizard_batch_waiting_on_step(step):
                nxt.configure(text="Waiting…", state="disabled")
            elif self._wizard_batch_ready_for_next(step):
                nxt.configure(text="Next >", state="normal")
            else:
                nxt.configure(
                    text=self._wizard_batch_primary_action_label(step),
                    state="normal" if self._go_fields_valid() else "disabled",
                )
        elif step == WIZARD_STEP_REPORT:
            busy = self._report_job_running
            report_ok = _summary_report_inputs_ok(wd) and not busy
            nxt.configure(
                text="Creating Report..." if busy else "Create Report",
                state="normal" if report_ok else "disabled",
            )
        if open_rpt is not None:
            busy = self._report_job_running
            has_index = self._working_directory_index_html_path(wd) is not None
            open_rpt.pack_forget()
            if step == WIZARD_STEP_SETUP and has_index:
                open_rpt.pack(side="left")
                open_rpt.configure(state="normal")
            elif step == WIZARD_STEP_REPORT and has_index:
                open_rpt.pack(side="right", padx=(0, 12))
                open_rpt.configure(state="normal" if not busy else "disabled")
        if step == WIZARD_STEP_SETUP:
            self._refresh_wizard_setup_status()
        self._maybe_schedule_automatic_advance()
        self._refresh_menu_bar_state()

    def _build_ui(self) -> None:
        self._build_ttk_styles()
        container = ctk.CTkFrame(self, corner_radius=0, fg_color="#ECECEC")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        title = ctk.CTkLabel(
            container,
            text="PDSVISION Cad Assessment Tool",
            font=ctk.CTkFont(size=18, weight="normal"),
            text_color="#111111",
        )
        title.pack(anchor="w", padx=32, pady=(6, 4))

        self.working_directory = ctk.StringVar(value="")
        self.creo_loadpoint = ctk.StringVar(value="")
        self.task = ctk.StringVar(value="")
        self._task_display_to_filename: dict[str, str] = {}
        self._task_filename_to_description: dict[str, str] = {}

        self.wizard_stepper_frame = ctk.CTkFrame(container, fg_color="transparent")
        self.wizard_stepper_frame.pack(fill="x", padx=32, pady=(4, 8))

        self.wizard_step_title_label = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#111111",
        )
        self.wizard_step_title_label.pack(anchor="w", padx=32, pady=(0, 2))

        self.wizard_step_intro_label = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#444444",
            wraplength=500,
            justify="left",
        )
        self.wizard_step_intro_label.pack(anchor="w", padx=32, pady=(0, 6))

        self.wizard_step_body = ctk.CTkFrame(container, fg_color="transparent")
        self.wizard_step_body.pack(fill="both", expand=True, padx=32, pady=(0, 8))

        self.wizard_setup_frame = ctk.CTkFrame(self.wizard_step_body, fg_color="transparent")
        self._build_path_row(
            self.wizard_setup_frame,
            label_text="Working Directory",
            variable=self.working_directory,
            browse_kind="directory",
        )
        self._build_path_row(
            self.wizard_setup_frame,
            label_text="Creo Loadpoint",
            variable=self.creo_loadpoint,
            browse_kind="directory",
        )
        self.wizard_setup_status_label = ctk.CTkLabel(
            self.wizard_setup_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#2E7D32",
            anchor="w",
            justify="left",
            wraplength=500,
        )

        self.wizard_scan_frame = ctk.CTkFrame(self.wizard_step_body, fg_color="transparent")
        self.wizard_scan_summary_label = ctk.CTkLabel(
            self.wizard_scan_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#666666",
            anchor="w",
            justify="left",
        )
        self.wizard_scan_summary_label.pack(anchor="w", pady=(0, 8))
        self._wizard_template_status_labels: dict[str, ctk.CTkLabel] = {}
        self._wizard_template_browse_buttons: dict[str, ctk.CTkButton] = {}
        self._wizard_template_clear_buttons: dict[str, ctk.CTkButton] = {}
        self._wizard_template_rows: dict[str, ctk.CTkFrame] = {}
        template_labels = {
            "prt": "Part template",
            "asm": "Assembly template",
            "drw": "Drawing template",
        }
        for kind, row_label in template_labels.items():
            row = ctk.CTkFrame(self.wizard_scan_frame, fg_color="transparent")
            self._wizard_template_rows[kind] = row
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=row_label,
                width=140,
                anchor="w",
                font=ctk.CTkFont(size=12),
                text_color="#111111",
            ).pack(side="left")
            browse_btn = ctk.CTkButton(
                row,
                text="Browse...",
                width=88,
                height=26,
                corner_radius=6,
                border_width=0,
                fg_color="#3B8ED0",
                text_color="#FFFFFF",
                hover_color="#367DB6",
                font=ctk.CTkFont(size=13),
                command=lambda k=kind: self._on_wizard_browse_template(k),
            )
            browse_btn.pack(side="right")
            self._wizard_template_browse_buttons[kind] = browse_btn
            clear_btn = ctk.CTkButton(
                row,
                text="×",
                width=24,
                height=26,
                corner_radius=6,
                border_width=1,
                fg_color="#ECECEC",
                border_color="#8F98A3",
                text_color="#666666",
                hover_color="#DDDDDD",
                font=ctk.CTkFont(size=16),
                command=lambda k=kind: self._on_wizard_clear_template(k),
            )
            self._wizard_template_clear_buttons[kind] = clear_btn
            status = ctk.CTkLabel(
                row,
                text="Not set",
                anchor="w",
                font=ctk.CTkFont(size=12),
                text_color="#666666",
            )
            status.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self._wizard_template_status_labels[kind] = status

        self.wizard_scan_progress_frame = ctk.CTkFrame(self.wizard_scan_frame, fg_color="transparent")
        self.wizard_scan_progress_label = ctk.CTkLabel(
            self.wizard_scan_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#111111",
            anchor="w",
            justify="left",
        )
        self.wizard_scan_progress_label.pack(anchor="w", pady=(0, 4))
        self.wizard_scan_progress_bar = ctk.CTkProgressBar(
            self.wizard_scan_progress_frame,
            width=460,
            height=12,
            progress_color="#3B8ED0",
        )
        self.wizard_scan_progress_bar.pack(anchor="w", fill="x")
        self.wizard_scan_progress_bar.set(0)
        self._refresh_wizard_template_row_visibility()

        self.wizard_batch_frame = ctk.CTkFrame(self.wizard_step_body, fg_color="transparent")
        self.wizard_batch_status_label = ctk.CTkLabel(
            self.wizard_batch_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#666666",
            anchor="w",
            justify="left",
            wraplength=500,
        )
        self.wizard_batch_status_label.pack(anchor="w")

        self.wizard_batch_progress_frame = ctk.CTkFrame(self.wizard_batch_frame, fg_color="transparent")
        self.wizard_batch_progress_label = ctk.CTkLabel(
            self.wizard_batch_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#111111",
            anchor="w",
            justify="left",
        )
        self.wizard_batch_progress_label.pack(anchor="w", pady=(0, 4))
        self.wizard_batch_progress_bar = ctk.CTkProgressBar(
            self.wizard_batch_progress_frame,
            width=460,
            height=12,
            progress_color="#3B8ED0",
        )
        self.wizard_batch_progress_bar.pack(anchor="w", fill="x")
        self.wizard_batch_progress_bar.set(0)
        self.wizard_jpeg_part_progress_frame = ctk.CTkFrame(
            self.wizard_batch_frame, fg_color="transparent"
        )
        self.wizard_jpeg_part_progress_label = ctk.CTkLabel(
            self.wizard_jpeg_part_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#111111",
            anchor="w",
            justify="left",
        )
        self.wizard_jpeg_part_progress_label.pack(anchor="w", pady=(0, 4))
        self.wizard_jpeg_part_progress_bar = ctk.CTkProgressBar(
            self.wizard_jpeg_part_progress_frame,
            width=460,
            height=12,
            progress_color="#3B8ED0",
        )
        self.wizard_jpeg_part_progress_bar.pack(anchor="w", fill="x")
        self.wizard_jpeg_part_progress_bar.set(0)
        self.wizard_jpeg_assembly_progress_frame = ctk.CTkFrame(
            self.wizard_batch_frame, fg_color="transparent"
        )
        self.wizard_jpeg_assembly_progress_label = ctk.CTkLabel(
            self.wizard_jpeg_assembly_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#111111",
            anchor="w",
            justify="left",
        )
        self.wizard_jpeg_assembly_progress_label.pack(anchor="w", pady=(0, 4))
        self.wizard_jpeg_assembly_progress_bar = ctk.CTkProgressBar(
            self.wizard_jpeg_assembly_progress_frame,
            width=460,
            height=12,
            progress_color="#3B8ED0",
        )
        self.wizard_jpeg_assembly_progress_bar.pack(anchor="w", fill="x")
        self.wizard_jpeg_assembly_progress_bar.set(0)
        self.wizard_jpeg_drawing_progress_frame = ctk.CTkFrame(
            self.wizard_batch_frame, fg_color="transparent"
        )
        self.wizard_jpeg_drawing_progress_label = ctk.CTkLabel(
            self.wizard_jpeg_drawing_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#111111",
            anchor="w",
            justify="left",
        )
        self.wizard_jpeg_drawing_progress_label.pack(anchor="w", pady=(0, 4))
        self.wizard_jpeg_drawing_progress_bar = ctk.CTkProgressBar(
            self.wizard_jpeg_drawing_progress_frame,
            width=460,
            height=12,
            progress_color="#3B8ED0",
        )
        self.wizard_jpeg_drawing_progress_bar.pack(anchor="w", fill="x")
        self.wizard_jpeg_drawing_progress_bar.set(0)
        self.wizard_batch_automatic_label = ctk.CTkLabel(
            self.wizard_batch_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#1565C0",
            anchor="w",
            justify="left",
            wraplength=500,
        )
        self.wizard_batch_failed_frame = ctk.CTkFrame(
            self.wizard_batch_frame,
            fg_color="transparent",
        )
        self.wizard_batch_failed_prefix = ctk.CTkLabel(
            self.wizard_batch_failed_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#C62828",
        )
        self.wizard_batch_failed_prefix.pack(side="left", padx=0)
        self.wizard_batch_failed_link = ctk.CTkLabel(
            self.wizard_batch_failed_frame,
            text="here",
            font=ctk.CTkFont(size=12, underline=True),
            text_color="#1565C0",
            cursor="hand2",
        )
        self.wizard_batch_failed_link.bind(
            "<Button-1>", lambda _event: self._on_wizard_open_batch_failed_log()
        )
        self.wizard_batch_failed_link.pack(side="left", padx=0)
        self.wizard_batch_failed_suffix = ctk.CTkLabel(
            self.wizard_batch_failed_frame,
            text=" to review files",
            font=ctk.CTkFont(size=12),
            text_color="#C62828",
        )
        self.wizard_batch_failed_suffix.pack(side="left", padx=0)

        self.wizard_report_frame = ctk.CTkFrame(self.wizard_step_body, fg_color="transparent")
        self.wizard_report_status_label = ctk.CTkLabel(
            self.wizard_report_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#666666",
            anchor="w",
            justify="left",
            wraplength=500,
        )
        self.wizard_report_status_label.pack(anchor="w")

        def _make_report_failed_row(parent, on_click) -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            prefix = ctk.CTkLabel(
                row,
                text="",
                font=ctk.CTkFont(size=12),
                text_color="#C62828",
            )
            prefix.pack(side="left", padx=0)
            link = ctk.CTkLabel(
                row,
                text="here",
                font=ctk.CTkFont(size=12, underline=True),
                text_color="#1565C0",
                cursor="hand2",
            )
            link.bind("<Button-1>", lambda _event: on_click())
            link.pack(side="left", padx=0)
            suffix = ctk.CTkLabel(
                row,
                text=" to review files",
                font=ctk.CTkFont(size=12),
                text_color="#C62828",
            )
            suffix.pack(side="left", padx=0)
            return row, prefix

        self.wizard_report_modelcheck_failed_frame, self.wizard_report_modelcheck_failed_prefix = (
            _make_report_failed_row(
                self.wizard_report_frame,
                self._on_wizard_open_report_modelcheck_failed_log,
            )
        )
        self.wizard_report_thumbnails_failed_frame, self.wizard_report_thumbnails_failed_prefix = (
            _make_report_failed_row(
                self.wizard_report_frame,
                self._on_wizard_open_report_thumbnails_failed_log,
            )
        )

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=32, pady=(0, 6))
        self.wizard_back_button = ctk.CTkButton(
            footer,
            text="< Back",
            width=100,
            height=28,
            corner_radius=6,
            border_width=1,
            fg_color="#ECECEC",
            border_color="#8F98A3",
            text_color="#111111",
            hover_color="#DDDDDD",
            font=ctk.CTkFont(size=13),
            command=self._on_wizard_back,
        )
        self.wizard_back_button.pack(side="left")
        self.wizard_open_report_button = ctk.CTkButton(
            footer,
            text="Open Report",
            width=120,
            height=28,
            corner_radius=6,
            border_width=0,
            fg_color="#2E7D32",
            text_color="#FFFFFF",
            hover_color="#256628",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_wizard_open_report,
        )
        btn_bar = ctk.CTkFrame(footer, fg_color="transparent")
        self.wizard_footer_btn_bar = btn_bar
        btn_bar.pack(side="right")
        self.wizard_skip_button = ctk.CTkButton(
            btn_bar,
            text="Skip",
            width=100,
            height=28,
            corner_radius=6,
            border_width=1,
            fg_color="#ECECEC",
            border_color="#8F98A3",
            text_color="#111111",
            hover_color="#DDDDDD",
            font=ctk.CTkFont(size=13),
            command=self._on_wizard_skip_step,
        )
        self.wizard_next_button = ctk.CTkButton(
            btn_bar,
            text="Next >",
            width=140,
            height=28,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_wizard_next,
        )
        self.wizard_next_button.pack(side="right")

        def _on_working_directory_or_loadpoint_changed(*_args: object) -> None:
            if self._suppress_settings_autosave:
                return
            self._invalidate_working_dir_file_cache()
            self._refresh_task_options()
            self._persist_working_directory_and_loadpoint()
            if self._wizard_step == WIZARD_STEP_SCAN:
                self._refresh_wizard_template_status()
            self._refresh_wizard_footer()

        def _on_task_var_changed(*_args: object) -> None:
            if self._suppress_task_var_refresh:
                return
            self._refresh_wizard_ui()

        self.working_directory.trace_add("write", _on_working_directory_or_loadpoint_changed)
        self.creo_loadpoint.trace_add("write", _on_working_directory_or_loadpoint_changed)
        self.task.trace_add("write", _on_task_var_changed)

        self._set_wizard_step(WIZARD_STEP_SETUP)

    def _build_path_row(
        self,
        parent: ctk.CTkFrame,
        label_text: str,
        variable: ctk.StringVar,
        browse_kind: str,
    ) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x")

        row_label = ctk.CTkLabel(
            block,
            text=label_text,
            font=ctk.CTkFont(size=13),
            text_color="#111111",
        )
        row_label.pack(anchor="w", pady=(0, 1))

        line = ctk.CTkFrame(block, fg_color="transparent")
        line.pack(fill="x", pady=(0, 5))

        browse_button = ctk.CTkButton(
            line,
            text="Browse...",
            width=88,
            height=26,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=13),
            command=lambda: self._browse_target(variable, browse_kind),
        )
        browse_button.pack(side="right")

        entry = ctk.CTkEntry(
            line,
            textvariable=variable,
            height=26,
            corner_radius=2,
            border_width=1,
            fg_color="#FFFFFF",
            border_color="#8F98A3",
            text_color="#1F1F1F",
            font=ctk.CTkFont(size=13),
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if variable is self.creo_loadpoint:
            self.creo_loadpoint_entry = entry
            entry.configure(state="disabled")
        elif variable is self.working_directory:
            self.working_directory_entry = entry
            entry.configure(state="disabled")

    def _set_working_directory_value(self, value: str) -> None:
        """Set working directory text; entry is disabled so we briefly enable to refresh the display."""
        text = (value or "").strip()
        e = getattr(self, "working_directory_entry", None)
        if e is not None:
            e.configure(state="normal")
        self.working_directory.set(text)
        if e is not None:
            e.configure(state="disabled")

    def _set_creo_loadpoint_value(self, value: str) -> None:
        """Set Creo loadpoint text; entry is disabled so we briefly enable to refresh the display."""
        text = (value or "").strip().rstrip("\\/")
        e = getattr(self, "creo_loadpoint_entry", None)
        if e is not None:
            e.configure(state="normal")
        self.creo_loadpoint.set(text)
        if e is not None:
            e.configure(state="disabled")

    def _build_menu_bar(self) -> None:
        menubar = tk.Menu(self)
        self._menubar = menubar

        file_menu = tk.Menu(menubar, tearoff=0)
        self._file_menu = file_menu
        file_menu.add_command(label="New", command=self._on_file_menu_new)
        file_menu.add_command(label="Open...", command=self._on_file_menu_open)
        self._recent_scans_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_command(label="Save", command=self._on_file_menu_save)
        file_menu.add_command(label="Save as...", command=self._on_file_menu_save_as)
        file_menu.add_separator()
        file_menu.add_command(
            label="Open Working Directory",
            command=self._on_open_working_directory,
        )
        file_menu.add_command(label="Zip report...", command=self._on_file_menu_zip_report)
        file_menu.add_separator()
        file_menu.add_command(label="Pause", command=self._on_file_menu_pause)
        file_menu.add_command(label="Stop", command=self._on_file_menu_stop)
        file_menu.add_command(label="Start over...", command=self._on_file_menu_start_over)
        file_menu.add_command(label="Purge cache...", command=self._on_file_menu_purge_cache)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        general_settings_menu = tk.Menu(menubar, tearoff=0)
        general_settings_menu.add_command(
            label="Scan settings...",
            command=self._on_scan_settings,
        )
        general_settings_menu.add_command(
            label="Batch settings...",
            command=self._on_batch_settings,
        )
        general_settings_menu.add_command(
            label="Checks...",
            command=self._on_checks_settings,
        )
        general_settings_menu.add_checkbutton(
            label="Automatic mode",
            variable=self._automatic_mode_var,
            command=self._on_automatic_mode_toggle,
        )
        general_settings_menu.add_checkbutton(
            label="Debug",
            variable=self._debug_mode_var,
            command=self._on_debug_mode_toggle,
        )
        menubar.add_cascade(label="Settings", menu=general_settings_menu)

        self._configuration_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Configuration", menu=self._configuration_menu)

        self._help_menu = tk.Menu(menubar, tearoff=0)
        help_menu = self._help_menu
        help_menu.add_command(label="About...", command=self._on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=menubar)
        self._refresh_configuration_menu()
        self._refresh_menu_bar_state()

    def _wizard_batch_is_running(self) -> bool:
        watch = self._wizard_batch_watch
        if watch is None:
            return False
        step = watch.get("step")
        if not isinstance(step, int):
            return False
        return self._wizard_batch_waiting_on_step(step)

    def _batch_stop_available(self) -> bool:
        if self._wizard_batch_is_running():
            return True
        proc = self._batch_runner_process
        return proc is not None and proc.poll() is None

    def _app_menus_fully_enabled(self) -> bool:
        return (
            self._wizard_step == WIZARD_STEP_SETUP
            and not self._wizard_batch_is_running()
            and not self._report_job_running
        )

    def _refresh_menu_bar_state(self) -> None:
        """Setup-only full menus; while a batch/report runs, only File → Exit stays enabled."""
        menubar = self._menubar
        fm = getattr(self, "_file_menu", None)
        if menubar is None or fm is None:
            return
        fully_enabled = self._app_menus_fully_enabled()
        batch_stop = self._batch_stop_available()
        try:
            if bool(self._automatic_mode_var.get()) != self._automatic_mode:
                self._automatic_mode_var.set(self._automatic_mode)
            if bool(self._debug_mode_var.get()) != self._debug_mode:
                self._debug_mode_var.set(self._debug_mode)
        except tk.TclError:
            pass
        for label in ("Settings", "Configuration"):
            try:
                menubar.entryconfigure(label, state=tk.NORMAL if fully_enabled else tk.DISABLED)
            except tk.TclError:
                pass
        try:
            menubar.entryconfigure("Help", state=tk.NORMAL)
        except tk.TclError:
            pass
        for label in (
            "New",
            "Open...",
            "Save",
            "Save as...",
            "Start over...",
            "Purge cache...",
        ):
            try:
                fm.entryconfigure(label, state=tk.NORMAL if fully_enabled else tk.DISABLED)
            except tk.TclError:
                pass
        wd = (self.working_directory.get() or "").strip()
        open_working_dir_ok = bool(wd) and _working_directory_exists_as_dir(wd)
        try:
            fm.entryconfigure(
                "Open Working Directory",
                state=tk.NORMAL if open_working_dir_ok else tk.DISABLED,
            )
        except tk.TclError:
            pass
        zip_report_ok = (
            self._wizard_step in (WIZARD_STEP_SETUP, WIZARD_STEP_REPORT)
            and self._working_directory_index_html_path() is not None
            and not self._report_job_running
            and not self._wizard_batch_is_running()
        )
        try:
            fm.entryconfigure(
                "Zip report...", state=tk.NORMAL if zip_report_ok else tk.DISABLED
            )
        except tk.TclError:
            pass
        try:
            fm.entryconfigure("Pause", state=tk.NORMAL if batch_stop else tk.DISABLED)
        except tk.TclError:
            pass
        try:
            fm.entryconfigure("Stop", state=tk.NORMAL if batch_stop else tk.DISABLED)
        except tk.TclError:
            pass
        try:
            fm.entryconfigure("Exit", state=tk.NORMAL)
        except tk.TclError:
            pass
        if fully_enabled:
            self._refresh_file_menu_save_state()
        self._refresh_recent_scans_menu()

    def _refresh_recent_scans_menu(self) -> None:
        """Rebuild File → Recent scans (Setup step only; hidden when the list is empty)."""
        fm = getattr(self, "_file_menu", None)
        rs_menu = getattr(self, "_recent_scans_menu", None)
        if fm is None or rs_menu is None:
            return
        rs_menu.delete(0, "end")
        idx = self._file_menu_recent_scans_index
        if self._wizard_step != WIZARD_STEP_SETUP or not self._recent_scans:
            if idx is not None:
                try:
                    fm.delete(idx)
                except tk.TclError:
                    pass
                self._file_menu_recent_scans_index = None
            return
        for index, path in enumerate(self._recent_scans, start=1):
            rs_menu.add_command(
                label=_format_recent_scan_menu_label(index, path),
                command=lambda p=path: self._on_file_menu_recent_scan(p),
            )
        if idx is None:
            try:
                fm.insert_cascade(2, label="Recent scans", menu=rs_menu)
                self._file_menu_recent_scans_index = 2
            except tk.TclError:
                pass

    def _record_recent_scan(self, working_dir: Path) -> None:
        try:
            path = str(working_dir.expanduser().resolve())
        except OSError:
            path = str(working_dir).strip()
        if not path:
            return
        self._recent_scans = _prepend_recent_scan(self._recent_scans, path)
        self._refresh_recent_scans_menu()

    def _on_file_menu_recent_scan(self, path: str) -> None:
        if not self._app_menus_fully_enabled():
            return
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = path.strip()
        if not resolved:
            return
        self._set_working_directory_value(resolved)
        self._persist_working_directory_and_loadpoint()
        self._warn_if_working_directory_invalid()
        self._warn_if_working_directory_has_spaces()
        self._warn_if_working_directory_has_no_creo_models()
        self._refresh_wizard_ui()

    def _refresh_file_menu_save_state(self) -> None:
        """Disable File → Save / Save as when settings are not in a savable state."""
        fm = getattr(self, "_file_menu", None)
        if fm is None:
            return
        ok, _ = self._settings_fields_ready()
        st = tk.NORMAL if ok else tk.DISABLED
        try:
            fm.entryconfigure("Save", state=st)
            fm.entryconfigure("Save as...", state=st)
        except tk.TclError:
            pass

    def _refresh_configuration_menu(self) -> None:
        if self._configuration_menu is None:
            return
        self._configuration_menu.delete(0, "end")
        for option in self._settings_options:
            if option == "Open configurations...":
                continue
            self._configuration_menu.add_command(
                label=option,
                command=lambda o=option: self._on_settings_config_item(o),
            )
        self._configuration_menu.add_separator()
        self._configuration_menu.add_command(
            label="Open configurations...",
            command=self._on_open_settings_folder,
        )

    def _settings_fields_ready(self) -> tuple[bool, str]:
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            return False, "Working directory cannot be empty."
        if not _working_directory_exists_as_dir(wd):
            return (
                False,
                "Working directory must be an existing folder (use Browse or a path that exists on disk).",
            )
        task_display = self.task.get() or ""
        if not self._go_model_source_ready(wd, task_display):
            types_label = self._model_scan_types_label(task_display)
            if self._is_scan_templates_task(task_display):
                return (
                    False,
                    "Upload at least one template (.prt, .asm, or .drw) on the Scan Templates wizard step.",
                )
            if self._is_jpeg_2d_plot_task(task_display):
                detail = (
                    f"Working directory must contain at least one {types_label} file "
                    "in that folder itself (.prt and .asm are not used for JPEG 2D plot batch; subfolders are not used)."
                )
            elif self._is_jpeg_3d_task(task_display):
                detail = (
                    f"Working directory must contain at least one {types_label} file "
                    "in that folder itself (.drw files are not used for JPEG 3D batch; subfolders are not used)."
                )
            else:
                detail = (
                    f"Working directory must contain at least one Creo model file "
                    f"({types_label}) in that folder itself (subfolders are not used)."
                )
            return False, detail
        if not (self.creo_loadpoint.get() or "").strip():
            return False, "Creo loadpoint cannot be empty."
        if not _creo_loadpoint_has_parametric_dir(self.creo_loadpoint.get()):
            return (
                False,
                'Creo loadpoint must be a Creo install folder that contains a "Parametric" subfolder.',
            )
        if not self._task_filename_from_ui(self.task.get() or ""):
            return False, "Task cannot be empty. Set Creo loadpoint to list TTDs, or use File → New."
        return True, ""

    def _settings_fields_ready_for_persist(self) -> tuple[bool, str]:
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            return False, "Working directory cannot be empty."
        if not _working_directory_exists_as_dir(wd):
            return (
                False,
                "Working directory must be an existing folder (use Browse or a path that exists on disk).",
            )
        lp = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        if not lp:
            return False, "Creo loadpoint cannot be empty."
        if not _creo_loadpoint_has_parametric_dir(lp):
            return (
                False,
                'Creo loadpoint must be a Creo install folder that contains a "Parametric" subfolder.',
            )
        return True, ""

    def _validated_settings_payload(self) -> tuple[dict[str, object] | None, str]:
        """Return ``(payload, \"\")`` when the form is savable, else ``(None, error)``."""
        ok, err = self._settings_fields_ready_for_persist()
        if not ok:
            return None, err
        return (
            _canonical_app_settings(
                {
                    "working_directory": self.working_directory.get().strip(),
                    "creo_loadpoint": self.creo_loadpoint.get().strip(),
                    "chunk_size": self._chunk_size,
                    "output_timeout_sec": self._output_timeout_sec,
                    "xtop_timeout_sec": self._xtop_gone_timeout_sec,
                    "automatic_mode": self._automatic_mode,
                    "debug_mode": self._debug_mode,
                    "scan_parts": self._scan_parts,
                    "scan_assemblies": self._scan_assemblies,
                    "scan_drawings": self._scan_drawings,
                    "recent_scans": self._recent_scans,
                }
            ),
            "",
        )

    def _write_paired_settings_json(self, payload: dict[str, str]) -> str | None:
        """If Save As / Open set a paired path, write the same JSON there. Returns error text or None."""
        paired = self._paired_settings_json_path
        if paired is None:
            return None
        try:
            p = paired.resolve()
        except OSError:
            self._paired_settings_json_path = None
            return None
        if p == _default_app_settings_path().resolve():
            return None
        try:
            p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            return (
                f"Wrote app_settings.json but could not update paired file:\n{p}\n\n{exc}"
            )
        return None

    def _warn_if_working_directory_invalid(self) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd or _working_directory_exists_as_dir(wd):
            return
        messagebox.showwarning(
            "Working directory",
            "This path is not an existing folder.\n\n"
            "Use Browse to pick a folder, or type a path that already exists on disk.",
        )

    def _wizard_working_directory_has_models(self, working_dir_str: str | None = None) -> bool:
        """True if the working folder has at least one top-level .prt, .asm, or .drw."""
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s or not _working_directory_exists_as_dir(s):
            return False
        return self._working_directory_has_creo_models(s, extensions=self._enabled_scan_extensions())

    def _warn_wizard_working_directory_missing_models(self) -> bool:
        """Warn when the working folder has no batchable Creo models. Returns True if missing."""
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            return False
        if self._wizard_working_directory_has_models(wd):
            return False
        types_label = self._enabled_scan_types_label()
        messagebox.showwarning(
            "Working directory",
            "No Creo models found in this folder.\n\n"
            f"Add at least one {types_label} file directly in this directory "
            "(the app does not look inside subfolders or zip files).",
        )
        return True

    def _warn_if_working_directory_has_no_creo_models(self) -> None:
        if self._wizard_step == WIZARD_STEP_SETUP:
            self._warn_wizard_working_directory_missing_models()
            return
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            return
        task_display = self.task.get() or ""
        if self._is_scan_templates_task(task_display):
            if self._templates_dir_has_creo_models(wd):
                return
            messagebox.showwarning(
                "Templates",
                "No template models found.\n\n"
                "Use Browse on the Scan Templates wizard step to copy at least one "
                f"{self._enabled_scan_types_label()} into:\n{Path(wd) / 'templates'}",
            )
            return
        scan_exts = self._model_scan_extensions_for_task(task_display)
        if self._working_directory_has_creo_models(wd, extensions=scan_exts):
            return
        types_label = self._model_scan_types_label(task_display)
        if self._is_jpeg_2d_plot_task(task_display):
            detail = (
                f"Add at least one {types_label} file directly in this directory "
                "(.prt and .asm are not used for JPEG 2D plot batch). "
            )
        elif self._is_jpeg_3d_task(task_display):
            detail = (
                f"Add at least one {types_label} file directly in this directory "
                "(.drw files are not used for JPEG 3D batch). "
            )
        else:
            detail = f"Add at least one {types_label} file directly in this directory "
        messagebox.showwarning(
            "Working directory",
            "No Creo models found in this folder.\n\n"
            f"{detail}"
            "(the app does not look inside subfolders).",
        )

    def _warn_if_working_directory_has_spaces(self) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _path_contains_spaces(wd):
            return
        messagebox.showerror(
            "Working directory",
            "Working directory path cannot contain spaces.\n\n"
            "Batch processing does not support paths with spaces.\n\n"
            "Choose or create a folder without spaces in the path "
            "(for example C:\\Projects\\MyBatch instead of C:\\My Projects\\MyBatch).",
        )

    def _warn_if_creo_loadpoint_missing_parametric(self) -> None:
        raw = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        if not raw or _creo_loadpoint_has_parametric_dir(raw):
            return
        messagebox.showwarning(
            "Creo loadpoint",
            "This folder does not look like a Creo loadpoint.\n\n"
            'It should be the Creo install folder that contains a "Parametric" subfolder '
            r"(where Parametric\bin\ptcdbatch.bat lives)." "\n\n"
            r"Example: C:\PTC\Creo 12.4.3.0",
        )

    @staticmethod
    def _clean_start_over_directory(directory: Path, *, remove_creo_models: bool = False) -> list[str]:
        """Remove scan/batch artifacts from one folder; return error lines for failures."""
        errors: list[str] = []
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            return [f"{directory}\n{exc}"]
        for entry in entries:
            try:
                if entry.is_dir():
                    if entry.name.casefold() not in _START_OVER_REMOVE_DIR_NAMES:
                        continue
                    if entry.name.casefold() == "templates":
                        for json_file in entry.glob("*.json"):
                            try:
                                json_file.unlink()
                            except OSError as exc:
                                errors.append(f"{json_file}\n{exc}")
                    shutil.rmtree(entry)
                    continue
                if not entry.is_file():
                    continue
                suffix = entry.suffix.casefold()
                if suffix in _START_OVER_FILE_SUFFIXES:
                    entry.unlink()
                    continue
                if remove_creo_models and _CREO_MODEL_TOPLEVEL_RE.match(entry.name):
                    entry.unlink()
            except OSError as exc:
                errors.append(f"{entry}\n{exc}")
        return errors

    def _run_kill_bat(self) -> tuple[bool, str | None]:
        kill_bat = _app_bundle_dir() / "kill.bat"
        if not kill_bat.is_file():
            return False, f"Could not find kill.bat next to the application:\n{kill_bat}"
        try:
            run_kw: dict = {
                "args": [str(kill_bat)],
                "cwd": str(kill_bat.parent),
                "check": False,
            }
            if sys.platform == "win32":
                run_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.run(**run_kw)
        except OSError as exc:
            return False, str(exc)
        return True, None

    def _on_file_menu_pause(self) -> None:
        if not self._batch_stop_available():
            messagebox.showinfo("Pause", "No batch is running.")
            return
        watch = self._wizard_batch_watch
        step = watch.get("step") if watch else self._wizard_step
        if not isinstance(step, int):
            step = self._wizard_step
        if step not in (WIZARD_STEP_SCAN, WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            messagebox.showinfo(
                "Pause",
                "Pause is only available during Scan Templates, ModelCHECK, or Thumbnails.",
            )
            return
        batch_dir, _ = self._wizard_batch_dxc_context_for_step(step)
        if batch_dir is None or not batch_dir.is_dir():
            messagebox.showwarning("Pause", "Could not find the batch folder for this step.")
            return
        self._automatic_wizard_paused = True
        self._cancel_automatic_wizard_chain()
        self._request_batch_runner_pause(batch_dir)
        self._show_batch_pause_dialog(batch_dir, step)

    def _batch_pause_is_active(self, batch_dir: Path) -> bool:
        """True when the runner has entered the pause hold (safe to use interactive Creo)."""
        try:
            return (batch_dir / BATCH_PAUSE_ACTIVE_BASENAME).is_file()
        except OSError:
            return False

    def _show_batch_pause_dialog(self, batch_dir: Path, step: int) -> None:
        """Wait for the runner to hold, then show Resume/Stop (safe to use Creo)."""
        step_label = (
            WIZARD_STEPPER_LABELS[step]
            if 0 <= step < len(WIZARD_STEPPER_LABELS)
            else "batch"
        )

        def handle_stop_choice() -> None:
            self._on_file_menu_stop()
            try:
                still_paused = (batch_dir / BATCH_PAUSE_FLAG_BASENAME).is_file()
            except OSError:
                still_paused = False
            if still_paused and self._batch_stop_available():
                self._show_batch_pause_dialog(batch_dir, step)

        if not self._batch_pause_is_active(batch_dir):
            wait_action = self._show_batch_pause_waiting_dialog(batch_dir, step_label)
            if wait_action == "stop":
                handle_stop_choice()
                return
            if wait_action == "cancel":
                self._clear_batch_pause_flag(batch_dir)
                self._automatic_wizard_paused = False
                return
            # "ready" — runner is held

        ready_action = self._show_batch_pause_ready_dialog(step_label)
        if ready_action == "stop":
            handle_stop_choice()
            return
        self._clear_batch_pause_flag(batch_dir)
        self._automatic_wizard_paused = False

    def _show_batch_pause_waiting_dialog(
        self, batch_dir: Path, step_label: str
    ) -> str:
        """Block until the runner is held, or the user cancels pause / stops."""
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title("Pause")
        dialog.resizable(False, False)
        dialog.transient(self)

        action = {"value": "cancel"}
        poll_job: dict[str, object | None] = {"id": None}

        def close(choice: str) -> None:
            jid = poll_job.get("id")
            if jid is not None:
                try:
                    dialog.after_cancel(jid)  # type: ignore[arg-type]
                except (tk.TclError, ValueError):
                    pass
                poll_job["id"] = None
            action["value"] = choice
            dialog.destroy()

        message = (
            f"Pause requested on the {step_label} step.\n\n"
            "Please wait for the current chunk to finish…\n"
            "Do not start interactive Creo yet."
        )
        ctk.CTkLabel(dialog, text=message, justify="left", wraplength=420).pack(
            anchor="w", padx=16, pady=(16, 12)
        )

        def poll_until_active() -> None:
            poll_job["id"] = None
            try:
                if not dialog.winfo_exists():
                    return
            except tk.TclError:
                return
            if self._batch_pause_is_active(batch_dir):
                close("ready")
                return
            try:
                poll_job["id"] = dialog.after(500, poll_until_active)
            except tk.TclError:
                pass

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=16, pady=(0, 16))
        stop_btn = self._mk_dialog_button(
            btn_row, text="Stop", width=88, primary=False, command=lambda: close("stop")
        )
        cancel_btn = self._mk_dialog_button(
            btn_row,
            text="Cancel pause",
            width=110,
            primary=False,
            command=lambda: close("cancel"),
        )
        stop_btn.pack(side="right", padx=(8, 0))
        cancel_btn.pack(side="right")

        dialog.bind("<Escape>", lambda _e: close("cancel"))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close("cancel"))

        poll_until_active()
        self._run_modal_toplevel_wait(
            dialog,
            anchor=self,
            focus_widget=cancel_btn,
            repaints=(stop_btn, cancel_btn),
        )
        return action["value"]

    def _show_batch_pause_ready_dialog(self, step_label: str) -> str:
        """Shown when the runner is held — safe to use interactive Creo."""
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title("Pause")
        dialog.resizable(False, False)
        dialog.transient(self)

        action = {"value": "resume"}

        def close(choice: str) -> None:
            action["value"] = choice
            dialog.destroy()

        message = (
            f"Paused on the {step_label} step.\n\n"
            "Safe to use interactive Creo now.\n"
            "When you are done, quit Creo and click Resume to continue the batch, or Stop to end it."
        )
        ctk.CTkLabel(dialog, text=message, justify="left", wraplength=420).pack(
            anchor="w", padx=16, pady=(16, 12)
        )
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=16, pady=(0, 16))
        stop_btn = self._mk_dialog_button(
            btn_row, text="Stop", width=88, primary=False, command=lambda: close("stop")
        )
        resume_btn = self._mk_dialog_button(
            btn_row, text="Resume", width=88, command=lambda: close("resume")
        )
        stop_btn.pack(side="right", padx=(8, 0))
        resume_btn.pack(side="right")

        dialog.bind("<Escape>", lambda _e: close("resume"))
        dialog.bind("<Return>", lambda _e: close("resume"))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close("resume"))

        self._run_modal_toplevel_wait(
            dialog,
            anchor=self,
            focus_widget=resume_btn,
            repaints=(stop_btn, resume_btn),
        )
        if action["value"] == "resume" and _xtop_is_running():
            messagebox.showwarning(
                "Creo is running",
                "Creo (xtop) is currently running.\n\n"
                "Quit Creo completely, then click Resume again.",
            )
            return self._show_batch_pause_ready_dialog(step_label)
        return action["value"]

    def _on_file_menu_stop(self) -> None:
        if not self._batch_stop_available():
            messagebox.showinfo("Stop", "No batch is running.")
            return
        watch = self._wizard_batch_watch
        step = watch.get("step") if watch else self._wizard_step
        if not isinstance(step, int):
            step = self._wizard_step
        step_label = (
            WIZARD_STEPPER_LABELS[step]
            if 0 <= step < len(WIZARD_STEPPER_LABELS)
            else "batch"
        )
        if self._debug_mode:
            stop_runner_note = (
                "This runs kill.bat to stop Creo and signals the runner to exit.\n"
                "The PowerShell window stays open so you can read the log.\n"
            )
        else:
            stop_runner_note = (
                "This closes the PowerShell runner and runs kill.bat to stop Creo.\n"
            )
        prompt = (
            f"Stop the running {step_label} batch?\n\n"
            f"{stop_runner_note}"
            "Outputs already written are kept.\n\n"
            "To continue later, run this wizard step again — completed models are skipped."
        )
        if not self._show_proceed_cancel_dialog("Stop", prompt, default_proceed=True):
            return
        self._automatic_wizard_paused = True
        self._cancel_automatic_wizard_chain()
        if watch is not None:
            self._wizard_capture_failed_models_after_batch(watch)
        self._cancel_post_batch_task_refresh()
        batch_dir, scan_templates = self._wizard_batch_dxc_context_for_step(step)
        kill_ok, kill_err = self._execute_batch_stop(batch_dir, scan_templates)
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            self._clear_step_failure_logs(step, batch_dir)
        self._cancel_wizard_batch_output_watch()
        self._refresh_wizard_ui()
        if not kill_ok:
            self._show_stop_result_message(
                "warning",
                "Stop",
                "Batch stopped, but kill.bat could not run:\n\n"
                f"{kill_err}\n\n"
                "Run kill.bat manually if Creo processes are still active.",
            )
            return
        self._show_stop_result_message(
            "info",
            "Stop",
            f"Batch stopped on the {step_label} step.\n\n"
            "Run this step again when you are ready to continue (completed outputs are skipped).",
        )

    def _execute_batch_stop(
        self, batch_dir: Path | None, scan_templates: bool
    ) -> tuple[bool, str | None]:
        """Signal the runner, wait briefly, force-close if needed, clean .dxc, run kill.bat."""
        self._request_batch_runner_stop(batch_dir)
        proc = self._batch_runner_process
        if proc is not None and proc.poll() is None:
            deadline = time.time() + BATCH_STOP_COOPERATIVE_WAIT_SEC
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    self.update_idletasks()
                except tk.TclError:
                    break
                time.sleep(0.2)
        if not self._debug_mode:
            self._close_batch_runner_window(force=True)
            self._close_stray_batch_runner_windows()
        if batch_dir is not None and batch_dir.is_dir():
            self._cleanup_leftover_batch_dxc(batch_dir, scan_templates=scan_templates)
            self._clear_batch_pause_flag(batch_dir)
            self._clear_batch_stop_flag(batch_dir)
        return self._run_kill_bat()

    def _show_stop_result_message(self, kind: str, title: str, message: str) -> None:
        """Show Stop result after wizard buttons repaint (avoids gray modal button text)."""

        def show() -> None:
            if kind == "warning":
                messagebox.showwarning(title, message)
            else:
                messagebox.showinfo(title, message)

        self.after(100, show)

    def _on_file_menu_start_over(self) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            messagebox.showwarning(
                "Start over",
                "Set a working directory before using Start over.",
            )
            return
        if not _working_directory_exists_as_dir(wd):
            messagebox.showwarning(
                "Start over",
                "Working directory must be an existing folder.",
            )
            return
        working_dir = Path(wd).expanduser().resolve()
        prompt = (
            "Remove prior scan and batch data from the working folder?\n\n"
            "Keeps Creo models (.prt, .asm, .drw) in the working folder.\n"
            "Removes templates\\ (including creo-batch-template-scan.json), modchk\\, "
            "batch status files (*-run.complete, pause/stop flags, .pvz), and other scan outputs."
        )
        if not self._show_proceed_cancel_dialog("Start over", prompt):
            return
        self._cancel_wizard_batch_output_watch()
        self._close_batch_runner_window()
        self._cancel_automatic_wizard_chain()
        self._invalidate_working_dir_file_cache()
        errors: list[str] = []
        errors.extend(_remove_batch_timeout_logs_in_directory(working_dir))
        errors.extend(_remove_batch_status_files_in_directory(working_dir))
        errors.extend(self._clean_start_over_directory(working_dir))
        self._refresh_action_buttons()
        self._wizard_step_outcome.clear()
        self._wizard_step_failed_models.clear()
        self._pending_template_sources.clear()
        self._wizard_report_auto_create_done = False
        self._automatic_wizard_paused = False
        self._session_failed_batch_go_choice = None
        self._set_wizard_step(WIZARD_STEP_SETUP)
        if errors:
            messagebox.showwarning(
                "Start over",
                "Some items could not be removed:\n\n" + "\n\n".join(errors),
            )
            return
        messagebox.showinfo(
            "Start over",
            f"Removed scan and batch data from:\n{working_dir}",
        )

    def _on_file_menu_purge_cache(self) -> None:
        prompt = (
            "Delete Creo and batch cache files?\n\n"
            "Removes ProgramData dbatch* folders, ModelCHECK mdlchk cache, "
            "Parametric\\bin log files (including rotated .log.N), and Parametric\\bin\\dsm_cache "
            "(uses creo_loadpoint from app settings).\n\n"
            "Close Creo first if it is running."
        )
        if not self._show_proceed_cancel_dialog("Purge cache", prompt):
            return
        ps1 = _app_bundle_dir() / PURGE_CACHE_PS1_BASENAME
        if not ps1.is_file():
            messagebox.showerror("Purge cache", f"Could not find:\n{ps1}")
            return
        ps_exe = self._resolve_powershell_exe()
        if not ps_exe:
            messagebox.showerror("PowerShell Not Found", "Could not locate powershell.exe.")
            return
        try:
            # Visible console + -NoExit so the user can read purge output (not hidden).
            ps_args = [
                "-NoProfile",
                "-NoExit",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1.resolve()),
            ]
            popen_kw: dict = {
                "args": [ps_exe, *ps_args],
                "cwd": str(_app_bundle_dir()),
                "creationflags": subprocess.CREATE_NEW_CONSOLE,
            }
            startupinfo = self._console_startupinfo(show_normal=True)
            if startupinfo is not None:
                popen_kw["startupinfo"] = startupinfo
            subprocess.Popen(**popen_kw)
        except OSError as exc:
            messagebox.showerror(
                "Purge cache",
                f"Could not start purge script:\n{ps1}\n\n{exc}",
            )

    def _on_exit(self) -> None:
        """Save settings when valid, stop batch runner, then close."""
        self._cancel_post_batch_task_refresh()
        self._cancel_automatic_wizard_chain()
        self._cancel_wizard_batch_output_watch()
        self._close_batch_runner_window()
        self._settings_path = _default_app_settings_path()
        ok, err = self._write_current_settings_to_disk()
        if not ok and (
            (self.working_directory.get() or "").strip()
            or (self.creo_loadpoint.get() or "").strip()
        ):
            messagebox.showwarning("Settings not saved", err)
        self.destroy()

    def _on_file_menu_new(self) -> None:
        self._settings_path = _default_app_settings_path()
        self._paired_settings_json_path = None
        self._set_working_directory_value("")
        self._set_creo_loadpoint_value("")
        self._cancel_wizard_batch_output_watch()
        self._cancel_automatic_wizard_chain()
        self._wizard_step_outcome.clear()
        self._wizard_step_failed_models.clear()
        self._pending_template_sources.clear()
        self._refresh_task_options()
        self._set_wizard_step(WIZARD_STEP_SETUP)

    def _write_current_settings_to_disk(self) -> tuple[bool, str]:
        """If valid, persist current form to ``app_settings.json`` and paired JSON (if any)."""
        self._settings_path = _default_app_settings_path()
        payload, err = self._validated_settings_payload()
        if payload is None:
            return False, err
        try:
            self._settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            return False, f"Could not write app_settings.json:\n{self._settings_path.resolve()}\n\n{exc}"
        err2 = self._write_paired_settings_json(payload)
        if err2:
            return False, err2
        return True, ""

    def _on_file_menu_save(self) -> None:
        ok, err = self._write_current_settings_to_disk()
        if not ok:
            messagebox.showwarning("Save", err)
            return
        msg = f"Settings saved to:\n{self._settings_path.resolve()}"
        paired = self._paired_settings_json_path
        if paired is not None:
            try:
                if paired.resolve() != self._settings_path.resolve():
                    msg += f"\n\nAlso updated:\n{paired.resolve()}"
            except OSError:
                pass
        messagebox.showinfo("Save", msg)

    def _on_file_menu_save_as(self) -> None:
        payload, err = self._validated_settings_payload()
        if payload is None:
            messagebox.showwarning("Save As", err)
            return
        initial_dir = str(self._settings_path.parent)
        if not Path(initial_dir).is_dir():
            initial_dir = str(_app_bundle_dir())
        initial_file = "settings_export.json"
        path = fd.asksaveasfilename(
            title="Save settings as (JSON)",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".json",
            filetypes=[("JSON settings", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        p = Path(path).resolve()
        if p.suffix.lower() != ".json":
            p = p.with_suffix(".json")
        payload2, err2 = self._validated_settings_payload()
        if payload2 is None:
            messagebox.showwarning("Save As", err2)
            return
        try:
            p.write_text(json.dumps(payload2, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save As", f"Could not write:\n{p}\n\n{exc}")
            return
        self._paired_settings_json_path = p.resolve()
        messagebox.showinfo(
            "Save As",
            f"Exported settings to:\n{p}\n\n"
            "File → Save and Exit will update this file and app_settings.json.",
        )

    def _on_file_menu_open(self) -> None:
        """Load fields from a chosen JSON file; File → Save / Exit keep that file in sync too."""
        initial_dir = str(self._settings_path.parent)
        if not Path(initial_dir).is_dir():
            initial_dir = str(_app_bundle_dir())
        path = fd.askopenfilename(
            title="Load settings from JSON",
            initialdir=initial_dir,
            filetypes=[("JSON settings", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        p = Path(path).resolve()
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Open", f"Could not read:\n{p}\n\n{exc}")
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            messagebox.showerror("Open", f"Invalid JSON in:\n{p}\n\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Open", "Settings file must contain a JSON object at the top level.")
            return
        self._settings_path = _default_app_settings_path()
        self._paired_settings_json_path = p.resolve()
        self._apply_settings_data(data)
        # Success case is intentionally quiet; errors are still shown.

    @staticmethod
    def _open_file_in_notepad(target: Path) -> None:
        """Open a file in Notepad (avoids Windows 'choose an app' for unknown extensions)."""
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        notepad = Path(system_root) / "System32" / "notepad.exe"
        if not notepad.is_file():
            notepad = Path(system_root) / "notepad.exe"
        subprocess.Popen([str(notepad), str(target)], close_fds=True)

    def _merge_session_into_app_settings_dict(self, data: dict[str, object]) -> dict[str, object]:
        """Keep checkbox/batch settings from memory so merge writes cannot drop them."""
        data["automatic_mode"] = self._automatic_mode
        data["debug_mode"] = self._debug_mode
        data["scan_parts"] = self._scan_parts
        data["scan_assemblies"] = self._scan_assemblies
        data["scan_drawings"] = self._scan_drawings
        data["chunk_size"] = self._chunk_size
        data["output_timeout_sec"] = self._output_timeout_sec
        data["xtop_timeout_sec"] = self._xtop_gone_timeout_sec
        data["recent_scans"] = self._recent_scans
        return data

    def _read_app_settings_dict(self) -> dict[str, object]:
        path = _default_app_settings_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_app_settings_dict(self, data: dict[str, object]) -> str | None:
        path = _default_app_settings_path()
        try:
            path.write_text(json.dumps(_canonical_app_settings(data), indent=2), encoding="utf-8")
        except OSError as exc:
            return f"Could not write app_settings.json:\n{path.resolve()}\n\n{exc}"
        return None

    def _persist_automatic_mode(self, enabled: bool) -> str | None:
        self._automatic_mode = _normalize_automatic_mode(enabled)
        data = self._merge_session_into_app_settings_dict(self._read_app_settings_dict())
        return self._write_app_settings_dict(data)

    def _on_automatic_mode_toggle(self) -> None:
        enabled = bool(self._automatic_mode_var.get())
        err = self._persist_automatic_mode(enabled)
        if err:
            self._automatic_mode_var.set(not enabled)
            self._automatic_mode = _normalize_automatic_mode(not enabled)
            messagebox.showerror("Automatic mode", err)
            return
        if not enabled:
            self._cancel_automatic_wizard_chain()
        self._refresh_wizard_ui()

    def _persist_debug_mode(self, enabled: bool) -> str | None:
        self._debug_mode = _normalize_automatic_mode(enabled)
        data = self._merge_session_into_app_settings_dict(self._read_app_settings_dict())
        return self._write_app_settings_dict(data)

    def _on_debug_mode_toggle(self) -> None:
        enabled = bool(self._debug_mode_var.get())
        err = self._persist_debug_mode(enabled)
        if err:
            self._debug_mode_var.set(not enabled)
            self._debug_mode = _normalize_automatic_mode(not enabled)
            messagebox.showerror("Debug", err)

    def _persist_batch_settings(
        self,
        *,
        chunk_size: int,
        output_timeout_sec: int,
        xtop_gone_timeout_sec: int,
    ) -> str | None:
        self._chunk_size = _normalize_chunk_size(chunk_size)
        self._output_timeout_sec = _normalize_output_timeout_sec(output_timeout_sec)
        self._xtop_gone_timeout_sec = _normalize_xtop_gone_timeout_sec(xtop_gone_timeout_sec)
        data = self._merge_session_into_app_settings_dict(self._read_app_settings_dict())
        return self._write_app_settings_dict(data)

    def _persist_scan_settings(
        self,
        *,
        scan_parts: bool,
        scan_assemblies: bool,
        scan_drawings: bool,
    ) -> str | None:
        self._scan_parts = _normalize_scan_type_flag(scan_parts, default=SCAN_PARTS_DEFAULT)
        self._scan_assemblies = _normalize_scan_type_flag(
            scan_assemblies, default=SCAN_ASSEMBLIES_DEFAULT
        )
        self._scan_drawings = _normalize_scan_type_flag(
            scan_drawings, default=SCAN_DRAWINGS_DEFAULT
        )
        if not (self._scan_parts or self._scan_assemblies or self._scan_drawings):
            self._scan_parts = SCAN_PARTS_DEFAULT
            self._scan_assemblies = SCAN_ASSEMBLIES_DEFAULT
            self._scan_drawings = SCAN_DRAWINGS_DEFAULT
        data = self._merge_session_into_app_settings_dict(self._read_app_settings_dict())
        err = self._write_app_settings_dict(data)
        if err is None:
            self._clear_templates_for_disabled_scan_types()
        return err

    def _on_scan_settings(self) -> None:
        dialog = self._create_modal_toplevel("Scan settings")
        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        ctk.CTkLabel(
            body,
            text="Which Creo models to include when scanning the working folder",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text="Choose one or more types. Unchecked types are ignored for batch runs "
            "(ModelCHECK, thumbnails, and scan templates). Re-run GO after changing these.",
            justify="left",
            wraplength=500,
            text_color="#555555",
        ).pack(anchor="w", pady=(4, 16))

        parts_var = tk.BooleanVar(value=self._scan_parts)
        asm_var = tk.BooleanVar(value=self._scan_assemblies)
        drw_var = tk.BooleanVar(value=self._scan_drawings)

        checks = ctk.CTkFrame(body, fg_color="transparent")
        checks.pack(anchor="w", fill="x")
        ctk.CTkCheckBox(checks, text="Parts (.prt)", variable=parts_var).pack(
            anchor="w", pady=(0, 8)
        )
        ctk.CTkCheckBox(checks, text="Assemblies (.asm)", variable=asm_var).pack(
            anchor="w", pady=(0, 8)
        )
        ctk.CTkCheckBox(checks, text="Drawings (.drw)", variable=drw_var).pack(anchor="w")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=20, pady=(0, 16))

        def close_dialog() -> None:
            dialog.destroy()

        def on_ok() -> None:
            if not (parts_var.get() or asm_var.get() or drw_var.get()):
                messagebox.showwarning(
                    "Scan settings",
                    "Choose at least one model type to scan.",
                    parent=dialog,
                )
                return
            err = self._persist_scan_settings(
                scan_parts=bool(parts_var.get()),
                scan_assemblies=bool(asm_var.get()),
                scan_drawings=bool(drw_var.get()),
            )
            if err:
                messagebox.showerror("Scan settings", err, parent=dialog)
                return
            self._refresh_wizard_ui()
            self._refresh_action_buttons()
            self._warn_if_working_directory_has_no_creo_models()
            close_dialog()

        ok_btn = self._mk_dialog_button(
            btn_row, text="OK", width=80, primary=True, command=on_ok
        )
        ok_btn.pack(side="right", padx=(12, 0))
        cancel_btn = self._mk_dialog_button(
            btn_row, text="Cancel", width=80, primary=False, command=close_dialog
        )
        cancel_btn.pack(side="right")

        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self._run_modal_toplevel_wait(
            dialog,
            focus_widget=ok_btn,
            repaints=(ok_btn, cancel_btn),
        )

    def _on_batch_settings(self) -> None:
        dialog = self._create_modal_toplevel("Batch settings")
        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        ctk.CTkLabel(
            body,
            text="ModelCHECK and Thumbnails batch runs",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text="Re-run GO on a wizard batch step after changing these values so a new runner script is generated.",
            justify="left",
            wraplength=500,
            text_color="#555555",
        ).pack(anchor="w", pady=(4, 16))

        first_entry: ctk.CTkEntry | None = None

        entry_widgets: list[ctk.CTkEntry] = []

        def add_field(title: str, description: str, initial: str) -> tk.StringVar:
            nonlocal first_entry
            block = ctk.CTkFrame(body, fg_color="transparent")
            block.pack(anchor="w", fill="x", pady=(0, 14))
            ctk.CTkLabel(block, text=title, font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            ctk.CTkLabel(
                block,
                text=description,
                justify="left",
                wraplength=500,
                text_color="#444444",
            ).pack(anchor="w", pady=(4, 8))
            value_var = tk.StringVar(value=initial)
            entry = ctk.CTkEntry(block, textvariable=value_var, width=88)
            entry.pack(anchor="w")
            entry_widgets.append(entry)
            if first_entry is None:
                first_entry = entry
            return value_var

        chunk_var = add_field(
            f"Chunk size ({CREO_BATCH_CHUNK_SIZE_MIN}–{CREO_BATCH_CHUNK_SIZE_MAX})",
            "Models per batch chunk (each creo-batch-N.dxc). Smaller chunks show progress "
            "more often; larger chunks reduce launcher overhead.",
            str(self._chunk_size),
        )
        output_var = add_field(
            f"Output wait timeout (seconds, minimum {BATCH_OUTPUT_WAIT_TIMEOUT_MIN})",
            "How long to wait with no new output files before a chunk times out. The timer "
            "starts when xtop appears for that chunk and resets when a new output file "
            "appears or xtop restarts between models.",
            str(self._output_timeout_sec),
        )
        xtop_var = add_field(
            f"Xtop gone timeout (seconds, minimum {BATCH_XTOP_GONE_TIMEOUT_SEC_MIN})",
            "How long to wait for xtop.exe to return after it exits mid-chunk (XTOP GONE). "
            f"Waiting for xtop to first appear after launch is fixed at "
            f"{BATCH_XTOP_START_WAIT_SEC} seconds (XTOP NEVER STARTED).",
            str(self._xtop_gone_timeout_sec),
        )

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=20, pady=(0, 16))

        def close_dialog() -> None:
            dialog.destroy()

        def on_ok() -> None:
            chunk_raw = chunk_var.get().strip()
            try:
                chunk_n = int(chunk_raw)
            except ValueError:
                messagebox.showwarning(
                    "Batch settings",
                    f"Chunk size must be a whole number from "
                    f"{CREO_BATCH_CHUNK_SIZE_MIN} to {CREO_BATCH_CHUNK_SIZE_MAX}.",
                    parent=dialog,
                )
                return
            if chunk_n < CREO_BATCH_CHUNK_SIZE_MIN or chunk_n > CREO_BATCH_CHUNK_SIZE_MAX:
                messagebox.showwarning(
                    "Batch settings",
                    f"Chunk size must be a whole number from "
                    f"{CREO_BATCH_CHUNK_SIZE_MIN} to {CREO_BATCH_CHUNK_SIZE_MAX}.",
                    parent=dialog,
                )
                return

            output_raw = output_var.get().strip()
            if not output_raw.isdigit():
                messagebox.showwarning(
                    "Batch settings",
                    f"Output wait timeout must be a whole number of seconds "
                    f"(minimum {BATCH_OUTPUT_WAIT_TIMEOUT_MIN}).",
                    parent=dialog,
                )
                return
            output_n = int(output_raw)
            if output_n < BATCH_OUTPUT_WAIT_TIMEOUT_MIN:
                messagebox.showwarning(
                    "Batch settings",
                    f"Output wait timeout must be a whole number of seconds "
                    f"(minimum {BATCH_OUTPUT_WAIT_TIMEOUT_MIN}).",
                    parent=dialog,
                )
                return

            xtop_raw = xtop_var.get().strip()
            if not xtop_raw.isdigit():
                messagebox.showwarning(
                    "Batch settings",
                    f"Xtop gone timeout must be a whole number of seconds "
                    f"(minimum {BATCH_XTOP_GONE_TIMEOUT_SEC_MIN}).",
                    parent=dialog,
                )
                return
            xtop_n = int(xtop_raw)
            if xtop_n < BATCH_XTOP_GONE_TIMEOUT_SEC_MIN:
                messagebox.showwarning(
                    "Batch settings",
                    f"Xtop gone timeout must be a whole number of seconds "
                    f"(minimum {BATCH_XTOP_GONE_TIMEOUT_SEC_MIN}).",
                    parent=dialog,
                )
                return

            err = self._persist_batch_settings(
                chunk_size=chunk_n,
                output_timeout_sec=output_n,
                xtop_gone_timeout_sec=xtop_n,
            )
            if err:
                messagebox.showerror("Batch settings", err, parent=dialog)
                return
            close_dialog()

        ok_btn = self._mk_dialog_button(
            btn_row, text="OK", width=80, primary=True, command=on_ok
        )
        ok_btn.pack(side="right", padx=(12, 0))
        cancel_btn = self._mk_dialog_button(
            btn_row, text="Cancel", width=80, primary=False, command=close_dialog
        )
        cancel_btn.pack(side="right")

        def bind_return_key(_event: object | None = None) -> str:
            on_ok()
            return "break"

        def enable_return_key() -> None:
            if not dialog.winfo_exists():
                return
            for entry in entry_widgets:
                entry.bind("<Return>", bind_return_key)

        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.after(150, enable_return_key)
        self._run_modal_toplevel_wait(
            dialog,
            focus_widget=first_entry,
            repaints=(ok_btn, cancel_btn),
        )

    def _condition_mcc_path(self) -> Path:
        return (self._config_dir / "condition.mcc").resolve()

    def _list_config_mch_files(self) -> list[str]:
        """``.mch`` basenames in ``config\\`` only (not ``config\\templates\\``)."""
        config_dir = self._config_dir.resolve()
        if not config_dir.is_dir():
            return []
        names = [
            p.name
            for p in config_dir.glob("*.mch")
            if p.is_file()
        ]
        return sorted(names, key=lambda n: n.casefold())

    def _current_mch_from_condition_mcc(self) -> str | None:
        path = self._condition_mcc_path()
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        match = re.search(r"\(([^()\s]+\.mch)\)", text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1)

    def _set_condition_mcc_checks_file(self, mch_name: str) -> str | None:
        """Replace every ``(….mch)`` in ``config\\condition.mcc``. Returns error or None."""
        name = (mch_name or "").strip()
        if not name.lower().endswith(".mch"):
            return "Choose a ModelCHECK .mch file."
        if any(sep in name for sep in ("/", "\\", "..")):
            return "Invalid checks file name."
        mch_path = (self._config_dir / name).resolve()
        try:
            mch_path.relative_to(self._config_dir.resolve())
        except ValueError:
            return "Checks file must be in the config folder."
        if not mch_path.is_file():
            return f"Checks file not found:\n{mch_path}"
        path = self._condition_mcc_path()
        if not path.is_file():
            return f"Missing condition file:\n{path}"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Could not read condition.mcc:\n{exc}"
        replacement = f"({name})"
        new_text, count = re.subn(
            r"\([^()\s]+\.mch\)",
            replacement,
            text,
            flags=re.IGNORECASE,
        )
        if count == 0:
            return (
                "No .mch entries found in condition.mcc.\n"
                "Expected lines like:\n"
                "  config=(checks.mch)(start.mcs)…"
            )
        if new_text == text:
            return None
        try:
            path.write_text(new_text, encoding="utf-8", newline="\n")
        except OSError as exc:
            return f"Could not write condition.mcc:\n{exc}"
        return None

    def _on_checks_settings(self) -> None:
        mch_files = self._list_config_mch_files()
        if not mch_files:
            messagebox.showerror(
                "Checks",
                f"No .mch files found in the config folder:\n{self._config_dir.resolve()}",
            )
            return
        condition_path = self._condition_mcc_path()
        if not condition_path.is_file():
            messagebox.showerror(
                "Checks",
                f"Missing condition file:\n{condition_path}",
            )
            return

        current = self._current_mch_from_condition_mcc()
        initial = current if current in mch_files else (
            "checks.mch" if "checks.mch" in mch_files else mch_files[0]
        )

        dialog = self._create_modal_toplevel("Checks")
        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        ctk.CTkLabel(
            body,
            text="ModelCHECK checks file",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text="Choose which .mch from the config folder ModelCHECK should use. "
            "This updates every .mch name in config\\condition.mcc (not config\\templates).",
            justify="left",
            wraplength=480,
            text_color="#555555",
        ).pack(anchor="w", pady=(4, 16))

        choice_var = tk.StringVar(value=initial)
        ctk.CTkOptionMenu(
            body,
            variable=choice_var,
            values=mch_files,
            width=320,
        ).pack(anchor="w")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=20, pady=(16, 16))

        def close_dialog() -> None:
            dialog.destroy()

        def on_ok() -> None:
            err = self._set_condition_mcc_checks_file(choice_var.get())
            if err:
                messagebox.showerror("Checks", err, parent=dialog)
                return
            close_dialog()

        ok_btn = self._mk_dialog_button(
            btn_row, text="OK", width=80, primary=True, command=on_ok
        )
        ok_btn.pack(side="right", padx=(12, 0))
        cancel_btn = self._mk_dialog_button(
            btn_row, text="Cancel", width=80, primary=False, command=close_dialog
        )
        cancel_btn.pack(side="right")

        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self._run_modal_toplevel_wait(
            dialog,
            focus_widget=ok_btn,
            repaints=(ok_btn, cancel_btn),
        )

    def _start_templates_dir(self) -> Path | None:
        wd = (self.working_directory.get() or "").strip()
        if not wd or not Path(wd).is_dir():
            return None
        return Path(wd) / "templates"

    @staticmethod
    def _creo_model_filename_matches(filename: str, kind: str) -> bool:
        pattern = _CREO_MODEL_EXT_PATTERNS.get(kind)
        if not pattern:
            return False
        return re.match(pattern, filename, re.IGNORECASE) is not None

    def _on_file_menu_zip_report(self) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            messagebox.showwarning(
                "Zip report",
                "Set a working directory that exists on disk before zipping the report.",
            )
            return
        working_dir = Path(wd).expanduser().resolve()
        if self._working_directory_index_html_path(wd) is None:
            messagebox.showwarning(
                "Zip report",
                "index.html was not found in the working directory.\n\n"
                "Create the report first.",
            )
            return
        try:
            zip_path = build_report_zip(working_dir)
        except OSError as exc:
            messagebox.showerror(
                "Zip report",
                f"Could not create the report zip.\n\n{exc}",
            )
            return
        messagebox.showinfo(
            "Zip report",
            f"Created:\n{zip_path}",
        )

    def _on_open_working_directory(self) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            messagebox.showwarning(
                "Open Working Directory",
                "Set a working directory that exists on disk before opening it.",
            )
            return
        target = Path(wd).resolve()
        try:
            os.startfile(str(target))
        except OSError as exc:
            messagebox.showerror(
                "Open failed",
                f"Could not open in File Explorer:\n{target}\n\n{exc}",
            )

    def _on_open_settings_folder(self) -> None:
        """Open the bundled config folder in File Explorer for manual edits."""
        target = self._config_dir.resolve()
        if not target.is_dir():
            messagebox.showerror(
                "Folder not found",
                f"Expected config folder next to the app:\n{target}",
            )
            return
        try:
            os.startfile(str(target))
        except OSError as exc:
            messagebox.showerror(
                "Open failed",
                f"Could not open in File Explorer:\n{target}\n\n{exc}",
            )

    def _on_settings_config_item(self, option: str) -> None:
        rel = self._settings_config_relative.get(option)
        if not rel:
            messagebox.showerror("Settings", f"No file mapping for:\n{option}")
            return
        target = (self._config_dir / rel).resolve()
        if not target.is_file():
            messagebox.showerror(
                "File not found",
                f"Expected sample config at:\n{target}\n\n(Relative to config/ next to the app.)",
            )
            return
        try:
            self._open_file_in_notepad(target)
        except OSError as exc:
            messagebox.showerror("Open failed", f"Could not open in Notepad:\n{target}\n\n{exc}")

    def _on_about(self) -> None:
        dialog = self._create_modal_toplevel("About")

        ctk.CTkLabel(dialog, text="PDSVISION Cad Assessment Tool", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8)
        )
        version = _read_app_version()
        if version:
            ctk.CTkLabel(dialog, text=f"Version {version}").pack(anchor="w", padx=16, pady=(0, 8))
        ctk.CTkLabel(dialog, text="Created by Michael P. Bourque").pack(anchor="w", padx=16, pady=(0, 4))
        ctk.CTkLabel(dialog, text="PDSVISION").pack(anchor="w", padx=16, pady=(0, 16))

        def close_dialog() -> None:
            dialog.destroy()

        ctk.CTkButton(dialog, text="OK", width=80, command=close_dialog).pack(anchor="e", padx=16, pady=(0, 16))

        dialog.bind("<Return>", lambda _e: close_dialog())
        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self._present_modal_toplevel(dialog)

    def _browse_target(self, target_variable: ctk.StringVar, browse_kind: str) -> None:
        initial = target_variable.get() or str(Path.home())
        selected_path = ""

        if browse_kind == "directory":
            selected_path = fd.askdirectory(initialdir=initial)
        elif browse_kind == "file":
            selected_path = fd.askopenfilename(initialdir=initial)

        if selected_path:
            if target_variable is self.creo_loadpoint:
                self._set_creo_loadpoint_value(selected_path)
                self._warn_if_creo_loadpoint_missing_parametric()
                self._refresh_task_options()
            elif target_variable is self.working_directory:
                self._record_recent_scan(Path(selected_path))
                self._set_working_directory_value(selected_path)
                self._warn_if_working_directory_invalid()
                self._warn_if_working_directory_has_spaces()
                self._warn_if_working_directory_has_no_creo_models()

    @staticmethod
    def _task_allowed_for_dropdown(filename: str, display_label: str) -> bool:
        """Only ModelCHECK, JPEG 3D, and JPEG 2D plot tasks appear in the Task combobox."""
        if filename.lower() == "modelcheck.ttd":
            return True
        if filename.lower() == JPEG_2D_PLOT_TTD.lower():
            return True
        if filename.lower() == JPEG_3D_TTD.lower():
            return True
        dl = display_label.casefold()
        if "jpeg" in dl and "3d" in dl:
            return True
        stem = Path(filename).stem.casefold()
        if "jpeg" in stem and "3d" in stem:
            return True
        return False

    def _batch_runner_debug_log_path(self, batch_dir: Path, task_display: str) -> Path | None:
        """``.log`` beside the runner ``.ps1`` when Debug mode is on."""
        if not self._debug_mode:
            return None
        stem = Path(self._batch_runner_basename_for_task(task_display)).stem
        return batch_dir / f"{stem}.log"

    def _go_fields_valid(self) -> bool:
        wd = (self.working_directory.get() or "").strip()
        lp = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        if self._wizard_step == WIZARD_STEP_JPEG_3D:
            task_display = self._wizard_thumbnails_task_display_to_run()
        else:
            task_display = (self.task.get() or "").strip()
        if self._is_create_report_task(task_display):
            return False
        task_fn = self._task_filename_from_ui(task_display)
        if not wd or not _working_directory_ok_for_go(wd):
            return False
        if _path_contains_spaces(wd):
            return False
        if not self._go_model_source_ready(wd, task_display):
            return False
        if not lp or not _creo_loadpoint_has_parametric_dir(lp):
            return False
        if not task_fn:
            return False
        ptc = Path(lp) / "Parametric" / "bin" / "ptcdbatch.bat"
        kill = _app_bundle_dir() / "kill.bat"
        return ptc.is_file() and kill.is_file()

    def _refresh_action_buttons(self, *_args: object) -> None:
        """Coalesce many StringVar writes into one UI update (faster startup / settings load)."""
        jid = self._refresh_action_buttons_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._refresh_action_buttons_job = self.after(0, self._refresh_action_buttons_run)

    def _on_first_window_map(self, _event: object = None) -> None:
        """First time the window is actually shown, force one button-state refresh.

        Without this, refreshes triggered during ``_load_settings`` can configure
        CTkButton state before the toplevel is mapped, and the buttons keep the
        disabled look until the user interacts (e.g., toggles the Task combobox).
        """
        if self._post_map_refresh_done:
            return
        self._post_map_refresh_done = True
        self._refresh_action_buttons()

    def _on_app_activate(self, _event: object = None) -> None:
        """Refresh action buttons when this window becomes active (debounced; skip during modals)."""
        if self._modal_dialog_depth > 0:
            return
        jid = self._activate_refresh_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._activate_refresh_job = self.after(250, self._on_app_activate_run)

    def _on_app_activate_run(self) -> None:
        self._activate_refresh_job = None
        if self._modal_dialog_depth > 0:
            self._activate_refresh_job = self.after(500, self._on_app_activate_run)
            return
        if not self._batch_run_active_for_heavy_ui_polls():
            self._update_create_report_task_list(advance_from_jpeg=False)
        self._refresh_action_buttons()

    def _install_dialog_parent(self) -> None:
        """Route message boxes through centered CTk dialogs; default file dialogs to this window."""

        def _messagebox_wrapper(*, kind: str, ask_yes_no: bool = False):
            def wrapped(*args, **kwargs):
                parent = kwargs.pop("parent", self)
                if len(args) >= 2:
                    title, message = args[0], args[1]
                elif len(args) == 1:
                    title, message = "", args[0]
                else:
                    title = str(kwargs.pop("title", ""))
                    message = str(kwargs.pop("message", ""))
                return self._show_app_messagebox(
                    title,
                    message,
                    kind=kind,
                    ask_yes_no=ask_yes_no,
                    parent=parent,
                )

            return wrapped

        def _filedialog_wrapper(orig_fn):
            def wrapped(*args, **kwargs):
                kwargs.setdefault("parent", self)
                return orig_fn(*args, **kwargs)

            return wrapped

        for name, kind in (
            ("showinfo", "info"),
            ("showwarning", "warning"),
            ("showerror", "error"),
            ("askquestion", "info"),
        ):
            fn = getattr(messagebox, name, None)
            if fn is not None:
                setattr(messagebox, name, _messagebox_wrapper(kind=kind))

        for name in ("askyesno", "askokcancel", "askyesnocancel", "askretrycancel"):
            fn = getattr(messagebox, name, None)
            if fn is not None:
                setattr(messagebox, name, _messagebox_wrapper(kind="info", ask_yes_no=True))

        for name in ("askdirectory", "askopenfilename", "asksaveasfilename"):
            fn = getattr(fd, name, None)
            if fn is not None:
                setattr(fd, name, _filedialog_wrapper(fn))

    @staticmethod
    def _mk_dialog_button(
        parent: tk.Misc,
        *,
        text: str,
        command: object,
        width: int = 80,
        primary: bool = True,
    ) -> ctk.CTkButton:
        style = _DIALOG_BTN_PRIMARY_KW if primary else _DIALOG_BTN_SECONDARY_KW
        return ctk.CTkButton(parent, text=text, width=width, command=command, **style)

    @staticmethod
    def _repaint_dialog_buttons(dialog: ctk.CTkToplevel, *buttons: ctk.CTkButton) -> None:
        """CTkButton can keep a disabled gray look after the main window was Waiting…."""

        def fix() -> None:
            for btn in buttons:
                try:
                    if btn.winfo_exists():
                        btn.configure(state="normal")
                except tk.TclError:
                    pass

        dialog.after_idle(fix)

    def _show_app_messagebox(
        self,
        title: str,
        message: str,
        *,
        kind: str = "info",
        ask_yes_no: bool = False,
        parent: tk.Misc | None = None,
    ) -> bool | None:
        anchor = parent if parent is not None else self
        dialog = ctk.CTkToplevel(anchor)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(anchor)

        result: dict[str, bool | None] = {"value": False if ask_yes_no else None}

        def close(value: bool | None = None) -> None:
            if value is not None:
                result["value"] = value
            elif not ask_yes_no:
                result["value"] = True
            dialog.destroy()

        ctk.CTkLabel(dialog, text=message, justify="left", wraplength=420).pack(
            anchor="w", padx=16, pady=(16, 12)
        )
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=16, pady=(0, 16))

        if ask_yes_no:
            no_btn = self._mk_dialog_button(
                btn_row, text="No", width=80, primary=False, command=lambda: close(False)
            )
            yes_btn = self._mk_dialog_button(
                btn_row, text="Yes", width=80, command=lambda: close(True)
            )
            no_btn.pack(side="right", padx=(8, 0))
            yes_btn.pack(side="right")
            dialog.bind("<Escape>", lambda _e: close(False))
            dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
            self._run_modal_toplevel_wait(
                dialog, anchor=anchor, focus_widget=yes_btn, repaints=(no_btn, yes_btn)
            )
        else:
            ok_btn = self._mk_dialog_button(
                btn_row, text="OK", width=80, command=lambda: close(True)
            )
            ok_btn.pack(side="right")
            dialog.bind("<Return>", lambda _e: close(True))
            dialog.bind("<Escape>", lambda _e: close(True))
            dialog.protocol("WM_DELETE_WINDOW", lambda: close(True))
            self._run_modal_toplevel_wait(
                dialog, anchor=anchor, focus_widget=ok_btn, repaints=(ok_btn,)
            )
        return result["value"]

    def _show_proceed_cancel_dialog(
        self, title: str, message: str, *, default_proceed: bool = False
    ) -> bool:
        """Return True when the user clicks Proceed (Cancel is the default unless overridden)."""
        anchor = self
        dialog = ctk.CTkToplevel(anchor)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(anchor)

        result = {"value": False}

        def close(proceed: bool) -> None:
            result["value"] = proceed
            dialog.destroy()

        ctk.CTkLabel(dialog, text=message, justify="left", wraplength=420).pack(
            anchor="w", padx=16, pady=(16, 12)
        )
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=16, pady=(0, 16))
        cancel_btn = self._mk_dialog_button(
            btn_row, text="Cancel", width=88, primary=False, command=lambda: close(False)
        )
        proceed_btn = self._mk_dialog_button(
            btn_row, text="Proceed", width=88, command=lambda: close(True)
        )
        cancel_btn.pack(side="right", padx=(8, 0))
        proceed_btn.pack(side="right")
        default_btn = proceed_btn if default_proceed else cancel_btn

        dialog.bind("<Escape>", lambda _e: close(False))
        dialog.bind("<Return>", lambda _e: close(default_proceed))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))

        self._run_modal_toplevel_wait(
            dialog,
            anchor=anchor,
            focus_widget=default_btn,
            repaints=(cancel_btn, proceed_btn),
        )
        return result["value"]

    def _create_modal_toplevel(self, title: str) -> ctk.CTkToplevel:
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self)
        return dialog

    def _present_modal_toplevel(
        self,
        dialog: ctk.CTkToplevel,
        *,
        parent: tk.Misc | None = None,
        focus_widget: tk.Misc | None = None,
    ) -> None:
        anchor = parent if parent is not None else self

        def show() -> None:
            if not dialog.winfo_exists():
                return
            _schedule_center_toplevel_on_parent(dialog, anchor)
            dialog.deiconify()
            try:
                dialog.lift()
                dialog.focus_force()
            except tk.TclError:
                pass
            if focus_widget is not None:
                try:
                    focus_widget.focus_set()
                    if hasattr(focus_widget, "select_range"):
                        focus_widget.select_range(0, "end")
                except tk.TclError:
                    pass
            _schedule_center_toplevel_on_parent(dialog, anchor)

        dialog.update_idletasks()
        dialog.after_idle(show)

    def _refresh_action_buttons_run(self) -> None:
        self._refresh_action_buttons_job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._refresh_wizard_ui()

    def _refresh_task_options(self) -> None:
        try:
            loadpoint = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
            if not loadpoint or not _creo_loadpoint_has_parametric_dir(loadpoint):
                if self._templates_dir_has_creo_models():
                    self._task_display_to_filename = {SCAN_TEMPLATES_DISPLAY: SCAN_TEMPLATES_DISPLAY}
                    self._task_filename_to_description = {
                        SCAN_TEMPLATES_DISPLAY: SCAN_TEMPLATES_DISPLAY
                    }
                else:
                    fallback = [(DEFAULT_MODELCHECK_TTD, DEFAULT_MODELCHECK_DISPLAY)]
                    self._task_display_to_filename = {lab: fn for fn, lab in fallback}
                    self._task_filename_to_description = {
                        DEFAULT_MODELCHECK_TTD: DEFAULT_MODELCHECK_DISPLAY
                    }
                self._refresh_configuration_menu()
                return

            ttd_folder = Path(loadpoint) / "Common Files" / "text" / "ttds"

            filenames: list[str] = []
            if ttd_folder.is_dir():
                filenames = sorted(
                    [p.name for p in ttd_folder.iterdir() if p.is_file() and p.suffix.lower() == ".ttd"],
                    key=str.lower,
                )

            pairs: list[tuple[str, str]] = []
            fn_mc = next((f for f in filenames if f.lower() == "modelcheck.ttd"), None)
            if fn_mc:
                pairs.append((fn_mc, self._read_ttd_description(ttd_folder / fn_mc)))
            fn_jpg = next((f for f in filenames if f.lower() == JPEG_3D_TTD.lower()), None)
            if fn_jpg:
                desc_j = self._read_ttd_description(ttd_folder / fn_jpg)
                pairs.append((fn_jpg, desc_j))
            fn_plot = next((f for f in filenames if f.lower() == JPEG_2D_PLOT_TTD.lower()), None)
            if fn_plot:
                pairs.append((fn_plot, JPEG_2D_PLOT_DISPLAY))

            self._task_filename_to_description = {name: desc for name, desc in pairs}

            labeled = self._unique_task_labels(pairs)
            allowed = [(fn, lab) for fn, lab in labeled if self._task_allowed_for_dropdown(fn, lab)]
            preferred = "modelcheck.ttd"
            preferred_rows = [(fn, lab) for fn, lab in allowed if fn.lower() == preferred]
            other_rows = [(fn, lab) for fn, lab in allowed if fn.lower() != preferred]
            plot_rows = [(fn, lab) for fn, lab in other_rows if fn.lower() == JPEG_2D_PLOT_TTD.lower()]
            middle_rows = [(fn, lab) for fn, lab in other_rows if fn.lower() != JPEG_2D_PLOT_TTD.lower()]
            middle_rows.sort(key=lambda row: row[1].casefold())
            ordered = (preferred_rows[:1] + middle_rows + plot_rows) if preferred_rows else (middle_rows + plot_rows)
            ordered = [
                (fn, lab)
                for fn, lab in ordered
                if lab not in (SCAN_TEMPLATES_DISPLAY, CREATE_REPORT_DISPLAY)
            ]
            if self._templates_dir_has_creo_models():
                scan_row = (SCAN_TEMPLATES_DISPLAY, SCAN_TEMPLATES_DISPLAY)
                ordered = [scan_row] + ordered
                self._task_filename_to_description[SCAN_TEMPLATES_DISPLAY] = SCAN_TEMPLATES_DISPLAY
            if self._create_report_task_available():
                ordered.append((CREATE_REPORT_DISPLAY, CREATE_REPORT_DISPLAY))
                self._task_filename_to_description[CREATE_REPORT_DISPLAY] = CREATE_REPORT_DISPLAY

            self._task_display_to_filename = {lab: fn for fn, lab in ordered}
            jpg_fn = next((fn for fn, _lab in ordered if fn.lower() == JPEG_3D_TTD.lower()), None)
            if jpg_fn:
                self._task_display_to_filename[JPEG_3D_DISPLAY] = jpg_fn
            display_values = [lab for _fn, lab in ordered]

            if len(display_values) <= 1:
                fallback_mc = (DEFAULT_MODELCHECK_TTD, DEFAULT_MODELCHECK_DISPLAY)
                if self._templates_dir_has_creo_models():
                    scan_row = (SCAN_TEMPLATES_DISPLAY, SCAN_TEMPLATES_DISPLAY)
                    ordered = [scan_row, fallback_mc]
                    self._task_filename_to_description[SCAN_TEMPLATES_DISPLAY] = SCAN_TEMPLATES_DISPLAY
                else:
                    ordered = [fallback_mc]
                if self._create_report_task_available():
                    ordered.append((CREATE_REPORT_DISPLAY, CREATE_REPORT_DISPLAY))
                    self._task_filename_to_description[CREATE_REPORT_DISPLAY] = CREATE_REPORT_DISPLAY
                self._task_display_to_filename = {lab: fn for fn, lab in ordered}
                self._task_display_to_filename.setdefault(JPEG_3D_DISPLAY, JPEG_3D_TTD)
                self._task_filename_to_description.setdefault(
                    DEFAULT_MODELCHECK_TTD, DEFAULT_MODELCHECK_DISPLAY
                )
                display_values = [lab for _fn, lab in ordered]

            task_display = self._wizard_task_display_for_step(self._wizard_step)
            if task_display:
                self.task.set(task_display)
            self._refresh_configuration_menu()
        finally:
            self._last_create_report_available = self._create_report_task_available()
            self._refresh_action_buttons()

    def _persist_working_directory_and_loadpoint(self) -> None:
        """Write working directory and loadpoint to app_settings.json (merge, non-blocking)."""
        if self._suppress_settings_autosave:
            return
        data = self._read_app_settings_dict()
        data["working_directory"] = self.working_directory.get().strip()
        data["creo_loadpoint"] = self.creo_loadpoint.get().strip()
        data["chunk_size"] = _normalize_chunk_size(
            data.get("chunk_size", self._chunk_size)
        )
        data["output_timeout_sec"] = _normalize_output_timeout_sec(
            data.get("output_timeout_sec", self._output_timeout_sec)
        )
        data["xtop_timeout_sec"] = _normalize_xtop_gone_timeout_sec(
            data.get("xtop_timeout_sec", self._xtop_gone_timeout_sec)
        )
        self._write_app_settings_dict(self._merge_session_into_app_settings_dict(data))

    def _apply_settings_data(self, data: dict[str, object]) -> None:
        """Apply settings from a dict (same keys as app_settings.json). Refreshes task list and menu."""
        self._suppress_settings_autosave = True
        try:
            self._apply_settings_data_impl(data)
        finally:
            self._suppress_settings_autosave = False

    def _apply_settings_data_impl(self, data: dict[str, object]) -> None:
        self._chunk_size = _normalize_chunk_size(
            data.get("chunk_size", CREO_BATCH_CHUNK_SIZE_DEFAULT)
        )
        self._output_timeout_sec = _normalize_output_timeout_sec(
            data.get("output_timeout_sec", BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT)
        )
        self._xtop_gone_timeout_sec = _normalize_xtop_gone_timeout_sec(
            data.get("xtop_timeout_sec", BATCH_XTOP_GONE_TIMEOUT_SEC_DEFAULT)
        )
        self._automatic_mode = _normalize_automatic_mode(
            data.get("automatic_mode", AUTOMATIC_MODE_DEFAULT)
        )
        self._automatic_mode_var.set(self._automatic_mode)
        self._debug_mode = _normalize_automatic_mode(
            data.get("debug_mode", DEBUG_MODE_DEFAULT)
        )
        self._debug_mode_var.set(self._debug_mode)
        self._scan_parts = _normalize_scan_type_flag(
            data.get("scan_parts"), default=SCAN_PARTS_DEFAULT
        )
        self._scan_assemblies = _normalize_scan_type_flag(
            data.get("scan_assemblies"), default=SCAN_ASSEMBLIES_DEFAULT
        )
        self._scan_drawings = _normalize_scan_type_flag(
            data.get("scan_drawings"), default=SCAN_DRAWINGS_DEFAULT
        )
        if not (self._scan_parts or self._scan_assemblies or self._scan_drawings):
            self._scan_parts = SCAN_PARTS_DEFAULT
            self._scan_assemblies = SCAN_ASSEMBLIES_DEFAULT
            self._scan_drawings = SCAN_DRAWINGS_DEFAULT
        self._clear_templates_for_disabled_scan_types()
        self._recent_scans = _normalize_recent_scans(data.get("recent_scans"))
        self._set_creo_loadpoint_value(str(data.get("creo_loadpoint") or ""))
        self._warn_if_creo_loadpoint_missing_parametric()
        self._set_working_directory_value(str(data.get("working_directory") or ""))
        self._warn_if_working_directory_invalid()
        self._warn_if_working_directory_has_spaces()
        self._warn_if_working_directory_has_no_creo_models()

        self._refresh_task_options()
        self._refresh_configuration_menu()
        self._refresh_action_buttons()
        self._refresh_recent_scans_menu()

    def _load_settings(self) -> None:
        """On startup, restore form from ``app_settings.json`` (create empty file if missing)."""
        self._settings_path = _default_app_settings_path()
        if not self._settings_path.exists():
            empty = _canonical_app_settings({})
            try:
                self._settings_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
            except OSError:
                self._refresh_task_options()
                return

        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._refresh_task_options()
            return

        if not isinstance(data, dict):
            self._refresh_task_options()
            return

        self._apply_settings_data(data)
        if "recent_scans" not in data:
            merged = self._merge_session_into_app_settings_dict(dict(data))
            self._write_app_settings_dict(merged)

    def _save_settings(self) -> None:
        """Persist paths and app options to ``app_settings.json`` (called after a successful GO)."""
        self._settings_path = _default_app_settings_path()
        payload, _ = self._validated_settings_payload()
        if payload is None:
            return
        try:
            self._settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # Keep GO success path non-blocking if settings save fails.
            pass

    def _scan_models_non_recursive(
        self, directory: Path, *, extensions: tuple[str, ...] = _CREO_MODEL_EXTENSIONS_ALL
    ) -> dict[Path, list[str]]:
        files: dict[Path, list[str]] = defaultdict(list)
        try:
            names = self._working_dir_model_names(directory, extensions)
        except OSError:
            names = ()
        for entry_name in names:
            files[directory].append(entry_name)
        return files

    def _get_latest_model_files(
        self, files_dict: dict[Path, list[str]], *, sort_by_size: bool = False
    ) -> list[Path]:
        latest_files: list[Path] = []
        for root, versions in files_dict.items():
            base_files: dict[str, list[str]] = defaultdict(list)
            for version in versions:
                base_name = re.sub(r"\.\d+$", "", version)
                base_files[base_name].append(version)

            for version_list in base_files.values():
                if all(re.match(r".*\.\d+$", v) is None for v in version_list):
                    latest_file = version_list[0]
                else:
                    latest_file = max(
                        version_list,
                        key=lambda x: int(x.split(".")[-1]) if re.match(r".*\.\d+$", x) else 0,
                    )
                latest_files.append(root / latest_file)

        def model_sort_key(path: Path) -> tuple:
            lower_name = path.name.lower()
            match = re.search(r"\.(prt|drw|asm)(?:\.\d+)?$", lower_name)
            ext = match.group(1) if match else ""
            rank = {"prt": 0, "drw": 1, "asm": 2}.get(ext, 3)
            if not sort_by_size:
                return (rank, lower_name)
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            return (rank, size, lower_name)

        return sorted(latest_files, key=model_sort_key)

    def _working_directory_has_creo_models(
        self, working_dir_str: str | None = None, *, extensions: tuple[str, ...] = _CREO_MODEL_EXTENSIONS_ALL
    ) -> bool:
        """True if the path is a directory with at least one matching model file at top level."""
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s:
            return False
        pattern = _creo_model_name_pattern(extensions)
        try:
            d = Path(s).expanduser()
            if not d.is_dir():
                return False
            return _directory_has_matching_file(
                d, pattern, globs=_creo_model_globs(extensions)
            )
        except OSError:
            return False

    def _working_directory_has_modelcheck_xml(self, working_dir_str: str | None = None) -> bool:
        """True if at least one ModelCHECK result XML exists in the working directory (top level only)."""
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s:
            return False
        try:
            d = Path(s).expanduser()
            if not d.is_dir():
                return False
            # Stop at the first match — do not collect every *.p/a/d.xml name.
            for pattern in ("*.p.xml", "*.a.xml", "*.d.xml"):
                try:
                    for path in d.glob(pattern):
                        try:
                            if path.is_file():
                                return True
                        except OSError:
                            continue
                except OSError:
                    continue
            return False
        except OSError:
            return False

    def _scan_files_recursive(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for entry in directory.rglob("*"):
            if entry.is_file():
                files.append(entry)
        return sorted(files, key=lambda p: str(p).lower())

    def _scan_modelcheck_config_files(self, directory: Path) -> list[Path]:
        """Files under a config folder to embed as ``<ConfigFile>`` in a .dxc.

        When ``directory`` is the main ``config\\`` folder, skips ``config\\templates\\``
        (template-scan configs only — see ``_modelcheck_config_dir_for_task``).
        """
        templates_subdir: Path | None = None
        try:
            candidate = (directory / "templates").resolve()
            if candidate.is_dir():
                templates_subdir = candidate
        except OSError:
            templates_subdir = None
        files: list[Path] = []
        for p in self._scan_files_recursive(directory):
            if p.suffix.lower() in _MODELCHECK_CONFIG_SKIP_SUFFIXES:
                continue
            if templates_subdir is not None:
                try:
                    p.resolve().relative_to(templates_subdir)
                    continue
                except ValueError:
                    pass
            files.append(p)
        return files

    def _chunk_paths(self, items: list[Path], chunk_size: int) -> list[list[Path]]:
        if chunk_size <= 0:
            return [items]
        return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def _remove_batch_runner_scripts(*directories: Path) -> None:
        """Remove generated batch runner .ps1 files from one or more folders."""
        for directory in directories:
            try:
                if not directory.is_dir():
                    continue
                for name in CREO_BATCH_RUNNER_BASENAMES:
                    runner = directory / name
                    if runner.is_file():
                        try:
                            runner.unlink()
                        except OSError:
                            pass
            except OSError:
                pass

    @staticmethod
    def _cleanup_leftover_batch_dxc(
        batch_dir: Path, *, scan_templates: bool, batch_dxc_base: str | None = None
    ) -> None:
        """Remove leftover batch .dxc files (does not remove runner .ps1)."""
        try:
            if not batch_dir.is_dir():
                return
            if scan_templates:
                dxc_candidates = [batch_dir / SCAN_TEMPLATES_DXC_BASENAME]
                dxc_candidates.extend(batch_dir.glob("scan-*.dxc"))
                base = (
                    batch_dxc_base
                    if batch_dxc_base
                    else BATCH_DXC_BASE_SCAN_TEMPLATES
                )
                dxc_candidates.extend(batch_dir.glob(f"{base}-*.dxc"))
            else:
                bases = (
                    [batch_dxc_base]
                    if batch_dxc_base
                    else list(BATCH_DXC_CHUNK_BASES)
                )
                dxc_candidates = []
                for base in bases:
                    dxc_candidates.extend(batch_dir.glob(f"{base}-*.dxc"))
            for p in dxc_candidates:
                if p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    @staticmethod
    def _clear_batch_stop_flag(batch_dir: Path) -> None:
        try:
            flag = batch_dir / BATCH_STOP_FLAG_BASENAME
            if flag.is_file():
                flag.unlink()
        except OSError:
            pass

    @staticmethod
    def _clear_batch_pause_flag(batch_dir: Path) -> None:
        for name in (BATCH_PAUSE_FLAG_BASENAME, BATCH_PAUSE_ACTIVE_BASENAME):
            try:
                flag = batch_dir / name
                if flag.is_file():
                    flag.unlink()
            except OSError:
                pass

    @staticmethod
    def _request_batch_runner_stop(batch_dir: Path | None) -> None:
        if batch_dir is None or not batch_dir.is_dir():
            return
        try:
            (batch_dir / BATCH_STOP_FLAG_BASENAME).write_text("", encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _request_batch_runner_pause(batch_dir: Path | None) -> None:
        if batch_dir is None or not batch_dir.is_dir():
            return
        try:
            (batch_dir / BATCH_PAUSE_FLAG_BASENAME).write_text("", encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _cleanup_leftover_batch_files(
        batch_dir: Path,
        *,
        scan_templates: bool,
        keep_runner_scripts: bool = False,
        batch_dxc_base: str | None = None,
    ) -> None:
        """Remove prior GO batch .dxc and runner script before writing new ones."""
        try:
            if not batch_dir.is_dir():
                return
            CreoDistributedBatchMakerApp._cleanup_leftover_batch_dxc(
                batch_dir,
                scan_templates=scan_templates,
                batch_dxc_base=batch_dxc_base,
            )
            CreoDistributedBatchMakerApp._cleanup_batch_run_complete_flags(
                batch_dir, batch_dxc_base=batch_dxc_base
            )
            CreoDistributedBatchMakerApp._clear_batch_pause_flag(batch_dir)
            CreoDistributedBatchMakerApp._clear_batch_stop_flag(batch_dir)
            if not keep_runner_scripts:
                CreoDistributedBatchMakerApp._remove_batch_runner_scripts(batch_dir)
        except OSError:
            pass

    @staticmethod
    def _ps_single_quoted_literal(path: Path) -> str:
        """Single-quoted PowerShell string literal for a filesystem path."""
        s = str(path.resolve())
        return "'" + s.replace("'", "''") + "'"

    @staticmethod
    def _ps_single_quoted_str(value: str) -> str:
        """Single-quoted PowerShell string literal for arbitrary text."""
        return "'" + (value or "").replace("'", "''") + "'"

    @staticmethod
    def _expected_output_basename(model_path: Path, *, is_modelcheck: bool) -> str | None:
        """Map a model filename to the basename produced in the working dir.

        ModelCHECK: ``foo.prt`` / ``foo.prt.3`` → ``foo.p.xml``; .asm → .a.xml; .drw → .d.xml.
        JPEG (raster write): any of the above → ``foo.jpg``.
        Returns ``None`` if the name does not match ``*.{prt,asm,drw}[.N]``.
        """
        name = model_path.name
        m_ver = re.match(r"^(.*)\.(\d+)$", name)
        if m_ver:
            name = m_ver.group(1)
        m_ext = re.match(r"^(.*)\.(prt|asm|drw)$", name, flags=re.IGNORECASE)
        if not m_ext:
            return None
        stem, ext_lower = m_ext.group(1), m_ext.group(2).lower()
        if is_modelcheck:
            basenames = _modelcheck_expected_output_basenames(model_path)
            return basenames[0] if basenames else None
        return f"{stem}.jpg"

    @staticmethod
    def _append_modelcheck_expected_outputs(
        names: list[str],
        out_to_model: dict[str, str],
        model_path: Path,
    ) -> None:
        for out in _modelcheck_expected_output_basenames(model_path):
            names.append(out)
            out_to_model[out] = model_path.name

    @classmethod
    def _batch_runner_init_stop_ps1(cls, *, cooperative_stop: bool) -> list[str]:
        if cooperative_stop:
            return cls._batch_runner_stop_helpers_ps1()
        return ["$stopRequested = $false", ""]

    @classmethod
    def _batch_runner_wait_delay_ps1(cls, *, indent: str, cooperative_stop: bool) -> list[str]:
        if cooperative_stop:
            return cls._batch_runner_poll_wait_ps1(indent=indent)
        return [f"{indent}Start-Sleep -Seconds 2"]

    @classmethod
    def _batch_runner_stop_helpers_ps1(cls) -> list[str]:
        poll_ms = int(BATCH_PAUSE_POLL_MS)
        return [
            f"$StopFlagPath = Join-Path -Path $WorkDir -ChildPath '{BATCH_STOP_FLAG_BASENAME}'",
            f"$PauseFlagPath = Join-Path -Path $WorkDir -ChildPath '{BATCH_PAUSE_FLAG_BASENAME}'",
            f"$PauseActivePath = Join-Path -Path $WorkDir -ChildPath '{BATCH_PAUSE_ACTIVE_BASENAME}'",
            "$stopRequested = $false",
            "$pauseActive = $false",
            "",
            "function Test-StopRequested {",
            "    return (Test-Path -LiteralPath $StopFlagPath)",
            "}",
            "",
            "function Test-PauseRequested {",
            "    return (Test-Path -LiteralPath $PauseFlagPath)",
            "}",
            "",
            "function Clear-PauseActiveFlag {",
            "    try {",
            "        if (Test-Path -LiteralPath $PauseActivePath) {",
            "            Remove-Item -LiteralPath $PauseActivePath -Force -ErrorAction Stop",
            "        }",
            "    } catch { }",
            "    $script:pauseActive = $false",
            "}",
            "",
            "function Set-PauseActiveFlag {",
            "    try {",
            '        Set-Content -LiteralPath $PauseActivePath -Value "1" -Encoding UTF8 -Force',
            "    } catch { }",
            "    $script:pauseActive = $true",
            "}",
            "",
            "function Invoke-StopRequested {",
            '    Write-ChLog "STOPPED: stop requested from app."',
            "    Clear-PauseActiveFlag",
            "    $script:stopRequested = $true",
            "}",
            "",
            "function Wait-IfPaused {",
            "    if (-not (Test-PauseRequested)) {",
            "        if ($script:pauseActive) {",
            '            Write-ChLog "RESUMED: pause flag cleared; continuing batch."',
            "            Clear-PauseActiveFlag",
            "        }",
            "        if (Test-StopRequested) {",
            "            Invoke-StopRequested",
            "            return $false",
            "        }",
            "        return $true",
            "    }",
            "    if (-not $script:pauseActive) {",
            '        Write-ChLog "PAUSED: pause requested from app; waiting for resume."',
            "        Set-PauseActiveFlag",
            "    }",
            "    while (Test-PauseRequested) {",
            "        if (Test-StopRequested) {",
            "            Invoke-StopRequested",
            "            return $false",
            "        }",
            f"        Start-Sleep -Milliseconds {poll_ms}",
            "    }",
            "    if (Test-StopRequested) {",
            "        Invoke-StopRequested",
            "        return $false",
            "    }",
            '    Write-ChLog "RESUMED: pause flag cleared; continuing batch."',
            "    Clear-PauseActiveFlag",
            "    return $true",
            "}",
            "",
            "function Wait-InterruptibleSeconds {",
            "    param([int]$Seconds)",
            "    $end = (Get-Date).AddSeconds($Seconds)",
            "    while ((Get-Date) -lt $end) {",
            "        if (Test-StopRequested) { return $false }",
            "        Start-Sleep -Milliseconds 200",
            "    }",
            "    return $true",
            "}",
            "",
        ]

    @classmethod
    def _batch_runner_pause_check_ps1(cls, *, indent: str) -> list[str]:
        """Hold between chunks / before kill when pause flag is present. Returns false path via stopRequested."""
        return [
            f"{indent}if (-not (Wait-IfPaused)) {{",
            f"{indent}    break",
            f"{indent}}}",
        ]

    @classmethod
    def _batch_runner_stop_check_ps1(cls, *, indent: str) -> list[str]:
        return [
            f"{indent}if (Test-StopRequested) {{",
            f"{indent}    Invoke-StopRequested",
            f"{indent}    break",
            f"{indent}}}",
        ]

    @classmethod
    def _batch_runner_poll_wait_ps1(cls, *, indent: str, seconds: int = 2) -> list[str]:
        return [
            f"{indent}if (-not (Wait-InterruptibleSeconds {int(seconds)})) {{",
            f"{indent}    Invoke-StopRequested",
            f"{indent}    break",
            f"{indent}}}",
        ]

    @classmethod
    def _batch_runner_stop_exit_ps1(cls, *, indent: str, message: str, sync_timeout_log: bool = False) -> list[str]:
        lines: list[str] = []
        if sync_timeout_log:
            lines.append(f"{indent}Sync-TimeoutLogFromMemory")
        lines.extend(
            [
                f"{indent}if ($stopRequested) {{",
                f'{indent}    Write-ChLog "{message}"',
                f"{indent}    return",
                f"{indent}}}",
            ]
        )
        return lines

    @classmethod
    def _batch_runner_xtop_helpers_ps1(cls, *, xtop_gone_timeout_sec: int) -> list[str]:
        return [
            f"$XtopStartWaitSec = {BATCH_XTOP_START_WAIT_SEC}",
            f"$XtopDeadChecksRequired = {BATCH_XTOP_DEAD_CHECKS}",
            f"$XtopRestartWaitSec = {int(xtop_gone_timeout_sec)}",
            "",
            "function Test-XtopAlive {",
            "    $procs = Get-Process -Name xtop -ErrorAction SilentlyContinue",
            "    if ($null -eq $procs) { return $false }",
            "    return (@($procs).Count -gt 0)",
            "}",
            "",
            "function Get-XtopPid {",
            "    $procs = @(Get-Process -Name xtop -ErrorAction SilentlyContinue)",
            "    if ($procs.Count -eq 0) { return $null }",
            "    if ($procs.Count -eq 1) { return $procs[0].Id }",
            "    return ($procs | Sort-Object -Property Id -Descending | Select-Object -First 1).Id",
            "}",
            "",
            "function Update-XtopDeadWatch {",
            "    param(",
            "        [ref]$DeadStreak,",
            "        [ref]$FirstDeadAt,",
            "        [ref]$WatchEnabled",
            "    )",
            "    if (Test-XtopAlive) {",
            "        $DeadStreak.Value = 0",
            "        $FirstDeadAt.Value = $null",
            "        return $false",
            "    }",
            "    if (-not $WatchEnabled.Value) { return $false }",
            "    $DeadStreak.Value = $DeadStreak.Value + 1",
            "    if ($null -eq $FirstDeadAt.Value) { $FirstDeadAt.Value = Get-Date }",
            "    $deadSec = [int][math]::Floor(((Get-Date) - $FirstDeadAt.Value).TotalSeconds)",
            "    if ($DeadStreak.Value -ge $XtopDeadChecksRequired -and $deadSec -ge $XtopRestartWaitSec) {",
            "        return $true",
            "    }",
            "    return $false",
            "}",
        ]

    @classmethod
    def _batch_runner_timeout_log_ps1(cls) -> list[str]:
        """Load existing timeout log on start; append new model names without duplicates."""
        return [
            "$TimedOutModels = @{}",
            "$TimeoutLogInitialized = $false",
            "$TimeoutLog = Join-Path -Path $WorkDir -ChildPath ('creo-batch-timeouts-' + $TaskKind + '.txt')",
            "",
            "function Get-CreoModelBaseName {",
            "    param([string]$Name)",
            "    if ($Name -match '^(.*\\.(?:prt|asm|drw))(?:\\.\\d+)?$') { return $Matches[1] }",
            "    if ($Name -match '^(.*)\\.p\\.xml$') { return ($Matches[1] + '.prt') }",
            "    if ($Name -match '^(.*)\\.a\\.xml$') { return ($Matches[1] + '.asm') }",
            "    if ($Name -match '^(.*)\\.d\\.xml$') { return ($Matches[1] + '.drw') }",
            "    return $Name",
            "}",
            "",
            "function Get-TimeoutLogModelKey {",
            "    param([string]$Name)",
            "    $base = Get-CreoModelBaseName $Name",
            "    if (-not $base) { return '' }",
            "    return $base.ToLowerInvariant()",
            "}",
            "",
            "function Test-TimedOutModelRecorded {",
            "    param([string]$Name)",
            "    $key = Get-TimeoutLogModelKey $Name",
            "    if (-not $key) { return $true }",
            "    foreach ($k in $TimedOutModels.Keys) {",
            "        if ($k -eq $key) { return $true }",
            "    }",
            "    return $false",
            "}",
            "",
            "function Register-TimeoutLogModelLine {",
            "    param([string]$Stripped, [ref]$PastHeader)",
            "    if (-not $PastHeader.Value) {",
            "        if ($Stripped -ieq 'Models timed out:') {",
            "            $PastHeader.Value = $true",
            "            return $null",
            "        }",
            "        if ($Stripped -match '^(?i)Models timed out:\\s*(.+)$') {",
            "            $PastHeader.Value = $true",
            "            return $Matches[1].Trim()",
            "        }",
            "        return $null",
            "    }",
            "    if (-not $Stripped) { return $null }",
            "    return $Stripped",
            "}",
            "",
            "if (Test-Path -LiteralPath $TimeoutLog) {",
            "    $pastHeader = $false",
            "    try {",
            "        foreach ($line in Get-Content -LiteralPath $TimeoutLog -Encoding UTF8) {",
            "            $stripped = $line.Trim().TrimStart([char]0xFEFF)",
            "            $modelLine = Register-TimeoutLogModelLine -Stripped $stripped -PastHeader ([ref]$pastHeader)",
            "            if (-not $modelLine) { continue }",
            "            $key = Get-TimeoutLogModelKey $modelLine",
            "            if ($key -and -not (Test-TimedOutModelRecorded $key)) {",
            "                $TimedOutModels[$key] = (Get-CreoModelBaseName $modelLine)",
            "            }",
            "        }",
            "    } catch { }",
            "    $script:TimeoutLogInitialized = $true",
            "    if ($TimedOutModels.Count -gt 0) {",
            r'        Write-ChLog ("TIMEOUT LOG: " + $TimedOutModels.Count + " existing timed-out model(s) in " + $TimeoutLog)',
            "    }",
            "}",
            "",
            "function Initialize-TimeoutLog {",
            "    if ($TimeoutLogInitialized) { return $true }",
            "    $header = @(",
            "        ('Task: ' + $TaskKind),",
            "        ('Started: ' + (Get-Date -Format 'HH:mm:ss')),",
            "        ('Log file: ' + $TimeoutLog),",
            "        '',",
            "        'Models timed out:',",
            "        ''",
            "    )",
            "    for ($attempt = 1; $attempt -le 8; $attempt++) {",
            "        try {",
            "            Set-Content -LiteralPath $TimeoutLog -Value ($header -join [Environment]::NewLine) -Encoding UTF8",
            "            $script:TimeoutLogInitialized = $true",
            r'            Write-ChLog ("TIMEOUT LOG: writing timed-out models to " + $TimeoutLog)',
            "            return $true",
            "        } catch {",
            "            if ($attempt -ge 8) {",
            r'                Write-ChLog ("TIMEOUT LOG: could not create " + $TimeoutLog + " (close it in Notepad if open)")',
            "                return $false",
            "            }",
            "            Start-Sleep -Milliseconds 250",
            "        }",
            "    }",
            "    return $false",
            "}",
            "",
            "function Add-TimeoutLogLine {",
            "    param([string]$Line)",
            "    for ($attempt = 1; $attempt -le 8; $attempt++) {",
            "        try {",
            "            if (Test-Path -LiteralPath $TimeoutLog) {",
            "                $raw = [System.IO.File]::ReadAllText($TimeoutLog)",
            "                if ($raw.Length -gt 0 -and $raw[-1] -notin @([char]10, [char]13)) {",
            "                    [System.IO.File]::AppendAllText($TimeoutLog, [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))",
            "                }",
            "            }",
            "            Add-Content -LiteralPath $TimeoutLog -Value $Line -Encoding UTF8",
            "            return $true",
            "        } catch {",
            "            if ($attempt -ge 8) {",
            r'                Write-ChLog ("TIMEOUT LOG: could not append to " + $TimeoutLog + " (close it in Notepad if open): " + $Line)',
            "                return $false",
            "            }",
            "            Start-Sleep -Milliseconds 250",
            "        }",
            "    }",
            "    return $false",
            "}",
            "",
            "function Record-TimedOutChunk {",
            "    param([int]$Chunk, [string[]]$MissingOutputs)",
            "    if ($MissingOutputs.Count -eq 0) { return }",
            "    if (-not (Initialize-TimeoutLog)) { return }",
            "    foreach ($mOut in $MissingOutputs) {",
            "        if (Test-OutputFilePresent -Dir $WorkDir -Name $mOut) { continue }",
            "        $mName = $null",
            "        if ($ModelByOutputByChunk.ContainsKey($Chunk)) {",
            "            $mName = $ModelByOutputByChunk[$Chunk][$mOut]",
            "        }",
            "        if (-not $mName) { $mName = $mOut }",
            "        $key = Get-TimeoutLogModelKey $mName",
            "        if (-not $key -or (Test-TimedOutModelRecorded $key)) { continue }",
            "        $base = Get-CreoModelBaseName $mName",
            "        $TimedOutModels[$key] = $base",
            "        Add-TimeoutLogLine -Line $base | Out-Null",
            "    }",
            "}",
            "",
            "function Get-TimeoutLogLinesOnDisk {",
            "    $onDisk = @{}",
            "    if (-not (Test-Path -LiteralPath $TimeoutLog)) { return $onDisk }",
            "    $pastHeader = $false",
            "    try {",
            "        foreach ($line in Get-Content -LiteralPath $TimeoutLog -Encoding UTF8) {",
            "            $stripped = $line.Trim().TrimStart([char]0xFEFF)",
            "            $modelLine = Register-TimeoutLogModelLine -Stripped $stripped -PastHeader ([ref]$pastHeader)",
            "            if (-not $modelLine) { continue }",
            "            $key = Get-TimeoutLogModelKey $modelLine",
            "            if ($key) { $onDisk[$key] = $true }",
            "        }",
            "    } catch { }",
            "    return $onDisk",
            "}",
            "",
            "function Sync-TimeoutLogFromMemory {",
            "    if ($TimedOutModels.Count -eq 0) { return }",
            "    if (-not (Initialize-TimeoutLog)) { return }",
            "    $onDisk = Get-TimeoutLogLinesOnDisk",
            "    foreach ($key in @($TimedOutModels.Keys)) {",
            "        if (-not $key -or $onDisk.ContainsKey($key)) { continue }",
            "        $base = $TimedOutModels[$key]",
            "        if (-not $base) { $base = $key }",
            "        Add-TimeoutLogLine -Line $base | Out-Null",
            "    }",
            "}",
        ]

    @classmethod
    def _batch_runner_output_file_helpers_ps1(cls) -> list[str]:
        """JPEG batches: treat renamed part/assembly/drawing thumbs as satisfying ``stem.jpg``."""
        return [
            "function Test-OutputFilePresent {",
            "    param([string]$Dir, [string]$Name)",
            "    if (-not $Name) { return $false }",
            "    $p = Join-Path -Path $Dir -ChildPath $Name",
            "    if (Test-Path -LiteralPath $p) { return $true }",
            "    if ($TaskKind -eq 'modelcheck' -and $Name -match '(?i)\\.(p|a|d)\\.(xml|html)$') {",
            "        $want = $Name.ToLowerInvariant()",
            "        try {",
            "            foreach ($entry in [System.IO.Directory]::EnumerateFiles($Dir)) {",
            "                if ([System.IO.Path]::GetFileName($entry).ToLowerInvariant() -eq $want) { return $true }",
            "            }",
            "        } catch { }",
            "    }",
            "    if ($Name -notmatch '(?i)\\.jpg$') { return $false }",
            "    $stem = $Name.Substring(0, $Name.Length - 4)",
            "    if ($TaskKind -eq 'jpeg3d_part') {",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.part.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.model.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "    }",
            "    if ($TaskKind -eq 'jpeg3d_asm') {",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.assembly.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.model.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "    }",
            "    if ($TaskKind -eq 'jpeg3d') {",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.model.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.part.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.assembly.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "    }",
            "    if ($TaskKind -eq 'jpeg2d') {",
            "        $alt = Join-Path -Path $Dir -ChildPath ($stem + '.drawing.jpg')",
            "        if (Test-Path -LiteralPath $alt) { return $true }",
            "    }",
            "    return $false",
            "}",
            "",
            "function Get-MissingOutputs {",
            "    param([string]$Dir, [string[]]$Names)",
            "    $missing = @()",
            "    foreach ($n in $Names) {",
            "        if (-not $n) { continue }",
            "        if (-not (Test-OutputFilePresent -Dir $Dir -Name $n)) { $missing += $n }",
            "    }",
            "    return ,$missing",
            "}",
            "",
        ]

    @classmethod
    def _batch_runner_finalize_chunk_timeout_log_ps1(cls, *, indent: str) -> list[str]:
        """Record any missing outputs for this chunk and flush the timeout log to disk."""
        i = indent
        return [
            f"{i}$missing = Get-MissingOutputs -Dir $WorkDir -Names $expected",
            f"{i}if ($missing.Count -gt 0) {{",
            f"{i}    Record-TimedOutChunk -Chunk $chunk -MissingOutputs $missing",
            f"{i}    $TimedOutFileCount += $missing.Count",
            f"{i}    $SuccessFileCount += ($expected.Count - $missing.Count)",
            f"{i}}} else {{",
            f'{i}    Write-ChLog ("DONE: all " + $expected.Count + " expected output file(s) present.")',
            f"{i}    $SuccessFileCount += $expected.Count",
            f"{i}}}",
            f"{i}Sync-TimeoutLogFromMemory",
            f'{i}if ($TimedOutModels.Count -gt 0) {{',
            f'{i}    Write-ChLog ("TIMEOUT LOG: chunk " + $chunk + " saved; " + $TimedOutModels.Count + " model(s) in " + $TimeoutLog)',
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_xtop_wait_init_ps1(cls, *, indent: str) -> list[str]:
        return [
            f"{indent}$xtopDeadStreak = 0",
            f"{indent}$xtopFirstDeadAt = $null",
            f"{indent}$xtopWatchEnabled = $false",
            f"{indent}$xtopWasAlive = $false",
            f"{indent}$xtopLastPid = $null",
            f"{indent}$xtopIgnoreUntilClear = $false",
        ]

    @classmethod
    def _batch_runner_prelaunch_kill_xtop_ps1(cls, *, indent: str) -> list[str]:
        """Run kill.bat before ptcdbatch when xtop is still running from a prior chunk."""
        i = indent
        return [
            f"{i}if (Test-XtopAlive) {{",
            f'{i}    Write-ChLog "Note: xtop still running before chunk launch; running kill.bat..."',
            f"{i}    try {{",
            f"{i}        $kp = Start-Process -FilePath $KillBat -Wait -PassThru -WindowStyle Hidden",
            f'{i}        Write-ChLog ("kill.bat exit code: " + $kp.ExitCode)',
            f"{i}    }} catch {{",
            f'{i}        Write-ChLog ("WARNING: kill.bat before chunk failed: " + $_.Exception.Message)',
            f"{i}    }}",
            *cls._batch_runner_post_kill_settle_ps1(indent=i, cooperative_stop=False),
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_post_kill_settle_ps1(
        cls, *, indent: str, cooperative_stop: bool
    ) -> list[str]:
        """Brief pause after kill.bat so Creo/db batch processes can exit before the next launch."""
        i = indent
        sec = BATCH_POST_KILL_SETTLE_SEC
        lines = [
            f'{i}Write-ChLog "Pausing {sec}s after kill.bat..."',
        ]
        if cooperative_stop:
            lines.extend(
                [
                    f"{i}if (-not (Wait-InterruptibleSeconds {sec})) {{",
                    f"{i}    $stopRequested = $true",
                    f"{i}}}",
                ]
            )
        else:
            lines.append(f"{i}Start-Sleep -Seconds {sec}")
        return lines

    @classmethod
    def _batch_runner_xtop_mark_stale_at_launch_ps1(cls, *, indent: str) -> list[str]:
        """Ignore xtop left over from the previous chunk until it exits."""
        i = indent
        return [
            f"{i}$xtopIgnoreUntilClear = (Test-XtopAlive)",
            f"{i}if ($xtopIgnoreUntilClear) {{",
            f'{i}    Write-ChLog "Note: xtop still running from prior chunk; ignoring until it exits before starting this chunk timer."',
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_xtop_wait_check_ps1(
        cls,
        *,
        indent: str,
        chunk_var: str | None = None,
    ) -> list[str]:
        lines = [
            f"{indent}if (Update-XtopDeadWatch -DeadStreak ([ref]$xtopDeadStreak) -FirstDeadAt ([ref]$xtopFirstDeadAt) -WatchEnabled ([ref]$xtopWatchEnabled)) {{",
            f'{indent}    Write-ChLog ("XTOP GONE: no xtop for " + $XtopRestartWaitSec + "s while waiting for output (no restart); moving on.")',
        ]
        if chunk_var is None:
            lines.extend(
                [
                    f"{indent}    $TimedOutFileCount = $missing.Count",
                    f"{indent}    $SuccessFileCount = $Expected.Count - $missing.Count",
                ]
            )
        lines.extend(
            [
                f"{indent}    $timedOut = $true",
                f"{indent}    break",
                f"{indent}}}",
            ]
        )
        return lines

    @classmethod
    def _batch_runner_xtop_manage_wait_timer_ps1(cls, *, indent: str) -> list[str]:
        """Track xtop; reset inactivity timer on first start, PID change, or xtop restarts between models."""
        i = indent
        return [
            f"{i}$xtopPid = Get-XtopPid",
            f"{i}if (Test-XtopAlive) {{",
            f"{i}    if ($xtopIgnoreUntilClear) {{",
            f"{i}        $staleSec = [int][math]::Floor(((Get-Date) - $chunkWaitStart).TotalSeconds)",
            f"{i}        if ($staleSec -ge 20) {{",
            f'{i}            Write-ChLog "Stale xtop still running; running kill.bat and waiting for a fresh xtop..."',
            f"{i}            try {{",
            f"{i}                $kp = Start-Process -FilePath $KillBat -Wait -PassThru -WindowStyle Hidden",
            f'{i}                Write-ChLog ("kill.bat exit code: " + $kp.ExitCode)',
            f"{i}            }} catch {{",
            f'{i}                Write-ChLog ("WARNING: kill.bat for stale xtop failed: " + $_.Exception.Message)',
            f"{i}            }}",
            *cls._batch_runner_post_kill_settle_ps1(indent=f"{i}            ", cooperative_stop=False),
            f"{i}            $xtopIgnoreUntilClear = $false",
            f"{i}            $xtopWasAlive = $false",
            f"{i}            $xtopLastPid = $null",
            f"{i}        }} else {{",
            f"{i}            $xtopWasAlive = $true",
            f"{i}            if ($null -ne $xtopPid) {{ $xtopLastPid = $xtopPid }}",
            f"{i}        }}",
            f"{i}    }} else {{",
            f"{i}        $pidRestart = ($xtopWatchEnabled -and $null -ne $xtopLastPid -and $null -ne $xtopPid -and $xtopPid -ne $xtopLastPid)",
            f"{i}        if ($pidRestart -or ($xtopWatchEnabled -and -not $xtopWasAlive)) {{",
            f'{i}            if ($pidRestart) {{',
            f'{i}                Write-ChLog ("XTOP RESTART: new xtop PID " + $xtopPid + " (was " + $xtopLastPid + "); resetting inactivity timer.")',
            f'{i}            }} else {{',
            f'{i}                Write-ChLog "XTOP RESTART: xtop running again; resetting inactivity timer."',
            f'{i}            }}',
            f"{i}            $waitStart = Get-Date",
            f"{i}            $xtopDeadStreak = 0",
            f"{i}            $xtopFirstDeadAt = $null",
            f"{i}        }}",
            f"{i}        if (-not $xtopWatchEnabled) {{",
            f"{i}            $xtopWatchEnabled = $true",
            f"{i}            $waitStart = Get-Date",
            f"{i}        }}",
            f"{i}        $xtopWasAlive = $true",
            f"{i}        if ($null -ne $xtopPid) {{ $xtopLastPid = $xtopPid }}",
            f"{i}    }}",
            f"{i}}} else {{",
            f"{i}    if ($xtopIgnoreUntilClear) {{",
            f"{i}        $xtopIgnoreUntilClear = $false",
            f'{i}        Write-ChLog "Prior xtop exited; waiting for new xtop for this chunk."',
            f"{i}    }}",
            f"{i}    $xtopWasAlive = $false",
            f"{i}    $xtopLastPid = $null",
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_xtop_start_timeout_check_ps1(cls, *, indent: str) -> list[str]:
        """Fail chunk when xtop never appears within XtopStartWaitSec after ptcdbatch launch."""
        i = indent
        return [
            f"{i}if (-not $xtopWatchEnabled) {{",
            f"{i}    $totalWaitSec = [int][math]::Floor(((Get-Date) - $chunkWaitStart).TotalSeconds)",
            f"{i}    if ($totalWaitSec -ge $XtopStartWaitSec) {{",
            f'{i}        Write-ChLog ("XTOP NEVER STARTED: no xtop within " + $XtopStartWaitSec + "s after launch; moving on.")',
            f"{i}        $timedOut = $true",
            f"{i}        break",
            f"{i}    }}",
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_wait_timeout_check_ps1(cls, *, indent: str, timeout_body: list[str]) -> list[str]:
        """Apply output inactivity timeout only after xtop has started at least once."""
        i = indent
        lines = [
            f"{i}$elapsed = [int][math]::Floor(((Get-Date) - $waitStart).TotalSeconds)",
            f"{i}if ($xtopWatchEnabled -and $elapsed -ge $OutputTimeoutSec) {{",
        ]
        for line in timeout_body:
            lines.append(f"{i}    {line}")
        lines.append(f"{i}}}")
        return lines

    @classmethod
    def _batch_runner_wait_progress_log_ps1(
        cls,
        *,
        indent: str,
        names_var: str,
        extra_tail: str = "",
    ) -> list[str]:
        """Log wait status; inactivity seconds only after xtop has started and exited."""
        i = indent
        tail = extra_tail
        return [
            f"{i}$totalWaitSec = [int][math]::Floor(((Get-Date) - $chunkWaitStart).TotalSeconds)",
            f"{i}if (-not $xtopWatchEnabled) {{",
            f"{i}    if ($totalWaitSec -le 4 -or ($totalWaitSec % 30 -eq 0)) {{",
            f'{i}        Write-ChLog ("WAITING: " + $missing.Count + " of " + ${names_var}.Count + " output file(s) missing (waiting for xtop to start; " + $totalWaitSec + "s total wait)"{tail})',
            f"{i}    }}",
            f"{i}}} elseif (Test-XtopAlive) {{",
            f"{i}    if ($elapsed -le 4 -or ($elapsed % 30 -eq 0)) {{",
            f'{i}        Write-ChLog ("WAITING: " + $missing.Count + " of " + ${names_var}.Count + " output file(s) missing (" + $elapsed + "s with no new output; xtop running; " + $totalWaitSec + "s total wait)"{tail})',
            f"{i}    }}",
            f"{i}}} else {{",
            f"{i}    if ($elapsed -le 4 -or ($elapsed % 30 -eq 0)) {{",
            f'{i}        Write-ChLog ("WAITING: " + $missing.Count + " of " + ${names_var}.Count + " output file(s) missing (" + $elapsed + "s with no progress; " + $totalWaitSec + "s total wait)"{tail})',
            f"{i}    }}",
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_kill_after_settle_ps1(
        cls, *, indent: str, names_var: str, cooperative_stop: bool
    ) -> list[str]:
        """Run kill.bat after chunk wait ends; message reflects missing outputs vs success."""
        i = indent
        lines = [
            f"{i}$missingAfterWait = Get-MissingOutputs -Dir $WorkDir -Names ${names_var}",
        ]
        if cooperative_stop:
            lines.extend(
                [
                    f"{i}if ($stopRequested) {{",
                    f'{i}    Write-ChLog "STOPPED: batch run ended by user."',
                    f"{i}}} elseif ($timedOut -or $missingAfterWait.Count -gt 0) {{",
                    f'{i}    Write-ChLog ("Chunk incomplete (" + $missingAfterWait.Count + " output file(s) still missing); running kill.bat...")',
                    f"{i}}} elseif (Test-XtopAlive) {{",
                    f'{i}    Write-ChLog "All output file(s) present; xtop still running — running kill.bat..."',
                    f"{i}}} else {{",
                    f'{i}    Write-ChLog ("Settling " + $OutputSettleSec + "s before kill.bat...")',
                    f"{i}    if (-not (Wait-InterruptibleSeconds $OutputSettleSec)) {{",
                    f"{i}        $stopRequested = $true",
                    f"{i}    }}",
                    f"{i}}}",
                    f"{i}if (-not $stopRequested) {{",
                    f"{i}    if (-not (Wait-IfPaused)) {{ }}",
                    f"{i}}}",
                    f"{i}if (-not $stopRequested) {{",
                ]
            )
        else:
            lines.extend(
                [
                    f"{i}if ($timedOut -or $missingAfterWait.Count -gt 0) {{",
                    f'{i}    Write-ChLog ("Chunk incomplete (" + $missingAfterWait.Count + " output file(s) still missing); running kill.bat...")',
                    f"{i}}} elseif (Test-XtopAlive) {{",
                    f'{i}    Write-ChLog "All output file(s) present; xtop still running — running kill.bat..."',
                    f"{i}}} else {{",
                    f'{i}    Write-ChLog ("Settling " + $OutputSettleSec + "s before kill.bat...")',
                    f"{i}    Start-Sleep -Seconds $OutputSettleSec",
                    f"{i}}}",
                ]
            )
        lines.extend(
            [
                f'{i}Write-ChLog "Running kill.bat..."',
                f"{i}try {{",
                f"{i}    $kp = Start-Process -FilePath $KillBat `",
                f"{i}        -WorkingDirectory ([System.IO.Path]::GetDirectoryName($KillBat)) -Wait -PassThru -NoNewWindow -ErrorAction Stop",
                f'{i}    Write-ChLog ("kill.bat exit code: " + $kp.ExitCode)',
                f"{i}}} catch {{",
                f'{i}    Write-ChLog ("ERROR: kill.bat failed: " + $_.Exception.Message)',
                f"{i}}}",
                *cls._batch_runner_post_kill_settle_ps1(
                    indent=i, cooperative_stop=cooperative_stop
                ),
            ]
        )
        if cooperative_stop:
            lines.append(f"{i}}}")
        return lines

    @classmethod
    def _batch_runner_write_chlog_ps1(cls, debug_log_path: Path | None) -> list[str]:
        """PowerShell ``Write-ChLog`` helper; mirrors console lines to ``debug_log_path`` when set."""
        lines: list[str] = []
        if debug_log_path is not None:
            log_ps = cls._ps_single_quoted_literal(debug_log_path)
            lines.extend(
                [
                    f"$DebugLogPath = {log_ps}",
                    "try {",
                    r'    "[$(Get-Date -Format ''yyyy-MM-dd HH:mm:ss'')] Runner log started." | Set-Content -LiteralPath $DebugLogPath -Encoding UTF8',
                    "} catch { }",
                    "",
                ]
            )
        lines.extend(
            [
                "function Write-ChLog {",
                "    param([string]$Message)",
                "    $ts = Get-Date -Format 'HH:mm:ss'",
                '    $line = "[$ts] $Message"',
            ]
        )
        if debug_log_path is not None:
            lines.extend(
                [
                    "    if ($DebugLogPath) {",
                    "        try { Add-Content -LiteralPath $DebugLogPath -Value $line -Encoding UTF8 } catch { }",
                    "    }",
                ]
            )
        lines.extend(
            [
                "    if ($Message -match '(?i)^DONE:' -or $Message -match '(?i)^SKIP:') {",
                '        Write-Host $line -ForegroundColor Green',
                "    } elseif ($Message -match '(?i)^TIMEOUT:') {",
                '        Write-Host $line -ForegroundColor Red',
                "    } elseif ($Message -match '(?i)^XTOP (GONE|NEVER STARTED):') {",
                '        Write-Host $line -ForegroundColor Red',
                "    } elseif ($Message -match '(?i)^PROGRESS:' -or $Message -match '(?i)new output file\\(s\\)') {",
                '        Write-Host $line -ForegroundColor Yellow',
                "    } elseif ($Message -match '(?i)^Pre-check:\\s*(\\d+)\\s+of\\s+(\\d+)\\s') {",
                "        if ([int]$Matches[1] -ne [int]$Matches[2]) {",
                '            Write-Host $line -ForegroundColor Yellow',
                "        } else {",
                '            Write-Host $line',
                "        }",
                "    } else {",
                '        Write-Host $line',
                "    }",
                "}",
                "",
            ]
        )
        return lines

    @classmethod
    def _build_scan_templates_runner_ps1(
        cls,
        ptcdbatch_bat: Path,
        templates_dir: Path,
        kill_bat: Path,
        expected_outputs: list[str],
        output_timeout_sec: int,
        xtop_gone_timeout_sec: int,
        debug_log_path: Path | None = None,
        cooperative_stop: bool = False,
    ) -> str:
        """PowerShell runner for Scan Templates: one templates.dxc, all template models.

        Removes templates.dxc in a finally block when the job finishes (run, skip, or error).
        """
        ptc = cls._ps_single_quoted_literal(ptcdbatch_bat)
        wd = cls._ps_single_quoted_literal(templates_dir)
        kb = cls._ps_single_quoted_literal(kill_bat)
        dxc_name = cls._ps_single_quoted_str(SCAN_TEMPLATES_DXC_BASENAME)
        if expected_outputs:
            expected_ps = "@(" + ", ".join(cls._ps_single_quoted_str(n) for n in expected_outputs) + ")"
        else:
            expected_ps = "@()"

        lines = [
            "$ErrorActionPreference = 'Continue'",
            f"$PtcDbatch = {ptc}",
            f"$WorkDir = {wd}",
            f"$KillBat = {kb}",
            f"$DxcName = {dxc_name}",
            f"$Expected = {expected_ps}",
            f"$OutputTimeoutSec = {int(output_timeout_sec)}",
            f"$OutputSettleSec = {BATCH_OUTPUT_SETTLE_SEC}",
            "",
            *cls._batch_runner_write_chlog_ps1(debug_log_path),
            *cls._batch_runner_init_stop_ps1(cooperative_stop=cooperative_stop),
            *cls._batch_runner_xtop_helpers_ps1(xtop_gone_timeout_sec=xtop_gone_timeout_sec),
            "",
            "function Get-MissingOutputs {",
            "    param([string]$Dir, [string[]]$Names)",
            "    $missing = @()",
            "    foreach ($n in $Names) {",
            "        if (-not $n) { continue }",
            "        $p = Join-Path -Path $Dir -ChildPath $n",
            "        if (-not (Test-Path -LiteralPath $p)) { $missing += $n }",
            "    }",
            "    return ,$missing",
            "}",
            "",
            "$SuccessFileCount = 0",
            "$TimedOutFileCount = 0",
            "$dxc = Join-Path -Path $WorkDir -ChildPath $DxcName",
            "",
            r'Write-ChLog "Scan Templates runner starting."',
            r'Write-ChLog "ptcdbatch: $PtcDbatch"',
            r'Write-ChLog "Working directory: $WorkDir"',
            r'Write-ChLog "DXC: $dxc"',
            r'Write-ChLog "kill.bat: $KillBat"',
            r'Write-ChLog ("Output wait timeout: " + $OutputTimeoutSec + " s; xtop start: " + $XtopStartWaitSec + " s; xtop gone: " + $XtopRestartWaitSec + " s; settle: " + $OutputSettleSec + " s")',
            "",
            "try {",
            "if (-not (Test-Path -LiteralPath $dxc)) {",
            r'    Write-ChLog "ERROR: DXC file missing."',
            "    exit 1",
            "}",
            "",
            "if ($Expected.Count -eq 0) {",
            r'    Write-ChLog "SKIP: no expected output files configured; nothing to do."',
            "} else {",
            r'    Write-ChLog "Removing prior template scan output file(s) before re-run."',
            "    foreach ($n in $Expected) {",
            "        if (-not $n) { continue }",
            "        $outPath = Join-Path -Path $WorkDir -ChildPath $n",
            "        if (Test-Path -LiteralPath $outPath) {",
            "            Remove-Item -LiteralPath $outPath -Force -ErrorAction SilentlyContinue",
            r'            Write-ChLog ("Removed prior output: " + $n)',
            "        }",
            "    }",
            r'    Write-ChLog ("Running dbatch for " + $Expected.Count + " expected output file(s).")',
            "",
            "    $batParent = [System.IO.Path]::GetDirectoryName($PtcDbatch)",
            r'    Write-ChLog "Launching ptcdbatch (hidden window): -nographics -process $dxc"',
            "    try {",
            "        $null = Start-Process -FilePath $PtcDbatch -WorkingDirectory $batParent `",
            "            -ArgumentList @('-nographics', '-process', $dxc) `",
            "            -WindowStyle Hidden -ErrorAction Stop",
            "    } catch {",
            r'        Write-ChLog ("ERROR: failed to start ptcdbatch: " + $_.Exception.Message)',
            "        exit 1",
            "    }",
            "",
            r'    Write-ChLog "WAITING: for expected output file(s) to appear (poll every 2s; inactivity timer starts when xtop appears; resets on new output or xtop restart)."',
            "    $chunkWaitStart = Get-Date",
            "    $waitStart = $chunkWaitStart",
            "    $missing = Get-MissingOutputs -Dir $WorkDir -Names $Expected",
            "    $lastMissingCount = $missing.Count",
            "    $timedOut = $false",
            *cls._batch_runner_xtop_wait_init_ps1(indent="    "),
            *cls._batch_runner_xtop_mark_stale_at_launch_ps1(indent="    "),
            "    while ($true) {",
            *(
                cls._batch_runner_stop_check_ps1(indent="        ")
                if cooperative_stop
                else []
            ),
            "        $missing = Get-MissingOutputs -Dir $WorkDir -Names $Expected",
            "        if ($missing.Count -eq 0) { break }",
            "        if ($missing.Count -lt $lastMissingCount) {",
            "            $delta = $lastMissingCount - $missing.Count",
            r'            Write-ChLog ("PROGRESS: " + $delta + " new output file(s); resetting timer. " + $missing.Count + " of " + $Expected.Count + " remaining.")',
            "            $waitStart = Get-Date",
            "            $lastMissingCount = $missing.Count",
            "        }",
            *cls._batch_runner_xtop_manage_wait_timer_ps1(indent="        "),
            *cls._batch_runner_xtop_start_timeout_check_ps1(indent="        "),
            *cls._batch_runner_wait_timeout_check_ps1(
                indent="        ",
                timeout_body=[
                    r'Write-ChLog ("TIMEOUT: no new output file(s) for " + $elapsed + "s; " + $missing.Count + " of " + $Expected.Count + " still missing.")',
                    "$TimedOutFileCount = $missing.Count",
                    "$SuccessFileCount = $Expected.Count - $missing.Count",
                    "$timedOut = $true",
                    "break",
                ],
            ),
            *cls._batch_runner_wait_progress_log_ps1(indent="        ", names_var="Expected"),
            *cls._batch_runner_xtop_wait_check_ps1(indent="        "),
            *cls._batch_runner_wait_delay_ps1(indent="        ", cooperative_stop=cooperative_stop),
            "    }",
            "    if (-not $timedOut) {",
            r'        Write-ChLog ("DONE: all " + $Expected.Count + " expected output file(s) present.")',
            "        $SuccessFileCount = $Expected.Count",
            "    }",
            "",
            *cls._batch_runner_kill_after_settle_ps1(
                indent="    ", names_var="Expected", cooperative_stop=cooperative_stop
            ),
            "}",
            "} finally {",
            "    try {",
            "        if (Test-Path -LiteralPath $dxc) {",
            "            Remove-Item -LiteralPath $dxc -Force -ErrorAction Stop",
            r'            Write-ChLog ("Removed chunk dxc: " + $dxc)',
            "        }",
            "    } catch {",
            r'        Write-ChLog ("Cleanup note: " + $_.Exception.Message)',
            "    }",
            "}",
            "",
            *cls._batch_runner_stop_exit_ps1(
                indent="",
                message="Scan Templates runner stopped by user request.",
            ),
            r'Write-ChLog "---------- Batch summary ----------"',
            r'Write-ChLog ("Count of Files Success: " + $SuccessFileCount)',
            r'Write-ChLog ("Count of Files Timed Out: " + $TimedOutFileCount)',
            "",
            "try {",
            f"    $runCompleteFlag = Join-Path -Path $WorkDir -ChildPath '{BATCH_DXC_BASE_SCAN_TEMPLATES}{BATCH_RUN_COMPLETE_FLAG_SUFFIX}'",
            '    Set-Content -LiteralPath $runCompleteFlag -Value "1" -Encoding UTF8 -Force',
            "} catch {",
            r'    Write-ChLog ("Cleanup note: could not write run-complete flag: " + $_.Exception.Message)',
            "}",
            "",
            r'Write-ChLog "Scan Templates runner finished."',
        ]
        return "\n".join(lines) + "\n"

    @classmethod
    def _build_chunk_runner_ps1(
        cls,
        ptcdbatch_bat: Path,
        working_dir: Path,
        kill_bat: Path,
        num_chunks: int,
        expected_outputs_per_chunk: list[list[str]],
        output_to_model_per_chunk: list[dict[str, str]],
        task_kind: str,
        output_timeout_sec: int,
        xtop_gone_timeout_sec: int,
        debug_log_path: Path | None = None,
        cooperative_stop: bool = False,
        chunk_base: str = CREO_BATCH_BASE,
        chunk_size: int = CREO_BATCH_CHUNK_SIZE_DEFAULT,
    ) -> str:
        """PowerShell: per chunk, skip if outputs already exist; else launch ptcdbatch, poll for expected output files, settle, then run kill.bat.

        If any outputs time out, write one per-run timeout summary file in ``working_dir``
        listing timed-out model names only. Removes each chunk .dxc when that chunk finishes.
        """
        ptc = cls._ps_single_quoted_literal(ptcdbatch_bat)
        wd = cls._ps_single_quoted_literal(working_dir)
        kb = cls._ps_single_quoted_literal(kill_bat)
        n = int(num_chunks)
        chunk_sz = int(chunk_size)
        base = chunk_base.replace("'", "''")
        task_kind_ps = cls._ps_single_quoted_str(task_kind)

        expected_table_lines: list[str] = ["$ExpectedByChunk = @{"]
        for idx in range(1, n + 1):
            names = expected_outputs_per_chunk[idx - 1] if idx - 1 < len(expected_outputs_per_chunk) else []
            if names:
                joined = ", ".join(cls._ps_single_quoted_str(name) for name in names)
                expected_table_lines.append(f"    {idx} = @({joined})")
            else:
                expected_table_lines.append(f"    {idx} = @()")
        expected_table_lines.append("}")
        model_map_lines: list[str] = ["$ModelByOutputByChunk = @{"]
        for idx in range(1, n + 1):
            out_map = output_to_model_per_chunk[idx - 1] if idx - 1 < len(output_to_model_per_chunk) else {}
            if out_map:
                pairs = "; ".join(
                    f"{cls._ps_single_quoted_str(out)} = {cls._ps_single_quoted_str(model)}"
                    for out, model in out_map.items()
                )
                model_map_lines.append(f"    {idx} = @{{ {pairs} }}")
            else:
                model_map_lines.append(f"    {idx} = @{{}}")
        model_map_lines.append("}")

        lines = [
            "$ErrorActionPreference = 'Continue'",
            f"$PtcDbatch = {ptc}",
            f"$WorkDir = {wd}",
            f"$KillBat = {kb}",
            f"$TaskKind = {task_kind_ps}",
            f"$NumChunks = {n}",
            f"$ChunkBase = '{base}'",
            f"$OutputTimeoutSec = {int(output_timeout_sec)}",
            f"$OutputSettleSec = {BATCH_OUTPUT_SETTLE_SEC}",
            "",
            *expected_table_lines,
            "",
            *model_map_lines,
            "",
            *cls._batch_runner_write_chlog_ps1(debug_log_path),
            *cls._batch_runner_init_stop_ps1(cooperative_stop=cooperative_stop),
            *cls._batch_runner_xtop_helpers_ps1(xtop_gone_timeout_sec=xtop_gone_timeout_sec),
            "",
            *cls._batch_runner_output_file_helpers_ps1(),
            *cls._batch_runner_timeout_log_ps1(),
            "$SuccessFileCount = 0",
            "$TimedOutFileCount = 0",
            "",
            f'Write-ChLog ("Runner starting. $NumChunks chunk(s); chunk size {chunk_sz}. Skips chunks whose outputs already exist; otherwise polls for expected output files.")',
            r'Write-ChLog "ptcdbatch: $PtcDbatch"',
            r'Write-ChLog "Working directory: $WorkDir"',
            r'Write-ChLog "kill.bat: $KillBat"',
            r'Write-ChLog ("Output wait timeout: " + $OutputTimeoutSec + " s; xtop start: " + $XtopStartWaitSec + " s; xtop gone: " + $XtopRestartWaitSec + " s; settle: " + $OutputSettleSec + " s")',
            "",
            "for ($chunk = 1; $chunk -le $NumChunks; $chunk++) {",
            *(
                (
                    ["    if ($stopRequested) { break }"]
                    + cls._batch_runner_pause_check_ps1(indent="    ")
                )
                if cooperative_stop
                else []
            ),
            r'    Write-ChLog "---------- Chunk $chunk / $NumChunks ----------"',
            '    $dxc = Join-Path -Path $WorkDir -ChildPath ("{0}-{1}.dxc" -f $ChunkBase, $chunk)',
            r'    Write-ChLog "DXC path: $dxc"',
            "    try {",
            "    if (-not (Test-Path -LiteralPath $dxc)) {",
            r'        Write-ChLog "ERROR: DXC file missing. Skipping this chunk."',
            "        continue",
            "    }",
            "",
            "    $expected = @($ExpectedByChunk[$chunk])",
            "    if ($expected.Count -eq 0) {",
            r'        Write-ChLog "SKIP: no expected output files were configured for this chunk; nothing to do."',
            "        continue",
            "    }",
            "    $missing = Get-MissingOutputs -Dir $WorkDir -Names $expected",
            "    if ($missing.Count -eq 0) {",
            r'        Write-ChLog ("SKIP: all " + $expected.Count + " expected output file(s) already exist for chunk " + $chunk + ".")',
            "        $SuccessFileCount += $expected.Count",
            "        continue",
            "    }",
            r'    Write-ChLog ("Pre-check: " + $missing.Count + " of " + $expected.Count + " output file(s) missing; will run dbatch.")',
            "",
            *cls._batch_runner_prelaunch_kill_xtop_ps1(indent="    "),
            "    $batParent = [System.IO.Path]::GetDirectoryName($PtcDbatch)",
            r'    Write-ChLog "Launching ptcdbatch (hidden window): -nographics -process $dxc"',
            "    try {",
            "        $null = Start-Process -FilePath $PtcDbatch -WorkingDirectory $batParent `",
            "            -ArgumentList @('-nographics', '-process', $dxc) `",
            "            -WindowStyle Hidden -ErrorAction Stop",
            "    } catch {",
            r'        Write-ChLog ("ERROR: failed to start ptcdbatch: " + $_.Exception.Message)',
            "        Record-TimedOutChunk -Chunk $chunk -MissingOutputs $missing",
            "        $TimedOutFileCount += $missing.Count",
            "        Sync-TimeoutLogFromMemory",
            "        continue",
            "    }",
            "",
            r'    Write-ChLog "WAITING: for expected output file(s) to appear (poll every 2s; inactivity timer starts when xtop appears; resets on new output or xtop restart)."',
            "    $chunkWaitStart = Get-Date",
            "    $waitStart = $chunkWaitStart",
            "    $missing = Get-MissingOutputs -Dir $WorkDir -Names $expected",
            "    $lastMissingCount = $missing.Count",
            "    $timedOut = $false",
            *cls._batch_runner_xtop_wait_init_ps1(indent="    "),
            *cls._batch_runner_xtop_mark_stale_at_launch_ps1(indent="    "),
            "    while ($true) {",
            *(
                cls._batch_runner_stop_check_ps1(indent="        ")
                if cooperative_stop
                else []
            ),
            "        $missing = Get-MissingOutputs -Dir $WorkDir -Names $expected",
            "        if ($missing.Count -eq 0) { break }",
            "        if ($missing.Count -lt $lastMissingCount) {",
            "            $delta = $lastMissingCount - $missing.Count",
            r'            Write-ChLog ("PROGRESS: " + $delta + " new output file(s) detected; resetting inactivity timer. " + $missing.Count + " of " + $expected.Count + " remaining.")',
            "            $waitStart = Get-Date",
            "            $lastMissingCount = $missing.Count",
            "        }",
            *cls._batch_runner_xtop_manage_wait_timer_ps1(indent="        "),
            *cls._batch_runner_xtop_start_timeout_check_ps1(indent="        "),
            *cls._batch_runner_wait_timeout_check_ps1(
                indent="        ",
                timeout_body=[
                    r'Write-ChLog ("TIMEOUT: no new output file(s) for " + $elapsed + "s; " + $missing.Count + " of " + $expected.Count + " still missing. First missing: " + $missing[0] + ".")',
                    "$timedOut = $true",
                    "break",
                ],
            ),
            *cls._batch_runner_wait_progress_log_ps1(
                indent="        ",
                names_var="expected",
                extra_tail=' + " First missing: " + $missing[0] + "."',
            ),
            *cls._batch_runner_xtop_wait_check_ps1(indent="        ", chunk_var="chunk"),
            *cls._batch_runner_wait_delay_ps1(indent="        ", cooperative_stop=cooperative_stop),
            "    }",
            *cls._batch_runner_finalize_chunk_timeout_log_ps1(indent="    "),
            "",
            *cls._batch_runner_kill_after_settle_ps1(
                indent="    ", names_var="expected", cooperative_stop=cooperative_stop
            ),
            *(
                ["    if ($stopRequested) { break }"]
                if cooperative_stop
                else []
            ),
            "    } finally {",
            "        try {",
            "            if (Test-Path -LiteralPath $dxc) {",
            "                Remove-Item -LiteralPath $dxc -Force -ErrorAction Stop",
            r'                Write-ChLog ("Removed chunk dxc: " + $dxc)',
            "            }",
            "        } catch {",
            r'            Write-ChLog ("Cleanup note: " + $_.Exception.Message)',
            "        }",
            "    }",
            "}",
            "",
            *cls._batch_runner_stop_exit_ps1(
                indent="",
                message="Runner stopped by user request.",
                sync_timeout_log=True,
            ),
            "Sync-TimeoutLogFromMemory",
            "if ($TimedOutModels.Count -gt 0) {",
            "    Write-ChLog ('TIMEOUT LOG: ' + $TimedOutModels.Count + ' model(s) recorded in ' + $TimeoutLog)",
            "} else {",
            r'    Write-ChLog "TIMEOUT LOG: no models timed out."',
            "}",
            "",
            r'Write-ChLog "---------- Batch summary ----------"',
            r'Write-ChLog ("Count of Files Success: " + $SuccessFileCount)',
            r'Write-ChLog ("Count of Files Timed Out: " + $TimedOutFileCount)',
            "",
            'try {',
            '    $runCompleteFlag = Join-Path -Path $WorkDir -ChildPath ($ChunkBase + "-run.complete")',
            '    Set-Content -LiteralPath $runCompleteFlag -Value "1" -Encoding UTF8 -Force',
            "} catch {",
            r'    Write-ChLog ("Cleanup note: could not write run-complete flag: " + $_.Exception.Message)',
            "}",
            "",
            r'Write-ChLog "Runner finished all chunks."',
        ]
        return "\n".join(lines) + "\n"

    def _on_go(self) -> None:
        if self._go_in_progress:
            return
        self._go_in_progress = True
        self._set_wizard_go_button_busy(True)
        try:
            self._on_go_impl()
        finally:
            self._go_in_progress = False
            self._set_wizard_go_button_busy(False)
            if self._wizard_thumbnails_go_phase_owned_by_on_go:
                self._wizard_thumbnails_go_phase = None
                self._wizard_thumbnails_go_phase_owned_by_on_go = False

    def _on_go_impl(self) -> None:
        if _xtop_is_running():
            messagebox.showwarning(
                "Creo is running",
                "Creo (xtop) is currently running.\n\n"
                "Quit Creo completely, then try again.",
            )
            return

        self._invalidate_working_dir_file_cache()
        working_dir_raw = (self.working_directory.get() or "").strip()
        loadpoint_raw = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        task_display_raw = (self.task.get() or "").strip()
        task_filename = self._task_filename_from_ui(task_display_raw)

        if not working_dir_raw:
            messagebox.showwarning("Missing Working Directory", "Please enter a working directory.")
            return
        if not _working_directory_ok_for_go(working_dir_raw):
            messagebox.showwarning(
                "Working directory",
                "Working directory must be an existing folder, or a new folder name under an existing folder.\n\n"
                "If the folder does not exist yet, its parent must exist so the app can create it.",
            )
            return
        if _path_contains_spaces(working_dir_raw):
            self._warn_if_working_directory_has_spaces()
            return
        scan_extensions = self._model_scan_extensions_for_task(task_display_raw)
        if not scan_extensions:
            messagebox.showwarning(
                "Scan settings",
                "No model types are enabled for this task.\n\n"
                "Open Settings → Scan settings… and enable the types you need.",
            )
            return
        types_label = self._model_scan_types_label(task_display_raw)
        scan_templates = self._is_scan_templates_task(task_display_raw)
        if scan_templates:
            self._wizard_step_outcome.pop(WIZARD_STEP_SCAN, None)
            ok, err = self._materialize_pending_templates()
            if not ok:
                messagebox.showerror("Templates", err)
                return
            wd = working_dir_raw.strip()
            if _working_directory_exists_as_dir(wd):
                make_html_statistics.clear_template_scan_session(wd)
        elif self._wizard_step == WIZARD_STEP_MODELCHECK:
            self._wizard_step_outcome.pop(WIZARD_STEP_MODELCHECK, None)
        if not self._go_model_source_ready(working_dir_raw, task_display_raw):
            if scan_templates:
                messagebox.showwarning(
                    "Templates",
                    f"GO needs at least one Creo template ({self._enabled_scan_types_label()}) in:\n"
                    f"{Path(working_dir_raw) / 'templates'}\n\n"
                    "Use Browse on the Scan Templates wizard step to upload templates first.",
                )
            elif self._is_jpeg_2d_plot_task(task_display_raw):
                messagebox.showwarning(
                    "Working directory",
                    f"GO needs at least one {types_label} file directly in the working directory "
                    "(.prt and .asm are not used for JPEG 2D plot batch) "
                    "(not in subfolders). If the folder does not exist yet, create it and add models first.",
                )
            elif self._is_jpeg_3d_task(task_display_raw):
                messagebox.showwarning(
                    "Working directory",
                    f"GO needs at least one {types_label} file directly in the working directory "
                    "(.drw files are not used for JPEG 3D batch) "
                    "(not in subfolders). If the folder does not exist yet, create it and add models first.",
                )
            else:
                messagebox.showwarning(
                    "Working directory",
                    f"GO needs at least one Creo model file ({types_label}) directly in the working directory "
                    "(not in subfolders). If the folder does not exist yet, create it and add models first.",
                )
            return
        use_modelcheck_config = self._is_modelcheck_task(task_display_raw)
        use_jpeg_config = self._is_jpeg_export_task(task_display_raw)
        modelcheck_config_dir = self._modelcheck_config_dir_for_task(task_display_raw)
        jpeg_config_pro: Path | None = None
        if modelcheck_config_dir is not None and not modelcheck_config_dir.is_dir():
            if scan_templates:
                messagebox.showerror(
                    "Missing config",
                    "Scan Templates requires the templates config folder next to the app:\n"
                    f"{modelcheck_config_dir}",
                )
            else:
                messagebox.showerror(
                    "Missing config",
                    f"Modelcheck task requires the config folder next to the app:\n{modelcheck_config_dir}",
                )
            return
        if use_jpeg_config:
            jpeg_config_pro = self._config_dir / "config.pro"
            if not jpeg_config_pro.is_file():
                messagebox.showerror(
                    "Missing config",
                    f"JPEG batch task requires config.pro in the config folder next to the app:\n{jpeg_config_pro}",
                )
                return
        if not loadpoint_raw:
            messagebox.showwarning("Missing Creo Loadpoint", "Please enter a Creo loadpoint.")
            return
        if not _creo_loadpoint_has_parametric_dir(loadpoint_raw):
            self._warn_if_creo_loadpoint_missing_parametric()
            return
        if not task_display_raw or not task_filename:
            messagebox.showwarning("Missing Task", "Please select a task.")
            return

        working_dir = Path(working_dir_raw).expanduser().resolve()
        batch_dir = self._batch_dir_for_task(working_dir, task_display_raw).resolve()
        models_dir = batch_dir if scan_templates else working_dir
        effective_ttd = self._effective_ttd_filename(task_display_raw)
        ttd_path = Path(loadpoint_raw) / "Common Files" / "text" / "ttds" / effective_ttd
        if scan_templates:
            group_name = SCAN_TEMPLATES_DISPLAY
        else:
            group_name = self._task_filename_to_description.get(task_filename) or self._read_ttd_description(
                ttd_path
            )
        group_name_attr = _xml_attr_escape(group_name)
        ptcdbatch_bat = Path(loadpoint_raw) / "Parametric" / "bin" / "ptcdbatch.bat"
        kill_bat = _app_bundle_dir() / "kill.bat"
        runner_basename = self._batch_runner_basename_for_task(task_display_raw)
        runner_ps1_path = batch_dir / runner_basename
        debug_log_path = self._batch_runner_debug_log_path(batch_dir, task_display_raw)

        if not ptcdbatch_bat.is_file():
            messagebox.showerror("File Not Found", f"Could not find:\n{ptcdbatch_bat}")
            return
        if not kill_bat.is_file():
            messagebox.showerror(
                "File Not Found",
                f"Could not find:\n{kill_bat}\n\nPlace kill.bat next to this application.",
            )
            return

        if self._is_regular_modelcheck_task(task_display_raw):
            ok, err, _ = self._sync_start_for_modelcheck_go()
            if not ok:
                messagebox.showerror("GO", err)
                return

        thumbnail_phase: str | None = None
        try:
            if self._wizard_step == WIZARD_STEP_JPEG_3D and not scan_templates:
                forced_phase = self._wizard_thumbnails_go_phase
                thumbnail_phase = (
                    forced_phase
                    if forced_phase
                    else self._wizard_thumbnails_next_pending_phase(working_dir)
                )
                if thumbnail_phase is None:
                    messagebox.showinfo(
                        "Batch",
                        "No models left to batch — every model already has the required "
                        "output for this step.",
                    )
                    return
                self._wizard_thumbnails_sync_active_phase_ui(thumbnail_phase)
                self._wizard_thumbnails_reset_phases_from(thumbnail_phase)
                self._wizard_step_outcome.pop(WIZARD_STEP_JPEG_3D, None)
                scan_extensions = self._wizard_thumbnails_phase_scan_extensions(
                    thumbnail_phase
                )
                if thumbnail_phase == _WIZARD_THUMBNAILS_PHASE_2D:
                    task_display_raw = self._wizard_jpeg_2d_display()
                    task_filename = self._task_filename_from_ui(task_display_raw)
                    batch_dir = self._batch_dir_for_task(
                        working_dir, task_display_raw
                    ).resolve()
                    runner_basename = self._batch_runner_basename_for_task(
                        task_display_raw
                    )
                    runner_ps1_path = batch_dir / runner_basename
                    debug_log_path = self._batch_runner_debug_log_path(
                        batch_dir, task_display_raw
                    )
            models_dir.mkdir(parents=True, exist_ok=True)
            scanned = self._scan_models_non_recursive(models_dir, extensions=scan_extensions)
            latest_files = self._get_latest_model_files(scanned, sort_by_size=True)
            chunk_size_override: int | None = None
            batch_task_kind: str | None = None
            if scan_templates:
                latest_files = _sort_scan_template_models(latest_files)
            else:
                batch_task_kind = self._runner_task_kind(task_display_raw)
                if thumbnail_phase is not None:
                    batch_task_kind = self._wizard_thumbnails_phase_runner_task_kind(
                        thumbnail_phase
                    )
                if batch_task_kind in ("modelcheck",) or batch_task_kind in _THUMBNAIL_JPEG_TASK_KINDS:
                    latest_files, continue_go, chunk_size_override, _ = (
                        self._resolve_batch_go_models(
                            latest_files,
                            batch_dir,
                            working_dir,
                            batch_task_kind,
                        )
                    )
                    if not continue_go:
                        return
                if not latest_files:
                    messagebox.showinfo(
                        "Batch",
                        "No models left to batch — every model already has the required "
                        "output for this step.",
                    )
                    return
            config_files = (
                self._scan_modelcheck_config_files(modelcheck_config_dir)
                if modelcheck_config_dir is not None
                else []
            )
            if scan_templates:
                model_chunks = self._chunk_paths(latest_files, SCAN_TEMPLATES_CHUNK_SIZE)
                if not model_chunks:
                    model_chunks = [[]]
            else:
                effective_chunk = (
                    chunk_size_override
                    if chunk_size_override is not None
                    else self._chunk_size
                )
                model_chunks = self._chunk_paths(latest_files, effective_chunk)
                if not model_chunks:
                    model_chunks = [[]]

            batch_dir.mkdir(parents=True, exist_ok=True)
            if batch_task_kind in ("modelcheck",) or batch_task_kind in _THUMBNAIL_JPEG_TASK_KINDS:
                self._clear_batch_failure_log_for_task(batch_dir, batch_task_kind)
                self._refresh_wizard_batch_failed_label(
                    self._wizard_step, working_dir
                )
            chunk_base = CREO_BATCH_BASE
            if scan_templates:
                chunk_base = BATCH_DXC_BASE_SCAN_TEMPLATES
            elif batch_task_kind:
                chunk_base = _batch_dxc_base_for_task_kind(batch_task_kind)
            self._cleanup_leftover_batch_files(
                batch_dir,
                scan_templates=scan_templates,
                keep_runner_scripts=self._debug_mode,
                batch_dxc_base=chunk_base,
            )
            if scan_templates:
                output_dir_attr = _xml_attr_escape(_dxc_path_str(batch_dir))
            else:
                output_dir_attr = _xml_attr_escape(working_dir_raw)
            for idx, chunk in enumerate(model_chunks, start=1):
                chunk_path = batch_dir / f"{chunk_base}-{idx}.dxc"
                group_lines = [
                    f'    <Group DSQM="_LOCAL" Name="{group_name_attr}" Output="2" '
                    f'OutputDir="{output_dir_attr}" PrimaryContent="0" '
                    f'TTD="{_xml_attr_escape(str(ttd_path))}" VaultResults="0">'
                ]
                if jpeg_config_pro is not None:
                    group_lines.append(f"        <Config>{str(jpeg_config_pro)}</Config>")
                if scan_templates:
                    group_lines.extend(f"        <Object>{_dxc_path_str(p)}</Object>" for p in chunk)
                else:
                    group_lines.extend(f"        <Object>{str(p)}</Object>" for p in chunk)
                if config_files:
                    group_lines.extend(f"        <ConfigFile>{str(p)}</ConfigFile>" for p in config_files)
                group_lines.append("    </Group>")
                data_block = "\n".join(group_lines) + "\n"
                file_content = f"<DXC>\n    <Windchill/>\n{data_block}</DXC>\n"
                chunk_path.write_text(file_content, encoding="utf-8")

            num_chunks = len(model_chunks)
            expected_outputs_per_chunk: list[list[str]] = []
            output_to_model_per_chunk: list[dict[str, str]] = []
            for chunk in model_chunks:
                names: list[str] = []
                out_to_model: dict[str, str] = {}
                for p in chunk:
                    if scan_templates or use_modelcheck_config:
                        self._append_modelcheck_expected_outputs(
                            names, out_to_model, p
                        )
                    else:
                        out = self._expected_output_basename(
                            p, is_modelcheck=False
                        )
                        if out:
                            names.append(out)
                            out_to_model[out] = p.name
                expected_outputs_per_chunk.append(names)
                output_to_model_per_chunk.append(out_to_model)
            if scan_templates:
                runner_task_kind = "modelcheck"
                effective_chunk = SCAN_TEMPLATES_CHUNK_SIZE
            else:
                runner_task_kind = (
                    batch_task_kind
                    if batch_task_kind is not None
                    else self._runner_task_kind(task_display_raw)
                )
                effective_chunk = (
                    chunk_size_override
                    if chunk_size_override is not None
                    else self._chunk_size
                )
            runner_text = self._build_chunk_runner_ps1(
                ptcdbatch_bat,
                batch_dir,
                kill_bat,
                num_chunks,
                expected_outputs_per_chunk,
                output_to_model_per_chunk,
                runner_task_kind,
                self._output_timeout_sec,
                self._xtop_gone_timeout_sec,
                debug_log_path,
                cooperative_stop=True,
                chunk_base=chunk_base,
                chunk_size=effective_chunk,
            )
            runner_ps1_path.write_text(runner_text, encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror(
                "Create File Failed",
                f"Could not create batch .dxc or runner script in:\n{batch_dir}\n\n{exc}",
            )
            return

        self._update_create_report_task_list()
        self._record_recent_scan(working_dir)
        self._save_settings()
        thumbnails_phase = thumbnail_phase if self._wizard_step == WIZARD_STEP_JPEG_3D else None
        if not self._launch_batch_runner(working_dir, task_display_raw):
            self._refresh_action_buttons_run()
            return
        self._schedule_post_batch_task_refresh()
        launched_dxc_count = len(model_chunks)
        self._start_wizard_batch_output_watch(
            self._wizard_step,
            batch_dir,
            scan_templates,
            launched_dxc_count=launched_dxc_count,
            thumbnails_phase=thumbnails_phase,
            batch_dxc_base=chunk_base if scan_templates else None,
        )
        self._refresh_action_buttons_run()
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def _build_master_xml_silent(self, working_dir: Path) -> tuple[bool, str | None]:
        """Merge ModelCHECK XML into master.xml and remove leftover runner .ps1 files."""
        out_path = str(working_dir / "master.xml")
        try:
            merge_master_xml.build_master_xml(
                working_directory=str(working_dir),
                output_file=out_path,
            )
        except OSError as exc:
            return False, f"Could not write master.xml.\n\n{exc}"
        except Exception as exc:
            return False, f"An error occurred while building master.xml.\n\n{exc}"
        templates_dir = working_dir / "templates"
        if not self._debug_mode:
            self._remove_batch_runner_scripts(working_dir, templates_dir)
        return True, None

    def _set_report_busy(self, busy: bool) -> None:
        self._report_job_running = busy
        try:
            self.configure(cursor="wait" if busy else "")
        except tk.TclError:
            pass
        if busy:
            self._show_report_processing_indicator()
        else:
            self._hide_report_processing_indicator()
        self._refresh_wizard_footer()
        self._refresh_menu_bar_state()

    def _show_report_processing_indicator(self) -> None:
        """Frameless 'Processing, please wait…' dialog with animated candy-stripe bar."""
        self._hide_report_processing_indicator()
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.overrideredirect(True)
        dialog.resizable(False, False)
        dialog.configure(fg_color="#FFFFFF")
        try:
            dialog.transient(self)
        except tk.TclError:
            pass
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        outer = ctk.CTkFrame(
            dialog,
            fg_color="#FFFFFF",
            corner_radius=6,
            border_width=1,
            border_color="#B0B0B0",
        )
        outer.pack(fill="both", expand=True)

        ctk.CTkLabel(
            outer,
            text="Processing, please wait...",
            font=ctk.CTkFont(size=13),
            text_color="#222222",
            anchor="w",
        ).pack(anchor="w", padx=22, pady=(18, 12))

        bar_w, bar_h = 300, 18
        canvas = tk.Canvas(
            outer,
            width=bar_w,
            height=bar_h,
            highlightthickness=0,
            bd=0,
            bg="#FFFFFF",
        )
        canvas.pack(padx=22, pady=(0, 20))

        phase = {"value": 0}
        stripe = 12
        blue = "#8EC8E8"
        white = "#FFFFFF"
        border = "#6BA3C8"

        def paint() -> None:
            canvas.delete("all")
            # Pill clip via rounded background + stripes inside.
            canvas.create_rectangle(
                1, 1, bar_w - 2, bar_h - 2, outline=border, width=1, fill=blue
            )
            off = phase["value"] % (stripe * 2)
            x = -bar_h - stripe + off
            i = 0
            while x < bar_w + bar_h:
                if i % 2 == 0:
                    # Diagonal white band (parallelogram).
                    canvas.create_polygon(
                        x,
                        1,
                        x + stripe,
                        1,
                        x + stripe + bar_h - 2,
                        bar_h - 1,
                        x + bar_h - 2,
                        bar_h - 1,
                        fill=white,
                        outline=white,
                    )
                x += stripe
                i += 1
            # Soft edge mask: redraw rounded-ish ends with white corners.
            canvas.create_oval(-6, -2, bar_h + 2, bar_h + 2, fill="#FFFFFF", outline="#FFFFFF")
            canvas.create_oval(
                bar_w - bar_h - 2,
                -2,
                bar_w + 6,
                bar_h + 2,
                fill="#FFFFFF",
                outline="#FFFFFF",
            )
            canvas.create_arc(
                1,
                1,
                bar_h,
                bar_h - 1,
                start=90,
                extent=180,
                style="arc",
                outline=border,
                width=1,
            )
            canvas.create_arc(
                bar_w - bar_h,
                1,
                bar_w - 1,
                bar_h - 1,
                start=270,
                extent=180,
                style="arc",
                outline=border,
                width=1,
            )

        def tick() -> None:
            self._report_processing_anim_job = None
            try:
                if not dialog.winfo_exists():
                    return
            except tk.TclError:
                return
            phase["value"] = (phase["value"] + 2) % (stripe * 2)
            paint()
            try:
                self._report_processing_anim_job = dialog.after(40, tick)
            except tk.TclError:
                pass

        paint()
        self._report_processing_dialog = dialog
        self._modal_dialog_depth += 1
        try:
            dialog.update_idletasks()
            _schedule_center_toplevel_on_parent(dialog, self)
            dialog.deiconify()
            dialog.lift()
            dialog.attributes("-topmost", True)
            dialog.grab_set()
            dialog.attributes("-topmost", False)
        except tk.TclError:
            pass
        try:
            self._report_processing_anim_job = dialog.after(40, tick)
        except tk.TclError:
            pass
        try:
            dialog.update_idletasks()
            dialog.update()
        except tk.TclError:
            pass

    def _hide_report_processing_indicator(self) -> None:
        job = self._report_processing_anim_job
        if job is not None:
            dialog = self._report_processing_dialog
            try:
                if dialog is not None and dialog.winfo_exists():
                    dialog.after_cancel(job)
                else:
                    self.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
            self._report_processing_anim_job = None
        dialog = self._report_processing_dialog
        self._report_processing_dialog = None
        if dialog is None:
            return
        try:
            if dialog.winfo_exists():
                try:
                    dialog.grab_release()
                except tk.TclError:
                    pass
                dialog.destroy()
                self._modal_dialog_depth = max(0, self._modal_dialog_depth - 1)
        except tk.TclError:
            pass

    def _bring_app_forward(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.update_idletasks()
        except tk.TclError:
            pass

    def _finish_report_job(self, result: dict[str, object]) -> None:
        self._set_report_busy(False)

        error = result.get("error")
        if error:
            self._bring_app_forward()
            kind = result.get("kind")
            if kind == "patch":
                messagebox.showerror(
                    "Report Failed",
                    f"Could not patch ModelCHECK HTML.\n\n{error}",
                )
            elif kind == "master":
                messagebox.showerror("Report Failed", str(error))
            elif kind == "notfound":
                messagebox.showerror("Report Failed", str(error))
            elif kind == "os":
                messagebox.showerror(
                    "Report Failed",
                    f"Could not write report HTML.\n\n{error}",
                )
            else:
                messagebox.showerror(
                    "Report Failed",
                    f"An error occurred while building the report.\n\n{error}",
                )
            return

        written = result.get("written")
        if written and not self._debug_mode:
            wd = (self.working_directory.get() or "").strip()
            if wd and _working_directory_exists_as_dir(wd):
                self._remove_master_xml_after_report(Path(wd).expanduser().resolve())
        if written:
            self._cancel_automatic_wizard_chain()
            self._wizard_report_auto_create_done = True
        open_in_browser = False
        if written:
            open_in_browser = bool(
                messagebox.askyesno(
                    "Report",
                    f"Wrote full report (with sidebar):\n{written}\n\nOpen in browser?",
                )
            )
        self._bring_app_forward()
        if open_in_browser:
            try:
                webbrowser.open(Path(str(written)).as_uri())
            except OSError as exc:
                messagebox.showerror(
                    "Open Failed",
                    f"Could not open report in browser.\n\n{exc}",
                )

    def _remove_master_xml_after_report(self, working_dir: Path) -> None:
        """Drop merged master.xml after a successful report when not in Debug mode."""
        master = working_dir / "master.xml"
        try:
            if master.is_file():
                master.unlink()
        except OSError:
            pass

    def _start_report_job(self, working_dir: Path) -> None:
        if self._report_job_running:
            return
        self._cancel_automatic_wizard_chain()
        self._set_report_busy(True)
        # Paint the overlay before any heavy work (master.xml used to run on the UI thread).
        try:
            self.update_idletasks()
            self.update()
        except tk.TclError:
            pass
        settings_path = _default_app_settings_path()
        wd = str(working_dir)

        def work() -> None:
            result: dict[str, object] = {"written": None, "error": None, "kind": None}
            try:
                ok, build_err = self._build_master_xml_silent(working_dir)
                if not ok:
                    result["error"] = build_err or "Could not build master.xml."
                    result["kind"] = "master"
                else:
                    patch.run(settings_path=settings_path, quiet=True)
                    result["written"] = build_errors_warnings_report.build_errors_warnings_html(
                        wd
                    )
            except patch.PatchError as exc:
                result["error"] = str(exc)
                result["kind"] = "patch"
            except FileNotFoundError as exc:
                result["error"] = str(exc)
                result["kind"] = "notfound"
            except OSError as exc:
                result["error"] = str(exc)
                result["kind"] = "os"
            except Exception as exc:
                result["error"] = str(exc)
                result["kind"] = "generic"
            self.after(0, lambda: self._finish_report_job(result))

        threading.Thread(target=work, daemon=True).start()

    def _on_write_summary_report(self) -> None:
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            messagebox.showwarning("Missing Working Directory", "Please enter a working directory.")
            return
        if not _working_directory_exists_as_dir(wd):
            self._warn_if_working_directory_invalid()
            return
        working_dir = Path(wd).expanduser().resolve()
        bundle = _app_bundle_dir()
        model_checks = bundle / "model_checks.xml"
        template = bundle / "report_template.html.j2"
        if not model_checks.is_file():
            messagebox.showerror(
                "Missing model_checks.xml",
                f"Place model_checks.xml in the same folder as the application executable:\n\n"
                f"  {_app_bundle_dir() / 'model_checks.xml'}\n\n"
                f"Executable:\n  {Path(sys.executable).resolve()}",
            )
            return
        if not template.is_file():
            messagebox.showerror(
                "Missing report_template.html.j2",
                f"Place report_template.html.j2 in the same folder as the application executable:\n\n"
                f"  {_app_bundle_dir() / 'report_template.html.j2'}\n\n"
                f"Executable:\n  {Path(sys.executable).resolve()}",
            )
            return
        if not self._working_directory_has_modelcheck_xml(wd):
            messagebox.showwarning(
                "Missing ModelCHECK XML",
                "No ModelCHECK result XML (*.p.xml, *.a.xml, *.d.xml) was found in the working directory.",
            )
            return
        self._persist_working_directory_and_loadpoint()
        self._start_report_job(working_dir)

    def _close_batch_runner_window(self, *, force: bool = False) -> None:
        """Close the tracked PowerShell console launched for the current batch runner."""
        proc = self._batch_runner_process
        self._batch_runner_process = None
        if proc is None:
            return
        if self._debug_mode and not force:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except OSError:
            pass

    def _close_stray_batch_runner_windows(self) -> None:
        """Best-effort: close any PowerShell process running a generated creo-batch-*.ps1 script."""
        if sys.platform != "win32":
            return
        ps_exe = self._resolve_powershell_exe()
        if not ps_exe:
            return
        script = (
            "$procs = Get-CimInstance Win32_Process "
            "| Where-Object { $_.Name -ieq 'powershell.exe' -and $_.CommandLine "
            "-and $_.CommandLine -match 'creo-batch-.*\\.ps1' }; "
            "foreach ($p in $procs) { "
            "try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} "
            "}"
        )
        try:
            subprocess.run(
                [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
        except OSError:
            pass

    def _launch_batch_runner(self, working_dir: Path, task_display: str) -> bool:
        """Start the task-specific PowerShell batch runner. Returns False on launch failure."""
        self._close_batch_runner_window()
        batch_dir = self._batch_dir_for_task(working_dir, task_display)
        runner_ps1 = batch_dir / self._batch_runner_basename_for_task(task_display)
        ps_exe = self._resolve_powershell_exe()
        if not ps_exe:
            messagebox.showerror("PowerShell Not Found", "Could not locate powershell.exe.")
            return False
        try:
            ps_args = [
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(runner_ps1.resolve()),
            ]
            if self._debug_mode:
                ps_args = ["-NoExit", *ps_args]
            popen_kw: dict = {
                "args": [ps_exe, *ps_args],
                "cwd": str(batch_dir),
                "creationflags": subprocess.CREATE_NEW_CONSOLE,
            }
            startupinfo = self._console_startupinfo(
                hidden=self._automatic_mode and not self._debug_mode,
                show_normal=self._debug_mode,
            )
            if startupinfo is not None:
                popen_kw["startupinfo"] = startupinfo
            self._batch_runner_process = subprocess.Popen(**popen_kw)
        except OSError as exc:
            self._batch_runner_process = None
            messagebox.showerror(
                "Launch Failed",
                f"Could not start:\n{runner_ps1}\n\n{exc}",
            )
            return False
        return True

    @staticmethod
    def _console_startupinfo(
        *, hidden: bool = False, show_normal: bool = False
    ) -> subprocess.STARTUPINFO | None:
        if sys.platform != "win32":
            return None
        info = subprocess.STARTUPINFO()
        info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        if show_normal:
            info.wShowWindow = getattr(subprocess, "SW_SHOW", 5)
        elif hidden:
            info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        else:
            info.wShowWindow = getattr(subprocess, "SW_SHOWMINNOACTIVE", 7)
        return info

    @staticmethod
    def _resolve_powershell_exe() -> str | None:
        # Try PATH first.
        candidate = shutil.which("powershell.exe")
        if candidate:
            return candidate
        # Typical Windows locations.
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        fallbacks = [
            Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
            Path(system_root) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        ]
        for path in fallbacks:
            if path.exists():
                return str(path)
        return None


def main() -> None:
    app = CreoDistributedBatchMakerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
