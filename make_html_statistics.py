"""

Compile batch-level engineering statistics from master.xml and write a preview HTML page.



Usage (like make_html_summary preview):



    python make_html_statistics.py



Uses working_directory from app_settings.json (same as the GUI). Reads

<working_dir>\\master.xml and writes <working_dir>\\statistics.html.

"""

from __future__ import annotations



import glob

import html

import json

import os

import re

import sys

import xml.etree.ElementTree as ET

from dataclasses import dataclass, field

from datetime import datetime

from pathlib import Path

from typing import Any, Callable
from urllib.parse import quote

from make_html_summary import _model_check_category_map

from update_start_from_xml import collect_template_scan_report_blocks








def _app_dir() -> Path:
    """Sidecar files live beside main.exe (dev: beside this script), not under PyInstaller _MEI temp."""
    if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent





def _app_settings_path() -> Path:

    return _app_dir() / "app_settings.json"





def load_working_directory_from_settings() -> str | None:

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


SCAN_PARTS_DEFAULT = True
SCAN_ASSEMBLIES_DEFAULT = True
SCAN_DRAWINGS_DEFAULT = True


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


def load_scan_type_flags_from_settings() -> tuple[bool, bool, bool]:
    """Read scan_parts / scan_assemblies / scan_drawings from app_settings.json."""
    settings_path = _app_settings_path()
    if not settings_path.is_file():
        return (SCAN_PARTS_DEFAULT, SCAN_ASSEMBLIES_DEFAULT, SCAN_DRAWINGS_DEFAULT)
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (SCAN_PARTS_DEFAULT, SCAN_ASSEMBLIES_DEFAULT, SCAN_DRAWINGS_DEFAULT)
    if not isinstance(data, dict):
        return (SCAN_PARTS_DEFAULT, SCAN_ASSEMBLIES_DEFAULT, SCAN_DRAWINGS_DEFAULT)
    scan_parts = _normalize_scan_type_flag(
        data.get("scan_parts"), default=SCAN_PARTS_DEFAULT
    )
    scan_assemblies = _normalize_scan_type_flag(
        data.get("scan_assemblies"), default=SCAN_ASSEMBLIES_DEFAULT
    )
    scan_drawings = _normalize_scan_type_flag(
        data.get("scan_drawings"), default=SCAN_DRAWINGS_DEFAULT
    )
    if not (scan_parts or scan_assemblies or scan_drawings):
        return (SCAN_PARTS_DEFAULT, SCAN_ASSEMBLIES_DEFAULT, SCAN_DRAWINGS_DEFAULT)
    return scan_parts, scan_assemblies, scan_drawings


def _model_type_in_scan_scope(
    display: str,
    *,
    scan_parts: bool,
    scan_assemblies: bool,
    scan_drawings: bool,
) -> bool:
    """True when this model's extension is enabled in Scan settings."""
    m = re.match(r"^.+\.(prt|asm|drw)$", (display or "").strip(), re.IGNORECASE)
    if not m:
        return True
    ext = m.group(1).lower()
    if ext == "prt":
        return scan_parts
    if ext == "asm":
        return scan_assemblies
    return scan_drawings


def _resolved_scan_type_flags(
    *,
    scan_parts: bool | None = None,
    scan_assemblies: bool | None = None,
    scan_drawings: bool | None = None,
) -> tuple[bool, bool, bool]:
    from_settings = load_scan_type_flags_from_settings()
    return (
        from_settings[0] if scan_parts is None else scan_parts,
        from_settings[1] if scan_assemblies is None else scan_assemblies,
        from_settings[2] if scan_drawings is None else scan_drawings,
    )



def _check_hidden_from_report(check_el: ET.Element) -> bool:

    hide = check_el.find("hideFromReport")

    return hide is not None and (hide.text or "").strip() == "Y"





def _file_report_check_stats(file_element: ET.Element) -> list[str]:

    stats: list[str] = []

    for check in file_element.findall(".//check"):

        if _check_hidden_from_report(check):

            continue

        stat_el = check.find("stat")

        stat = stat_el.text if stat_el is not None else ""

        if stat == "INFO":

            continue

        stats.append(stat)

    return stats





def _file_in_report_scan(file_element: ET.Element) -> bool:

    return bool(_file_report_check_stats(file_element))


def _report_scanned_file_elements(master_root: ET.Element) -> list[ET.Element]:
    """``File`` entries included in the report (same set as Family table detail)."""
    return [
        file_element
        for file_element in master_root.findall("File")
        if _file_in_report_scan(file_element)
    ]





def _parse_positive_ans(check_el: ET.Element) -> bool:

    ans_el = check_el.find("ans")

    if ans_el is None or not (ans_el.text or "").strip():

        return False

    text = ans_el.text.strip()

    try:

        return float(text) > 0

    except ValueError:

        return False





def _parse_mb(file_size_text: str) -> float | None:

    t = (file_size_text or "").strip()

    if t.lower().endswith(" mb"):

        try:

            return float(t[:-3].strip())

        except ValueError:

            return None

    return None





def _find_check(file_element: ET.Element, name: str) -> ET.Element | None:

    for check in file_element.findall(".//check"):

        if (check.get("name") or "") == name:

            return check

    return None





def _model_display_lower(model: str) -> str:

    base, ext = os.path.splitext((model or "").strip())

    if ext:

        return base.lower() + ext.lower()

    return (model or "").strip().lower()


def _is_skeleton_name(name: str) -> bool:
    """True when the name contains ``_SKEL`` (case-insensitive), e.g. ``name_skel.prt`` or ``DRAWER_SKEL``."""
    return "_skel" in (name or "").casefold()


def _skeleton_identity_key(name: str) -> str:
    """Casefold key for deduplicating skeleton models and family-table instance labels."""
    label = (name or "").strip()
    if "|" in label:
        label = label.split("|")[-1].strip()
    if re.search(r"\.(prt|asm|drw)$", label, re.IGNORECASE):
        return _model_display_lower(label)
    return label.casefold()


def _family_skel_instance_names(file_element: ET.Element) -> list[str]:
    """``_SKEL`` instance labels from a generic model's ``FAMILY_INFO`` table."""
    family = _find_check(file_element, "FAMILY_INFO")
    if family is None:
        return []
    ans = (family.findtext("ans") or "").strip().upper()
    if "GENERIC" not in ans:
        return []
    names: list[str] = []
    for item in family.findall("item"):
        name = (item.findtext("info1") or "").strip()
        if name and _is_skeleton_name(name):
            names.append(name)
    return names


def scan_skeleton_model_count(master_root: ET.Element) -> int:
    """
    Count skeleton models in the full batch (all ``File`` entries).

    Uses ``_SKEL`` in the model name or family-table instance name. When a generic
    lists ``_SKEL`` instances, those instances are counted and the generic itself
    is not double-counted (e.g. 8 instances + 1 other skeleton file = 9).
    """
    keys: set[str] = set()
    for file_element in master_root.findall("File"):
        model = (file_element.findtext("Model") or "").strip()
        skel_instances = _family_skel_instance_names(file_element)
        for name in skel_instances:
            keys.add(_skeleton_identity_key(name))
        if _is_skeleton_name(model) and not skel_instances:
            keys.add(_skeleton_identity_key(model))
    return len(keys)


_CREO_MODEL_FILE_RE = re.compile(
    r"^(?P<base>.+)\.(?P<ext>prt|asm|drw)(?:\.(?P<ver>\d+))?$",
    re.IGNORECASE,
)

_CHECK_XML_BASENAME_RE = re.compile(r"^(?P<stem>.+)\.(?P<kind>p|a|d)\.xml$", re.IGNORECASE)

_CHECK_XML_KIND_TO_EXT = {"p": "prt", "a": "asm", "d": "drw"}


def _logical_model_display_from_filename(filename: str) -> str | None:
    """Map a top-level Creo model filename to a lowercase display name (``drawer.prt``)."""
    m = _CREO_MODEL_FILE_RE.match((filename or "").strip())
    if not m:
        return None
    return f"{m.group('base').lower()}.{m.group('ext').lower()}"


def _check_xml_basename_for_display(display: str) -> str | None:
    """``drawer.prt`` → ``drawer.p.xml`` (stem casing from display base)."""
    m = re.match(r"^(?P<base>.+)\.(prt|asm|drw)$", (display or "").strip(), re.IGNORECASE)
    if not m:
        return None
    ext = m.group(2).lower()
    return f"{m.group('base')}.{ext[0]}.xml"


def _display_from_check_xml_basename(basename: str) -> str | None:
    """``drawer.p.xml`` → ``drawer.prt``."""
    m = _CHECK_XML_BASENAME_RE.match((basename or "").strip())
    if not m:
        return None
    kind = m.group("kind").lower()
    ext = _CHECK_XML_KIND_TO_EXT.get(kind)
    if not ext:
        return None
    return f"{m.group('stem').lower()}.{ext}"


def _pick_latest_rev_filename(filenames: list[str]) -> str:
    """Choose the highest numbered rev for one logical model (same rules as GO batch)."""
    if len(filenames) == 1:
        return filenames[0]
    if all(re.match(r".*\.\d+$", name) is None for name in filenames):
        return filenames[0]
    return max(
        filenames,
        key=lambda name: int(name.split(".")[-1]) if re.match(r".*\.\d+$", name) else 0,
    )


def _latest_logical_models_on_disk(working_dir: str) -> dict[str, str]:
    """
    One ``name.ext`` entry per top-level Creo model, using only the latest numbered rev.
    """
    by_logical: dict[str, list[str]] = {}
    try:
        entries = os.listdir(working_dir)
    except OSError:
        return {}
    for name in entries:
        if not os.path.isfile(os.path.join(working_dir, name)):
            continue
        display = _logical_model_display_from_filename(name)
        if not display:
            continue
        logical_key = re.sub(r"\.\d+$", "", name)
        by_logical.setdefault(logical_key.casefold(), []).append(name)

    models: dict[str, str] = {}
    for filenames in by_logical.values():
        latest_name = _pick_latest_rev_filename(filenames)
        display = _logical_model_display_from_filename(latest_name)
        if display:
            models[display.casefold()] = display
    return models


def _check_xml_basenames_in_folder(working_dir: str) -> set[str]:
    basenames: set[str] = set()
    for pattern in ("**/*.p.xml", "**/*.a.xml", "**/*.d.xml"):
        for path in glob.glob(os.path.join(working_dir, pattern), recursive=True):
            basenames.add(os.path.basename(path).casefold())
    return basenames


def _scanned_model_keys(master_root: ET.Element) -> set[str]:
    """Casefolded ``Model`` names from every ``File`` entry in ``master.xml``."""
    keys: set[str] = set()
    for el in master_root.findall("File"):
        model = (el.findtext("Model") or "").strip()
        if model:
            keys.add(model.casefold())
    return keys


