"""Update sample_start.mcs from ModelCHECK template XML under a working directory.

Updates ``sample_start.mcs`` from template ModelCHECK XML under ``<working_dir>\\templates\\``:
part (``part_template.p.xml``), assembly (``assembly_template.a.xml``), and drawing
(``drawing_template.d.xml``).

Insertion anchors ``! PRT_PARAMETER``, ``! PRT_LAYER``, ``! ASM_PARAMETER``,
``! ASM_LAYER``, ``! DRW_PARAMETER``, ``! DRW_LAYER``, and ``! DRW_SYMBOL`` are kept. Each block
is written as: anchor, generated lines, then a blank line after the last item. Parameters from
``PARAM_INFO``; layers from ``EXTRA_LAYERS``; drawing symbols from ``SYMBOL_INFO`` (unique ``info1``).

Usage:
    python update_sample_start_from_xml.py
    python update_sample_start_from_xml.py --dry-run

Uses working_directory from app_settings.json (same as the GUI). Sections with no matching
template XML are reset to anchor comments only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

_LAYER_SUFFIX_RE = re.compile(r"\s+\[(?:no items|\d+ items?)\]$", re.IGNORECASE)
_PRT_PARAM_MARKER_RE = re.compile(r"^!\s*PRT_PARAMETER\s*$", re.IGNORECASE)
_PRT_LAYER_MARKER_RE = re.compile(r"^!\s*PRT_LAYER\s*$", re.IGNORECASE)
_ASM_PARAM_MARKER_RE = re.compile(r"^!\s*ASM_PARAMETER\s*$", re.IGNORECASE)
_ASM_LAYER_MARKER_RE = re.compile(r"^!\s*ASM_LAYER\s*$", re.IGNORECASE)
_DRW_PARAM_MARKER_RE = re.compile(r"^!\s*DRW_PARAMETER\s*$", re.IGNORECASE)
_DRW_LAYER_MARKER_RE = re.compile(r"^!\s*DRW_LAYER\s*$", re.IGNORECASE)
_DRW_SYMBOL_MARKER_RE = re.compile(r"^!\s*DRW_SYMBOL\s*$", re.IGNORECASE)

PART_TEMPLATE_XML = "part_template.p.xml"
ASM_TEMPLATE_XML = "assembly_template.a.xml"
DRW_TEMPLATE_XML = "drawing_template.d.xml"


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


def _section_bounds(lines: list[str], start_marker: str, end_marker: str) -> tuple[int, int]:
    start = 0
    end = len(lines)
    for i, line in enumerate(lines):
        if start_marker in line:
            start = i
        if end_marker in line:
            end = i
            break
    return start, end


def _part_section_bounds(lines: list[str]) -> tuple[int, int]:
    return _section_bounds(lines, "PART MODE START", "ASSEMBLY MODE START")


def _assembly_section_bounds(lines: list[str]) -> tuple[int, int]:
    return _section_bounds(lines, "ASSEMBLY MODE START", "DRAWING INFORMATION")


def _drawing_section_bounds(lines: list[str]) -> tuple[int, int]:
    return _section_bounds(lines, "DRAWING INFORMATION", "# SHEETMETAL BEND TABLE NAME LIST")


def _is_prt_parameter_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped == "PRT_PARAMETER":
        return True
    return stripped.startswith("PRT_PARAMETER ") and not stripped.startswith("PRT_PARAMETER_")


def _is_prt_layer_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped.startswith(("PRT_LAYER_UNWANTED", "PRT_LAYER_MOVE")):
        return False
    if stripped == "PRT_LAYER":
        return True
    return stripped.startswith("PRT_LAYER ") and not stripped.startswith("PRT_LAYER_")


def _is_prt_parameter_marker(line: str) -> bool:
    return bool(_PRT_PARAM_MARKER_RE.match(line.strip()))


def _is_prt_layer_marker(line: str) -> bool:
    return bool(_PRT_LAYER_MARKER_RE.match(line.strip()))


def _is_asm_parameter_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped == "ASM_PARAMETER":
        return True
    return stripped.startswith("ASM_PARAMETER ") and not stripped.startswith("ASM_PARAMETER_")


def _is_asm_layer_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped.startswith(("ASM_LAYER_UNWANTED", "ASM_LAYER_MOVE")):
        return False
    if stripped == "ASM_LAYER":
        return True
    return stripped.startswith("ASM_LAYER ") and not stripped.startswith("ASM_LAYER_")


def _is_asm_parameter_marker(line: str) -> bool:
    return bool(_ASM_PARAM_MARKER_RE.match(line.strip()))


def _is_asm_layer_marker(line: str) -> bool:
    return bool(_ASM_LAYER_MARKER_RE.match(line.strip()))


def _is_drw_parameter_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped == "DRW_PARAMETER":
        return True
    return stripped.startswith("DRW_PARAMETER ") and not stripped.startswith("DRW_PARAMETER_")


def _is_drw_parameter_marker(line: str) -> bool:
    return bool(_DRW_PARAM_MARKER_RE.match(line.strip()))


def _is_drw_layer_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped.startswith(("DRW_LAYER_UNWANTED", "DRW_LAYER_MOVE")):
        return False
    if stripped == "DRW_LAYER":
        return True
    return stripped.startswith("DRW_LAYER ") and not stripped.startswith("DRW_LAYER_")


def _is_drw_layer_marker(line: str) -> bool:
    return bool(_DRW_LAYER_MARKER_RE.match(line.strip()))


def _is_drw_symbol_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return False
    if stripped == "DRW_SYMBOL":
        return True
    return stripped.startswith("DRW_SYMBOL ") and not stripped.startswith("DRW_SYMBOL_")


def _is_drw_symbol_marker(line: str) -> bool:
    return bool(_DRW_SYMBOL_MARKER_RE.match(line.strip()))


def _format_mcs_line(keyword: str, value: str) -> str:
    # sample_start.mcs aligns the value column at char 22 (keyword field width 21).
    return f"{keyword:<21}{value}"


def _mcs_output_lines(
    param_names: list[str],
    layer_names: list[str],
    *,
    param_keyword: str = "PRT_PARAMETER",
    layer_keyword: str = "PRT_LAYER",
) -> list[str]:
    lines = [_format_mcs_line(param_keyword, name) for name in param_names]
    if lines and layer_names:
        lines.append("")
    lines.extend(_format_mcs_line(layer_keyword, name) for name in layer_names)
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
        name = (item.findtext("info1") or "").strip()
        if name:
            values.append(name)
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


def parse_template_xml(xml_path: Path) -> tuple[list[str], list[str]]:
    root = ET.parse(xml_path).getroot()
    param_names = _unique_preserve_order(_check_items(_find_check(root, "PARAM_INFO")))
    layer_names = _unique_preserve_order(
        [_normalize_layer_name(n) for n in _check_items(_find_check(root, "EXTRA_LAYERS"))]
    )
    return param_names, layer_names


def parse_part_xml(xml_path: Path) -> tuple[list[str], list[str]]:
    return parse_template_xml(xml_path)


def parse_asm_xml(xml_path: Path) -> tuple[list[str], list[str]]:
    return parse_template_xml(xml_path)


def parse_drw_xml(xml_path: Path) -> tuple[list[str], list[str], list[str]]:
    root = ET.parse(xml_path).getroot()
    param_names = _unique_preserve_order(_check_items(_find_check(root, "PARAM_INFO")))
    layer_names = _unique_preserve_order(
        [_normalize_layer_name(n) for n in _check_items(_find_check(root, "EXTRA_LAYERS"))]
    )
    symbol_names = _unique_preserve_order(_check_items(_find_check(root, "SYMBOL_INFO")))
    return param_names, layer_names, symbol_names


PART_TEMPLATE_MODEL = "part_template.prt"
ASM_TEMPLATE_MODEL = "assembly_template.asm"
DRW_TEMPLATE_MODEL = "drawing_template.drw"

_TEMPLATE_XML_FILES = (
    ("Part template", PART_TEMPLATE_MODEL, PART_TEMPLATE_XML, "model"),
    ("Assembly template", ASM_TEMPLATE_MODEL, ASM_TEMPLATE_XML, "model"),
    ("Drawing template", DRW_TEMPLATE_MODEL, DRW_TEMPLATE_XML, "drawing"),
)

_DTM_REPORT_GROUPS: tuple[tuple[str, str], ...] = (
    ("DTM_PLANE_INFO", "Plane"),
    ("DTM_CSYS_INFO", "Coordinate system"),
    ("DTM_AXES_INFO", "Axis"),
    ("DTM_POINT_INFO", "Point"),
)


def _relation_display_items(check: ET.Element | None) -> list[str]:
    if check is None:
        return []
    values: list[str] = []
    for item in check.findall("item"):
        info1 = (item.findtext("info1") or "").strip()
        info2 = (item.findtext("info2") or "").strip()
        if info1 and "=" in info1:
            values.append(info1)
        elif info1 and info2:
            values.append(f"{info1}={info2}")
        elif info1:
            values.append(info1)
        elif info2:
            values.append(info2)
    return _unique_preserve_order(values)


def _direct_ans(check: ET.Element | None) -> str | None:
    """First direct child ``<ans>`` only (``find('ans')`` can match nested descendants)."""
    if check is None:
        return None
    for child in check:
        if child.tag == "ans":
            text = (child.text or "").strip()
            if text:
                return text
    return None


def _normalize_units_length(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    key = text.upper()
    return {"MM": "mm", "INCH": "in", "IN": "in"}.get(key, text)


def _report_category_named_items(
    root: ET.Element, check_name: str, label: str
) -> tuple[str, int, list[str]]:
    check = _find_check(root, check_name)
    names = _unique_preserve_order(_check_items(check))
    if names:
        return (label, len(names), [", ".join(names)])
    ans = _direct_ans(check)
    if ans:
        return (label, 1, [ans])
    return (label, 0, [])


def _report_category_scalar(
    root: ET.Element,
    check_name: str,
    label: str,
    *,
    normalizer: Callable[[str], str] | None = None,
) -> tuple[str, int | None, list[str]]:
    check = _find_check(root, check_name)
    ans = _direct_ans(check)
    if ans:
        text = normalizer(ans) if normalizer else ans
        return (label, None, [text])
    return (label, None, [])


def _report_category_accuracy(root: ET.Element) -> tuple[str, int | None, list[str]]:
    check = _find_check(root, "ACCURACY_INFO")
    ans = _direct_ans(check)
    if ans:
        return ("Accuracy", None, [ans])
    values = _relation_display_items(check)
    return ("Accuracy", None, [_join_report_values(values)] if values else [])


def _model_template_base_categories(
    root: ET.Element, *, include_designated_attr: bool = False
) -> list[tuple[str, int | None, list[str]]]:
    """(label, count, body lines) for part or assembly template XML."""
    datum_groups: list[tuple[str, list[str]]] = []
    datum_count = 0
    for check_name, group_label in _DTM_REPORT_GROUPS:
        names = _check_items(_find_check(root, check_name))
        if names:
            datum_groups.append((group_label, names))
            datum_count += len(names)
    datum_lines = [f"{label}: {', '.join(names)}" for label, names in datum_groups]

    views = _check_items(_find_check(root, "VIEW_INFO"))
    parameters = _check_items(_find_check(root, "PARAM_INFO"))
    layers = _unique_preserve_order(
        [_normalize_layer_name(n) for n in _check_items(_find_check(root, "EXTRA_LAYERS"))]
    )
    relations = _relation_display_items(_find_check(root, "RELATION_INFO"))
    simpreps = _check_items(_find_check(root, "SIMPREP_INFO"))

    categories: list[tuple[str, int | None, list[str]]] = [
        ("Start datums", datum_count, datum_lines),
        ("Views", len(views), [", ".join(views)] if views else []),
        (
            "Simplified representations",
            len(simpreps),
            [", ".join(simpreps)] if simpreps else [],
        ),
        ("Start parameters", len(parameters), [", ".join(parameters)] if parameters else []),
    ]
    if include_designated_attr:
        categories.append(
            _report_category_named_items(root, "DESIGNATED_ATTR", "Designated attributes")
        )
    categories.extend(
        [
            ("Start layers", len(layers), [", ".join(layers)] if layers else []),
            ("Start relations", len(relations), [_join_report_values(relations)] if relations else []),
        ]
    )
    return categories


def _part_template_report_categories(root: ET.Element) -> list[tuple[str, int | None, list[str]]]:
    categories = _model_template_base_categories(root, include_designated_attr=True)
    categories.extend(
        [
            _report_category_scalar(
                root, "UNITS_LENGTH", "Length units", normalizer=_normalize_units_length
            ),
            _report_category_accuracy(root),
        ]
    )
    return categories


def _asm_template_report_categories(root: ET.Element) -> list[tuple[str, int | None, list[str]]]:
    categories = _model_template_base_categories(root, include_designated_attr=True)
    categories.extend(
        [
            _report_category_scalar(
                root, "UNITS_LENGTH", "Length units", normalizer=_normalize_units_length
            ),
            _report_category_accuracy(root),
        ]
    )
    return categories


def _drawing_template_report_categories(root: ET.Element) -> list[tuple[str, int, list[str]]]:
    parameters = _check_items(_find_check(root, "PARAM_INFO"))
    layers = _unique_preserve_order(
        [_normalize_layer_name(n) for n in _check_items(_find_check(root, "EXTRA_LAYERS"))]
    )
    return [
        ("Start parameters", len(parameters), [", ".join(parameters)] if parameters else []),
        ("Start layers", len(layers), [", ".join(layers)] if layers else []),
        _report_category_scalar(root, "NUM_DRAW_SHEETS", "Number of sheets"),
        _report_category_named_items(root, "SHEET_SIZE_INFO", "Sheet sizes"),
        _report_category_named_items(root, "SYMBOL_INFO", "Drawing symbols"),
        _report_category_named_items(root, "NOTE_INFO", "Notes"),
    ]


def _join_report_values(values: list[str]) -> str:
    return " · ".join(values)


def collect_template_scan_report_blocks(templates_dir: Path) -> list[tuple[str, str, list[tuple[str, int, list[str]]]]]:
    """
    Return ``(title, model_filename, categories)`` for each template XML on disk.

    ``categories`` is a list of ``(label, count, body_lines)``.
    """
    blocks: list[tuple[str, str, list[tuple[str, int, list[str]]]]] = []
    if not templates_dir.is_dir():
        return blocks
    for title, model_file, xml_name, kind in _TEMPLATE_XML_FILES:
        xml_path = templates_dir / xml_name
        if not xml_path.is_file():
            continue
        try:
            root = ET.parse(xml_path).getroot()
        except (OSError, ET.ParseError):
            continue
        if kind == "drawing":
            categories = _drawing_template_report_categories(root)
        elif xml_name == PART_TEMPLATE_XML:
            categories = _part_template_report_categories(root)
        else:
            categories = _asm_template_report_categories(root)
        blocks.append((title, model_file, categories))
    return blocks


def templates_dir_has_scan_xml(templates_dir: Path) -> bool:
    if not templates_dir.is_dir():
        return False
    return any((templates_dir / xml_name).is_file() for _t, _m, xml_name, _k in _TEMPLATE_XML_FILES)


def _fallback_param_insert(part_lines: list[str]) -> int:
    last_view = -1
    for i, line in enumerate(part_lines):
        if line.strip().startswith("PRT_VIEW"):
            last_view = i
    if last_view >= 0:
        return last_view + 1
    for i, line in enumerate(part_lines):
        if "PART MODE START" in line:
            return i + 1
    return 0


def _fallback_layer_insert(part_lines: list[str]) -> int:
    for i, line in enumerate(part_lines):
        stripped = line.strip()
        if stripped.startswith(("PRT_LAYER_MOVE", "PRT_LAYER_UNWANTED", "PRT_COMMENT", "PRT_RELATION")):
            return i
    return len(part_lines)


def _fallback_asm_param_insert(asm_lines: list[str]) -> int:
    last_view = -1
    for i, line in enumerate(asm_lines):
        if line.strip().startswith("ASM_VIEW"):
            last_view = i
    if last_view >= 0:
        return last_view + 1
    for i, line in enumerate(asm_lines):
        if "ASSEMBLY MODE START" in line:
            return i + 1
    return 0


def _fallback_asm_layer_insert(asm_lines: list[str]) -> int:
    for i, line in enumerate(asm_lines):
        stripped = line.strip()
        if stripped.startswith(
            ("ASM_LAYER_MOVE", "ASM_LAYER_UNWANTED", "ASM_COMMENT", "ASM_RELATION", "ASM_TOL_TYPE")
        ):
            return i
    return len(asm_lines)


def _marker_index(part_lines: list[str], is_marker_line) -> int | None:
    for i, line in enumerate(part_lines):
        if is_marker_line(line):
            return i
    return None


def _param_block_end(part_lines: list[str], start: int) -> int:
    for i in range(start, len(part_lines)):
        line = part_lines[i]
        if _is_prt_layer_marker(line):
            return i
        if _is_prt_layer_line(line):
            return i
        stripped = line.strip()
        if stripped and not stripped.startswith("!"):
            if stripped.startswith(("PRT_LAYER_MOVE", "PRT_COMMENT", "PRT_RELATION")):
                return i
    return len(part_lines)


def _layer_block_end(part_lines: list[str], start: int) -> int:
    for i in range(start, len(part_lines)):
        line = part_lines[i]
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            return i
        if _is_prt_layer_line(line):
            continue
        return i
    return len(part_lines)


def _asm_param_block_end(asm_lines: list[str], start: int) -> int:
    for i in range(start, len(asm_lines)):
        line = asm_lines[i]
        if _is_asm_layer_marker(line):
            return i
        if _is_asm_layer_line(line):
            return i
        stripped = line.strip()
        if stripped and not stripped.startswith("!"):
            if stripped.startswith(
                (
                    "ASM_LAYER_MOVE",
                    "ASM_LAYER_UNWANTED",
                    "ASM_PARAM_",
                    "ASM_TOL_TYPE",
                    "ASM_COMMENT",
                    "ASM_RELATION",
                )
            ):
                return i
    return len(asm_lines)


def _asm_layer_block_end(asm_lines: list[str], start: int) -> int:
    for i in range(start, len(asm_lines)):
        line = asm_lines[i]
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            return i
        if _is_asm_layer_line(line):
            continue
        return i
    return len(asm_lines)


def _fallback_drw_param_insert(drw_lines: list[str]) -> int:
    for i, line in enumerate(drw_lines):
        stripped = line.strip()
        if stripped.startswith(
            ("DRW_LAYER_UNWANTED", "DRW_PARAM_UNWANTED", "DRW_LAYER_MOVE", "DRW_SYMBOL")
        ):
            return i
    return len(drw_lines)


def _fallback_drw_layer_insert(drw_lines: list[str]) -> int:
    last_height = -1
    for i, line in enumerate(drw_lines):
        if line.strip().startswith("DRW_NOTE_HEIGHT"):
            last_height = i
    if last_height >= 0:
        return last_height + 1
    for i, line in enumerate(drw_lines):
        if "DRAWING INFORMATION" in line:
            return i + 1
    return 0


def _drw_param_block_end(drw_lines: list[str], start: int) -> int:
    for i in range(start, len(drw_lines)):
        line = drw_lines[i]
        if _is_drw_layer_marker(line):
            return i
        if _is_drw_layer_line(line):
            return i
        stripped = line.strip()
        if stripped and not stripped.startswith("!"):
            if stripped.startswith(
                (
                    "DRW_LAYER_UNWANTED",
                    "DRW_PARAM_UNWANTED",
                    "DRW_PARAM_MAP",
                    "DRW_LAYER_MOVE",
                    "DRW_SYMBOL",
                    "DRW_TABLE_CELLS",
                    "DRW_NOTE_UNACC",
                    "DRW_IGNORE_SHEETS",
                )
            ):
                return i
    return len(drw_lines)


def _drw_layer_block_end(drw_lines: list[str], start: int) -> int:
    for i in range(start, len(drw_lines)):
        line = drw_lines[i]
        if _is_drw_parameter_marker(line):
            return i
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            return i
        if _is_drw_layer_line(line):
            continue
        return i
    return len(drw_lines)


def _fallback_drw_symbol_insert(drw_lines: list[str]) -> int:
    for i, line in enumerate(drw_lines):
        stripped = line.strip()
        if "DRW_TABLE_CELLS" in stripped or stripped.startswith(
            ("DRW_NOTE_UNACC", "DRW_IGNORE_SHEETS")
        ):
            return i
    return len(drw_lines)


def _drw_symbol_block_end(drw_lines: list[str], start: int) -> int:
    for i in range(start, len(drw_lines)):
        line = drw_lines[i]
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            return i
        if _is_drw_symbol_line(line):
            continue
        return i
    return len(drw_lines)


def _lines_after_anchor(new_lines: list[str]) -> list[str]:
    """Content lines immediately after anchor; blank line after the last item when non-empty."""
    if not new_lines:
        return []
    return [*new_lines, ""]


def _apply_block_update(
    part_lines: list[str],
    new_lines: list[str],
    *,
    is_content_line,
    is_marker_line,
    block_end,
    fallback_insert,
) -> list[str]:
    """Replace content after a marker, or existing lines, or at a fallback index."""
    marker_idx = _marker_index(part_lines, is_marker_line)
    if marker_idx is not None:
        start = marker_idx + 1
        end = block_end(part_lines, start)
        return part_lines[:start] + _lines_after_anchor(new_lines) + part_lines[end:]

    content_indices = [i for i, line in enumerate(part_lines) if is_content_line(line)]
    if content_indices:
        start = min(content_indices)
        end = max(content_indices) + 1
        return part_lines[:start] + new_lines + part_lines[end:]

    insert_at = fallback_insert(part_lines)
    return part_lines[:insert_at] + new_lines + part_lines[insert_at:]


def _replace_mode_blocks(
    lines: list[str],
    section_bounds,
    param_keyword: str,
    layer_keyword: str,
    *,
    is_param_line,
    is_layer_line,
    is_param_marker,
    is_layer_marker,
    param_block_end,
    layer_block_end,
    fallback_param_insert,
    fallback_layer_insert,
    param_names: list[str],
    layer_names: list[str],
) -> list[str]:
    section_start, section_end = section_bounds(lines)
    section_lines = lines[section_start:section_end]

    new_param_lines = [_format_mcs_line(param_keyword, name) for name in param_names]
    new_layer_lines = [_format_mcs_line(layer_keyword, name) for name in layer_names]

    section_lines = _apply_block_update(
        section_lines,
        new_param_lines,
        is_content_line=is_param_line,
        is_marker_line=is_param_marker,
        block_end=param_block_end,
        fallback_insert=fallback_param_insert,
    )
    section_lines = _apply_block_update(
        section_lines,
        new_layer_lines,
        is_content_line=is_layer_line,
        is_marker_line=is_layer_marker,
        block_end=layer_block_end,
        fallback_insert=fallback_layer_insert,
    )

    return lines[:section_start] + section_lines + lines[section_end:]


def replace_prt_blocks(
    lines: list[str],
    param_names: list[str],
    layer_names: list[str],
) -> list[str]:
    return _replace_mode_blocks(
        lines,
        _part_section_bounds,
        "PRT_PARAMETER",
        "PRT_LAYER",
        is_param_line=_is_prt_parameter_line,
        is_layer_line=_is_prt_layer_line,
        is_param_marker=_is_prt_parameter_marker,
        is_layer_marker=_is_prt_layer_marker,
        param_block_end=_param_block_end,
        layer_block_end=_layer_block_end,
        fallback_param_insert=_fallback_param_insert,
        fallback_layer_insert=_fallback_layer_insert,
        param_names=param_names,
        layer_names=layer_names,
    )


def replace_asm_blocks(
    lines: list[str],
    param_names: list[str],
    layer_names: list[str],
) -> list[str]:
    return _replace_mode_blocks(
        lines,
        _assembly_section_bounds,
        "ASM_PARAMETER",
        "ASM_LAYER",
        is_param_line=_is_asm_parameter_line,
        is_layer_line=_is_asm_layer_line,
        is_param_marker=_is_asm_parameter_marker,
        is_layer_marker=_is_asm_layer_marker,
        param_block_end=_asm_param_block_end,
        layer_block_end=_asm_layer_block_end,
        fallback_param_insert=_fallback_asm_param_insert,
        fallback_layer_insert=_fallback_asm_layer_insert,
        param_names=param_names,
        layer_names=layer_names,
    )


def replace_drw_blocks(
    lines: list[str],
    param_names: list[str],
    layer_names: list[str],
    symbol_names: list[str],
) -> list[str]:
    lines = _replace_mode_blocks(
        lines,
        _drawing_section_bounds,
        "DRW_PARAMETER",
        "DRW_LAYER",
        is_param_line=_is_drw_parameter_line,
        is_layer_line=_is_drw_layer_line,
        is_param_marker=_is_drw_parameter_marker,
        is_layer_marker=_is_drw_layer_marker,
        param_block_end=_drw_param_block_end,
        layer_block_end=_drw_layer_block_end,
        fallback_param_insert=_fallback_drw_param_insert,
        fallback_layer_insert=_fallback_drw_layer_insert,
        param_names=param_names,
        layer_names=layer_names,
    )
    section_start, section_end = _drawing_section_bounds(lines)
    section_lines = lines[section_start:section_end]
    new_symbol_lines = [_format_mcs_line("DRW_SYMBOL", name) for name in symbol_names]
    section_lines = _apply_block_update(
        section_lines,
        new_symbol_lines,
        is_content_line=_is_drw_symbol_line,
        is_marker_line=_is_drw_symbol_marker,
        block_end=_drw_symbol_block_end,
        fallback_insert=_fallback_drw_symbol_insert,
    )
    return lines[:section_start] + section_lines + lines[section_end:]


def _is_template_extracted_line(line: str) -> bool:
    """True for PRT/ASM/DRW parameter, layer, and symbol lines written from template XML."""
    return (
        _is_prt_parameter_line(line)
        or _is_prt_layer_line(line)
        or _is_asm_parameter_line(line)
        or _is_asm_layer_line(line)
        or _is_drw_parameter_line(line)
        or _is_drw_layer_line(line)
        or _is_drw_symbol_line(line)
    )


def _strip_template_extracted_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if not _is_template_extracted_line(line)]


def clear_sample_start_template_blocks(
    mcs_path: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Reset PRT/ASM/DRW template blocks in sample_start.mcs to anchor comments only."""
    if not mcs_path.is_file():
        raise FileNotFoundError(f"MCS file not found:\n{mcs_path}")
    original = mcs_path.read_text(encoding="utf-8")
    updated_lines = _strip_template_extracted_lines(original.splitlines())
    updated_text = "\n".join(updated_lines) + ("\n" if original.endswith("\n") else "")
    if not dry_run:
        mcs_path.write_text(updated_text, encoding="utf-8")


