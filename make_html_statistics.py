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

from pathlib import Path

from typing import Any

from make_html_summary import _model_check_category_map








def _app_dir() -> Path:

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


def scan_skipped_models(working_dir: str, master_root: ET.Element) -> list[str]:
    """
    Models in the working folder that did not fully make it into the batch scan.

    Compares latest-rev top-level ``name.ext`` models with matching check XML and
    ``master.xml`` entries. Family-table instances may have check XML but no separate
    ``.prt`` / ``.asm`` on disk; any model listed in ``master.xml`` was scanned and
    is not reported as skipped.
    """
    wd = os.path.normpath(os.path.abspath(working_dir))
    scanned = _scanned_model_keys(master_root)
    xml_on_disk = _check_xml_basenames_in_folder(wd)
    models_on_disk = _latest_logical_models_on_disk(wd)

    skipped: dict[str, str] = {}

    for display_cf in sorted(models_on_disk.keys(), key=lambda k: models_on_disk[k].casefold()):
        display = models_on_disk[display_cf]
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





def find_top_level_assembly(master_root: ET.Element) -> str | None:

    """

    Assembly with no other batch assembly referencing it as a sub-assembly (UNQ_COMPONENTS).

    Tie-break multiple roots by most direct .ASM children in UNQ_COMPONENTS.

    """

    assemblies: dict[str, str] = {}

    child_counts: dict[str, int] = {}

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

        child_counts[key] = len(asm_children)

        for child in asm_children:

            referenced.add(child.upper())



    if not assemblies:

        return None



    roots = [assemblies[k] for k in assemblies if k not in referenced]

    if len(roots) == 1:

        return roots[0]

    if len(roots) > 1:

        return max(roots, key=lambda m: child_counts.get(m.upper(), 0))

    return None





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

    top_features_parts: list[tuple[str, int]] = field(default_factory=list)

    top_size_parts: list[tuple[str, float]] = field(default_factory=list)





def scan_batch_statistics(master_root: ET.Element, *, master_path: str = "") -> BatchStatistics:

    stats = BatchStatistics(master_path=master_path)

    scanned_files: list[ET.Element] = []

    for file_element in master_root.findall("File"):

        if not _file_in_report_scan(file_element):

            continue

        scanned_files.append(file_element)



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



        family = _find_check(file_element, "FAMILY_INFO")

        if family is None:

            continue

        ans = (family.findtext("ans") or "").strip().upper()

        if "GENERIC" in ans:

            names: list[str] = []

            for item in family.findall("item"):

                name = (item.findtext("info1") or "").strip()

                if name:

                    names.append(name)

            stats.family_generics_detail.append(FamilyGenericRow(model=model, instance_names=names))

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