def scan_skipped_models(
    working_dir: str,
    master_root: ET.Element,
    *,
    scan_parts: bool | None = None,
    scan_assemblies: bool | None = None,
    scan_drawings: bool | None = None,
) -> list[str]:
    """
    Models in the working folder that did not fully make it into the batch scan.

    Compares latest-rev top-level ``name.ext`` models with matching check XML and
    ``master.xml`` entries. Family-table instances may have check XML but no separate
    ``.prt`` / ``.asm`` on disk; any model listed in ``master.xml`` was scanned and
    is not reported as skipped.

    Model types turned off in Scan settings are omitted (not listed as failed).
    """
    scan_parts, scan_assemblies, scan_drawings = _resolved_scan_type_flags(
        scan_parts=scan_parts,
        scan_assemblies=scan_assemblies,
        scan_drawings=scan_drawings,
    )
    wd = os.path.normpath(os.path.abspath(working_dir))
    scanned = _scanned_model_keys(master_root)
    xml_on_disk = _check_xml_basenames_in_folder(wd)
    models_on_disk = _latest_logical_models_on_disk(wd)

    skipped: dict[str, str] = {}

    for display_cf in sorted(models_on_disk.keys(), key=lambda k: models_on_disk[k].casefold()):
        display = models_on_disk[display_cf]
        if not _model_type_in_scan_scope(
            display,
            scan_parts=scan_parts,
            scan_assemblies=scan_assemblies,
            scan_drawings=scan_drawings,
        ):
            continue
        xml_base = _check_xml_basename_for_display(display)
        if not xml_base:
            continue
        if xml_base.casefold() not in xml_on_disk:
            skipped[display_cf] = display
            continue
        if display_cf not in scanned:
            skipped[display_cf] = display

    for pattern in ("**/*.p.xml", "**/*.a.xml", "**/*.d.xml"):
        for path in glob.glob(os.path.join(wd, pattern), recursive=True):
            basename = os.path.basename(path)
            display = _display_from_check_xml_basename(basename)
            if not display:
                continue
            if not _model_type_in_scan_scope(
                display,
                scan_parts=scan_parts,
                scan_assemblies=scan_assemblies,
                scan_drawings=scan_drawings,
            ):
                continue
            display_cf = display.casefold()
            if display_cf in skipped or display_cf in scanned:
                continue
            if display_cf not in models_on_disk:
                skipped[display_cf] = display

    return [skipped[k] for k in sorted(skipped.keys(), key=lambda k: skipped[k].casefold())]





def _unq_asm_children(file_element: ET.Element) -> list[str]:

    check = _find_check(file_element, "UNQ_COMPONENTS")

    if check is None:

        return []

    children: list[str] = []

    for item in check.findall("item"):

        info1 = (item.findtext("info1") or "").strip()

        if info1.upper().endswith(".ASM"):

            children.append(info1)

    return children





def _asm_subtree_assembly_count(graph: dict[str, list[str]], start_key: str) -> int:
    """Unique .ASM models in the UNQ_COMPONENTS tree below ``start_key`` (includes root)."""
    seen: set[str] = set()

    def dfs(key: str) -> None:
        k = key.upper()
        if k in seen or not k.endswith(".ASM"):
            return
        seen.add(k)
        for child in graph.get(k, []):
            dfs(child)

    dfs(start_key)
    return len(seen)


def _find_file_element_by_model(
    master_root: ET.Element,
    model_name: str,
) -> ET.Element | None:
    """Return the ``File`` element whose ``Model`` matches ``model_name`` (basename, casefold)."""
    want = os.path.basename((model_name or "").strip()).casefold()
    if not want:
        return None
    for file_element in master_root.findall("File"):
        model = (file_element.findtext("Model") or "").strip()
        if os.path.basename(model).casefold() == want:
            return file_element
    return None


def _top_level_assembly_feature_total(
    master_root: ET.Element,
    top_assembly: str,
) -> int | None:
    """
    Component features in the top-level product (each part/sub-assembly occurrence).

    Uses ``NUM_COMPONENTS`` on the top assembly (Creo total parts and sub-assemblies).
    Falls back to ``ASM_BOM`` line count excluding the root assembly row.
    """
    top_file = _find_file_element_by_model(master_root, top_assembly)
    if top_file is None:
        return None
    n = _parse_int_metric(_check_ans_text(top_file, "NUM_COMPONENTS"))
    if n is not None:
        return n
    check = _find_check(top_file, "ASM_BOM")
    if check is None:
        return None
    top_key = os.path.basename(top_assembly.strip()).casefold()
    count = 0
    for item in check.findall("item"):
        name = (item.findtext("info1") or "").strip()
        if not name:
            continue
        if os.path.basename(name).casefold() == top_key:
            continue
        count += 1
    return count if count else None


def find_top_level_assembly(master_root: ET.Element) -> str | None:

    """

    Assembly with no other batch assembly referencing it as a sub-assembly (UNQ_COMPONENTS).

    Tie-break multiple roots by the highest count of .ASM models in that assembly's subtree.

    """

    assemblies: dict[str, str] = {}

    asm_graph: dict[str, list[str]] = {}

    referenced: set[str] = set()



    for file_element in master_root.findall("File"):

        if (file_element.findtext("ProType") or "").strip().upper() != "ASM":

            continue

        model = (file_element.findtext("Model") or "").strip()

        if not model:

            continue

        key = model.upper()

        assemblies[key] = model

        asm_children = _unq_asm_children(file_element)

        asm_graph[key] = [child.upper() for child in asm_children]

        for child in asm_children:

            referenced.add(child.upper())



    if not assemblies:

        return None



    roots = [assemblies[k] for k in assemblies if k not in referenced]

    if len(roots) == 1:

        return roots[0]

    if len(roots) > 1:

        return max(roots, key=lambda m: _asm_subtree_assembly_count(asm_graph, m))

    return None


# --- Performance report table (Creo Performance Report–style batch metrics) ---

PERFORMANCE_REPORT_ISSUE_ROW_CHECKS: dict[str, str] = {
    "_FLEXIBLE_COMPONENTS": "FLEX_COMPONENTS",
    "_PACKAGED_COMPONENTS": "PACK_COMPONENTS",
    "_MECH_COMPONENTS": "MECH_COMPONENTS",
}

PERFORMANCE_TABLE_SECTIONS: list[tuple[str, list[tuple[str, str | None]]]] = [
    (
        "Scan Summary",
        [
            ("Scan date", "_SCAN_DATE"),
            ("Model checks", "_MODEL_CHECKS"),
            ("Working directory", "_WORKING_DIRECTORY"),
            ("Scan duration", "_SCAN_DURATION"),
            ("Total size of scanned models", "_TOTAL_SCANNED_SIZE"),
        ],
    ),
    (
        "Dataset Overview",
        [
            ("Models scanned", "_FILES_SCANNED"),
            ("Duplicate models", "_DUPLICATE_MODELS"),
            ("Parts", "_PART_COUNT"),
            ("Assemblies", "_ASSEMBLY_COUNT"),
            ("Drawings", "_DRAWING_COUNT"),
        ],
    ),
    (
        "Model Type Breakdown",
        [
            ("Sheet metal parts", "_SHEETMETAL_PARTS"),
            ("Multibody parts", "_MULTIBODY_PARTS"),
            ("Skeleton parts", "_SKELETON_MODELS"),
            ("Bulk parts", "_BULK_PARTS"),
            ("Non solid parts", "_NON_SOLID_PARTS"),
        ],
    ),
    (
        "Assembly Structure",
        [
            ("Total components in all assemblies", "NUM_COMPONENTS"),
            ("Number of unique components", "UNQ_COMPONENTS"),
            ("Number of components in master representation", "_MASTER_REP_COUNT"),
            ("Maximum assembly depth", "_MAX_ASSEMBLY_DEPTH"),
        ],
    ),
    (
        "Assembly State / Placement Health",
        [
            ("Total number of suppressed components", "_SUPPRESSED_COMPONENTS"),
            ("Number of packaged components", "_PACKAGED_COMPONENTS"),
            ("Total number of fixed components", "_FIXED_COMPONENTS"),
            ("Number of flexible components", "_FLEXIBLE_COMPONENTS"),
        ],
    ),
    (
        "Representations and Advanced Assembly Usage",
        [
            ("Number of created simplified representations", "_SIMPREP_REPRESENTATIONS"),
            ("Number of mechanism components", "_MECH_COMPONENTS"),
        ],
    ),
    (
        "Family Table Usage",
        [
            ("Number of family table generics", "_FAMILY_GENERIC_PART_COUNT"),
            ("Number of family table instances", "_FAMILY_INSTANCE_COUNT"),
        ],
    ),
    ("Metadata", [("Last saved by", "_USERS")]),
    (
        "Notable Model Findings",
        [("Total number of features in top level assembly", "_TOP_LEVEL_FEATURES")],
    ),
]


@dataclass
class PerformanceMetrics:
    family_generic_part_count: int = 0
    family_instance_count: int = 0
    total_num_components: int = 0
    unique_model_count: int = 0
    max_assembly_depth: int = 0
    master_rep_component_count: int = 0
    report_issue_counts: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in PERFORMANCE_REPORT_ISSUE_ROW_CHECKS}
    )
    simprep_unique_count: int = 0
    sheetmetal_parts: int = 0
    multibody_parts: int = 0
    skeleton_models: int = 0
    duplicate_models: int = 0
    bulk_parts: int = 0
    non_solid_parts: int = 0
    fixed_components: int = 0
    suppressed_components: int = 0
    files_seen: int = 0
    files_scanned: int = 0
    part_count: int = 0
    assembly_count: int = 0
    drawing_count: int = 0
    scan_date: str = ""
    model_checks_mch: str = ""
    working_directory: str = ""
    scan_duration: str = ""
    users: list[str] = field(default_factory=list)
    total_scanned_bytes: int = 0
    top_level_assembly_name: str = ""
    top_level_assembly_features: int | None = None


