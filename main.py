from __future__ import annotations

from collections import defaultdict
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
import patch
import update_sample_start_from_xml

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
# ModelCHECK detail outputs under templates\ removed when Scan Templates finishes (Next >).
# Runner scripts (creo-batch-*.ps1) are removed separately — not via this suffix list.
_TEMPLATE_SCAN_DETAIL_SUFFIXES = (".html", ".js", ".png", ".css")

# Chunk .dxc files: working_dir / f"{CREO_BATCH_BASE}-1.dxc", "-2.dxc", ...
CREO_BATCH_BASE = "creo-batch"
# Models per chunk in each .dxc (default 10). User can change via Settings → Chunk size...
CREO_BATCH_CHUNK_SIZE_DEFAULT = 10
CREO_BATCH_CHUNK_SIZE_MIN = 1
CREO_BATCH_CHUNK_SIZE_MAX = 10
# GO writes a task-specific driver next to the chunk .dxc files (legacy name cleaned on GO).
CREO_BATCH_RUNNER_LEGACY_BASENAME = "creo-batch-run.ps1"
CREO_BATCH_RUNNER_MODELCHECK_BASENAME = "creo-batch-modelcheck.ps1"
CREO_BATCH_RUNNER_JPEG_3D_BASENAME = "creo-batch-jpeg3d.ps1"
CREO_BATCH_RUNNER_JPEG_2D_BASENAME = "creo-batch-jpeg2d.ps1"
CREO_BATCH_RUNNER_SCAN_TEMPLATES_BASENAME = "creo-batch-scan-templates.ps1"
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
# After all expected outputs for a chunk appear, settle this many seconds before running kill.bat.
BATCH_OUTPUT_SETTLE_SEC = 5
# xtop.exe: abort chunk wait after N consecutive dead polls with no restart within restart sec (within window sec of first dead poll).
BATCH_XTOP_DEAD_CHECKS = 2
BATCH_XTOP_RESTART_WAIT_SEC = 10
BATCH_XTOP_DEAD_WINDOW_SEC = 30
# Wizard polls the batch folder until chunk .dxc files are gone (runner deletes them when done).
WIZARD_BATCH_DXC_POLL_MS = 3000
BATCH_TIMEOUT_LOG_PREFIX = "creo-batch-timeouts-"
_BATCH_TIMEOUT_LOG_HEADER = "Models timed out:"
# Chunk ETA on ModelCHECK / JPEG 3D: show after this many chunks finish (depends on total).
WIZARD_BATCH_ETA_MIN_CHUNKS_DEFAULT = 2
WIZARD_BATCH_ETA_MIN_CHUNKS_SMALL = 1
WIZARD_BATCH_ETA_SMALL_BATCH_MAX_CHUNKS = 2
WIZARD_BATCH_ETA_ESTIMATING_SUFFIX = " · Estimating time…"
WIZARD_AUTOMATIC_MODE_MESSAGE = (
    "Automatic Mode — runs each batch in sequence when the previous step finishes "
    "(Scan Templates → ModelCHECK → JPEG 3D → Report)."
)
AUTOMATIC_MODE_DEFAULT = True
DEBUG_MODE_DEFAULT = False
# When no Creo loadpoint / no .ttd list yet, File → New uses this default task (filename + UI label).
DEFAULT_MODELCHECK_TTD = "modelcheck.ttd"
DEFAULT_MODELCHECK_DISPLAY = "ModelCHECK"
SCAN_TEMPLATES_DISPLAY = "Scan Templates"
CREATE_REPORT_DISPLAY = "Create Report"
SCAN_TEMPLATES_DXC_BASENAME = "templates.dxc"
JPEG_2D_PLOT_TTD = "plot_jpeg_a-size.ttd"
JPEG_2D_PLOT_DISPLAY = "JPEG 2D Export to file, A Paper Size"
JPEG_3D_TTD = "solid-raster_write_jpg.ttd"
TASK_COMBOBOX_FONT = ("Segoe UI", 11)
_START_OVER_FILE_SUFFIXES = frozenset(
    {".ps1", ".dxc", ".xml", ".html", ".js", ".jpg", ".png", ".log", ".css"}
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
WIZARD_STEPPER_LABELS = ("Setup", "Templates", "ModelCHECK", "JPEG 3D", "Report")
WIZARD_STEPPER_FONT_SIZE = 14


def _creo_model_name_pattern(extensions: tuple[str, ...]) -> re.Pattern[str]:
    inner = "|".join(re.escape(ext) for ext in extensions)
    return re.compile(rf".*\.({inner})(\.\d+)?$", re.IGNORECASE)


def _app_bundle_dir() -> Path:
    """Sidecar files live beside main.exe (dev: beside main.py), not under PyInstaller _MEI temp."""
    if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


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


def _parse_batch_timeout_log(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    models: list[str] = []
    past_header = False
    header_cf = _BATCH_TIMEOUT_LOG_HEADER.casefold()
    for line in text.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not past_header:
            if stripped.casefold() == header_cf:
                past_header = True
            continue
        if stripped:
            models.append(stripped)
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


def _is_batch_timeout_log_name(name: str) -> bool:
    n = name.casefold()
    return n.startswith(BATCH_TIMEOUT_LOG_PREFIX.casefold()) and n.endswith(".txt")


def _remove_batch_timeout_logs_in_directory(directory: Path) -> list[str]:
    """Remove ``creo-batch-timeouts-*.txt`` failure logs; return unlink error lines."""
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


def _clear_batch_timeout_logs(batch_dir: Path, task_kind: str) -> None:
    """Remove failure logs for one task before a new batch run."""
    if not batch_dir.is_dir():
        return
    prefix = f"{BATCH_TIMEOUT_LOG_PREFIX}{task_kind}".casefold()
    try:
        for path in batch_dir.iterdir():
            if not path.is_file():
                continue
            if not _is_batch_timeout_log_name(path.name):
                continue
            if path.name.casefold().startswith(prefix):
                path.unlink()
    except OSError:
        pass


def _format_batch_failed_models_line(models: list[str]) -> str:
    if not models:
        return ""
    return f"Failed ({len(models)}): {', '.join(models)}"


def _batch_eta_min_chunks_done(total_chunks: int) -> int:
    if total_chunks <= WIZARD_BATCH_ETA_SMALL_BATCH_MAX_CHUNKS:
        return WIZARD_BATCH_ETA_MIN_CHUNKS_SMALL
    return WIZARD_BATCH_ETA_MIN_CHUNKS_DEFAULT


def _format_batch_eta_remaining(seconds: float) -> str:
    minutes = max(1, int(round(max(0.0, seconds) / 60)))
    if minutes == 1:
        return "~1 min remaining"
    return f"~{minutes} min remaining"


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


def _normalize_automatic_mode(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _canonical_app_settings(data: dict[str, object]) -> dict[str, object]:
    """Keys persisted in app_settings.json (task selection is not stored)."""
    return {
        "working_directory": str(data.get("working_directory") or ""),
        "creo_loadpoint": str(data.get("creo_loadpoint") or ""),
        "chunk_size": _normalize_chunk_size(
            data.get("chunk_size", CREO_BATCH_CHUNK_SIZE_DEFAULT)
        ),
        "output_timeout_sec": _normalize_output_timeout_sec(
            data.get("output_timeout_sec", BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT)
        ),
        "automatic_mode": _normalize_automatic_mode(
            data.get("automatic_mode", AUTOMATIC_MODE_DEFAULT)
        ),
        "debug_mode": _normalize_automatic_mode(
            data.get("debug_mode", DEBUG_MODE_DEFAULT)
        ),
    }


def _center_toplevel_on_parent(toplevel: tk.Misc, parent: tk.Misc) -> None:
    """Place *toplevel* centered over *parent* (call after widgets are laid out)."""
    toplevel.update_idletasks()
    parent.update_idletasks()
    tw = toplevel.winfo_width()
    th = toplevel.winfo_height()
    if tw <= 1:
        tw = toplevel.winfo_reqwidth()
    if th <= 1:
        th = toplevel.winfo_reqheight()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    if pw <= 1:
        pw = parent.winfo_reqwidth()
    if ph <= 1:
        ph = parent.winfo_reqheight()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    x = px + max(0, (pw - tw) // 2)
    y = py + max(0, (ph - th) // 2)
    toplevel.geometry(f"+{x}+{y}")


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
        self.resizable(False, False)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Keep a tiny PIL image around to establish Pillow usage
        # and provide an easy place to swap in a real icon later.
        self._placeholder_image = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        self._settings_path = _default_app_settings_path()
        # After Save As or Open: File → Save / Exit also update this path (same JSON as app_settings).
        self._paired_settings_json_path: Path | None = None
        self._configs_dir = _app_bundle_dir() / "configs"
        self._configs_templates_dir = self._configs_dir / "templates"
        self._chunk_size = CREO_BATCH_CHUNK_SIZE_DEFAULT
        self._output_timeout_sec = BATCH_OUTPUT_WAIT_TIMEOUT_DEFAULT
        self._automatic_mode = AUTOMATIC_MODE_DEFAULT
        self._automatic_mode_var = tk.BooleanVar(master=self, value=AUTOMATIC_MODE_DEFAULT)
        self._debug_mode = DEBUG_MODE_DEFAULT
        self._debug_mode_var = tk.BooleanVar(master=self, value=DEBUG_MODE_DEFAULT)
        self._automatic_wizard_chain_job: str | None = None
        self._automatic_chain_phase: str | int | None = None
        self._configuration_menu: tk.Menu | None = None
        self._menubar: tk.Menu | None = None
        self._settings_options = [
            "Model Checks...",
            "Config.pro...",
            "Angles...",
            "GMC...",
            "Modelcheck Config...",
            "Defaults...",
            "Designers...",
            "Holes...",
            "Inch Settings...",
            "Metric Settings...",
            "Sheetmetal Thickness...",
            "Open configurations...",
        ]
        self._refresh_action_buttons_job: str | None = None
        self._activate_refresh_job: str | None = None
        self._post_batch_task_refresh_job: str | None = None
        self._wizard_batch_watch: dict[str, object] | None = None
        self._wizard_batch_watch_job: str | None = None
        self._batch_runner_process: subprocess.Popen | None = None
        self._last_create_report_available = False
        self._modal_dialog_depth = 0
        self._report_job_running = False
        self._post_map_refresh_done = False
        self._suppress_settings_autosave = False
        self._settings_config_relative: dict[str, str] = {
            "Model Checks...": "default_checks.mch",
            "Config.pro...": "config.pro",
            "Angles...": "angles.txt",
            "GMC...": "config.gmc",
            "Modelcheck Config...": "config_init.mc",
            "Defaults...": "default_start.mcs",
            "Designers...": "designers.txt",
            "Holes...": "holes.txt",
            "Inch Settings...": "inch.mcn",
            "Metric Settings...": "mm.mcn",
            "Sheetmetal Thickness...": "thick.txt",
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

    def _update_sample_start_from_template_xml_if_present(self) -> tuple[bool, str, str]:
        """Refresh configs\\sample_start.mcs when template scan XML exists.

        Returns (ok, error_message, status_note). status_note is updated or skipped.
        """
        skipped = "Template extraction: skipped"
        updated = "Template extraction: updated"
        cleared = "Template extraction: cleared"
        error = "Template extraction: error"
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            return True, "", skipped
        templates_dir = Path(wd) / "templates"
        part_xml = templates_dir / "part_template.p.xml"
        asm_xml = templates_dir / "assembly_template.a.xml"
        drw_xml = templates_dir / "drawing_template.d.xml"
        part_path = part_xml if part_xml.is_file() else None
        asm_path = asm_xml if asm_xml.is_file() else None
        drw_path = drw_xml if drw_xml.is_file() else None
        mcs_path = _app_bundle_dir() / "configs" / "sample_start.mcs"
        try:
            update_sample_start_from_xml.update_sample_start(
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

    def _effective_ttd_filename(self, task_display: str) -> str:
        if self._is_scan_templates_task(task_display):
            return DEFAULT_MODELCHECK_TTD
        return self._task_filename_from_ui(task_display)

    def _modelcheck_config_dir_for_task(self, task_display: str) -> Path | None:
        if self._is_scan_templates_task(task_display):
            return self._configs_templates_dir
        if self._is_modelcheck_task(task_display):
            return self._configs_dir
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
        if not templates.is_dir():
            return False
        return self._working_directory_has_creo_models(
            str(templates), extensions=_CREO_MODEL_EXTENSIONS_ALL
        )

    def _templates_dir_has_scan_xml(self, working_dir_str: str | None = None) -> bool:
        """True when a prior Scan Templates run left ModelCHECK XML in templates\\."""
        wd = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not wd:
            return False
        templates_dir = Path(wd) / "templates"
        if not templates_dir.is_dir():
            return False
        for name in (
            "part_template.p.xml",
            "assembly_template.a.xml",
            "drawing_template.d.xml",
        ):
            if (templates_dir / name).is_file():
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

    def _working_directory_has_jpg_files(self, working_dir_str: str | None = None) -> bool:
        """True if at least one .jpg exists in the working directory (top level only)."""
        s = (working_dir_str if working_dir_str is not None else self.working_directory.get()).strip()
        if not s:
            return False
        try:
            d = Path(s).expanduser()
            if not d.is_dir():
                return False
            for entry in d.iterdir():
                if entry.is_file() and entry.suffix.casefold() == ".jpg":
                    return True
            return False
        except OSError:
            return False

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
        filename = self._task_filename_from_ui(task_display)
        if not filename:
            return False
        if filename.lower() == JPEG_3D_TTD.lower():
            return True
        display = (task_display or "").strip().casefold()
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

    def _model_scan_extensions_for_task(self, task_display: str) -> tuple[str, ...]:
        if self._is_jpeg_2d_plot_task(task_display):
            return ("drw",)
        if self._is_jpeg_3d_task(task_display):
            return ("prt", "asm")
        return _CREO_MODEL_EXTENSIONS_ALL

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
        return self._task_display_to_filename.get(key, "")

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

    def _wizard_jpeg_3d_display(self) -> str:
        return (
            self._task_display_for_ttd_filename(JPEG_3D_TTD)
            or "JPEG 3D"
        )

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
                "Optional: upload templates for model types in your working folder, then run "
                "ModelCHECK on them to seed configs. Part template is always shown; assembly and "
                "drawing rows appear only when .asm or .drw files are present. At least one "
                "template is required to scan."
            )
        if step == WIZARD_STEP_MODELCHECK:
            return (
                "Run ModelCHECK on models in the working directory. "
                "Outputs (XML, HTML, etc.) are written to the working folder."
            )
        if step == WIZARD_STEP_JPEG_3D:
            return (
                "Export JPEG 3D images for parts and assemblies in the working directory."
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

    def _wizard_template_kind_visible(self, kind: str) -> bool:
        """Show a template row for part always; asm/drw only when WD has that type or template is set."""
        if kind == "prt":
            return True
        if self._template_is_set(kind):
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
        paths = self._template_scan_artifact_paths(kind)
        if not paths:
            return
        errors: list[str] = []
        for path in paths:
            try:
                path.unlink()
            except OSError as exc:
                errors.append(f"{path}\n{exc}")
        self._update_sample_start_from_template_xml_if_present()
        self._refresh_task_options()
        self._refresh_wizard_template_status()
        self._refresh_wizard_footer()
        if errors:
            messagebox.showwarning(
                "Remove template",
                "Some files could not be removed:\n\n" + "\n\n".join(errors),
            )

    def _templates_upload_count(self) -> int:
        return sum(1 for kind, _ in _START_TEMPLATE_KINDS if self._template_is_set(kind))

    def _set_wizard_step(self, step: int) -> None:
        step = max(WIZARD_STEP_SETUP, min(WIZARD_STEP_COUNT - 1, step))
        if step != self._wizard_step:
            self._cancel_wizard_batch_output_watch()
        self._wizard_step = step
        task_display = self._wizard_task_display_for_step(step)
        if task_display:
            self.task.set(task_display)
        self._refresh_configuration_menu()
        self._refresh_wizard_ui()

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
        return self._batch_dxc_files_exist(batch_dir, scan_templates)

    def _wizard_batch_ready_for_next(self, step: int) -> bool:
        """True when this step's batch finished (all .dxc gone after a run) and Next should show."""
        if self._wizard_step_has_remaining_dxc(step):
            return False
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            return self._wizard_batch_outputs_ready(watch)
        return self._wizard_batch_step_already_complete(step)

    @staticmethod
    def _batch_dxc_files_exist(batch_dir: Path, scan_templates: bool) -> bool:
        try:
            if scan_templates:
                return (batch_dir / SCAN_TEMPLATES_DXC_BASENAME).is_file()
            return any(batch_dir.glob(f"{CREO_BATCH_BASE}-*.dxc"))
        except OSError:
            return False

    @staticmethod
    def _batch_dxc_count(batch_dir: Path, scan_templates: bool) -> int:
        try:
            if scan_templates:
                return 1 if (batch_dir / SCAN_TEMPLATES_DXC_BASENAME).is_file() else 0
            return len(list(batch_dir.glob(f"{CREO_BATCH_BASE}-*.dxc")))
        except OSError:
            return 0

    def _wizard_batch_progress_info(self, watch: dict[str, object] | None) -> tuple[float, str] | None:
        if watch is None or not watch.get("had_dxc"):
            return None
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return None
        scan_templates = bool(watch.get("scan_templates"))
        initial = watch.get("initial_dxc_count")
        if not isinstance(initial, int) or initial <= 0:
            return None
        remaining = self._batch_dxc_count(batch_dir, scan_templates)
        done = max(0, initial - remaining)
        if scan_templates or initial == 1:
            if remaining:
                return 0.0, "Template scan running…"
            return 1.0, "Template scan finished."
        if remaining == 0:
            return 1.0, f"Batch progress: {initial} of {initial} chunks complete."
        fraction = done / initial
        chunks_word = "chunks" if initial != 1 else "chunk"
        text = f"Batch progress: {done} of {initial} {chunks_word} complete."
        text += _batch_progress_eta_suffix(
            watch, done=done, remaining=remaining, initial=initial
        )
        return fraction, text

    def _wizard_step_shows_batch_progress(self, step: int) -> bool:
        if step not in (WIZARD_STEP_SCAN, WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return False
        if (
            self._wizard_batch_waiting_on_step(step)
            or self._wizard_batch_ready_for_next(step)
        ):
            return True
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            batch_dir, _ = self._wizard_batch_dir_for_step(step)
            if batch_dir is not None and self._wizard_failed_models_for_step(step, batch_dir):
                return True
        return False

    def _wizard_batch_progress_info_for_step(self, step: int) -> tuple[float, str] | None:
        watch = self._wizard_batch_watch
        if watch is not None and watch.get("step") == step:
            info = self._wizard_batch_progress_info(watch)
            if info is not None:
                return info
        if not self._wizard_batch_ready_for_next(step):
            return None
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return None
        if scan_templates:
            return 1.0, "Template scan finished."
        return 1.0, "Batch finished."

    def _refresh_wizard_step_batch_progress(self, step: int) -> None:
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
        for _, frame, _label, _bar in rows:
            if frame is not None:
                frame.pack_forget()
        if not self._wizard_step_shows_batch_progress(step):
            return
        frame = label = bar = None
        if step == WIZARD_STEP_SCAN:
            frame = getattr(self, "wizard_scan_progress_frame", None)
            label = getattr(self, "wizard_scan_progress_label", None)
            bar = getattr(self, "wizard_scan_progress_bar", None)
        elif step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            frame = getattr(self, "wizard_batch_progress_frame", None)
            label = getattr(self, "wizard_batch_progress_label", None)
            bar = getattr(self, "wizard_batch_progress_bar", None)
        if frame is None or label is None or bar is None:
            return
        info = self._wizard_batch_progress_info_for_step(step)
        failures_only = False
        if info is None and step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            batch_dir, _ = self._wizard_batch_dir_for_step(step)
            if batch_dir is not None and self._wizard_failed_models_for_step(step, batch_dir):
                failures_only = True
        if info is None and not failures_only:
            wait_text = "Waiting for batch to finish…"
            watch = self._wizard_batch_watch
            if (
                step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D)
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
            label.configure(
                text=text,
                text_color="#2E7D32" if finished and text else "#111111",
            )
            bar.set(fraction)
        frame.pack(anchor="w", fill="x", pady=(8, 0))
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            batch_dir, _ = self._wizard_batch_dxc_context_for_step(step)
            self._refresh_wizard_batch_automatic_label(step)
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

    def _wizard_batch_outputs_ready(self, watch: dict[str, object]) -> bool:
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return False
        scan_templates = bool(watch.get("scan_templates"))
        has_dxc = self._batch_dxc_files_exist(batch_dir, scan_templates)
        if has_dxc:
            watch["had_dxc"] = True
            count = self._batch_dxc_count(batch_dir, scan_templates)
            initial = watch.get("initial_dxc_count")
            if not isinstance(initial, int) or count > initial:
                watch["initial_dxc_count"] = count
            return False
        return bool(watch.get("had_dxc"))

    def _cancel_wizard_batch_output_watch(self) -> None:
        jid = self._wizard_batch_watch_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._wizard_batch_watch_job = None
        self._wizard_batch_watch = None

    def _start_wizard_batch_output_watch(
        self,
        step: int,
        batch_dir: Path,
        scan_templates: bool,
        *,
        launched_dxc_count: int = 0,
    ) -> None:
        self._cancel_wizard_batch_output_watch()
        self._wizard_step_failed_models.pop(step, None)
        file_had_dxc = self._batch_dxc_files_exist(batch_dir, scan_templates)
        file_dxc_count = self._batch_dxc_count(batch_dir, scan_templates)
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
            "had_dxc": had_dxc,
            "initial_dxc_count": initial_dxc_count,
            "started_at": time.time(),
        }
        self._tick_wizard_batch_output_watch()

    def _tick_wizard_batch_output_watch(self) -> None:
        self._wizard_batch_watch_job = None
        watch = self._wizard_batch_watch
        if watch is None:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self._modal_dialog_depth > 0:
            self._wizard_batch_watch_job = self.after(1000, self._tick_wizard_batch_output_watch)
            return
        ready = self._wizard_batch_outputs_ready(watch)
        if ready:
            self._wizard_capture_failed_models_after_batch(watch)
        self._refresh_wizard_ui()
        if ready:
            step = watch.get("step")
            if step == WIZARD_STEP_JPEG_3D:
                self._update_create_report_task_list(advance_from_jpeg=False)
            if self._automatic_mode and step in (
                WIZARD_STEP_SCAN,
                WIZARD_STEP_MODELCHECK,
                WIZARD_STEP_JPEG_3D,
            ):
                self._schedule_automatic_wizard_chain(step)
            return
        self._wizard_batch_watch_job = self.after(
            WIZARD_BATCH_DXC_POLL_MS, self._tick_wizard_batch_output_watch
        )

    def _cancel_automatic_wizard_chain(self) -> None:
        jid = self._automatic_wizard_chain_job
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._automatic_wizard_chain_job = None
        self._automatic_chain_phase = None

    def _schedule_automatic_wizard_chain(self, completed_step: int) -> None:
        if not self._automatic_mode:
            return
        if completed_step not in (
            WIZARD_STEP_SCAN,
            WIZARD_STEP_MODELCHECK,
            WIZARD_STEP_JPEG_3D,
        ):
            return
        self._cancel_automatic_wizard_chain()
        self._automatic_chain_phase = completed_step
        self._automatic_wizard_chain_job = self.after(250, self._run_automatic_wizard_chain)

    def _run_automatic_wizard_chain(self) -> None:
        self._automatic_wizard_chain_job = None
        if not self._automatic_mode:
            self._automatic_chain_phase = None
            return
        if self._modal_dialog_depth > 0:
            self._automatic_wizard_chain_job = self.after(500, self._run_automatic_wizard_chain)
            return

        phase = self._automatic_chain_phase
        step = self._wizard_step

        if phase == WIZARD_STEP_SCAN and step == WIZARD_STEP_SCAN:
            if not self._wizard_batch_ready_for_next(step):
                self._automatic_wizard_chain_job = self.after(
                    500, self._run_automatic_wizard_chain
                )
                return
            self._wizard_advance_one_step_after_batch()
            self._automatic_chain_phase = "start_modelcheck"
            self._automatic_wizard_chain_job = self.after(300, self._run_automatic_wizard_chain)
            return

        if phase == "start_modelcheck" and step == WIZARD_STEP_MODELCHECK:
            if self._wizard_batch_waiting_on_step(step):
                self._automatic_wizard_chain_job = self.after(
                    500, self._run_automatic_wizard_chain
                )
                return
            if self._wizard_batch_ready_for_next(step):
                self._automatic_chain_phase = WIZARD_STEP_MODELCHECK
                self._run_automatic_wizard_chain()
                return
            if self._go_fields_valid():
                self._automatic_chain_phase = None
                self._on_wizard_next()
                return
            self._automatic_wizard_chain_job = self.after(
                500, self._run_automatic_wizard_chain
            )
            return

        if phase == WIZARD_STEP_MODELCHECK and step == WIZARD_STEP_MODELCHECK:
            if not self._wizard_batch_ready_for_next(step):
                self._automatic_wizard_chain_job = self.after(
                    500, self._run_automatic_wizard_chain
                )
                return
            self._on_wizard_next()
            self._automatic_chain_phase = "start_jpeg"
            self._automatic_wizard_chain_job = self.after(300, self._run_automatic_wizard_chain)
            return

        if phase == "start_jpeg" and step == WIZARD_STEP_JPEG_3D:
            if self._wizard_batch_waiting_on_step(step):
                self._automatic_wizard_chain_job = self.after(
                    500, self._run_automatic_wizard_chain
                )
                return
            if self._wizard_batch_ready_for_next(step):
                self._automatic_chain_phase = WIZARD_STEP_JPEG_3D
                self._run_automatic_wizard_chain()
                return
            if self._go_fields_valid():
                self._automatic_chain_phase = None
                self._on_wizard_next()
                return
            self._automatic_wizard_chain_job = self.after(
                500, self._run_automatic_wizard_chain
            )
            return

        if phase == WIZARD_STEP_JPEG_3D and step == WIZARD_STEP_JPEG_3D:
            if not self._wizard_batch_ready_for_next(step):
                self._automatic_wizard_chain_job = self.after(
                    500, self._run_automatic_wizard_chain
                )
                return
            self._on_wizard_next()
            self._automatic_chain_phase = "create_report"
            self._automatic_wizard_chain_job = self.after(300, self._run_automatic_wizard_chain)
            return

        if phase == "create_report" and step == WIZARD_STEP_REPORT:
            if self._report_job_running:
                self._automatic_wizard_chain_job = self.after(500, self._run_automatic_wizard_chain)
                return
            wd = (self.working_directory.get() or "").strip()
            if _summary_report_inputs_ok(wd):
                self._automatic_chain_phase = None
                self._on_wizard_next()
            return

    def _wizard_batch_step_already_complete(self, step: int) -> bool:
        """True only when this step's batch already finished earlier in this session."""
        if self._wizard_step_outcome.get(step) != "done":
            return False
        batch_dir, scan_templates = self._wizard_batch_dir_for_step(step)
        if batch_dir is None:
            return False
        return not self._batch_dxc_files_exist(batch_dir, scan_templates)

    def _wizard_batch_waiting_on_step(self, step: int) -> bool:
        watch = self._wizard_batch_watch
        if watch is None or watch.get("step") != step:
            return False
        if self._wizard_step_has_remaining_dxc(step):
            return True
        return not self._wizard_batch_outputs_ready(watch)

    def _wizard_capture_failed_models_after_batch(self, watch: dict[str, object]) -> None:
        step = watch.get("step")
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return
        batch_dir = watch.get("batch_dir")
        if not isinstance(batch_dir, Path):
            return
        task_display = self._wizard_task_display_for_step(step)
        if not task_display:
            return
        task_kind = self._runner_task_kind(task_display)
        self._wizard_step_failed_models[step] = _read_batch_failed_models(
            batch_dir, task_kind
        )

    def _wizard_failed_models_for_step(self, step: int, log_dir: Path) -> list[str]:
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            return []
        task_display = self._wizard_task_display_for_step(step)
        if not task_display:
            return []
        task_kind = self._runner_task_kind(task_display)
        models = _read_batch_failed_models(log_dir, task_kind)
        self._wizard_step_failed_models[step] = models
        return models

    def _refresh_wizard_batch_failed_label(self, step: int, log_dir: Path | None) -> None:
        label = getattr(self, "wizard_batch_failed_label", None)
        if label is None:
            return
        if step not in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D) or log_dir is None:
            label.configure(text="")
            label.pack_forget()
            return
        failed_line = _format_batch_failed_models_line(
            self._wizard_failed_models_for_step(step, log_dir)
        )
        if failed_line:
            label.configure(text=failed_line, text_color="#C62828")
            label.pack(anchor="w", pady=(4, 0))
        else:
            label.configure(text="")
            label.pack_forget()

    def _wizard_batch_primary_action_label(self, step: int) -> str:
        if step == WIZARD_STEP_SCAN:
            return "Scan Templates >"
        if step == WIZARD_STEP_MODELCHECK:
            return "Run ModelCHECK >"
        if step == WIZARD_STEP_JPEG_3D:
            return "Run JPEG 3D >"
        return "Next >"

    def _on_wizard_back(self) -> None:
        if self._wizard_step <= WIZARD_STEP_SETUP:
            return
        if self._wizard_batch_waiting_on_step(self._wizard_step):
            return
        self._cancel_automatic_wizard_chain()
        self._cancel_wizard_batch_output_watch()
        self._set_wizard_step(self._wizard_step - 1)

    def _on_wizard_skip_step(self) -> None:
        step = self._wizard_step
        self._cancel_automatic_wizard_chain()
        self._cancel_wizard_batch_output_watch()
        self._close_batch_runner_window()
        if step == WIZARD_STEP_SCAN:
            if self._warn_wizard_working_directory_missing_models():
                return
            self._wizard_step_outcome[WIZARD_STEP_SCAN] = "skipped"
            self._set_wizard_step(WIZARD_STEP_MODELCHECK)
        elif step == WIZARD_STEP_MODELCHECK:
            self._wizard_step_outcome[WIZARD_STEP_MODELCHECK] = "skipped"
            self._set_wizard_step(WIZARD_STEP_JPEG_3D)
        elif step == WIZARD_STEP_JPEG_3D:
            self._wizard_step_outcome[WIZARD_STEP_JPEG_3D] = "skipped"
            self._set_wizard_step(WIZARD_STEP_REPORT)
            self._update_create_report_task_list(advance_from_jpeg=False)

    def _on_wizard_next(self) -> None:
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
            if self._wizard_batch_ready_for_next(step):
                self._wizard_advance_one_step_after_batch()
                return
            self._on_go()
            return
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            if self._wizard_batch_waiting_on_step(step):
                return
            if self._wizard_batch_ready_for_next(step):
                self._wizard_advance_one_step_after_batch()
                return
            self._on_go()
            return
        if step == WIZARD_STEP_REPORT:
            self._on_write_summary_report()

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
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Template",
                f"Could not create templates folder:\n{dest_dir.resolve()}\n\n{exc}",
            )
            return
        dest_name = _START_TEMPLATE_DEST_NAMES.get(kind)
        if not dest_name:
            return
        dest = dest_dir / dest_name
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            messagebox.showerror(
                "Template",
                f"Could not copy template:\n{source}\n\n→\n\n{dest.resolve()}\n\n{exc}",
            )
            return
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
                if dest is not None and dest.is_file():
                    label.configure(text=f"Set ({dest.name})", text_color="#2E7D32")
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
        if self._wizard_batch_ready_for_next(step):
            return False
        if step == WIZARD_STEP_SCAN:
            return self._scan_templates_skip_allowed()
        if step == WIZARD_STEP_MODELCHECK:
            return self._working_directory_has_modelcheck_xml()
        if step == WIZARD_STEP_JPEG_3D:
            return self._working_directory_has_jpg_files()
        return False

    def _latest_models_for_task(self, working_dir: Path, task_display: str) -> list[Path]:
        """Same model list GO uses: top-level only, latest revision per base name."""
        scanned = self._scan_models_non_recursive(
            working_dir,
            extensions=self._model_scan_extensions_for_task(task_display),
        )
        return self._get_latest_model_files(scanned)

    def _format_batch_model_count_message(self, latest_files: list[Path], _task_display: str) -> str:
        if not latest_files:
            return "No models to batch in the working directory yet."
        count = len(latest_files)
        models_word = "model" if count == 1 else "models"
        return f"{count} {models_word} will be batched in the working directory."

    def _refresh_wizard_batch_status(self) -> None:
        label = getattr(self, "wizard_batch_status_label", None)
        if label is None:
            return
        step = self._wizard_step
        if step in (WIZARD_STEP_MODELCHECK, WIZARD_STEP_JPEG_3D):
            self._refresh_wizard_step_batch_progress(step)
        if self._wizard_batch_waiting_on_step(step):
            return
        task_display = self._wizard_task_display_for_step(step)
        wd = (self.working_directory.get() or "").strip()
        if not wd:
            label.configure(text="Set the working directory on the Setup step.", text_color="#666666")
            return
        try:
            working_dir = Path(wd).expanduser()
            if not working_dir.is_dir() and not working_dir.parent.is_dir():
                label.configure(text="Working directory is not ready.", text_color="#666666")
                return
            if working_dir.is_dir():
                latest_files = self._latest_models_for_task(working_dir, task_display)
                lines: list[str] = []
                lines.append(self._format_batch_model_count_message(latest_files, task_display))
                ok = bool(latest_files)
                if step == WIZARD_STEP_MODELCHECK:
                    has_xml = self._working_directory_has_modelcheck_xml(wd)
                    lines.append(
                        "ModelCHECK XML found." if has_xml else "ModelCHECK XML not found yet."
                    )
                    ok = ok or has_xml
                elif step == WIZARD_STEP_JPEG_3D:
                    has_jpg = self._working_directory_has_jpg_files(wd)
                    lines.append("JPEG files found." if has_jpg else "JPEG files not found yet.")
                    ok = ok or has_jpg
                label.configure(
                    text="\n".join(lines),
                    text_color="#2E7D32" if ok else "#666666",
                )
                self._refresh_wizard_batch_failed_label(step, working_dir)
            else:
                label.configure(
                    text="Working folder will be created when you run this step.",
                    text_color="#111111",
                )
        except OSError:
            label.configure(text="Could not scan the working directory.", text_color="#666666")

    def _refresh_wizard_report_status(self) -> None:
        label = getattr(self, "wizard_report_status_label", None)
        if label is None:
            return
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            label.configure(text="Working directory is not ready.", text_color="#666666")
            return
        has_xml = self._working_directory_has_modelcheck_xml(wd)
        has_jpg = self._working_directory_has_jpg_files(wd)
        has_index = self._working_directory_index_html_path(wd) is not None
        lines: list[str] = []
        lines.append("ModelCHECK XML found." if has_xml else "ModelCHECK XML not found yet.")
        lines.append("JPEG files found." if has_jpg else "JPEG files not found yet.")
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
            if self._wizard_batch_waiting_on_step(step):
                nxt.configure(text="Waiting…", state="disabled")
            elif self._wizard_batch_ready_for_next(step):
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
            status = ctk.CTkLabel(
                row,
                text="Not set",
                anchor="w",
                font=ctk.CTkFont(size=12),
                text_color="#666666",
            )
            status.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self._wizard_template_status_labels[kind] = status
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
        self.wizard_batch_automatic_label = ctk.CTkLabel(
            self.wizard_batch_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#1565C0",
            anchor="w",
            justify="left",
            wraplength=500,
        )
        self.wizard_batch_failed_label = ctk.CTkLabel(
            self.wizard_batch_progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#C62828",
            anchor="w",
            justify="left",
            wraplength=500,
        )

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
            self._refresh_task_options()
            self._persist_working_directory_and_loadpoint()
            if self._wizard_step == WIZARD_STEP_SCAN:
                self._refresh_wizard_template_status()
            self._refresh_wizard_footer()

        def _on_task_var_changed(*_args: object) -> None:
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
        file_menu.add_command(label="Save", command=self._on_file_menu_save)
        file_menu.add_command(label="Save as...", command=self._on_file_menu_save_as)
        file_menu.add_separator()
        file_menu.add_command(
            label="Open Working Directory",
            command=self._on_open_working_directory,
        )
        file_menu.add_command(label="Zip report...", command=self._on_file_menu_zip_report)
        file_menu.add_separator()
        file_menu.add_command(label="Stop", command=self._on_file_menu_stop)
        file_menu.add_command(label="Start over...", command=self._on_file_menu_start_over)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        general_settings_menu = tk.Menu(menubar, tearoff=0)
        general_settings_menu.add_command(
            label="Chunk size...",
            command=self._on_chunk_size_settings,
        )
        general_settings_menu.add_command(
            label="Timeout...",
            command=self._on_timeout_settings,
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
            "Open Working Directory",
            "Start over...",
        ):
            try:
                fm.entryconfigure(label, state=tk.NORMAL if fully_enabled else tk.DISABLED)
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
            fm.entryconfigure("Stop", state=tk.NORMAL if batch_stop else tk.DISABLED)
        except tk.TclError:
            pass
        try:
            fm.entryconfigure("Exit", state=tk.NORMAL)
        except tk.TclError:
            pass
        if fully_enabled:
            self._refresh_file_menu_save_state()

    def _refresh_file_menu_save_state(self) -> None:
        """Disable File → Save / Save as when settings are not in a savable state."""
        fm = getattr(self, "_file_menu", None)
        if fm is None:
            return
        ok, _ = self._settings_fields_ready()
        st = tk.NORMAL if ok else tk.DISABLED
        try:
            fm.entryconfigure(2, state=st)
            fm.entryconfigure(3, state=st)
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
                    "automatic_mode": self._automatic_mode,
                    "debug_mode": self._debug_mode,
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
        return self._working_directory_has_creo_models(s, extensions=_CREO_MODEL_EXTENSIONS_ALL)

    def _warn_wizard_working_directory_missing_models(self) -> bool:
        """Warn when the working folder has no batchable Creo models. Returns True if missing."""
        wd = (self.working_directory.get() or "").strip()
        if not wd or not _working_directory_exists_as_dir(wd):
            return False
        if self._wizard_working_directory_has_models(wd):
            return False
        types_label = "/".join(f".{ext}" for ext in _CREO_MODEL_EXTENSIONS_ALL)
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
                f".prt, .asm, or .drw into:\n{Path(wd) / 'templates'}",
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
                    if entry.name.casefold() != "modchk":
                        continue
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
                "This runs kill.bat to stop Creo (Debug mode leaves the PowerShell window open).\n"
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
        if not self._show_proceed_cancel_dialog("Stop", prompt):
            return
        if watch is not None:
            self._wizard_capture_failed_models_after_batch(watch)
        self._cancel_automatic_wizard_chain()
        self._cancel_post_batch_task_refresh()
        self._close_batch_runner_window()
        kill_ok, kill_err = self._run_kill_bat()
        self._cancel_wizard_batch_output_watch()
        self._refresh_wizard_ui()
        if not kill_ok:
            messagebox.showwarning(
                "Stop",
                "Batch stopped, but kill.bat could not run:\n\n"
                f"{kill_err}\n\n"
                "Run kill.bat manually if Creo processes are still active.",
            )
            return
        messagebox.showinfo(
            "Stop",
            f"Batch stopped on the {step_label} step.\n\n"
            "Run this step again when you are ready to continue (completed outputs are skipped).",
        )

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
        templates_dir = working_dir / "templates"
        prompt = (
            "Remove prior scan and batch data from the working folder?\n\n"
            "Keeps Creo models (.prt, .asm, .drw) in the working folder and in templates\\."
        )
        if not self._show_proceed_cancel_dialog("Start over", prompt):
            return
        self._cancel_wizard_batch_output_watch()
        self._close_batch_runner_window()
        self._cancel_automatic_wizard_chain()
        errors: list[str] = []
        errors.extend(_remove_batch_timeout_logs_in_directory(working_dir))
        errors.extend(self._clean_start_over_directory(working_dir))
        if templates_dir.is_dir():
            errors.extend(_remove_batch_timeout_logs_in_directory(templates_dir))
            errors.extend(self._clean_start_over_directory(templates_dir))
        self._refresh_action_buttons()
        self._wizard_step_outcome.clear()
        self._wizard_step_failed_models.clear()
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
        data = self._read_app_settings_dict()
        data["automatic_mode"] = self._automatic_mode
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
        data = self._read_app_settings_dict()
        data["debug_mode"] = self._debug_mode
        return self._write_app_settings_dict(data)

    def _on_debug_mode_toggle(self) -> None:
        enabled = bool(self._debug_mode_var.get())
        err = self._persist_debug_mode(enabled)
        if err:
            self._debug_mode_var.set(not enabled)
            self._debug_mode = _normalize_automatic_mode(not enabled)
            messagebox.showerror("Debug", err)

    def _persist_chunk_size(self, chunk_size: int) -> str | None:
        self._chunk_size = _normalize_chunk_size(chunk_size)
        data = self._read_app_settings_dict()
        data["chunk_size"] = self._chunk_size
        return self._write_app_settings_dict(data)

    def _on_chunk_size_settings(self) -> None:
        dialog = self._create_modal_toplevel("Chunk size")

        ctk.CTkLabel(
            dialog,
            text=f"Models per batch chunk ({CREO_BATCH_CHUNK_SIZE_MIN}–{CREO_BATCH_CHUNK_SIZE_MAX}):",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        value_var = tk.StringVar(value=str(self._chunk_size))
        entry = ctk.CTkEntry(dialog, textvariable=value_var, width=80)
        entry.pack(anchor="w", padx=16, pady=(0, 12))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=16, pady=(0, 16))

        def close_dialog() -> None:
            dialog.destroy()

        def on_ok() -> None:
            raw = value_var.get().strip()
            try:
                n = int(raw)
            except ValueError:
                def warn() -> None:
                    messagebox.showwarning(
                        "Chunk size",
                        f"Enter a whole number from {CREO_BATCH_CHUNK_SIZE_MIN} to {CREO_BATCH_CHUNK_SIZE_MAX}.",
                        parent=dialog,
                    )

                warn()
                return
            if n < CREO_BATCH_CHUNK_SIZE_MIN or n > CREO_BATCH_CHUNK_SIZE_MAX:
                def warn_range() -> None:
                    messagebox.showwarning(
                        "Chunk size",
                        f"Enter a whole number from {CREO_BATCH_CHUNK_SIZE_MIN} to {CREO_BATCH_CHUNK_SIZE_MAX}.",
                        parent=dialog,
                    )

                warn_range()
                return
            err = self._persist_chunk_size(n)
            if err:

                def show_err() -> None:
                    messagebox.showerror("Chunk size", err, parent=dialog)

                show_err()
                return
            close_dialog()

        ctk.CTkButton(btn_row, text="OK", width=80, command=on_ok).pack(side="right", padx=(12, 0))
        ctk.CTkButton(btn_row, text="Cancel", width=80, command=close_dialog).pack(side="right")

        dialog.bind("<Return>", lambda _e: on_ok())
        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self._present_modal_toplevel(dialog, focus_widget=entry)

    def _persist_output_timeout_sec(self, timeout_sec: int) -> str | None:
        self._output_timeout_sec = _normalize_output_timeout_sec(timeout_sec)
        data = self._read_app_settings_dict()
        data["output_timeout_sec"] = self._output_timeout_sec
        return self._write_app_settings_dict(data)

    def _on_timeout_settings(self) -> None:
        dialog = self._create_modal_toplevel("Timeout")

        ctk.CTkLabel(
            dialog,
            text=f"Output wait timeout in seconds (minimum {BATCH_OUTPUT_WAIT_TIMEOUT_MIN}):",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        value_var = tk.StringVar(value=str(self._output_timeout_sec))
        entry = ctk.CTkEntry(dialog, textvariable=value_var, width=80)
        entry.pack(anchor="w", padx=16, pady=(0, 12))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(anchor="e", padx=16, pady=(0, 16))

        def close_dialog() -> None:
            dialog.destroy()

        def on_ok() -> None:
            raw = value_var.get().strip()
            if not raw.isdigit():

                def warn_digits() -> None:
                    messagebox.showwarning(
                        "Timeout",
                        f"Enter a whole number of seconds (minimum {BATCH_OUTPUT_WAIT_TIMEOUT_MIN}).",
                        parent=dialog,
                    )

                warn_digits()
                return
            n = int(raw)
            if n < BATCH_OUTPUT_WAIT_TIMEOUT_MIN:

                def warn_min() -> None:
                    messagebox.showwarning(
                        "Timeout",
                        f"Enter a whole number of seconds (minimum {BATCH_OUTPUT_WAIT_TIMEOUT_MIN}).",
                        parent=dialog,
                    )

                warn_min()
                return
            err = self._persist_output_timeout_sec(n)
            if err:

                def show_err() -> None:
                    messagebox.showerror("Timeout", err, parent=dialog)

                show_err()
                return
            close_dialog()

        ctk.CTkButton(btn_row, text="OK", width=80, command=on_ok).pack(side="right", padx=(12, 0))
        ctk.CTkButton(btn_row, text="Cancel", width=80, command=close_dialog).pack(side="right")

        dialog.bind("<Return>", lambda _e: on_ok())
        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        self._present_modal_toplevel(dialog, focus_widget=entry)

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
        """Open the bundled configs folder in File Explorer for manual edits."""
        target = self._configs_dir.resolve()
        if not target.is_dir():
            messagebox.showerror(
                "Folder not found",
                f"Expected configs folder next to the app:\n{target}",
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
        target = (self._configs_dir / rel).resolve()
        if not target.is_file():
            messagebox.showerror(
                "File not found",
                f"Expected sample config at:\n{target}\n\n(Relative to configs/ next to the app.)",
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

    def _go_fields_valid(self) -> bool:
        wd = (self.working_directory.get() or "").strip()
        lp = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        task_display = (self.task.get() or "").strip()
        if self._is_create_report_task(task_display):
            return False
        task_fn = self._task_filename_from_ui(task_display)
        if not wd or not _working_directory_ok_for_go(wd):
            return False
        if _path_contains_spaces(wd):
            return False
        if not self._go_model_source_ready(wd, self.task.get() or ""):
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
            ctk.CTkButton(btn_row, text="No", width=80, command=lambda: close(False)).pack(
                side="right", padx=(8, 0)
            )
            ctk.CTkButton(btn_row, text="Yes", width=80, command=lambda: close(True)).pack(side="right")
            dialog.bind("<Escape>", lambda _e: close(False))
            dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        else:
            ctk.CTkButton(btn_row, text="OK", width=80, command=lambda: close(True)).pack(side="right")
            dialog.bind("<Return>", lambda _e: close(True))
            dialog.bind("<Escape>", lambda _e: close(True))
            dialog.protocol("WM_DELETE_WINDOW", lambda: close(True))

        def place_centered() -> None:
            if not dialog.winfo_exists():
                return
            try:
                anchor.deiconify()
                anchor.update_idletasks()
            except tk.TclError:
                pass
            dialog.update_idletasks()
            try:
                _center_toplevel_on_parent(dialog, anchor)
            except tk.TclError:
                pass

        def show() -> None:
            if not dialog.winfo_exists():
                return
            dialog.deiconify()
            place_centered()
            try:
                dialog.attributes("-topmost", True)
                dialog.lift()
                dialog.focus_force()
                dialog.after(200, lambda: dialog.attributes("-topmost", False) if dialog.winfo_exists() else None)
            except tk.TclError:
                pass
            dialog.after(50, place_centered)

        self._modal_dialog_depth += 1
        try:
            dialog.update_idletasks()
            dialog.after_idle(show)
            dialog.wait_window()
        finally:
            self._modal_dialog_depth = max(0, self._modal_dialog_depth - 1)
            # CTkButton state can stay visually disabled until the next UI event (same as
            # _on_first_window_map); refresh after the modal closes so GO stays in sync.
            if anchor is self:

                def _repaint_action_buttons() -> None:
                    try:
                        self._refresh_action_buttons_run()
                        self.update_idletasks()
                    except tk.TclError:
                        pass

                self.after_idle(_repaint_action_buttons)
        return result["value"]

    def _show_proceed_cancel_dialog(self, title: str, message: str) -> bool:
        """Return True when the user clicks Proceed (Cancel is the default)."""
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
        cancel_btn = ctk.CTkButton(
            btn_row, text="Cancel", width=88, command=lambda: close(False)
        )
        proceed_btn = ctk.CTkButton(
            btn_row, text="Proceed", width=88, command=lambda: close(True)
        )
        cancel_btn.pack(side="right", padx=(8, 0))
        proceed_btn.pack(side="right")

        def place_centered() -> None:
            if not dialog.winfo_exists():
                return
            try:
                anchor.deiconify()
                anchor.update_idletasks()
            except tk.TclError:
                pass
            dialog.update_idletasks()
            try:
                _center_toplevel_on_parent(dialog, anchor)
            except tk.TclError:
                pass

        def show() -> None:
            if not dialog.winfo_exists():
                return
            dialog.deiconify()
            place_centered()
            try:
                dialog.attributes("-topmost", True)
                dialog.lift()
                cancel_btn.focus_set()
                dialog.after(
                    200,
                    lambda: dialog.attributes("-topmost", False)
                    if dialog.winfo_exists()
                    else None,
                )
            except tk.TclError:
                pass
            dialog.after(50, place_centered)

        dialog.bind("<Escape>", lambda _e: close(False))
        dialog.bind("<Return>", lambda _e: close(False))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))

        self._modal_dialog_depth += 1
        try:
            dialog.update_idletasks()
            dialog.after_idle(show)
            dialog.wait_window()
        finally:
            self._modal_dialog_depth = max(0, self._modal_dialog_depth - 1)
            if anchor is self:

                def _repaint_action_buttons() -> None:
                    try:
                        self._refresh_action_buttons_run()
                        self.update_idletasks()
                    except tk.TclError:
                        pass

                self.after_idle(_repaint_action_buttons)
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

        def place_centered() -> None:
            if not dialog.winfo_exists():
                return
            dialog.update_idletasks()
            try:
                _center_toplevel_on_parent(dialog, anchor)
            except tk.TclError:
                pass

        def show() -> None:
            if not dialog.winfo_exists():
                return
            dialog.deiconify()
            place_centered()
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
            dialog.after(50, place_centered)

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
        self._write_app_settings_dict(data)

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
        self._automatic_mode = _normalize_automatic_mode(
            data.get("automatic_mode", AUTOMATIC_MODE_DEFAULT)
        )
        self._automatic_mode_var.set(self._automatic_mode)
        self._debug_mode = _normalize_automatic_mode(
            data.get("debug_mode", DEBUG_MODE_DEFAULT)
        )
        self._debug_mode_var.set(self._debug_mode)
        self._set_creo_loadpoint_value(str(data.get("creo_loadpoint") or ""))
        self._warn_if_creo_loadpoint_missing_parametric()
        self._set_working_directory_value(str(data.get("working_directory") or ""))
        self._warn_if_working_directory_invalid()
        self._warn_if_working_directory_has_spaces()
        self._warn_if_working_directory_has_no_creo_models()

        self._refresh_task_options()
        self._refresh_configuration_menu()
        self._refresh_action_buttons()

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
        patterns = [_CREO_MODEL_EXT_PATTERNS[ext] for ext in extensions if ext in _CREO_MODEL_EXT_PATTERNS]
        files: dict[Path, list[str]] = defaultdict(list)
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            for pattern in patterns:
                if re.match(pattern, entry.name, re.IGNORECASE):
                    files[directory].append(entry.name)
                    break
        return files

    def _get_latest_model_files(self, files_dict: dict[Path, list[str]]) -> list[Path]:
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

        def model_sort_key(path: Path) -> tuple[int, str]:
            lower_name = path.name.lower()
            match = re.search(r"\.(prt|drw|asm)(?:\.\d+)?$", lower_name)
            ext = match.group(1) if match else ""
            rank = {"prt": 0, "drw": 1, "asm": 2}.get(ext, 3)
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
            for entry in d.iterdir():
                if entry.is_file() and pattern.match(entry.name):
                    return True
            return False
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
            for entry in d.iterdir():
                if not entry.is_file():
                    continue
                low = entry.name.lower()
                if low.endswith((".p.xml", ".a.xml", ".d.xml")):
                    return True
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
        """Files under a configs folder to embed as ``<ConfigFile>`` in a .dxc."""
        return [
            p
            for p in self._scan_files_recursive(directory)
            if p.suffix.lower() not in _MODELCHECK_CONFIG_SKIP_SUFFIXES
        ]

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
    def _cleanup_leftover_batch_dxc(batch_dir: Path, *, scan_templates: bool) -> None:
        """Remove leftover batch .dxc files (does not remove runner .ps1)."""
        try:
            if not batch_dir.is_dir():
                return
            if scan_templates:
                dxc_candidates = [batch_dir / SCAN_TEMPLATES_DXC_BASENAME]
                dxc_candidates.extend(batch_dir.glob("scan-*.dxc"))
            else:
                dxc_candidates = list(batch_dir.glob(f"{CREO_BATCH_BASE}-*.dxc"))
            for p in dxc_candidates:
                if p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    @staticmethod
    def _cleanup_leftover_batch_files(
        batch_dir: Path, *, scan_templates: bool, keep_runner_scripts: bool = False
    ) -> None:
        """Remove prior GO batch .dxc and runner script before writing new ones."""
        try:
            if not batch_dir.is_dir():
                return
            CreoDistributedBatchMakerApp._cleanup_leftover_batch_dxc(
                batch_dir, scan_templates=scan_templates
            )
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
            return f"{stem}.{ext_lower[0]}.xml"
        return f"{stem}.jpg"

    @classmethod
    def _batch_runner_xtop_helpers_ps1(cls) -> list[str]:
        return [
            f"$XtopDeadChecksRequired = {BATCH_XTOP_DEAD_CHECKS}",
            f"$XtopRestartWaitSec = {BATCH_XTOP_RESTART_WAIT_SEC}",
            f"$XtopDeadWindowSec = {BATCH_XTOP_DEAD_WINDOW_SEC}",
            "",
            "function Test-XtopAlive {",
            "    $procs = Get-Process -Name xtop -ErrorAction SilentlyContinue",
            "    if ($null -eq $procs) { return $false }",
            "    return (@($procs).Count -gt 0)",
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
            "        $WatchEnabled.Value = $true",
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
    def _batch_runner_xtop_wait_init_ps1(cls, *, indent: str) -> list[str]:
        return [
            f"{indent}$xtopDeadStreak = 0",
            f"{indent}$xtopFirstDeadAt = $null",
            f"{indent}$xtopWatchEnabled = $false",
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
            f'{indent}    Write-ChLog ("XTOP GONE: xtop not running for " + $XtopDeadChecksRequired + " consecutive checks (within " + $XtopDeadWindowSec + "s) and no restart within " + $XtopRestartWaitSec + "s; moving on.")',
        ]
        if chunk_var is not None:
            lines.extend(
                [
                    f"{indent}    Record-TimedOutChunk -Chunk ${chunk_var} -MissingOutputs $missing",
                    f"{indent}    $TimedOutFileCount += $missing.Count",
                    f"{indent}    $SuccessFileCount += ($expected.Count - $missing.Count)",
                ]
            )
        else:
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
        """Start or extend output inactivity timer only while xtop.exe is running."""
        return [
            f"{indent}if (Test-XtopAlive) {{",
            f"{indent}    $xtopWatchEnabled = $true",
            f"{indent}    $waitStart = Get-Date",
            f"{indent}}}",
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
            f"{i}    if ($totalWaitSec -le 4 -or ($totalWaitSec % 30 -eq 0)) {{",
            f'{i}        Write-ChLog ("WAITING: " + $missing.Count + " of " + ${names_var}.Count + " output file(s) missing (xtop running; inactivity timer paused; " + $totalWaitSec + "s total wait)"{tail})',
            f"{i}    }}",
            f"{i}}} else {{",
            f"{i}    if ($elapsed -le 4 -or ($elapsed % 30 -eq 0)) {{",
            f'{i}        Write-ChLog ("WAITING: " + $missing.Count + " of " + ${names_var}.Count + " output file(s) missing (" + $elapsed + "s with no progress; " + $totalWaitSec + "s total wait)"{tail})',
            f"{i}    }}",
            f"{i}}}",
        ]

    @classmethod
    def _batch_runner_kill_after_settle_ps1(cls, *, indent: str) -> list[str]:
        """Settle, wait for xtop.exe to exit, then run kill.bat."""
        i = indent
        return [
            f"{i}Write-ChLog (\"Settling \" + $OutputSettleSec + \"s before kill.bat...\")",
            f"{i}Start-Sleep -Seconds $OutputSettleSec",
            f"{i}$xtopExitWaitStart = Get-Date",
            f"{i}while (Test-XtopAlive) {{",
            f"{i}    $xtopExitSec = [int][math]::Floor(((Get-Date) - $xtopExitWaitStart).TotalSeconds)",
            f"{i}    if ($xtopExitSec -le 4 -or ($xtopExitSec % 30 -eq 0)) {{",
            f'{i}        Write-ChLog ("WAITING: xtop still running (" + $xtopExitSec + "s); waiting for exit before kill.bat.")',
            f"{i}    }}",
            f"{i}    Start-Sleep -Seconds 2",
            f"{i}}}",
            f'{i}$killParent = [System.IO.Path]::GetDirectoryName($KillBat)',
            f'{i}Write-ChLog "Running kill.bat (wait)..."',
            f"{i}try {{",
            f"{i}    $kp = Start-Process -FilePath $KillBat -WorkingDirectory $killParent `",
            f"{i}        -Wait -PassThru -NoNewWindow -ErrorAction Stop",
            f'{i}    Write-ChLog ("kill.bat exit code: " + $kp.ExitCode)',
            f"{i}}} catch {{",
            f'{i}    Write-ChLog ("ERROR: kill.bat failed: " + $_.Exception.Message)',
            f"{i}}}",
        ]

    @classmethod
    def _build_scan_templates_runner_ps1(
        cls,
        ptcdbatch_bat: Path,
        templates_dir: Path,
        kill_bat: Path,
        expected_outputs: list[str],
        output_timeout_sec: int,
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
            "function Write-ChLog {",
            "    param([string]$Message)",
            "    $ts = Get-Date -Format 'HH:mm:ss'",
            '    $line = "[$ts] $Message"',
            "    if ($Message -match '(?i)^DONE:' -or $Message -match '(?i)^SKIP:') {",
            '        Write-Host $line -ForegroundColor Green',
            "    } elseif ($Message -match '(?i)^TIMEOUT:') {",
            '        Write-Host $line -ForegroundColor Red',
            "    } elseif ($Message -match '(?i)^XTOP GONE:') {",
            '        Write-Host $line -ForegroundColor Red',
            "    } else {",
            '        Write-Host $line',
            "    }",
            "}",
            "",
            *cls._batch_runner_xtop_helpers_ps1(),
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
            r'Write-ChLog ("Output wait timeout: " + $OutputTimeoutSec + " s; settle: " + $OutputSettleSec + " s")',
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
            "$missing = Get-MissingOutputs -Dir $WorkDir -Names $Expected",
            "if ($missing.Count -eq 0) {",
            r'    Write-ChLog ("SKIP: all " + $Expected.Count + " expected output file(s) already exist.")',
            "    $SuccessFileCount = $Expected.Count",
            "} else {",
            r'    Write-ChLog ("Pre-check: " + $missing.Count + " of " + $Expected.Count + " output file(s) missing; will run dbatch.")',
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
            r'    Write-ChLog "WAITING: for expected output file(s) to appear (poll every 2s; inactivity timer starts when xtop appears; resets when a file appears or while xtop is running)."',
            "    $chunkWaitStart = Get-Date",
            "    $waitStart = $chunkWaitStart",
            "    $missing = Get-MissingOutputs -Dir $WorkDir -Names $Expected",
            "    $lastMissingCount = $missing.Count",
            "    $timedOut = $false",
            *cls._batch_runner_xtop_wait_init_ps1(indent="    "),
            "    while ($true) {",
            "        $missing = Get-MissingOutputs -Dir $WorkDir -Names $Expected",
            "        if ($missing.Count -eq 0) { break }",
            "        if ($missing.Count -lt $lastMissingCount) {",
            "            $delta = $lastMissingCount - $missing.Count",
            r'            Write-ChLog ("PROGRESS: " + $delta + " new output file(s); resetting timer. " + $missing.Count + " of " + $Expected.Count + " remaining.")',
            "            if ($xtopWatchEnabled) { $waitStart = Get-Date }",
            "            $lastMissingCount = $missing.Count",
            "        }",
            *cls._batch_runner_xtop_manage_wait_timer_ps1(indent="        "),
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
            "        Start-Sleep -Seconds 2",
            "    }",
            "    if (-not $timedOut) {",
            r'        Write-ChLog ("DONE: all " + $Expected.Count + " expected output file(s) present.")',
            "        $SuccessFileCount = $Expected.Count",
            "    }",
            "",
            *cls._batch_runner_kill_after_settle_ps1(indent="    "),
            "}",
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
            r'Write-ChLog "---------- Batch summary ----------"',
            r'Write-ChLog ("Count of Files Success: " + $SuccessFileCount)',
            r'Write-ChLog ("Count of Files Timed Out: " + $TimedOutFileCount)',
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
    ) -> str:
        """PowerShell: per chunk, skip if outputs already exist; else launch ptcdbatch, poll for expected output files, settle, then run kill.bat.

        If any outputs time out, write one per-run timeout summary file in ``working_dir``
        listing timed-out model names only. Removes each chunk .dxc when that chunk finishes.
        """
        ptc = cls._ps_single_quoted_literal(ptcdbatch_bat)
        wd = cls._ps_single_quoted_literal(working_dir)
        kb = cls._ps_single_quoted_literal(kill_bat)
        n = int(num_chunks)
        base = CREO_BATCH_BASE.replace("'", "''")
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
            "function Write-ChLog {",
            "    param([string]$Message)",
            "    $ts = Get-Date -Format 'HH:mm:ss'",
            '    $line = "[$ts] $Message"',
            "    if ($Message -match '(?i)^DONE:' -or $Message -match '(?i)^SKIP:') {",
            '        Write-Host $line -ForegroundColor Green',
            "    } elseif ($Message -match '(?i)^TIMEOUT:') {",
            '        Write-Host $line -ForegroundColor Red',
            "    } elseif ($Message -match '(?i)^XTOP GONE:') {",
            '        Write-Host $line -ForegroundColor Red',
            "    } else {",
            '        Write-Host $line',
            "    }",
            "}",
            "",
            *cls._batch_runner_xtop_helpers_ps1(),
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
            "$TimedOutModels = @{}",
            "$TimeoutLogInitialized = $false",
            "$SuccessFileCount = 0",
            "$TimedOutFileCount = 0",
            "$TimeoutLog = Join-Path -Path $WorkDir -ChildPath ('creo-batch-timeouts-' + $TaskKind + '.txt')",
            "",
            "function Record-TimedOutChunk {",
            "    param([int]$Chunk, [string[]]$MissingOutputs)",
            "    if ($MissingOutputs.Count -eq 0) { return }",
            "    if (-not $TimeoutLogInitialized) {",
            "        $header = @(",
            "            ('Task: ' + $TaskKind),",
            "            ('Started: ' + (Get-Date -Format 'HH:mm:ss')),",
            "            ('Log file: ' + $TimeoutLog),",
            "            '',",
            "            'Models timed out:'",
            "        )",
            "        Set-Content -LiteralPath $TimeoutLog -Value $header -Encoding UTF8",
            "        $script:TimeoutLogInitialized = $true",
            r'        Write-ChLog ("TIMEOUT LOG: writing timed-out models to " + $TimeoutLog)',
            "    }",
            "    foreach ($mOut in $MissingOutputs) {",
            "        $mName = $null",
            "        if ($ModelByOutputByChunk.ContainsKey($Chunk)) {",
            "            $mName = $ModelByOutputByChunk[$Chunk][$mOut]",
            "        }",
            "        if (-not $mName) { $mName = $mOut }",
            "        if ($TimedOutModels.ContainsKey($mName)) { continue }",
            "        $TimedOutModels[$mName] = $true",
            "        Add-Content -LiteralPath $TimeoutLog -Value $mName -Encoding UTF8",
            "    }",
            "}",
            "",
            r'Write-ChLog "Runner starting. $NumChunks chunk(s). Skips chunks whose outputs already exist; otherwise polls for expected output files."',
            r'Write-ChLog "ptcdbatch: $PtcDbatch"',
            r'Write-ChLog "Working directory: $WorkDir"',
            r'Write-ChLog "kill.bat: $KillBat"',
            r'Write-ChLog ("Output wait timeout: " + $OutputTimeoutSec + " s; settle: " + $OutputSettleSec + " s")',
            "",
            "for ($chunk = 1; $chunk -le $NumChunks; $chunk++) {",
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
            "    $batParent = [System.IO.Path]::GetDirectoryName($PtcDbatch)",
            r'    Write-ChLog "Launching ptcdbatch (hidden window): -nographics -process $dxc"',
            "    try {",
            "        $null = Start-Process -FilePath $PtcDbatch -WorkingDirectory $batParent `",
            "            -ArgumentList @('-nographics', '-process', $dxc) `",
            "            -WindowStyle Hidden -ErrorAction Stop",
            "    } catch {",
            r'        Write-ChLog ("ERROR: failed to start ptcdbatch: " + $_.Exception.Message)',
            "        continue",
            "    }",
            "",
            r'    Write-ChLog "WAITING: for expected output file(s) to appear (poll every 2s; inactivity timer starts when xtop appears; resets when a file appears or while xtop is running)."',
            "    $chunkWaitStart = Get-Date",
            "    $waitStart = $chunkWaitStart",
            "    $missing = Get-MissingOutputs -Dir $WorkDir -Names $expected",
            "    $lastMissingCount = $missing.Count",
            "    $timedOut = $false",
            *cls._batch_runner_xtop_wait_init_ps1(indent="    "),
            "    while ($true) {",
            "        $missing = Get-MissingOutputs -Dir $WorkDir -Names $expected",
            "        if ($missing.Count -eq 0) { break }",
            "        if ($missing.Count -lt $lastMissingCount) {",
            "            $delta = $lastMissingCount - $missing.Count",
            r'            Write-ChLog ("PROGRESS: " + $delta + " new output file(s) detected; resetting inactivity timer. " + $missing.Count + " of " + $expected.Count + " remaining.")',
            "            if ($xtopWatchEnabled) { $waitStart = Get-Date }",
            "            $lastMissingCount = $missing.Count",
            "        }",
            *cls._batch_runner_xtop_manage_wait_timer_ps1(indent="        "),
            *cls._batch_runner_wait_timeout_check_ps1(
                indent="        ",
                timeout_body=[
                    r'Write-ChLog ("TIMEOUT: no new output file(s) for " + $elapsed + "s; " + $missing.Count + " of " + $expected.Count + " still missing. First missing: " + $missing[0] + ".")',
                    "Record-TimedOutChunk -Chunk $chunk -MissingOutputs $missing",
                    "$TimedOutFileCount += $missing.Count",
                    "$SuccessFileCount += ($expected.Count - $missing.Count)",
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
            "        Start-Sleep -Seconds 2",
            "    }",
            "    if (-not $timedOut) {",
            r'        Write-ChLog ("DONE: all " + $expected.Count + " expected output file(s) present.")',
            "        $SuccessFileCount += $expected.Count",
            "    }",
            "",
            *cls._batch_runner_kill_after_settle_ps1(indent="    "),
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
            r'Write-ChLog "Runner finished all chunks."',
        ]
        return "\n".join(lines) + "\n"

    def _on_go(self) -> None:
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
        types_label = self._model_scan_types_label(task_display_raw)
        scan_templates = self._is_scan_templates_task(task_display_raw)
        if not self._go_model_source_ready(working_dir_raw, task_display_raw):
            if scan_templates:
                messagebox.showwarning(
                    "Templates",
                    "GO needs at least one Creo template (.prt, .asm, or .drw) in:\n"
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
                    "Missing configs",
                    "Scan Templates requires the templates config folder next to the app:\n"
                    f"{modelcheck_config_dir}",
                )
            else:
                messagebox.showerror(
                    "Missing configs",
                    f"Modelcheck task requires the configs folder next to the app:\n{modelcheck_config_dir}",
                )
            return
        if use_jpeg_config:
            jpeg_config_pro = self._configs_dir / "config.pro"
            if not jpeg_config_pro.is_file():
                messagebox.showerror(
                    "Missing configs",
                    f"JPEG batch task requires config.pro in the configs folder next to the app:\n{jpeg_config_pro}",
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

        if not ptcdbatch_bat.is_file():
            messagebox.showerror("File Not Found", f"Could not find:\n{ptcdbatch_bat}")
            return
        if not kill_bat.is_file():
            messagebox.showerror(
                "File Not Found",
                f"Could not find:\n{kill_bat}\n\nPlace kill.bat next to this application.",
            )
            return

        sample_start_note = ""
        if self._is_regular_modelcheck_task(task_display_raw):
            ok, err, _ = self._update_sample_start_from_template_xml_if_present()
            if not ok:
                messagebox.showerror("GO", err)
                return

        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            scanned = self._scan_models_non_recursive(models_dir, extensions=scan_extensions)
            latest_files = self._get_latest_model_files(scanned)
            if scan_templates:
                latest_files = _sort_scan_template_models(latest_files)
            config_files = (
                self._scan_modelcheck_config_files(modelcheck_config_dir)
                if modelcheck_config_dir is not None
                else []
            )
            if scan_templates:
                model_chunks = [latest_files]
            else:
                model_chunks = self._chunk_paths(latest_files, self._chunk_size)
                if not model_chunks:
                    model_chunks = [[]]

            batch_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_leftover_batch_files(
                batch_dir,
                scan_templates=scan_templates,
                keep_runner_scripts=self._debug_mode,
            )
            if scan_templates:
                output_dir_attr = _xml_attr_escape(_dxc_path_str(batch_dir))
            else:
                output_dir_attr = _xml_attr_escape(working_dir_raw)
            for idx, chunk in enumerate(model_chunks, start=1):
                if scan_templates:
                    chunk_path = batch_dir / SCAN_TEMPLATES_DXC_BASENAME
                else:
                    chunk_path = batch_dir / f"{CREO_BATCH_BASE}-{idx}.dxc"
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

            if scan_templates:
                scan_expected: list[str] = []
                for p in latest_files:
                    out = self._expected_output_basename(p, is_modelcheck=True)
                    if out:
                        scan_expected.append(out)
                runner_text = self._build_scan_templates_runner_ps1(
                    ptcdbatch_bat,
                    batch_dir,
                    kill_bat,
                    scan_expected,
                    self._output_timeout_sec,
                )
            else:
                num_chunks = len(model_chunks)
                expected_outputs_per_chunk: list[list[str]] = []
                output_to_model_per_chunk: list[dict[str, str]] = []
                for chunk in model_chunks:
                    names: list[str] = []
                    out_to_model: dict[str, str] = {}
                    for p in chunk:
                        out = self._expected_output_basename(p, is_modelcheck=use_modelcheck_config)
                        if out:
                            names.append(out)
                            out_to_model[out] = p.name
                    expected_outputs_per_chunk.append(names)
                    output_to_model_per_chunk.append(out_to_model)
                runner_text = self._build_chunk_runner_ps1(
                    ptcdbatch_bat,
                    batch_dir,
                    kill_bat,
                    num_chunks,
                    expected_outputs_per_chunk,
                    output_to_model_per_chunk,
                    self._runner_task_kind(task_display_raw),
                    self._output_timeout_sec,
                )
            runner_ps1_path.write_text(runner_text, encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror(
                "Create File Failed",
                f"Could not create batch .dxc or runner script in:\n{batch_dir}\n\n{exc}",
            )
            return

        self._update_create_report_task_list()
        self._save_settings()
        if not scan_templates and task_display_raw:
            task_kind = self._runner_task_kind(task_display_raw)
            if task_kind in ("modelcheck", "jpeg3d"):
                _clear_batch_timeout_logs(batch_dir, task_kind)
                self._wizard_step_failed_models.pop(self._wizard_step, None)
        if not self._launch_batch_runner(working_dir, task_display_raw):
            self._refresh_action_buttons_run()
            return
        self._schedule_post_batch_task_refresh()
        launched_dxc_count = 1 if scan_templates else len(model_chunks)
        self._start_wizard_batch_output_watch(
            self._wizard_step,
            batch_dir,
            scan_templates,
            launched_dxc_count=launched_dxc_count,
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
        self._refresh_wizard_footer()
        self._refresh_menu_bar_state()

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
        self._refresh_action_buttons()
        self._bring_app_forward()

        error = result.get("error")
        if error:
            kind = result.get("kind")
            if kind == "patch":
                messagebox.showerror(
                    "Report Failed",
                    f"Could not patch ModelCHECK HTML.\n\n{error}",
                )
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
        if written and messagebox.askyesno(
            "Report",
            f"Wrote full report (with sidebar):\n{written}\n\nOpen in browser?",
        ):
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
        self._set_report_busy(True)
        settings_path = _default_app_settings_path()
        wd = str(working_dir)

        def work() -> None:
            result: dict[str, object] = {"written": None, "error": None, "kind": None}
            try:
                patch.run(settings_path=settings_path, quiet=True)
                result["written"] = build_errors_warnings_report.build_errors_warnings_html(wd)
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
        if not self._working_directory_has_modelcheck_xml(wd):
            messagebox.showwarning(
                "Missing ModelCHECK XML",
                "No ModelCHECK result XML (*.p.xml, *.a.xml, *.d.xml) was found in the working directory.",
            )
            return
        ok, build_err = self._build_master_xml_silent(working_dir)
        if not ok:
            messagebox.showerror("Report Failed", build_err or "Could not build master.xml.")
            return
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
        self._persist_working_directory_and_loadpoint()
        self._start_report_job(working_dir)

    def _close_batch_runner_window(self) -> None:
        """Close the PowerShell console launched for the current batch runner, if still open."""
        proc = self._batch_runner_process
        self._batch_runner_process = None
        if proc is None:
            return
        if self._debug_mode:
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
            popen_kw: dict = {
                "args": [
                    ps_exe,
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(runner_ps1.resolve()),
                ],
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