.mq-stat-card h2 { margin: 0 0 12px 0; font-size: 1.05rem; font-weight: 700; color: #0f172a; }

.mq-stat-card p { margin: 5px 0; font-size: 0.92rem; line-height: 1.4; }

.mq-stat-card strong { color: #0f172a; }

.mq-stat-num { font-size: 1.65rem; font-weight: 800; color: #0369a1; line-height: 1.2; }

.mq-stat-label { font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }

.mq-section { background: #fff; border-radius: 12px; padding: 18px 20px;

  box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 16px; }

.mq-section h2 { margin: 0 0 12px 0; font-size: 1.15rem; font-weight: 700; color: #0f172a; }

.mq-section-note { font-size: 0.85rem; color: #475569; margin: 0 0 14px 0; line-height: 1.45; }

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

.mq-inst-names { line-height: 1.45; }

.mq-skipped-names { color: #334155; }

.mq-skipped-rest[hidden] { display: none !important; }

.mq-skipped-more-btn {
  display: inline; border: none; background: none; padding: 0; margin: 0;
  font: inherit; color: #007bff; cursor: pointer;
}

.mq-skipped-more-btn:hover { text-decoration: underline; }

.mq-list-more-wrap { display: inline; }

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

</style>"""





def _esc(text: Any) -> str:

    return html.escape(str(text) if text is not None else "", quote=False)


_LIST_PREVIEW_LIMIT = 20

_FAMILY_TABLE_PREVIEW_LIMIT = 5

_BOM_LIST_PREVIEW_LIMIT = 10


def _comma_separated_list_html(names: list[str], *, span_class: str) -> str:
    """Comma-separated names; first 20 inline, then ``more...`` expands the rest on the same line."""
    if not names:
        return "—"
    if len(names) <= _LIST_PREVIEW_LIMIT:
        return f'<span class="{span_class}">{", ".join(_esc(name) for name in names)}</span>'
    visible = ", ".join(_esc(name) for name in names[:_LIST_PREVIEW_LIMIT])
    rest = ", ".join(_esc(name) for name in names[_LIST_PREVIEW_LIMIT:])
    return (
        f'<span class="{span_class}">{visible}'
        f'<span class="mq-skipped-rest" hidden>, {rest}</span></span>'
        f'<span class="mq-list-more-wrap">, '
        f'<button type="button" class="mq-skipped-more-btn" '
        f'onclick="var w=this.parentElement;var l=w.previousElementSibling;'
        f"var r=l.querySelector(&quot;.mq-skipped-rest&quot;);"
        f"r.removeAttribute(&quot;hidden&quot;);w.remove();\">more...</button></span>"
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


def _bom_row(row: BomComponentRow, *, embedded: bool, collapsed: bool = False) -> str:
    display = _esc(_model_display_lower(row.name))
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
            _bom_row(row, embedded=embedded)
            for row in bom_rows[:_BOM_LIST_PREVIEW_LIMIT]
        ) + "".join(
            _bom_row(row, embedded=embedded, collapsed=True)
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
        rows_html = "".join(_bom_row(row, embedded=embedded) for row in bom_rows)
        more_html = ""

    asm_display = _esc(_model_display_lower(assembly_name))
    note = f"BOM from {asm_display} ({total} components)."
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


def _skipped_models_summary_line(skipped_models: list[str]) -> str:
    """One summary-card line for models skipped in the batch scan."""
    if not skipped_models:
        return ""
    total = len(skipped_models)
    return (
        f"<p><strong>Models skipped ({total}):</strong> "
        f'{_comma_separated_list_html(skipped_models, span_class="mq-skipped-names")}</p>'
    )





def generate_statistics_html(stats: BatchStatistics, *, embedded: bool = False) -> str:

    summary_bits: list[str] = []

    if stats.top_level_assembly:

        top_asm = _esc(_model_display_lower(stats.top_level_assembly))

        summary_bits.append(f"<p><strong>Top level assembly:</strong> {top_asm}</p>")

    if stats.sheetmetal_parts > 0:

        summary_bits.append(f"<p><strong>Sheetmetal parts:</strong> {stats.sheetmetal_parts}</p>")

    if stats.multibody_parts > 0:

        summary_bits.append(f"<p><strong>Multibody parts:</strong> {stats.multibody_parts}</p>")

    if stats.skeleton_models > 0:

        summary_bits.append(f"<p><strong>Skeleton models:</strong> {stats.skeleton_models}</p>")

    skipped_line = _skipped_models_summary_line(stats.skipped_models)

    if skipped_line:

        summary_bits.append(skipped_line)

    summary_grid = ""

    if summary_bits:

        summary_grid = f"""

  <div class="mq-stats-grid">

    <div class="mq-stat-card">

      {''.join(summary_bits)}

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

    <h2>At a glance</h2>

    {''.join(health_rows)}

  </div>"""



    top_feat_rows = "".join(

        f"<tr><td>{_esc(_model_display_lower(m))}</td><td>{n}</td></tr>"
        for m, n in stats.top_features_parts

    )

    top_size_rows = "".join(

        f"<tr><td>{_esc(_model_display_lower(m))}</td><td>{sz:.2f} MB</td></tr>"
        for m, sz in stats.top_size_parts

    )

    complexity_snapshot_section = ""

    if top_feat_rows or top_size_rows:

        snapshot_parts = ['<div class="mq-stats-grid" style="margin-top:4px">']

        if top_feat_rows:

            snapshot_parts.append(f"""

      <div>

        <h3 style="font-size:0.95rem;margin:0 0 8px 0">Top parts by features</h3>

        <table class="mq-table"><thead><tr><th>Model</th><th>Features</th></tr></thead><tbody>{top_feat_rows}</tbody></table>

      </div>""")

        if top_size_rows:

            snapshot_parts.append(f"""

      <div>

        <h3 style="font-size:0.95rem;margin:0 0 8px 0">Top parts by file size</h3>

        <table class="mq-table"><thead><tr><th>Model</th><th>Size</th></tr></thead><tbody>{top_size_rows}</tbody></table>

      </div>""")

        snapshot_parts.append("</div>")

        complexity_snapshot_section = f"""

  <div class="mq-section">

    <h2>Model Complexity</h2>

    {''.join(snapshot_parts)}

  </div>"""



    body_sections = summary_grid + bom_section + health_section + complexity_snapshot_section + family_section

    if not body_sections.strip():

        body_sections = """

  <div class="mq-section">

    <p>No additional statistics for this batch.</p>

  </div>"""

    page_class = "mq-stats-page mq-stats-embedded" if embedded else "mq-stats-page"
    if embedded:
        title_html = '  <h1 class="mq-page-title" id="statistics">Scan Statistics</h1>'
    else:
        title_html = '  <h1 class="mq-stats-title">Scan Statistics</h1>'
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
    stats.skipped_models = scan_skipped_models(working_dir, master_root)
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

    stats.skipped_models = scan_skipped_models(working_dir, root)
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

        "  <title>Scan Statistics</title>\n"

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