def _parse_int_metric(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _check_ans_text(file_element: ET.Element, check_name: str) -> str | None:
    check = _find_check(file_element, check_name)
    if check is None:
        return None
    text = (check.findtext("ans") or "").strip()
    if text:
        return text
    items = check.findall("item")
    if items:
        return str(len(items))
    return None


def _check_stat_text(check: ET.Element) -> str:
    stat_el = check.find("stat")
    return (stat_el.text if stat_el is not None else "").strip().upper()


def _counts_as_report_issue(file_element: ET.Element, check_name: str) -> int:
    """1 when this model has the check as ERROR/WARNING (errors/warnings report sections)."""
    check = _find_check(file_element, check_name)
    if check is None or _check_hidden_from_report(check):
        return 0
    if _check_stat_text(check) in ("ERROR", "WARNING"):
        return 1
    return 0


def _bulk_item_names(file_element: ET.Element) -> list[str]:
    """Unique BULK_ITEMS ``info1`` model names from one report-visible check."""
    check = _find_check(file_element, "BULK_ITEMS")
    if check is None or _check_hidden_from_report(check):
        return []
    if _check_stat_text(check) not in ("ERROR", "WARNING"):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for item in check.findall("item"):
        name = (item.findtext("info1") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _unq_model_names_from(file_element: ET.Element) -> list[str]:
    check = _find_check(file_element, "UNQ_COMPONENTS")
    if check is None:
        return []
    return [
        (item.findtext("info1") or "").strip()
        for item in check.findall("item")
        if (item.findtext("info1") or "").strip()
    ]


def _assembly_name_key(model: str, path: str) -> str:
    if path:
        return os.path.basename(path).casefold()
    name = (model or "").strip()
    if name and not os.path.splitext(name)[1]:
        return f"{name}.asm".casefold()
    return name.casefold()


def _max_subasm_depth(graph: dict[str, list[str]], start_key: str) -> int:
    cache: dict[str, int] = {}

    def dfs(key: str, visiting: set[str]) -> int:
        if key in cache:
            return cache[key]
        asm_children = [c for c in graph.get(key, []) if c.endswith(".asm")]
        if not asm_children:
            cache[key] = 0
            return 0
        best = 0
        for child in asm_children:
            if child in visiting:
                continue
            visiting.add(child)
            best = max(best, 1 + dfs(child, visiting))
            visiting.remove(child)
        cache[key] = best
        return best

    return dfs(start_key.casefold(), set())


def _batch_max_assembly_depth(asm_subassemblies: dict[str, list[str]]) -> int:
    if not asm_subassemblies:
        return 0
    return max(_max_subasm_depth(asm_subassemblies, key) for key in asm_subassemblies)


def _master_rep_count_from_element(file_element: ET.Element) -> int:
    simp = (_check_ans_text(file_element, "SIMPREP_MASTER") or "").upper()
    num = _parse_int_metric(_check_ans_text(file_element, "NUM_COMPONENTS"))
    if simp in ("YES", "Y", "TRUE", "1") and num is not None:
        return num
    return 0


def _simprep_names_from(file_element: ET.Element) -> list[str]:
    check = _find_check(file_element, "SIMPREP_INFO")
    if check is None:
        return []
    return [
        (item.findtext("info1") or "").strip()
        for item in check.findall("item")
        if (item.findtext("info1") or "").strip()
    ]


def _is_multibody_part(file_element: ET.Element) -> bool:
    mb = _find_check(file_element, "MULTIBODY_MODEL")
    if mb is None:
        return False
    ans = (mb.findtext("ans") or "").strip().upper()
    return ans in ("YES", "Y", "TRUE", "1") or _parse_positive_ans(mb)


def _is_sheetmetal_part(file_element: ET.Element) -> bool:
    return _find_check(file_element, "SHTMTL_THICK") is not None


def _body_info_item_state(info2: str) -> str | None:
    """``BODY_INFO`` ``info2`` tail after ``:`` is ``Type/State/Construction``."""
    text = (info2 or "").strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    parts = [part.strip() for part in text.split("/")]
    if len(parts) < 2:
        return None
    return parts[1]


def _is_non_solid_part(file_element: ET.Element) -> bool:
    """True when every ``BODY_INFO`` body row has State ``No Geometry``."""
    check = _find_check(file_element, "BODY_INFO")
    if check is None or _check_hidden_from_report(check):
        return False
    items = check.findall("item")
    if not items:
        return False
    for item in items:
        state = _body_info_item_state(item.findtext("info2") or "")
        if not state or state.casefold() != "no geometry":
            return False
    return True


def _file_size_bytes_from_element(file_element: ET.Element) -> int | None:
    """``FILE_SIZE`` check ``<ans>`` is size in bytes when it is all digits."""
    check = _find_check(file_element, "FILE_SIZE")
    if check is None:
        return None
    for child in check:
        if child.tag == "ans":
            text = (child.text or "").strip()
            if text.isdigit():
                return int(text)
            return None
    return None


def _format_total_scanned_size(total_bytes: int) -> str:
    """e.g. ``842.37 MB`` or ``1.24 GB`` (1024-based)."""
    if total_bytes <= 0:
        return "—"
    mb = total_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.2f} MB"


def _username_from_last_saved(last_saved: str) -> str | None:
    """Username is the text before `` -`` in ``LastSaved``.

    Handles ``MBOURQUE - Pro/E v. …`` and truncated values like ``JERRY.L.TAYLOR -``.
    """
    text = (last_saved or "").strip()
    if not text:
        return None
    if " -" in text:
        user = text.split(" -", 1)[0].strip()
    else:
        user = text
    return user or None


def scan_performance_metrics(master_root: ET.Element) -> PerformanceMetrics:
    """Batch-wide performance table metrics from every ``File`` entry in master.xml."""
    metrics = PerformanceMetrics()
    unique_models: set[str] = set()
    simprep_names: set[str] = set()
    skeleton_keys: set[str] = set()
    bulk_part_keys: set[str] = set()
    asm_subassemblies: dict[str, list[str]] = {}
    users: list[str] = []
    users_seen: set[str] = set()

    for file_element in master_root.findall("File"):
        metrics.files_seen += 1
        model = (file_element.findtext("Model") or "").strip()
        path = (file_element.findtext("Path") or "").strip()
        pro_type = (file_element.findtext("ProType") or "").strip().upper()
        if _file_in_report_scan(file_element):
            metrics.files_scanned += 1

        user = _username_from_last_saved(file_element.findtext("LastSaved") or "")
        if user:
            key = user.casefold()
            if key not in users_seen:
                users_seen.add(key)
                users.append(user)

        metrics.duplicate_models += _counts_as_report_issue(file_element, "DUPLICATE_MODELS")
        for bulk_name in _bulk_item_names(file_element):
            bulk_part_keys.add(bulk_name.casefold())
        metrics.fixed_components += _parse_int_metric(_check_ans_text(file_element, "FIXED_COMPONENTS")) or 0
        metrics.suppressed_components += _parse_int_metric(_check_ans_text(file_element, "SUP_COMPONENTS")) or 0

        for unq_name in _unq_model_names_from(file_element):
            unique_models.add(unq_name.casefold())

        for simp_name in _simprep_names_from(file_element):
            simprep_names.add(simp_name.casefold())

        skel_instances = _family_skel_instance_names(file_element)
        for skel_name in skel_instances:
            skeleton_keys.add(_skeleton_identity_key(skel_name))
        if _is_skeleton_name(model) and not skel_instances:
            skeleton_keys.add(_skeleton_identity_key(model))

        if pro_type in ("PRT", "ASM", "DRW"):
            size_bytes = _file_size_bytes_from_element(file_element)
            if size_bytes is not None:
                metrics.total_scanned_bytes += size_bytes

        if pro_type == "PRT":
            metrics.part_count += 1
            if _is_sheetmetal_part(file_element):
                metrics.sheetmetal_parts += 1
            if _is_multibody_part(file_element):
                metrics.multibody_parts += 1
            if _is_non_solid_part(file_element):
                metrics.non_solid_parts += 1
        elif pro_type == "ASM":
            metrics.assembly_count += 1
            metrics.total_num_components += _parse_int_metric(_check_ans_text(file_element, "NUM_COMPONENTS")) or 0
            metrics.master_rep_component_count += _master_rep_count_from_element(file_element)
            for row_key, check_name in PERFORMANCE_REPORT_ISSUE_ROW_CHECKS.items():
                metrics.report_issue_counts[row_key] += _counts_as_report_issue(file_element, check_name)
            asm_children = _unq_asm_children(file_element)
            asm_subassemblies[_assembly_name_key(model, path)] = [
                child.casefold() for child in asm_children
            ]
        elif pro_type == "DRW":
            metrics.drawing_count += 1

    metrics.unique_model_count = len(unique_models)
    metrics.max_assembly_depth = _batch_max_assembly_depth(asm_subassemblies)
    metrics.simprep_unique_count = len(simprep_names)
    metrics.skeleton_models = len(skeleton_keys)
    metrics.bulk_parts = len(bulk_part_keys)
    family_generics = collect_family_generics_detail(
        master_root,
        file_elements=_report_scanned_file_elements(master_root),
    )
    metrics.family_generic_part_count = len(family_generics)
    metrics.family_instance_count = sum(len(row.instance_names) for row in family_generics)
    metrics.users = users

    top_asm = find_top_level_assembly(master_root)
    if top_asm:
        metrics.top_level_assembly_name = top_asm
        metrics.top_level_assembly_features = _top_level_assembly_feature_total(
            master_root, top_asm
        )

    return metrics


def _format_scan_date(dt: datetime) -> str:
    """e.g. Thursday July 3, 2026 8:15am"""
    hour12 = dt.hour % 12 or 12
    ampm = "am" if dt.hour < 12 else "pm"
    return f"{dt.strftime('%A %B')} {dt.day}, {dt.year} {hour12}:{dt.minute:02d}{ampm}"


def _format_scan_duration(seconds: float) -> str:
    """e.g. 8hrs 23min, 45min, 12sec."""
    total = max(0, int(round(seconds)))
    if total < 60:
        return "1sec" if total <= 1 else f"{total}sec"
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours >= 1:
        hr = "1hr" if hours == 1 else f"{hours}hrs"
        if minutes:
            return f"{hr} {minutes}min"
        return hr
    return "1min" if minutes == 1 else f"{minutes}min"


def _scan_date_for_report(master_path: str = "") -> str:
    """Prefer master.xml write time (scan merge); otherwise report build time."""
    dt: datetime | None = None
    if master_path:
        try:
            path = Path(master_path)
            if path.is_file():
                dt = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            pass
    if dt is None:
        dt = datetime.now()
    return _format_scan_date(dt)


def _scan_duration_from_modelcheck_xml(working_dir: str) -> str:
    """Span from earliest to latest top-level ModelCHECK ``*.p/a/d.xml`` write time.

    One ``scandir`` of the working folder: non-XML names are skipped without ``stat``;
    only matching XML files contribute min/max mtime (not a full 31k-file inventory).
    """
    if not working_dir:
        return ""
    try:
        root = Path(working_dir).expanduser()
        if not root.is_dir():
            return ""
    except OSError:
        return ""
    earliest: float | None = None
    latest: float | None = None
    count = 0
    try:
        with os.scandir(root) as it:
            for entry in it:
                low = entry.name.lower()
                if not (
                    low.endswith(".p.xml")
                    or low.endswith(".a.xml")
                    or low.endswith(".d.xml")
                ):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    mtime = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                count += 1
                if earliest is None or mtime < earliest:
                    earliest = mtime
                if latest is None or mtime > latest:
                    latest = mtime
    except OSError:
        return ""
    if count < 2 or earliest is None or latest is None:
        return ""
    span = latest - earliest
    if span < 1:
        return ""
    return _format_scan_duration(span)


def _model_checks_mch_from_condition_mcc() -> str:
    """``.mch`` basename currently set in ``config\\condition.mcc`` (Settings → Checks…)."""
    path = _app_dir() / "config" / "condition.mcc"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = re.search(r"\(([^()\s]+\.mch)\)", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1)


def performance_metrics_answers(metrics: PerformanceMetrics) -> dict[str, str]:
    answers: dict[str, str] = {
        "_SCAN_DATE": metrics.scan_date or "—",
        "_MODEL_CHECKS": metrics.model_checks_mch or "—",
        "_WORKING_DIRECTORY": metrics.working_directory or "—",
        "_SCAN_DURATION": metrics.scan_duration or "—",
        "_USERS": ", ".join(metrics.users) if metrics.users else "—",
        "_FILES_SCANNED": str(metrics.files_scanned),
        "_PART_COUNT": str(metrics.part_count),
        "_ASSEMBLY_COUNT": str(metrics.assembly_count),
        "_DRAWING_COUNT": str(metrics.drawing_count),
        "NUM_COMPONENTS": str(metrics.total_num_components),
        "UNQ_COMPONENTS": str(metrics.unique_model_count),
        "_MAX_ASSEMBLY_DEPTH": str(metrics.max_assembly_depth),
        "_FAMILY_GENERIC_PART_COUNT": str(metrics.family_generic_part_count),
        "_FAMILY_INSTANCE_COUNT": str(metrics.family_instance_count),
        "_MASTER_REP_COUNT": str(metrics.master_rep_component_count),
        "_SIMPREP_REPRESENTATIONS": str(metrics.simprep_unique_count),
        "_SHEETMETAL_PARTS": str(metrics.sheetmetal_parts),
        "_MULTIBODY_PARTS": str(metrics.multibody_parts),
        "_SKELETON_MODELS": str(metrics.skeleton_models),
        "_DUPLICATE_MODELS": str(metrics.duplicate_models),
        "_BULK_PARTS": str(metrics.bulk_parts),
        "_NON_SOLID_PARTS": str(metrics.non_solid_parts),
        "_TOTAL_SCANNED_SIZE": _format_total_scanned_size(metrics.total_scanned_bytes),
        "_FIXED_COMPONENTS": str(metrics.fixed_components),
        "_SUPPRESSED_COMPONENTS": str(metrics.suppressed_components),
        "_TOP_LEVEL_FEATURES": (
            str(metrics.top_level_assembly_features)
            if metrics.top_level_assembly_features is not None
            else "—"
        ),
    }
    for row_key in PERFORMANCE_REPORT_ISSUE_ROW_CHECKS:
        answers[row_key] = str(metrics.report_issue_counts.get(row_key, 0))
    return answers


def _resolve_performance_value(answers: dict[str, str], key: str | None) -> tuple[str, str | None]:
    if key is None:
        return ("—", None)
    if key == "_MASTER_REP_COUNT":
        val = answers.get(key)
        return (val if val is not None else "—", "SIMPREP_MASTER")
    if key == "_FAMILY_GENERIC_PART_COUNT":
        val = answers.get(key)
        return (val if val is not None else "—", "FAMILY_INFO")
    if key == "_FAMILY_INSTANCE_COUNT":
        val = answers.get(key)
        return (val if val is not None else "—", "FAMILY_INFO")
    if key in (
        "_SCAN_DATE",
        "_MODEL_CHECKS",
        "_WORKING_DIRECTORY",
        "_SCAN_DURATION",
        "_USERS",
        "_FILES_SCANNED",
        "_PART_COUNT",
        "_ASSEMBLY_COUNT",
        "_DRAWING_COUNT",
    ):
        val = answers.get(key)
        return (val if val is not None else "—", None)
    if key == "_TOTAL_SCANNED_SIZE":
        val = answers.get(key)
        return (val if val is not None else "—", "FILE_SIZE")
    if key == "_SHEETMETAL_PARTS":
        val = answers.get(key)
        return (val if val is not None else "—", "SHTMTL_THICK")
    if key == "_MULTIBODY_PARTS":
        val = answers.get(key)
        return (val if val is not None else "—", "MULTIBODY_MODEL")
    if key == "_SKELETON_MODELS":
        val = answers.get(key)
        return (val if val is not None else "—", None)
    if key == "_MAX_ASSEMBLY_DEPTH":
        val = answers.get(key)
        return (val if val is not None else "—", "UNQ_COMPONENTS")
    if key == "_SIMPREP_REPRESENTATIONS":
        val = answers.get(key)
        return (val if val is not None else "—", "SIMPREP_INFO")
    if key == "_FLEXIBLE_COMPONENTS":
        val = answers.get(key)
        return (val if val is not None else "—", "FLEX_COMPONENTS")
    if key == "_SUPPRESSED_COMPONENTS":
        val = answers.get(key)
        return (val if val is not None else "—", "SUP_COMPONENTS")
    if key == "_PACKAGED_COMPONENTS":
        val = answers.get(key)
        return (val if val is not None else "—", "PACK_COMPONENTS")
    if key == "_FIXED_COMPONENTS":
        val = answers.get(key)
        return (val if val is not None else "—", "FIXED_COMPONENTS")
    if key == "_MECH_COMPONENTS":
        val = answers.get(key)
        return (val if val is not None else "—", "MECH_COMPONENTS")
    if key == "_DUPLICATE_MODELS":
        val = answers.get(key)
        return (val if val is not None else "—", "DUPLICATE_MODELS")
    if key == "_BULK_PARTS":
        val = answers.get(key)
        return (val if val is not None else "—", "BULK_ITEMS")
    if key == "_NON_SOLID_PARTS":
        val = answers.get(key)
        return (val if val is not None else "—", "BODY_INFO")
    if key == "_TOP_LEVEL_FEATURES":
        val = answers.get(key)
        return (val if val is not None else "—", "NUM_COMPONENTS")
    val = answers.get(key)
    if val is None:
        return ("—", key)
    return (val, key)


def _top_level_features_label(metrics: PerformanceMetrics) -> str:
    name = (metrics.top_level_assembly_name or "").strip()
    if name:
        return f"Total number of features in {name}"
    return "Total number of features in top level assembly"


def build_performance_table_rows(metrics: PerformanceMetrics) -> list[tuple[str, str | None, str, str | None]]:
    answers = performance_metrics_answers(metrics)
    rows: list[tuple[str, str | None, str, str | None]] = []
    for section, section_rows in PERFORMANCE_TABLE_SECTIONS:
        rows.append(("section", None, section, None))
        for label, key in section_rows:
            if key == "_TOP_LEVEL_FEATURES":
                label = _top_level_features_label(metrics)
            value, check = _resolve_performance_value(answers, key)
            rows.append(("item", label, value, check if key and not key.startswith("_") else key))
    return rows


def generate_performance_table_html(
    metrics: PerformanceMetrics,
    *,
    extra_summary_html: str = "",
) -> str:
    """Performance metrics table for Scan Information (embedded mq-stats styles)."""
    body_rows: list[str] = []
    for row_type, label, value, check_key in build_performance_table_rows(metrics):
        if row_type == "section":
            body_rows.append(
                f'<tr class="mq-perf-section-row"><td colspan="2">{_esc(value)}</td></tr>'
            )
            continue
        if label is None:
            continue
        label_esc = _esc(label)
        if value == "—":
            val_html = '<span class="mq-perf-missing">—</span>'
            title_attr = ' title="Not in ModelCHECK master.xml"' if check_key is None else ""
            val_class = "mq-perf-val"
        else:
            val_html = _esc(value)
            title_attr = ""
            val_class = (
                "mq-perf-plain"
                if label in ("Last saved by", "Working directory")
                else "mq-perf-val"
            )
        body_rows.append(
            f"<tr><td class=\"mq-perf-label\">{label_esc}</td>"
            f"<td class=\"{val_class}\"{title_attr}>{val_html}</td></tr>"
        )
    table_body = "\n".join(body_rows)
    extras = extra_summary_html or ""
    return f"""
  <div class="mq-stats-grid">
    <div class="mq-stat-card mq-perf-card">
      <h2>CAD Assessment Summary</h2>
      <table class="mq-perf-table" role="table">
        <tbody>
{table_body}
        </tbody>
      </table>
      {extras}
    </div>
  </div>"""


def generate_performance_report_page(metrics: PerformanceMetrics) -> str:
    """Standalone ``performance_report.html`` page."""
    section = generate_performance_table_html(metrics)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "  <meta charset=\"UTF-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "  <title>performance_report</title>\n"
        f"{_MQ_STATS_CSS}\n"
        "</head>\n<body style=\"margin:0;background:#e8eaed;\">\n"
        f'<div class="mq-stats-page">{section}\n</div>\n</body>\n</html>\n'
    )


