#!/usr/bin/env python3
"""
Copy Creo ModelCHECK web assets locally and patch report HTML to use them.

Reads ``app_settings.json`` (``creo_loadpoint``, ``working_directory``), copies
``<loadpoint>/Common Files/modchk`` to ``<working_directory>/modchk``, then
rewrites ModelCHECK HTML in the working directory so ``file:///.../Common Files/modchk/``
references become relative ``modchk/`` paths.

Skips ``index.html`` (app summary report) and any ``.html`` under ``modchk/``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# file:///C:/Creo 12.4.4.0/...  or file:///C:\PTC\Creo 12.4.4.0\... (spaces allowed in path)
_FILE_URI_MODCHK = re.compile(
    r"file://[^\"']*?Common\s+Files[\\/]modchk[\\/]",
    re.IGNORECASE,
)

# Full Windows path without file://
_PLAIN_MODCHK = re.compile(
    r"[A-Za-z]:[^\"']*?Common\s+Files[\\/]modchk[\\/]",
    re.IGNORECASE,
)


class PatchError(Exception):
    """Invalid settings or paths for patch."""


@dataclass(frozen=True)
class PatchResult:
    working_dir: Path
    modchk_dest: Path
    html_files_scanned: int
    patched_files: int
    total_replacements: int


def _app_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_settings_path() -> Path:
    return _app_bundle_dir() / "app_settings.json"


def _load_settings(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise PatchError(f"Settings file not found:\n{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatchError(f"Invalid JSON in {path}:\n{exc}") from exc
    if not isinstance(data, dict):
        raise PatchError(f"Settings file must be a JSON object: {path}")
    return {str(k): str(v) if v is not None else "" for k, v in data.items()}


def _require_path(settings: dict[str, str], key: str, label: str) -> Path:
    raw = (settings.get(key) or "").strip()
    if not raw:
        raise PatchError(f"Missing or empty {key!r} in app_settings.json ({label}).")
    p = Path(raw)
    if not p.is_dir():
        raise PatchError(f"{label} is not an existing folder:\n{p}")
    return p.resolve()


def _modchk_source(loadpoint: Path) -> Path:
    src = loadpoint / "Common Files" / "modchk"
    if not src.is_dir():
        raise PatchError(
            f"ModelCHECK web folder not found under loadpoint:\n{src}\n\n"
            "Expected: <creo_loadpoint>/Common Files/modchk"
        )
    return src


def _path_prefixes_for_replace(modchk_src: Path) -> list[str]:
    """Literal prefixes to replace with ``modchk/`` (covers non-file:// paths)."""
    base = modchk_src.resolve()
    prefixes: list[str] = []
    for p in (str(base), str(base).replace("\\", "/")):
        if p and p not in prefixes:
            prefixes.append(p)
        if not p.endswith(("/", "\\")):
            for suffix in ("/", "\\"):
                candidate = p + suffix
                if candidate not in prefixes:
                    prefixes.append(candidate)
    return sorted(prefixes, key=len, reverse=True)


def patch_html_text(text: str, modchk_src: Path) -> tuple[str, int]:
    """Return patched text and number of substitutions."""
    count = 0
    text, n1 = _FILE_URI_MODCHK.subn("modchk/", text)
    count += n1
    text, n2 = _PLAIN_MODCHK.subn("modchk/", text)
    count += n2
    for prefix in _path_prefixes_for_replace(modchk_src):
        while prefix in text:
            text = text.replace(prefix, "modchk/", 1)
            count += 1
    return text, count


def _html_files_to_patch(working_dir: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(working_dir.glob("*.html")):
        if path.name.lower() == "index.html":
            continue
        out.append(path)
    return out


def _modchk_dest_looks_usable(dest: Path) -> bool:
    """Best-effort check that existing local modchk has expected assets."""
    return (
        (dest / "templates_new").is_dir()
        and (dest / "templates_new" / "mctopban.js").is_file()
        and (dest / "text").is_dir()
    )


def copy_modchk(
    src: Path,
    dest: Path,
    *,
    dry_run: bool = False,
    quiet: bool = False,
    replace_existing: bool = False,
) -> None:
    if dest.exists() and not dest.is_dir():
        raise PatchError(f"Cannot create modchk folder; path exists as a file:\n{dest}")
    if dry_run:
        if not quiet:
            print(f"[dry-run] would copy:\n  {src}\n  -> {dest}")
        return
    if dest.exists() and dest.is_dir() and not replace_existing and _modchk_dest_looks_usable(dest):
        if not quiet:
            print(f"Using existing modchk:\n  {dest}")
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    if not quiet:
        print(f"Copied modchk:\n  {src}\n  -> {dest}")


def run(
    *,
    settings_path: Path | None = None,
    dry_run: bool = False,
    quiet: bool = False,
    replace_existing_modchk: bool = False,
) -> PatchResult:
    path = (settings_path or default_settings_path()).resolve()
    settings = _load_settings(path)
    loadpoint = _require_path(settings, "creo_loadpoint", "Creo loadpoint")
    working_dir = _require_path(settings, "working_directory", "Working directory")

    modchk_src = _modchk_source(loadpoint)
    modchk_dest = working_dir / "modchk"
    copy_modchk(
        modchk_src,
        modchk_dest,
        dry_run=dry_run,
        quiet=quiet,
        replace_existing=replace_existing_modchk,
    )

    html_files = _html_files_to_patch(working_dir)
    patched_files = 0
    total_replacements = 0
    for html_path in html_files:
        original = html_path.read_text(encoding="utf-8", errors="replace")
        updated, n = patch_html_text(original, modchk_src)
        if n == 0:
            continue
        patched_files += 1
        total_replacements += n
        if dry_run:
            if not quiet:
                print(f"[dry-run] would patch {html_path.name} ({n} replacement(s))")
        else:
            html_path.write_text(updated, encoding="utf-8")
            if not quiet:
                print(f"Patched {html_path.name} ({n} replacement(s))")

    result = PatchResult(
        working_dir=working_dir,
        modchk_dest=modchk_dest,
        html_files_scanned=len(html_files),
        patched_files=patched_files,
        total_replacements=total_replacements,
    )
    if not quiet:
        print(
            f"\nDone: {result.patched_files} of {result.html_files_scanned} HTML file(s) updated, "
            f"{result.total_replacements} reference(s) switched to modchk/."
        )
        if result.patched_files == 0:
            print("No file://.../Common Files/modchk/ references found (already patched?).")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy Creo modchk assets locally and patch ModelCHECK HTML reports.",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help=f"Path to app_settings.json (default: {default_settings_path()})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied/patched without writing files",
    )
    args = parser.parse_args(argv)
    try:
        run(settings_path=args.settings, dry_run=args.dry_run, quiet=False)
        return 0
    except PatchError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
