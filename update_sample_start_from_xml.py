"""Update sample_start.mcs from ModelCHECK template XML under a working directory.

Currently updates the PART section (PRT_PARAMETER / PRT_LAYER) from part_template.p.xml.
Assembly and drawing support will be added later.

Usage:
    python update_sample_start_from_xml.py
    python update_sample_start_from_xml.py --dry-run

Uses working_directory from app_settings.json (same as the GUI) and
<working_dir>\\templates\\part_template.p.xml.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_LAYER_SUFFIX_RE = re.compile(r"\s+\[(?:no items|\d+ items?)\]$", re.IGNORECASE)


def _app_dir() -> Path:
    return Path(__file__).resolve().parent


def _app_settings_path() -> Path:
    return _app_dir() / "app_settings.json"


def _load_working_directory_from_settings() -> str | None:
    """Read working_directory from app_settings.json next to this script."""
    settings_path = _app_settings_path()
    if not settings_path.is_file():
        return None
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    wd = str(data.get("working_directory") or "").strip()
    return wd or None


def _default_mcs_path() -> Path:
    return _app_dir() / "configs" / "sample_start.mcs"


def _part_section_bounds(lines: list[str]) -> tuple[int, int]:
    start = 0
    end = len(lines)
    for i, line in enumerate(lines):
        if "PART MODE START" in line:
            start = i
        if "ASSEMBLY MODE START" in line:
            end = i
            break
    return start, end


def _is_prt_parameter_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    return stripped.startswith("PRT_PARAMETER ") or stripped == "PRT_PARAMETER"


def _is_prt_layer_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped.startswith(("PRT_LAYER_UNWANTED", "PRT_LAYER_MOVE")):
        return False
    return stripped.startswith("PRT_LAYER ") or stripped == "PRT_LAYER"


def _format_mcs_line(keyword: str, value: str) -> str:
    # sample_start.mcs aligns the value column at char 22 (keyword field width 21).
    return f"{keyword:<21}{value}"


def _mcs_output_lines(param_names: list[str], layer_names: list[str]) -> list[str]:
    lines = [_format_mcs_line("PRT_PARAMETER", name) for name in param_names]
    if lines and layer_names:
        lines.append("")
    lines.extend(_format_mcs_line("PRT_LAYER", name) for name in layer_names)
    return lines


def _find_check(root: ET.Element, check_name: str) -> ET.Element | None:
    for check in root.findall(".//check"):
        if check.get("name") == check_name:
            return check
    return None


def _check_items(check: ET.Element | None) -> list[str]:
    if check is None:
        return []
    values: list[str] = []
    for item in check.findall("item"):
        info1 = item.find("info1")
        if info1 is not None and info1.text:
            values.append(info1.text.strip())
    return values


def _unique_preserve_order(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _normalize_layer_name(name: str) -> str:
    return _LAYER_SUFFIX_RE.sub("", name.strip())


def parse_part_xml(xml_path: Path) -> tuple[list[str], list[str]]:
    root = ET.parse(xml_path).getroot()
    param_names = _unique_preserve_order(_check_items(_find_check(root, "PARAM_INFO")))
    layer_names = _unique_preserve_order(
        [_normalize_layer_name(n) for n in _check_items(_find_check(root, "LAYER_INFO"))]
    )
    return param_names, layer_names


def replace_prt_blocks(
    lines: list[str],
    param_names: list[str],
    layer_names: list[str],
) -> list[str]:
    part_start, part_end = _part_section_bounds(lines)
    part_lines = lines[part_start:part_end]

    param_indices = [i for i, line in enumerate(part_lines) if _is_prt_parameter_line(line)]
    layer_indices = [i for i, line in enumerate(part_lines) if _is_prt_layer_line(line)]

    new_param_lines = [_format_mcs_line("PRT_PARAMETER", name) for name in param_names]
    new_layer_lines = [_format_mcs_line("PRT_LAYER", name) for name in layer_names]

    remove_param = set(param_indices)
    remove_layer = set(layer_indices)
    param_insert_at = min(param_indices) if param_indices else None
    layer_insert_at = min(layer_indices) if layer_indices else None

    kept: list[str] = []
    for i, line in enumerate(part_lines):
        if i in remove_param:
            if i == param_insert_at:
                kept.extend(new_param_lines)
            continue
        if i in remove_layer:
            if i == layer_insert_at:
                kept.extend(new_layer_lines)
            continue
        kept.append(line)

    return lines[:part_start] + kept + lines[part_end:]


def update_sample_start(
    mcs_path: Path,
    part_xml_path: Path,
    *,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    if not part_xml_path.is_file():
        raise FileNotFoundError(f"Part XML not found:\n{part_xml_path}")
    if not mcs_path.is_file():
        raise FileNotFoundError(f"MCS file not found:\n{mcs_path}")

    param_names, layer_names = parse_part_xml(part_xml_path)
    original = mcs_path.read_text(encoding="utf-8")
    updated_lines = replace_prt_blocks(original.splitlines(), param_names, layer_names)
    updated_text = "\n".join(updated_lines) + ("\n" if original.endswith("\n") else "")

    if not dry_run:
        mcs_path.write_text(updated_text, encoding="utf-8")

    return param_names, layer_names


def main(argv: list[str] | None = None) -> int:
    default_mcs = _default_mcs_path()

    parser = argparse.ArgumentParser(
        description="Update sample_start.mcs from template ModelCHECK XML (part support first)",
    )
    parser.add_argument(
        "--mcs",
        type=Path,
        default=default_mcs,
        help=f"sample_start.mcs to update (default: {default_mcs})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print exact MCS lines that would be written; do not update sample_start.mcs",
    )
    args = parser.parse_args(argv)

    working_dir = _load_working_directory_from_settings()
    if not working_dir:
        parser.error(
            "Set working_directory in app_settings.json (same file the GUI uses)"
        )
        return 2

    part_xml = (Path(working_dir) / "templates" / "part_template.p.xml").resolve()

    try:
        param_names, layer_names = update_sample_start(
            args.mcs.resolve(),
            part_xml,
            dry_run=args.dry_run,
        )
    except (OSError, ET.ParseError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Working dir: {Path(working_dir).resolve()}", file=sys.stderr)
    print(f"Part XML: {part_xml}", file=sys.stderr)
    print(f"MCS: {args.mcs.resolve()}", file=sys.stderr)

    output_lines = _mcs_output_lines(param_names, layer_names)
    if args.dry_run:
        print("(dry run — sample_start.mcs not written)", file=sys.stderr)
        for line in output_lines:
            print(line)
    else:
        print(f"Updated sample_start.mcs ({len(param_names)} PRT_PARAMETER, {len(layer_names)} PRT_LAYER)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