def _apply_performance_report_meta(
    metrics: PerformanceMetrics,
    *,
    working_dir: str = "",
    master_path: str = "",
) -> None:
    """Fill Scan date / Model checks / Working directory / Scan duration for the table."""
    wd = (working_dir or "").strip()
    if not wd and master_path:
        try:
            wd = str(Path(master_path).expanduser().resolve().parent)
        except OSError:
            wd = str(Path(master_path).parent)
    metrics.scan_date = _scan_date_for_report(master_path)
    metrics.model_checks_mch = _model_checks_mch_from_condition_mcc()
    metrics.working_directory = wd
    metrics.scan_duration = _scan_duration_from_modelcheck_xml(wd)


def write_performance_report_file(master_xml_path: str, output_path: str | None = None) -> str:
    """Write ``performance_report.html`` beside ``master.xml`` from batch performance metrics."""
    master_xml_path = os.path.abspath(master_xml_path)
    root = ET.parse(master_xml_path).getroot()
    metrics = scan_performance_metrics(root)
    _apply_performance_report_meta(
        metrics,
        working_dir=os.path.dirname(master_xml_path) or "",
        master_path=master_xml_path,
    )
    if metrics.files_seen == 0:
        raise ValueError("No model entries found in master.xml")
    out_path = output_path or os.path.join(os.path.dirname(master_xml_path), "performance_report.html")
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(generate_performance_report_page(metrics))
    return out_path