def update_sample_start(
    mcs_path: Path,
    *,
    part_xml_path: Path | None = None,
    asm_xml_path: Path | None = None,
    drw_xml_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str], list[str]]:
    if not mcs_path.is_file():
        raise FileNotFoundError(f"MCS file not found:\n{mcs_path}")

    if part_xml_path is not None and part_xml_path.is_file():
        part_params, part_layers = parse_part_xml(part_xml_path)
    else:
        part_params, part_layers = [], []

    if asm_xml_path is not None and asm_xml_path.is_file():
        asm_params, asm_layers = parse_asm_xml(asm_xml_path)
    else:
        asm_params, asm_layers = [], []

    if drw_xml_path is not None and drw_xml_path.is_file():
        drw_params, drw_layers, drw_symbols = parse_drw_xml(drw_xml_path)
    else:
        drw_params, drw_layers, drw_symbols = [], [], []

    original = mcs_path.read_text(encoding="utf-8")
    updated_lines = original.splitlines()
    if (
        not part_params
        and not part_layers
        and not asm_params
        and not asm_layers
        and not drw_params
        and not drw_layers
        and not drw_symbols
    ):
        updated_lines = _strip_template_extracted_lines(updated_lines)
    else:
        updated_lines = replace_prt_blocks(updated_lines, part_params, part_layers)
        updated_lines = replace_asm_blocks(updated_lines, asm_params, asm_layers)
        updated_lines = replace_drw_blocks(
            updated_lines, drw_params, drw_layers, drw_symbols
        )

    updated_text = "\n".join(updated_lines) + ("\n" if original.endswith("\n") else "")

    if not dry_run:
        mcs_path.write_text(updated_text, encoding="utf-8")

    return part_params, part_layers, asm_params, asm_layers, drw_params, drw_layers, drw_symbols