def _resolve_check_xml_path(working_dir: str, model: str) -> str | None:
    """Locate ``*.p.xml`` / ``*.a.xml`` / ``*.d.xml`` for a logical model name in ``working_dir``."""
    display = _model_display_lower(model)
    xml_base = _check_xml_basename_for_display(display)
    if not xml_base:
        return None
    wd = os.path.normpath(os.path.abspath(working_dir))
    direct = os.path.join(wd, xml_base)
    if os.path.isfile(direct):
        return direct
    target_cf = xml_base.casefold()
    try:
        for name in os.listdir(wd):
            if name.casefold() == target_cf:
                path = os.path.join(wd, name)
                if os.path.isfile(path):
                    return path
    except OSError:
        return None
    return None


def _parse_mc_bom_item_names(check_xml_path: str) -> list[str]:
    """Read ``<mc_bom><item><name>…</name></item></mc_bom>`` from a ModelCHECK result XML."""
    try:
        root = ET.parse(check_xml_path).getroot()
    except (ET.ParseError, OSError):
        return []
    bom = root.find(".//mc_bom")
    if bom is None:
        return []
    names: list[str] = []
    for item in bom.findall("item"):
        name = (item.findtext("name") or "").strip()
        if name:
            names.append(name)
    return names


def scan_model_issue_counts(
    master_root: ET.Element,
    model_checks_xml_path: str | None = None,
) -> dict[str, tuple[int, int]]:
    """Casefold model name -> (error_count, warning_count) for report-visible checks."""
    allowed: set[str] | None = None
    if model_checks_xml_path and os.path.isfile(model_checks_xml_path):
        allowed = set(_model_check_category_map(model_checks_xml_path).keys())

    counts: dict[str, tuple[int, int]] = {}
    for file_element in master_root.findall("File"):
        model = (file_element.findtext("Model") or "").strip()
        if not model:
            continue
        errors = 0
        warnings = 0
        for check in file_element.findall(".//check"):
            if _check_hidden_from_report(check):
                continue
            stat_el = check.find("stat")
            stat = (stat_el.text if stat_el is not None else "").strip().upper()
            if stat not in ("ERROR", "WARNING"):
                continue
            name = check.get("name") or ""
            if allowed is not None and name not in allowed:
                continue
            if stat == "ERROR":
                errors += 1
            else:
                warnings += 1
        key = model.casefold()
        prev_e, prev_w = counts.get(key, (0, 0))
        counts[key] = (prev_e + errors, prev_w + warnings)
    return counts


@dataclass
class BomComponentRow:
    name: str
    errors: int = 0
    warnings: int = 0


def load_top_level_assembly_bom(
    working_dir: str,
    top_level_assembly: str | None,
    *,
    master_root: ET.Element | None = None,
    model_checks_xml_path: str | None = None,
) -> list[BomComponentRow]:
    """BOM components from the top assembly's ``.a.xml``, with issue counts from ``master.xml``."""
    if not top_level_assembly:
        return []
    xml_path = _resolve_check_xml_path(working_dir, top_level_assembly)
    if not xml_path:
        return []
    names = _parse_mc_bom_item_names(xml_path)
    issue_counts: dict[str, tuple[int, int]] = {}
    if master_root is not None:
        issue_counts = scan_model_issue_counts(master_root, model_checks_xml_path)
    rows: list[BomComponentRow] = []
    for name in names:
        errors, warnings = issue_counts.get(name.casefold(), (0, 0))
        rows.append(BomComponentRow(name=name, errors=errors, warnings=warnings))
    return rows


def _model_checks_xml_path() -> Path:
    return _app_dir() / "model_checks.xml"


HEALTH_CHECKS: list[tuple[str, str]] = [

    ("REGEN_ERRS", "Regeneration errors"),

    ("REGEN_WRNS", "Regeneration warnings"),

    ("INCOMPLETE_FEAT", "Incomplete features"),

    ("BURIED_FEAT", "Buried features"),

    ("MIS_COMPONENTS", "Missing components"),

    ("SUP_COMPONENTS", "Suppressed components"),

    ("FAILED_COMPONENTS", "Failed components"),

    ("PACK_COMPONENTS", "Packaged components"),

    ("GEN_COMPONENTS", "Generic components placed"),

    ("EDGE_REFERENCES", "Edge References"),

    ("CIRCULAR_REFS", "Circular References"),

    ("WEAK_SKETCHER_DIMS", "Weak dimensions"),

    ("GLOBAL_INTF", "Global Interferences"),

    ("INSERT_MODE", "Insert Mode Usage"),

    ("SUP_FEATURES", "Suppressed Features"),

    ("FAILED_FEATURES", "Failed Features"),

    ("FIXED_COMPONENTS", "Fixed components"),

    ("STARTPARM", "Missing Parameters"),

    ("UNUSED_MODELS", "Unused Models"),

    ("SHTMTL_UNBENDS", "Sheet Metal Unbend Features"),

]





@dataclass

class FamilyGenericRow:

    model: str

    instance_names: list[str] = field(default_factory=list)


def _family_generic_row_from_file(file_element: ET.Element) -> FamilyGenericRow | None:
    """One family-table generic row (same rules as Family table detail)."""
    model = (file_element.findtext("Model") or "").strip()
    if not model:
        return None
    family = _find_check(file_element, "FAMILY_INFO")
    if family is None:
        return None
    ans = (family.findtext("ans") or "").strip().upper()
    if "GENERIC" not in ans:
        return None
    names: list[str] = []
    for item in family.findall("item"):
        name = (item.findtext("info1") or "").strip()
        if name:
            names.append(name)
    return FamilyGenericRow(model=model, instance_names=names)


def collect_family_generics_detail(
    master_root: ET.Element,
    *,
    file_elements: list[ET.Element] | None = None,
) -> list[FamilyGenericRow]:
    """Generic models with ``FAMILY_INFO`` (same rows as Family table detail section)."""
    elements = file_elements if file_elements is not None else _report_scanned_file_elements(master_root)
    rows: list[FamilyGenericRow] = []
    for file_element in elements:
        row = _family_generic_row_from_file(file_element)
        if row is not None:
            rows.append(row)
    return rows




@dataclass

class BatchStatistics:

    master_path: str

    skipped_models: list[str] = field(default_factory=list)

    top_level_assembly: str | None = None

    top_level_assembly_bom: list[BomComponentRow] = field(default_factory=list)

    family_generics_detail: list[FamilyGenericRow] = field(default_factory=list)

    health_counts: dict[str, int] = field(default_factory=dict)

    sheetmetal_parts: int = 0

    multibody_parts: int = 0

    skeleton_models: int = 0

    templates_scanned: list[str] = field(default_factory=list)

    top_features_parts: list[tuple[str, int]] = field(default_factory=list)

    top_size_parts: list[tuple[str, float]] = field(default_factory=list)

    performance_metrics: PerformanceMetrics | None = None





def scan_batch_statistics(master_root: ET.Element, *, master_path: str = "") -> BatchStatistics:

    stats = BatchStatistics(master_path=master_path)

    scanned_files = _report_scanned_file_elements(master_root)

    health_counts = {label: 0 for _, label in HEALTH_CHECKS}

    part_features: list[tuple[str, int]] = []

    part_sizes: list[tuple[str, float]] = []



    for file_element in scanned_files:

        model = (file_element.findtext("Model") or "").strip()

        pro_type = (file_element.findtext("ProType") or "").strip().upper()



        for check_name, label in HEALTH_CHECKS:

            check = _find_check(file_element, check_name)

            if check is not None and _parse_positive_ans(check):

                health_counts[label] += 1



        if pro_type == "PRT":

            shtmtl = _find_check(file_element, "SHTMTL_THICK")

            if shtmtl is not None:

                stats.sheetmetal_parts += 1



            mb = _find_check(file_element, "MULTIBODY_MODEL")

            if mb is not None:

                ans = (mb.findtext("ans") or "").strip().upper()

                if ans in ("YES", "Y", "TRUE", "1") or _parse_positive_ans(mb):

                    stats.multibody_parts += 1



            nf_text = (file_element.findtext("NumFeatures") or "").strip()

            if nf_text.isdigit():

                nf = int(nf_text)

                part_features.append((model, nf))



            fs_text = file_element.findtext("FileSize") or ""

            mb_val = _parse_mb(fs_text)

            if mb_val is not None:

                part_sizes.append((model, mb_val))

    stats.family_generics_detail = collect_family_generics_detail(
        master_root, file_elements=scanned_files
    )
    stats.health_counts = health_counts

    stats.skeleton_models = scan_skeleton_model_count(master_root)



    if part_features:

        top = sorted(part_features, key=lambda x: (-x[1], x[0].casefold()))[:5]

        stats.top_features_parts = top



    if part_sizes:

        stats.top_size_parts = sorted(part_sizes, key=lambda x: (-x[1], x[0].casefold()))[:5]



    stats.top_level_assembly = find_top_level_assembly(master_root)

    return stats





_MQ_STATS_CSS = """

<style>

.mq-stats-page { font-family: "Segoe UI", Arial, sans-serif; background: #e8eaed; color: #1a1a1a;

  padding: 16px; border-radius: 8px; box-sizing: border-box; max-width: 1200px; margin: 0 auto; }

.mq-stats-page * { box-sizing: border-box; }

.mq-stats-title { font-size: 1.75rem; font-weight: 700; margin: 0 0 20px 0; letter-spacing: 0.02em; color: #0f172a; }

.mq-stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin-bottom: 20px; }

.mq-stat-card { background: #fff; border-radius: 12px; padding: 16px 18px;

  box-shadow: 0 1px 3px rgba(0,0,0,.08); }

.mq-stats-page h2 { margin: 0 0 12px 0; font-size: 1.15rem; font-weight: 700; color: #0f172a; }

.mq-stat-card p { margin: 5px 0; font-size: 0.92rem; line-height: 1.4; }

.mq-stat-card strong { color: #0f172a; }

.mq-perf-card { grid-column: 1 / -1; }

.mq-perf-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }

.mq-perf-table tbody tr { transition: background-color 0.15s ease; }

.mq-perf-table tbody tr:not(.mq-perf-section-row):hover td { background: #f1f5f9; }

.mq-perf-table td { padding: 8px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }

.mq-perf-table tr:last-child td { border-bottom: none; }

.mq-perf-section-row td { padding: 14px 10px 6px 10px; border-bottom: none; color: #0f172a; font-weight: 700; letter-spacing: .01em; background: #fff; }

.mq-perf-label { text-align: left; color: #1a1a1a; width: 1%; white-space: nowrap; vertical-align: top; padding-left: 28px !important; }

.mq-perf-val { text-align: right; font-weight: 600; color: #0f172a; white-space: nowrap; }

.mq-perf-plain { font-weight: 400; color: #334155; white-space: normal; text-align: right; line-height: 1.45; }

.mq-perf-missing { color: #94a3b8; font-weight: 400; }

.mq-stat-num { font-size: 1.65rem; font-weight: 800; color: #0369a1; line-height: 1.2; }

.mq-stat-label { font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }

.mq-section { background: #fff; border-radius: 12px; padding: 18px 20px;

  box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 16px; }

.mq-section-note { font-size: 0.85rem; color: #475569; margin: 0 0 14px 0; line-height: 1.45; }

.mq-template-categories { margin: 0; }
.mq-template-category { margin: 0 0 14px 0; }
.mq-template-category:last-child { margin-bottom: 0; }
.mq-template-cat-title { margin: 0 0 4px 0; font-size: 0.92rem; font-weight: 600; color: #0f172a; }
.mq-template-cat-body { margin: 0; padding-left: 12px; font-size: 0.92rem; line-height: 1.45; color: #334155; }
.mq-template-cat-pre { white-space: pre-line; }
.mq-template-cat-body + .mq-template-cat-body { margin-top: 4px; }
.mq-template-empty { color: #94a3b8; }

.mq-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }

.mq-table th, .mq-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }

.mq-table th { font-size: 0.78rem; text-transform: uppercase; letter-spacing: .04em; color: #64748b; font-weight: 600; }

.mq-table tr:last-child td { border-bottom: none; }

.mq-health-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 0.88rem; }

.mq-health-label { flex: 1; min-width: 160px; }

.mq-health-track { flex: 2; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; max-width: 280px; }

.mq-health-fill { height: 100%; background: #f59e0b; border-radius: 4px; }

.mq-health-count { width: 48px; text-align: right; font-weight: 600; color: #0f172a; }

.mq-stats-embedded button.mq-health-jump {
  display: flex; align-items: center; gap: 10px; width: 100%; margin-bottom: 8px;
  border: none; background: transparent; text-align: left; font: inherit; color: inherit;
  padding: 4px 6px; border-radius: 6px; cursor: pointer;
}
.mq-stats-embedded button.mq-health-jump:hover { background: #f1f5f9; }
.mq-stats-embedded button.mq-health-jump:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }

.mq-complexity-table { width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.mq-complexity-head {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 10px; border-bottom: 1px solid #e2e8f0;
  font-size: 0.78rem; text-transform: uppercase; letter-spacing: .04em;
  color: #64748b; font-weight: 600; background: #fff;
}
.mq-complexity-head .mq-complexity-model { flex: 1; min-width: 0; text-align: left; }
.mq-complexity-head .mq-complexity-val { width: 5.5rem; text-align: right; flex-shrink: 0; }
.mq-complexity-row, .mq-stats-embedded button.mq-complexity-jump {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 10px; border-bottom: 1px solid #e2e8f0;
  font-size: 0.88rem; box-sizing: border-box;
}
.mq-complexity-row .mq-complexity-model, .mq-stats-embedded button.mq-complexity-jump .mq-complexity-model {
  flex: 1; min-width: 0; text-align: left;
  color: #1a1a1a; font-weight: normal; text-decoration: none;
}
.mq-complexity-row .mq-complexity-val, .mq-stats-embedded button.mq-complexity-jump .mq-complexity-val {
  width: 5.5rem; text-align: right; flex-shrink: 0;
  font-weight: 600; color: #0f172a; text-decoration: none;
}
.mq-stats-embedded button.mq-complexity-jump {
  border: none; background: transparent; text-align: left; font: inherit; color: #1a1a1a;
  cursor: pointer; margin: 0; text-decoration: none;
}
.mq-stats-embedded button.mq-complexity-jump:hover { background: #f1f5f9; }
.mq-stats-embedded button.mq-complexity-jump:hover .mq-complexity-model,
.mq-stats-embedded button.mq-complexity-jump:hover .mq-complexity-val {
  color: #1a1a1a; text-decoration: none;
}
.mq-stats-embedded button.mq-complexity-jump:focus-visible { outline: 2px solid #2563eb; outline-offset: -2px; }
.mq-complexity-table > .mq-complexity-row:last-child,
.mq-complexity-table > button.mq-complexity-jump:last-of-type { border-bottom: none; }

.mq-inst-names { line-height: 1.45; }

.mq-skipped-names { color: #334155; }

.mq-skipped-drag { color: #0369a1; text-decoration: underline; cursor: grab; }
.mq-skipped-drag:active { cursor: grabbing; }
.mq-skipped-name-plain { color: #334155; }

.mq-skipped-section-list { margin: 0; font-size: 0.92rem; line-height: 1.45; color: #334155; }

.mq-skipped-rest[hidden] { display: none !important; }

.mq-skipped-more-btn {
  display: inline; border: none; background: none; padding: 0; margin: 0;
  font: inherit; color: #007bff; cursor: pointer;
}

.mq-skipped-more-btn:hover { text-decoration: underline; }

.mq-list-more-wrap { display: inline; }

.mq-list-expand-btn[hidden], .mq-list-collapse-btn[hidden] { display: none !important; }

.mq-family-table-rest[hidden] { display: none !important; }

.mq-family-more-wrap { margin: 10px 0 0 0; font-size: 0.88rem; }
.mq-family-expand-btn[hidden], .mq-family-collapse-btn[hidden] { display: none !important; }

.mq-stats-page.mq-stats-embedded { background: transparent; padding: 0; margin-top: 20px; max-width: none; }

.mq-bom-table { width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.mq-bom-head {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 10px; border-bottom: 1px solid #e2e8f0;
  font-size: 0.78rem; text-transform: uppercase; letter-spacing: .04em;
  color: #64748b; font-weight: 600; background: #fff;
}
.mq-bom-head .mq-bom-model { flex: 1; min-width: 0; text-align: left; }
.mq-bom-head .mq-bom-num { width: 5.5rem; text-align: center; flex-shrink: 0; }
.mq-bom-row, .mq-stats-embedded button.mq-bom-jump {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 10px; border-bottom: 1px solid #e2e8f0;
  font-size: 0.88rem; box-sizing: border-box;
}
.mq-bom-row .mq-bom-model, .mq-stats-embedded button.mq-bom-jump .mq-bom-model {
  flex: 1; min-width: 0; text-align: left;
}
.mq-bom-row .mq-bom-num, .mq-stats-embedded button.mq-bom-jump .mq-bom-num {
  width: 5.5rem; text-align: center; flex-shrink: 0;
  font-weight: 600; color: #0f172a;
}
.mq-stats-embedded button.mq-bom-jump {
  border: none; background: transparent; text-align: left; font: inherit; color: inherit;
  cursor: pointer; margin: 0;
}
.mq-stats-embedded button.mq-bom-jump:hover { background: #f1f5f9; }
.mq-stats-embedded button.mq-bom-jump:focus-visible { outline: 2px solid #2563eb; outline-offset: -2px; }
.mq-bom-table > .mq-bom-row:last-child,
.mq-bom-table > button.mq-bom-jump:last-of-type { border-bottom: none; }
.mq-bom-table-rest[hidden] { display: none !important; }
.mq-bom-more-wrap { margin: 12px 0 0 0; font-size: 0.88rem; }
.mq-bom-expand-btn[hidden], .mq-bom-collapse-btn[hidden] { display: none !important; }

.mq-stats-embedded button.mq-bom-jump.mq-inline-model-jump {
  display: inline; width: auto; padding: 0; margin: 0;
  font: inherit; color: #007bff; font-weight: 600; vertical-align: baseline;
}
.mq-stats-embedded button.mq-bom-jump.mq-inline-model-jump:hover {
  background: transparent; text-decoration: underline;
}
.mq-stats-embedded button.mq-bom-jump.mq-inline-model-jump:focus-visible {
  outline: 2px solid #2563eb; outline-offset: 2px;
}

</style>"""


_MQ_SKIPPED_DRAG_SCRIPT = """
<script>
(function () {
    function initSkippedModelDrag() {
        var links = document.querySelectorAll('a.mq-skipped-drag[href]');
        for (var i = 0; i < links.length; i++) {
            (function (link) {
                link.addEventListener('dragstart', function (e) {
                    var rel = link.getAttribute('href');
                    if (!rel) { return; }
                    var fileUrl;
                    try {
                        fileUrl = new URL(rel, window.location.href).href;
                    } catch (err) {
                        fileUrl = rel;
                    }
                    e.dataTransfer.setData('text/uri-list', fileUrl);
                    e.dataTransfer.setData('text/plain', fileUrl);
                    e.dataTransfer.effectAllowed = 'copy';
                });
            })(links[i]);
        }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSkippedModelDrag);
    } else {
        initSkippedModelDrag();
    }
})();
</script>"""





def _esc(text: Any) -> str:

    return html.escape(str(text) if text is not None else "", quote=False)


_LIST_PREVIEW_LIMIT = 20

_FAMILY_TABLE_PREVIEW_LIMIT = 5

_BOM_LIST_PREVIEW_LIMIT = 10


def _name_has_creo_path_ref(display_name: str) -> bool:
    if "<<" in display_name and ">>" in display_name:
        return True
    if "[[" in display_name and "]]" in display_name:
        return True
    return False


def _skipped_model_name_html(name: str) -> str:
    """Draggable link for Creo drop (click does nothing); plain span for session-style names."""
    if _name_has_creo_path_ref(name):
        return f'<span class="mq-skipped-name-plain">{_esc(name)}</span>'
    href = "./" + quote(name)
    return (
        f'<a class="mq-skipped-drag" href="{_esc(href)}" '
        f'onclick="void(0); return false;" title="Drag into Creo">{_esc(name)}</a>'
    )