def main(argv: list[str] | None = None) -> int:
    default_mcs = _default_mcs_path()

    parser = argparse.ArgumentParser(
        description="Update sample_start.mcs from template ModelCHECK XML (part, assembly, drawing)",
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

    templates_dir = Path(working_dir) / "templates"
    part_xml = (templates_dir / PART_TEMPLATE_XML).resolve()
    asm_xml = (templates_dir / ASM_TEMPLATE_XML).resolve()
    drw_xml = (templates_dir / DRW_TEMPLATE_XML).resolve()
    part_path = part_xml if part_xml.is_file() else None
    asm_path = asm_xml if asm_xml.is_file() else None
    drw_path = drw_xml if drw_xml.is_file() else None
    try:
        (
            part_params,
            part_layers,
            asm_params,
            asm_layers,
            drw_params,
            drw_layers,
            drw_symbols,
        ) = update_sample_start(
            args.mcs.resolve(),
            part_xml_path=part_path,
            asm_xml_path=asm_path,
            drw_xml_path=drw_path,
            dry_run=args.dry_run,
        )
    except (OSError, ET.ParseError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Working dir: {Path(working_dir).resolve()}", file=sys.stderr)
    if part_path:
        print(f"Part XML: {part_path}", file=sys.stderr)
    if asm_path:
        print(f"Assembly XML: {asm_path}", file=sys.stderr)
    if drw_path:
        print(f"Drawing XML: {drw_path}", file=sys.stderr)
    print(f"MCS: {args.mcs.resolve()}", file=sys.stderr)

    if args.dry_run:
        print("(dry run — sample_start.mcs not written)", file=sys.stderr)
        if part_path:
            for line in _mcs_output_lines(part_params, part_layers):
                print(line)
        if asm_path:
            for line in _mcs_output_lines(
                asm_params,
                asm_layers,
                param_keyword="ASM_PARAMETER",
                layer_keyword="ASM_LAYER",
            ):
                print(line)
        if drw_path:
            for line in _mcs_output_lines(
                drw_params,
                drw_layers,
                param_keyword="DRW_PARAMETER",
                layer_keyword="DRW_LAYER",
            ):
                print(line)
            for name in drw_symbols:
                print(_format_mcs_line("DRW_SYMBOL", name))
    else:
        if not part_path and not asm_path and not drw_path:
            print(
                "Cleared template blocks in sample_start.mcs (anchors only; no template XML)",
                file=sys.stderr,
            )
        else:
            parts: list[str] = []
            if part_path:
                parts.append(f"{len(part_params)} PRT_PARAMETER, {len(part_layers)} PRT_LAYER")
            if asm_path:
                parts.append(f"{len(asm_params)} ASM_PARAMETER, {len(asm_layers)} ASM_LAYER")
            if drw_path:
                parts.append(
                    f"{len(drw_params)} DRW_PARAMETER, {len(drw_layers)} DRW_LAYER, "
                    f"{len(drw_symbols)} DRW_SYMBOL"
                )
            print(f"Updated sample_start.mcs ({'; '.join(parts)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