def _comma_separated_list_html(
    names: list[str],
    *,
    span_class: str,
    item_html: Callable[[str], str] | None = None,
) -> str:
    """Comma-separated names; first 20 inline, then ``More...`` expands the rest on the same line."""
    if not names:
        return "—"

    def one(name: str) -> str:
        return item_html(name) if item_html else _esc(name)

    if len(names) <= _LIST_PREVIEW_LIMIT:
        return f'<span class="{span_class}">{", ".join(one(name) for name in names)}</span>'
    visible = ", ".join(one(name) for name in names[:_LIST_PREVIEW_LIMIT])
    rest = ", ".join(one(name) for name in names[_LIST_PREVIEW_LIMIT:])
    return (
        f'<span class="{span_class}">{visible}'
        f'<span class="mq-skipped-rest" hidden>, {rest}</span></span>'
        f'<span class="mq-list-more-wrap">, '
        f'<button type="button" class="mq-skipped-more-btn mq-list-expand-btn" '
        f'onclick="var w=this.closest(&quot;.mq-list-more-wrap&quot;);'
        f"var l=w.previousElementSibling;var r=l.querySelector(&quot;.mq-skipped-rest&quot;);"
        f"r.removeAttribute(&quot;hidden&quot;);"
        f"w.querySelector('.mq-list-expand-btn').setAttribute('hidden','');"
        f"w.querySelector('.mq-list-collapse-btn').removeAttribute('hidden');\">More...</button>"
        f'<button type="button" class="mq-skipped-more-btn mq-list-collapse-btn" hidden '
        f'onclick="var w=this.closest(&quot;.mq-list-more-wrap&quot;);'
        f"var l=w.previousElementSibling;var r=l.querySelector(&quot;.mq-skipped-rest&quot;);"
        f"r.setAttribute(&quot;hidden&quot;,&quot;&quot;);"
        f"w.querySelector('.mq-list-collapse-btn').setAttribute('hidden','');"
        f"w.querySelector('.mq-list-expand-btn').removeAttribute('hidden');\">Collapse</button></span>"
    )


def _family_table_row(generic: FamilyGenericRow, *, collapsed: bool = False) -> str:
    inst_html = _comma_separated_list_html(generic.instance_names, span_class="mq-inst-names")
    tr_attrs = ' class="mq-family-table-rest" hidden' if collapsed else ""
    return (
        f"<tr{tr_attrs}><td>{_esc(_model_display_lower(generic.model))}</td>"
        f"<td>{len(generic.instance_names)}</td><td>{inst_html}</td></tr>"
    )


def _family_table_section(generics: list[FamilyGenericRow]) -> str:
    if not generics:
        return ""
    generics = sorted(
        generics,
        key=lambda g: (-len(g.instance_names), _model_display_lower(g.model).casefold()),
    )
    more_html = ""
    if len(generics) > _FAMILY_TABLE_PREVIEW_LIMIT:
        total = len(generics)
        tbody_html = "".join(
            _family_table_row(g)
            for g in generics[:_FAMILY_TABLE_PREVIEW_LIMIT]
        ) + "".join(
            _family_table_row(g, collapsed=True)
            for g in generics[_FAMILY_TABLE_PREVIEW_LIMIT:]
        )
        more_html = (
            '<p class="mq-family-more-wrap">'
            '<button type="button" class="mq-skipped-more-btn mq-family-expand-btn" '
            'onclick="var s=this.closest(&quot;.mq-section&quot;);'
            "s.querySelectorAll('.mq-family-table-rest').forEach(function(r){r.removeAttribute('hidden');});"
            'var w=this.closest(&quot;.mq-family-more-wrap&quot;);'
            "w.querySelector('.mq-family-expand-btn').setAttribute('hidden','');"
            "w.querySelector('.mq-family-collapse-btn').removeAttribute('hidden');\">"
            f"Show all {total} rows…</button>"
            '<button type="button" class="mq-skipped-more-btn mq-family-collapse-btn" hidden '
            'onclick="var s=this.closest(&quot;.mq-section&quot;);'
            "s.querySelectorAll('.mq-family-table-rest').forEach(function(r){r.setAttribute('hidden','');});"
            'var w=this.closest(&quot;.mq-family-more-wrap&quot;);'
            "w.querySelector('.mq-family-collapse-btn').setAttribute('hidden','');"
            "w.querySelector('.mq-family-expand-btn').removeAttribute('hidden');\">"
            "Collapse</button></p>"
        )
    else:
        tbody_html = "".join(_family_table_row(g) for g in generics)
    return f"""

  <div class="mq-section">

    <h2>Family table detail</h2>

    <table class="mq-table">

      <thead><tr><th>Generic</th><th>Count</th><th>Instance names</th></tr></thead>

      <tbody>{tbody_html}</tbody>

    </table>{more_html}

  </div>"""


def _top_level_asm_name_html(assembly_name: str, *, embedded: bool) -> str:
    """Assembly name in the BOM note; jump link in embedded report."""
    asm_display = _esc(_model_display_lower(assembly_name))
    if embedded:
        return (
            f'<button type="button" class="mq-bom-jump mq-inline-model-jump" '
            f'data-mq-model-jump="{_esc(assembly_name)}">{asm_display}</button>'
        )
    return asm_display


def _bom_row(
    row: BomComponentRow,
    *,
    embedded: bool,
    collapsed: bool = False,
    top_level_assembly: str | None = None,
) -> str:
    display = _model_display_lower(row.name)
    if top_level_assembly and row.name.casefold() == top_level_assembly.casefold():
        display = f"{display} (Top Level)"
    display = _esc(display)
    hidden_attr = " hidden" if collapsed else ""
    rest_cls = " mq-bom-table-rest" if collapsed else ""
    inner = (
        f'<span class="mq-bom-model">{display}</span>'
        f'<span class="mq-bom-num">{row.errors}</span>'
        f'<span class="mq-bom-num">{row.warnings}</span>'
    )
    if embedded:
        return (
            f'<button type="button" class="mq-bom-jump{rest_cls}"{hidden_attr} '
            f'data-mq-model-jump="{_esc(row.name)}">{inner}</button>'
        )
    return f'<div class="mq-bom-row{rest_cls}"{hidden_attr}>{inner}</div>'


def _complexity_row(model: str, value_html: str, *, embedded: bool) -> str:
    display = _esc(_model_display_lower(model))
    inner = (
        f'<span class="mq-complexity-model">{display}</span>'
        f'<span class="mq-complexity-val">{value_html}</span>'
    )
    if embedded:
        return (
            f'<button type="button" class="mq-complexity-jump" '
            f'data-mq-model-jump="{_esc(model)}">{inner}</button>'
        )
    return f'<div class="mq-complexity-row">{inner}</div>'


def _complexity_table_block(
    *,
    title: str,
    value_heading: str,
    rows_html: str,
) -> str:
    return f"""

      <div>

        <h3 style="font-size:0.95rem;margin:0 0 8px 0">{title}</h3>

        <div class="mq-complexity-table">
          <div class="mq-complexity-head">
            <span class="mq-complexity-model">Model</span>
            <span class="mq-complexity-val">{value_heading}</span>
          </div>
          {rows_html}
        </div>

      </div>"""


def _top_level_bom_section(
    bom_rows: list[BomComponentRow],
    *,
    assembly_name: str,
    embedded: bool,
) -> str:
    if not bom_rows:
        return ""
    total = len(bom_rows)
    if total > _BOM_LIST_PREVIEW_LIMIT:
        rows_html = "".join(
            _bom_row(row, embedded=embedded, top_level_assembly=assembly_name)
            for row in bom_rows[:_BOM_LIST_PREVIEW_LIMIT]
        ) + "".join(
            _bom_row(row, embedded=embedded, collapsed=True, top_level_assembly=assembly_name)
            for row in bom_rows[_BOM_LIST_PREVIEW_LIMIT:]
        )
        more_html = (
            '<p class="mq-bom-more-wrap">'
            '<button type="button" class="mq-skipped-more-btn mq-bom-expand-btn" '
            'onclick="var s=this.closest(&quot;.mq-section&quot;);'
            "s.querySelectorAll('.mq-bom-table-rest').forEach(function(r){r.removeAttribute('hidden');});"
            'var w=this.closest(&quot;.mq-bom-more-wrap&quot;);'
            "w.querySelector('.mq-bom-expand-btn').setAttribute('hidden','');"
            "w.querySelector('.mq-bom-collapse-btn').removeAttribute('hidden');\">"
            f"Show all {total} components…</button>"
            '<button type="button" class="mq-skipped-more-btn mq-bom-collapse-btn" hidden '
            'onclick="var s=this.closest(&quot;.mq-section&quot;);'
            "s.querySelectorAll('.mq-bom-table-rest').forEach(function(r){r.setAttribute('hidden','');});"
            'var w=this.closest(&quot;.mq-bom-more-wrap&quot;);'
            "w.querySelector('.mq-bom-collapse-btn').setAttribute('hidden','');"
            "w.querySelector('.mq-bom-expand-btn').removeAttribute('hidden');\">"
            "Collapse</button></p>"
        )
    else:
        rows_html = "".join(
            _bom_row(row, embedded=embedded, top_level_assembly=assembly_name)
            for row in bom_rows
        )
        more_html = ""

    asm_html = _top_level_asm_name_html(assembly_name, embedded=embedded)
    note = f"BOM from {asm_html} (Top Level) ({total} components)."
    if embedded:
        note += " Click a row to scroll to that model in the report."

    return f"""

  <div class="mq-section mq-top-asm-bom">

    <h2>Top level assembly information</h2>

    <p class="mq-section-note">{note}</p>

    <div class="mq-bom-table">
      <div class="mq-bom-head">
        <div class="mq-bom-model">Model</div>
        <div class="mq-bom-num">Errors</div>
        <div class="mq-bom-num">Warnings</div>
      </div>
      {rows_html}
    </div>{more_html}

  </div>"""


def _skipped_models_section(skipped_models: list[str]) -> str:
    """Own section at top of Scan Information for models not in master.xml."""
    if not skipped_models:
        return ""
    total = len(skipped_models)
    list_html = _comma_separated_list_html(
        skipped_models,
        span_class="mq-skipped-names",
        item_html=_skipped_model_name_html,
    )
    return f"""

  <div class="mq-section">

    <h2>Models failed ({total})</h2>

    <p class="mq-skipped-section-list">{list_html}</p>

  </div>"""


TEMPLATE_SCAN_SESSION_BASENAME = "creo-batch-template-scan.json"


def _template_scan_session_path(working_dir: str) -> str:
    return os.path.join(working_dir, "templates", TEMPLATE_SCAN_SESSION_BASENAME)


def _remove_empty_working_templates_dir(working_dir: str) -> None:
    """Remove ``working_dir\\templates`` when it exists and has no files."""
    templates_dir = os.path.join(working_dir, "templates")
    try:
        if os.path.isdir(templates_dir) and not os.listdir(templates_dir):
            os.rmdir(templates_dir)
    except OSError:
        pass


def write_template_scan_session(
    working_dir: str, outcome: str, kinds: list[str] | None = None
) -> None:
    """Write ``templates\\creo-batch-template-scan.json`` when Scan Templates finishes."""
    if outcome != "done":
        return
    path = _template_scan_session_path(working_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload: dict[str, object] = {"outcome": outcome}
    if kinds:
        payload["kinds"] = kinds
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def clear_template_scan_session(working_dir: str) -> None:
    path = _template_scan_session_path(working_dir)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    _remove_empty_working_templates_dir(working_dir)


def read_template_scan_session(working_dir: str) -> tuple[str | None, list[str]]:
    path = _template_scan_session_path(working_dir)
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None, []
    outcome = data.get("outcome")
    if not isinstance(outcome, str):
        return None, []
    raw_kinds = data.get("kinds", [])
    kinds: list[str] = []
    if isinstance(raw_kinds, list):
        for item in raw_kinds:
            if isinstance(item, str) and item:
                kinds.append(item)
    return outcome, kinds


def scan_templates_scanned(working_dir: str) -> list[str]:
    """Model types scanned in this session (empty when skipped or no session record)."""
    outcome, kinds = read_template_scan_session(working_dir)
    if outcome != "done":
        return []
    return kinds


def _templates_scanned_summary_line(kinds: list[str]) -> str:
    if not kinds:
        return ""
    count_words = {1: "one", 2: "two", 3: "all three"}
    count_word = count_words.get(len(kinds), str(len(kinds)))
    types_label = ", ".join(kinds)
    return f"<p><strong>Templates scanned ({count_word}):</strong> {types_label}</p>"


def _template_category_html(label: str, count: int | None, lines: list[str]) -> str:
    if count is None:
        title = _esc(label)
    else:
        title = f"{_esc(label)} ({count})"
    if not lines:
        body = '<p class="mq-template-cat-body mq-template-empty">—</p>'
    elif len(lines) == 1 and "\n" in lines[0]:
        body = f'<p class="mq-template-cat-body mq-template-cat-pre">{_esc(lines[0])}</p>'
    else:
        body = "".join(
            f'<p class="mq-template-cat-body">{_esc(line)}</p>' for line in lines
        )
    return (
        f'<div class="mq-template-category">'
        f'<p class="mq-template-cat-title">{title}</p>{body}</div>'
    )


def _template_block_html(
    title: str, model_file: str, categories: list[tuple[str, int | None, list[str]]]
) -> str:
    rows = "".join(_template_category_html(label, count, lines) for label, count, lines in categories)
    return f"""

  <div class="mq-section mq-template-block">

    <h2>{_esc(title)} — {_esc(model_file)}</h2>

    <div class="mq-template-categories">{rows}
    </div>

  </div>"""


def generate_template_information_html(working_dir: str, *, embedded: bool = False) -> str:
    """Template scan details from ``templates\\*.xml``; empty when no template XML exists."""
    wd = os.path.normpath(os.path.abspath(working_dir))
    templates_dir = Path(wd) / "templates"
    blocks = collect_template_scan_report_blocks(templates_dir)
    if not blocks:
        return ""
    body = "".join(
        _template_block_html(title, model_file, categories)
        for title, model_file, categories in blocks
    )
    page_class = "mq-stats-page mq-stats-embedded" if embedded else "mq-stats-page"
    if embedded:
        title_html = '  <h1 class="mq-page-title" id="template-information">Template Information</h1>'
    else:
        title_html = '  <h1 class="mq-stats-title">Template Information</h1>'
    return f"""{_MQ_STATS_CSS}

<div class="{page_class}">

{title_html}
{body}

</div>"""


def generate_template_information_fragment(working_dir: str, *, embedded: bool = True) -> str:
    return generate_template_information_html(working_dir, embedded=embedded)





def generate_statistics_html(stats: BatchStatistics, *, embedded: bool = False) -> str:

    extra_summary: list[str] = []
    templates_line = _templates_scanned_summary_line(stats.templates_scanned)
    if templates_line:
        extra_summary.append(templates_line)

    skipped_section = _skipped_models_section(stats.skipped_models)

    summary_grid = ""
    if stats.performance_metrics and stats.performance_metrics.files_seen > 0:
        summary_grid = generate_performance_table_html(
            stats.performance_metrics,
            extra_summary_html="".join(extra_summary),
        )
    elif extra_summary:
        summary_grid = f"""

  <div class="mq-stats-grid">

    <div class="mq-stat-card">

      {''.join(extra_summary)}

    </div>

  </div>"""



    family_section = _family_table_section(stats.family_generics_detail)

    bom_section = ""
    if stats.top_level_assembly and stats.top_level_assembly_bom:
        bom_section = _top_level_bom_section(
            stats.top_level_assembly_bom,
            assembly_name=stats.top_level_assembly,
            embedded=embedded,
        )

    health_max = max(stats.health_counts.values()) if stats.health_counts else 0

    health_rows = []

    ranked_health = sorted(
        (
            (stats.health_counts.get(label, 0), check_name, label)
            for check_name, label in HEALTH_CHECKS
        ),
        key=lambda item: (-item[0], item[2].casefold()),
    )

    for count, check_name, label in ranked_health:

        if count == 0:

            continue

        bar_w = (count / health_max * 100) if health_max else 0

        bar_inner = f"""
          <div class="mq-health-label">{_esc(label)}</div>
          <div class="mq-health-track"><div class="mq-health-fill" style="width:{bar_w:.0f}%"></div></div>
          <div class="mq-health-count">{count}</div>"""

        if embedded:

            health_rows.append(
                f"""
        <button type="button" class="mq-health-bar mq-health-jump" data-mq-health-check="{_esc(check_name)}">{bar_inner}
        </button>"""
            )

        else:

            health_rows.append(
                f"""
        <div class="mq-health-bar">{bar_inner}
        </div>"""
            )

    health_section = ""

    if health_rows:

        health_section = f"""

  <div class="mq-section">

    <h2>Biggest problems:</h2>

    {''.join(health_rows)}

  </div>"""



    top_feat_rows = "".join(
        _complexity_row(m, str(n), embedded=embedded)
        for m, n in stats.top_features_parts
    )

    top_size_rows = "".join(
        _complexity_row(m, f"{sz:.2f} MB", embedded=embedded)
        for m, sz in stats.top_size_parts
    )

    complexity_snapshot_section = ""

    if top_feat_rows or top_size_rows:

        snapshot_parts = ['<div class="mq-stats-grid" style="margin-top:4px">']

        if top_feat_rows:

            snapshot_parts.append(
                _complexity_table_block(
                    title="Top parts by features",
                    value_heading="Features",
                    rows_html=top_feat_rows,
                )
            )

        if top_size_rows:

            snapshot_parts.append(
                _complexity_table_block(
                    title="Top parts by file size",
                    value_heading="Size",
                    rows_html=top_size_rows,
                )
            )

        snapshot_parts.append("</div>")

        complexity_snapshot_section = f"""

  <div class="mq-section">

    <h2>Model Complexity</h2>

    {''.join(snapshot_parts)}

  </div>"""



    body_sections = skipped_section + summary_grid + bom_section + health_section + complexity_snapshot_section + family_section

    if not body_sections.strip():

        body_sections = """

  <div class="mq-section">

    <p>No additional statistics for this batch.</p>

  </div>"""

    page_class = "mq-stats-page mq-stats-embedded" if embedded else "mq-stats-page"
    if embedded:
        title_html = '  <h1 class="mq-page-title" id="statistics">Scan Information</h1>'
    else:
        title_html = '  <h1 class="mq-stats-title">Scan Information</h1>'
    return f"""{_MQ_STATS_CSS}

<div class="{page_class}">

{title_html}
{body_sections}

</div>"""


def generate_statistics_fragment(
    master_root: ET.Element,
    working_dir: str,
    *,
    master_path: str = "",
    embedded: bool = False,
) -> str:
    """Build statistics HTML from an already-parsed ``master.xml`` root."""
    stats = scan_batch_statistics(master_root, master_path=master_path)
    stats.performance_metrics = scan_performance_metrics(master_root)
    _apply_performance_report_meta(
        stats.performance_metrics,
        working_dir=working_dir,
        master_path=master_path,
    )
    stats.skipped_models = scan_skipped_models(working_dir, master_root)
    stats.templates_scanned = scan_templates_scanned(working_dir)
    if stats.top_level_assembly:
        stats.top_level_assembly_bom = load_top_level_assembly_bom(
            working_dir,
            stats.top_level_assembly,
            master_root=master_root,
            model_checks_xml_path=str(_model_checks_xml_path()),
        )
    return generate_statistics_html(stats, embedded=embedded)





def write_statistics_html_file(master_xml_path: str, output_path: str) -> str:

    master_xml_path = os.path.abspath(master_xml_path)

    root = ET.parse(master_xml_path).getroot()

    working_dir = os.path.dirname(master_xml_path) or os.getcwd()

    stats = scan_batch_statistics(root, master_path=master_xml_path)
    stats.performance_metrics = scan_performance_metrics(root)
    _apply_performance_report_meta(
        stats.performance_metrics,
        working_dir=working_dir,
        master_path=master_xml_path,
    )
    stats.skipped_models = scan_skipped_models(working_dir, root)
    stats.templates_scanned = scan_templates_scanned(working_dir)
    if stats.top_level_assembly:
        stats.top_level_assembly_bom = load_top_level_assembly_bom(
            working_dir,
            stats.top_level_assembly,
            master_root=root,
            model_checks_xml_path=str(_model_checks_xml_path()),
        )

    fragment = generate_statistics_html(stats, embedded=False)

    doc = (

        "<!DOCTYPE html>\n"

        '<html lang="en">\n<head>\n'

        '  <meta charset="UTF-8">\n'

        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'

        "  <title>Scan Information</title>\n"

        f"{_MQ_SKIPPED_DRAG_SCRIPT}\n"

        "</head>\n<body style=\"margin:0;background:#e8eaed;\">\n"

        f"{fragment}\n"

        "</body>\n</html>\n"

    )

    out_dir = os.path.dirname(os.path.abspath(output_path))

    if out_dir:

        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:

        f.write(doc)

    return output_path





def build_statistics_html(working_dir: str) -> str:

    """Read ``working_dir\\master.xml`` and write ``working_dir\\statistics.html``."""

    working_dir = os.path.normpath(os.path.abspath(working_dir))

    master_file = os.path.join(working_dir, "master.xml")

    if not os.path.isfile(master_file):

        raise FileNotFoundError(f"master.xml not found: {master_file}")

    output_file = os.path.join(working_dir, "statistics.html")

    return write_statistics_html_file(master_file, output_file)





def main() -> int:

    working_dir = load_working_directory_from_settings()

    if not working_dir:

        print(

            "Error: Set working_directory in app_settings.json (same file the GUI uses).",

            file=sys.stderr,

        )

        return 1

    if not os.path.isdir(working_dir):

        print(f"Error: Working directory not found: {working_dir}", file=sys.stderr)

        return 1



    try:

        out = build_statistics_html(working_dir)

    except FileNotFoundError as exc:

        print(f"Error: {exc}", file=sys.stderr)

        return 1

    print(f"Wrote {out}")

    return 0





if __name__ == "__main__":

    raise SystemExit(main())


