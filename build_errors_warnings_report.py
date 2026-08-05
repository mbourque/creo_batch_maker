"""
Build an HTML errors/warnings report from master.xml and model_checks.xml.

Uses ``report_template.html.j2`` and ``model_checks.xml`` from the same folder as
this script (the project / app bundle). Only ``master.xml`` is read from the
working directory you pass in.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import html
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from urllib.parse import quote

import markdown
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw

from make_html_statistics import _MQ_STATS_CSS, generate_statistics_fragment
from make_html_summary import (
    _MQ_DASHBOARD_CSS,
    generate_adjusted_summary_shell,
    get_category_descriptions,
    scan_visible_issue_summary,
)


def _app_bundle_dir() -> str:
    """Sidecar files live beside main.exe (dev: beside this .py), not under PyInstaller _MEI temp."""
    if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _direct_child_ans(check_el: ET.Element) -> ET.Element | None:
    for child in check_el:
        if child.tag == "ans":
            return child
    return None


def _check_item_details(check_el: ET.Element, limit: int = 5) -> tuple[list[str], bool]:
    """Return up to ``limit`` non-empty item rows built from their ``info#`` values."""
    details: list[str] = []
    total = 0
    for item in check_el.findall("item"):
        values = [
            (child.text or "").strip()
            for child in item
            if re.fullmatch(r"info\d+", child.tag, flags=re.IGNORECASE)
            and (child.text or "").strip()
        ]
        if not values:
            continue
        total += 1
        if len(details) < limit:
            details.append(" · ".join(values))
    return details, total > limit


def _ans_element_is_empty(ans_el: ET.Element | None) -> bool:
    """True for missing ``<ans>``, ``<ans />``, or ``<ans></ans>``."""
    if ans_el is None:
        return True
    if (ans_el.text or "").strip():
        return False
    return not "".join(ans_el.itertext()).strip()


def _ans_text_from_element(ans_el: ET.Element | None) -> str:
    if _ans_element_is_empty(ans_el):
        return ""
    return "".join(ans_el.itertext()).strip()


def _info_ans_is_reportable(ans: str, *, ans_empty: bool = False) -> bool:
    """False for empty ``<ans>`` / ``<ans />``, zero, negative, NA, NO, or NOT FOUND INFO answers."""
    if ans_empty:
        return False
    text = (ans or "").strip()
    if not text or text == "0":
        return False
    upper = text.upper()
    if upper in ("NA", "NO", "NOT FOUND"):
        return False
    try:
        return float(text.replace(",", "")) > 0.0
    except ValueError:
        return True


def _mb_from_file_size_check(check_el: ET.Element) -> float | None:
    """Creo FILE_SIZE check: <ans> is size in bytes when it is all digits."""
    ans_el = _direct_child_ans(check_el)
    if ans_el is None or not ans_el.text:
        return None
    text = ans_el.text.strip()
    if not text.isdigit():
        return None
    return round(int(text) / (1024 * 1024), 2)


def _format_file_size_bytes(raw_bytes: str) -> str | None:
    """Format Creo's byte count as MB, or GB for files at least 1 GiB."""
    text = (raw_bytes or "").strip()
    if not text.isdigit():
        return None
    size_bytes = int(text)
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f} GB"
    return f"{size_bytes / (1024**2):.2f} MB"


_ISSUE_SORT_NON_NUMERIC = frozenset(
    {"NA", "NO", "NOT FOUND", "YES", "PASS", "Y", "N", "TRUE", "FALSE"}
)
_ISSUE_SORT_SIZE_RE = re.compile(
    r"^(?P<num>[-+]?\d+(?:[.,]\d+)?)\s*(?P<unit>Ki?B|Mi?B|Gi?B|Ti?B|bytes?|B)\s*$",
    re.IGNORECASE,
)
_ISSUE_SORT_SIZE_MULT = {
    "B": 1.0,
    "BYTE": 1.0,
    "BYTES": 1.0,
    "KB": 1024.0,
    "KIB": 1024.0,
    "MB": 1024.0**2,
    "MIB": 1024.0**2,
    "GB": 1024.0**3,
    "GIB": 1024.0**3,
    "TB": 1024.0**4,
    "TIB": 1024.0**4,
}


def _issue_sort_metric(ans: str) -> float | None:
    """
    Numeric value for ordering models within a check (highest first).

    Plain numbers and sizes like ``12.34 MB`` count; labels such as NA / YES do not.
    """
    text = (ans or "").strip()
    if not text:
        return None
    if text.upper() in _ISSUE_SORT_NON_NUMERIC:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        pass
    m = _ISSUE_SORT_SIZE_RE.match(text)
    if not m:
        return None
    try:
        num = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    unit = (m.group("unit") or "").upper()
    mult = _ISSUE_SORT_SIZE_MULT.get(unit)
    if mult is None:
        return None
    return num * mult


def _sort_issue_files(files: list[dict]) -> list[dict]:
    """Highest useful ``ans`` first; rows without a number fall back to display name."""

    def sort_key(row: dict) -> tuple:
        metric = row.get("sort_metric")
        if metric is None:
            metric = _issue_sort_metric(str(row.get("ans") or ""))
        name = (row.get("display_name") or "").casefold()
        if metric is None:
            return (1, 0.0, name)
        return (0, -float(metric), name)

    return sorted(files, key=sort_key)


def _file_size_header_is_zero(size_text: str) -> bool:
    t = (size_text or "").strip()
    if not t:
        return True
    if t.lower().endswith(" mb"):
        num = t[:-3].strip()
        try:
            return float(num) == 0.0
        except ValueError:
            return True
    return False


def _pro_type_ext(pro_type: str) -> str:
    pt = (pro_type or "").strip().upper()
    if pt == "ASM":
        return ".ASM"
    return ".PRT"


def _normalize_family_instance_key(name: str, *, default_ext: str = ".PRT") -> str:
    """Map FAMILY_INFO instance labels to a Model-tag style key (uppercase, with extension)."""
    s = (name or "").strip()
    if not s:
        return ""
    up = s.upper()
    if up.endswith((".PRT", ".ASM", ".DRW")):
        return up
    return up + default_ext


def _family_info_instance_lookup_keys(info1_text: str, *, default_ext: str = ".PRT") -> list[str]:
    """
    Normalized lookup keys for one FAMILY_INFO ``info1`` value.

    Creo often uses ``parent|instance`` (see ``title1`` Instance|Verified|…). Register the
    full label and each pipe segment so ``<Model>`` tags match simple or nested instances.
    """
    raw = (info1_text or "").strip()
    if not raw:
        return []
    keys: list[str] = []
    seen: set[str] = set()

    def add(part: str) -> None:
        key = _normalize_family_instance_key(part, default_ext=default_ext)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    add(raw)
    if "|" in raw:
        for segment in raw.split("|"):
            segment = segment.strip()
            if segment:
                add(segment)
    return keys


def build_family_instance_to_generic_map(root: ET.Element) -> dict[str, str]:
    """
    For each generic model in master.xml, map family-table instance names (from FAMILY_INFO
  items) to that generic's ``<Model>`` value.
    """
    instance_to_generic: dict[str, str] = {}
    for file_element in root.findall("File"):
        model_el = file_element.find("Model")
        if model_el is None or not (model_el.text or "").strip():
            continue
        generic_model = model_el.text.strip()
        pro_type_el = file_element.find("ProType")
        default_ext = _pro_type_ext(pro_type_el.text if pro_type_el is not None else "PRT")

        family = None
        for check in file_element.findall(".//check"):
            if (check.get("name") or "") == "FAMILY_INFO":
                family = check
                break
        if family is None:
            continue

        ans_el = family.find("ans")
        ans = (ans_el.text or "").strip().upper() if ans_el is not None else ""
        if "GENERIC" not in ans:
            continue

        for item in family.findall("item"):
            info1 = item.find("info1")
            if info1 is None or not (info1.text or "").strip():
                continue
            for key in _family_info_instance_lookup_keys(info1.text, default_ext=default_ext):
                instance_to_generic[key] = generic_model

    return instance_to_generic


def _family_info_is_instance(file_element: ET.Element) -> bool:
    for check in file_element.findall(".//check"):
        if (check.get("name") or "") != "FAMILY_INFO":
            continue
        ans_el = check.find("ans")
        ans = (ans_el.text or "").strip().upper() if ans_el is not None else ""
        return "INSTANCE" in ans
    return False


def build_working_dir_file_index(working_dir: str) -> dict[str, str]:
    """Map casefolded basename -> absolute path for files in ``working_dir``."""
    idx: dict[str, str] = {}
    wd = os.path.normpath(os.path.abspath(working_dir))
    try:
        for fn in os.listdir(wd):
            full = os.path.join(wd, fn)
            if os.path.isfile(full):
                idx[fn.casefold()] = full
    except OSError:
        pass
    return idx


def model_file_exists_on_disk(
    working_dir: str,
    model_tag: str,
    xml_path: str,
    *,
    file_index: dict[str, str] | None = None,
) -> bool:
    """True if the Creo model file exists (path from master.xml or under working_dir)."""
    if xml_path:
        if os.path.isfile(xml_path):
            return True
        try:
            if os.path.isfile(os.path.normpath(xml_path)):
                return True
        except OSError:
            pass

    model_tag = (model_tag or "").strip()
    if not model_tag:
        return False

    wd = os.path.normpath(os.path.abspath(working_dir))
    direct = os.path.join(wd, model_tag)
    if os.path.isfile(direct):
        return True

    stem, ext = os.path.splitext(model_tag)
    if ext:
        for variant in (ext, ext.lower(), ext.upper()):
            p = os.path.join(wd, stem + variant)
            if os.path.isfile(p):
                return True
        if file_index is None:
            pattern = os.path.join(wd, stem + ext + ".*")
            if glob.glob(pattern):
                return True
        else:
            prefix = (stem + ext).casefold()
            for key, full in file_index.items():
                if key.startswith(prefix) and key != prefix:
                    return True

    want = model_tag.casefold()
    if file_index is not None:
        return want in file_index
    try:
        for fn in os.listdir(wd):
            if fn.casefold() == want:
                full = os.path.join(wd, fn)
                if os.path.isfile(full):
                    return True
    except OSError:
        pass
    return False


def model_tag_to_display_name(model_tag: str) -> str:
    base, ext = os.path.splitext((model_tag or "").strip())
    if ext:
        return base + ext.lower()
    return (model_tag or "").strip().lower()


def _parse_duplicate_models_check(check: ET.Element) -> dict | None:
    """Extract preview lines from DUPLICATE_MODELS (func_str + item info1 names)."""
    if (check.get("name") or "") != "DUPLICATE_MODELS":
        return None
    func_str_el = check.find("func_str")
    func_str = (func_str_el.text or "").strip() if func_str_el is not None else ""
    if not func_str:
        func_str = "Preview the model :"
    models: list[str] = []
    for item in check.findall("item"):
        info1 = (item.findtext("info1") or "").strip()
        if info1:
            models.append(info1)
    if not models:
        return None
    return {"func_str": func_str, "models": models}


def build_duplicate_models_detail_html(
    duplicate_models: dict,
    *,
    jump_display_names: set[str],
) -> str:
    """HTML lines: ``func_str`` + linked model name (in-report jump when the model is listed)."""
    func_str = (duplicate_models.get("func_str") or "Preview the model :").strip()
    prefix = html.escape(func_str)
    if not prefix.endswith(" "):
        prefix += " "
    lines: list[str] = []
    for raw_name in duplicate_models.get("models") or []:
        jump_name = model_tag_to_display_name(raw_name)
        visible = html.escape(raw_name)
        if jump_name.casefold() in jump_display_names:
            link = (
                f'<button type="button" class="mq-bom-jump mq-duplicate-model-jump" '
                f'data-mq-model-jump="{html.escape(jump_name, quote=True)}">{visible}</button>'
            )
        else:
            link = f'<span class="model-name-plain">{visible}</span>'
        lines.append(f'<p class="mq-duplicate-preview-line">{prefix}{link}</p>')
    return "\n".join(lines)


def collect_report_model_jump_names(files_info: dict) -> set[str]:
    """Casefolded display names for models that appear as issue rows (jump targets)."""
    names: set[str] = set()
    for file_path, file_info in files_info.items():
        display = get_display_name(file_path)
        if display:
            names.add(display.casefold())
        report_display = file_info.get("report_display_name")
        if report_display:
            names.add(report_display.casefold())
        model_tag = (file_info.get("model") or "").strip()
        if model_tag:
            names.add(model_tag_to_display_name(model_tag).casefold())
    return names


def resolve_report_display_name(
    *,
    working_dir: str,
    file_path: str,
    file_info: dict,
    family_map: dict[str, str],
    file_index: dict[str, str] | None = None,
) -> str:
    """
    Display / thumbnail / detail HTML name for the report.

    When the instance ``<Model>`` file is missing on disk but master.xml lists it as a
    family-table instance, use the generic ``<Model>`` from the matching FAMILY_INFO table.
    """
    model_tag = (file_info.get("model") or "").strip()
    xml_path = (file_info.get("path") or "").strip()
    display = get_display_name(file_path)
    if not model_tag:
        return display
    # Family-table fallback is only for part/assembly models.
    if model_tag.upper().endswith(".DRW"):
        return display

    if model_file_exists_on_disk(working_dir, model_tag, xml_path, file_index=file_index):
        return display

    if not file_info.get("family_is_instance"):
        return display

    key = _normalize_family_instance_key(model_tag)
    generic_model = family_map.get(key)
    if not generic_model:
        stem_key = _normalize_family_instance_key(os.path.splitext(model_tag)[0])
        generic_model = family_map.get(stem_key)
    if not generic_model:
        return display

    generic_display = model_tag_to_display_name(generic_model)
    if model_file_exists_on_disk(working_dir, generic_model, "", file_index=file_index):
        return generic_display
    return display


def _parse_master_root(root: ET.Element) -> dict:
    files_info: dict = {}

    for file_element in root.findall("File"):
            file_info = {
                "path": file_element.find("Path").text if file_element.find("Path") is not None else "",
                "model": file_element.find("Model").text if file_element.find("Model") is not None else "",
                "pro_type": file_element.find("ProType").text if file_element.find("ProType") is not None else "",
                "date": file_element.find("Date").text if file_element.find("Date") is not None else "",
                "last_saved": file_element.find("LastSaved").text if file_element.find("LastSaved") is not None else "",
                "created": file_element.find("Created").text if file_element.find("Created") is not None else "",
                "file_size": file_element.find("FileSize").text if file_element.find("FileSize") is not None else "",
                "num_features": file_element.find("NumFeatures").text if file_element.find("NumFeatures") is not None else "",
                "overall_size": file_element.find("OverallSize").text if file_element.find("OverallSize") is not None else "",
                "units_length": file_element.find("UnitsLength").text if file_element.find("UnitsLength") is not None else "",
                "checks": [],
                "family_is_instance": _family_info_is_instance(file_element),
            }

            for check in file_element.findall(".//check"):
                hide_from_report = check.find("hideFromReport")
                if hide_from_report is not None and (hide_from_report.text or "").strip() == "Y":
                    continue

                stat_el = check.find("stat")
                stat = stat_el.text if stat_el is not None else ""
                name = check.get("name") or ""
                desc_el = check.find("desc")
                msg_el = check.find("msg")
                desc = desc_el.text if desc_el is not None else ""
                msg = msg_el.text if msg_el is not None else ""
                ans_el = _direct_child_ans(check)
                ans_empty = _ans_element_is_empty(ans_el)
                ans = _ans_text_from_element(ans_el)
                sort_metric: float | None = None
                if name == "FILE_SIZE":
                    if ans.isdigit():
                        sort_metric = float(ans)
                    formatted = _format_file_size_bytes(ans)
                    if formatted:
                        ans = formatted
                    elif sort_metric is None:
                        sort_metric = _issue_sort_metric(ans)
                else:
                    sort_metric = _issue_sort_metric(ans)
                condensed_msg = f"{msg.strip()} {ans}" if msg and ans else msg.strip()

                check_entry: dict = {
                    "stat": stat,
                    "name": name,
                    "desc": desc,
                    "ans": ans,
                    "ans_empty": ans_empty,
                    "sort_metric": sort_metric,
                    "condensed_msg": condensed_msg,
                }
                duplicate_models = _parse_duplicate_models_check(check)
                if duplicate_models is not None:
                    check_entry["duplicate_models"] = duplicate_models
                elif stat in ("ERROR", "WARNING", "INFO"):
                    item_details, item_details_truncated = _check_item_details(check)
                    check_entry["item_details"] = item_details
                    check_entry["item_details_truncated"] = item_details_truncated
                file_info["checks"].append(check_entry)

            if _file_size_header_is_zero(file_info["file_size"]):
                for chk in file_element.findall(".//check"):
                    if (chk.get("name") or "") != "FILE_SIZE":
                        continue
                    mb = _mb_from_file_size_check(chk)
                    if mb is not None:
                        file_info["file_size"] = f"{mb} MB"
                        break

            files_info[file_info["path"]] = file_info

    return files_info


def read_master_xml(master_xml_file: str, working_dir: str | None = None) -> dict:
    try:
        tree = ET.parse(master_xml_file)
        root = tree.getroot()
        family_map = build_family_instance_to_generic_map(root)
        files_info = _parse_master_root(root)
        if working_dir:
            wd = os.path.normpath(os.path.abspath(working_dir))
            file_index = build_working_dir_file_index(wd)
            for file_path, file_info in files_info.items():
                file_info["report_display_name"] = resolve_report_display_name(
                    working_dir=wd,
                    file_path=file_path,
                    file_info=file_info,
                    family_map=family_map,
                    file_index=file_index,
                )
        return files_info
    except ET.ParseError as e:
        print(f"Error parsing master XML file {master_xml_file}: {e}")
        return {}


def get_display_name(file_path: str) -> str:
    if file_path.endswith(".p.xml"):
        return file_path.split(os.sep)[-1].replace(".p.xml", ".prt")
    if file_path.endswith(".a.xml"):
        return file_path.split(os.sep)[-1].replace(".a.xml", ".asm")
    if file_path.endswith(".d.xml"):
        return file_path.split(os.sep)[-1].replace(".d.xml", ".drw")
    return file_path.split(os.sep)[-1]


# Single JPEG next to the report for all “no preview” thumbnails (avoids per-model files).
_SHARED_PLACEHOLDER_JPEG = "_mc_no_preview.jpg"

def more_info_html_basename(display_name: str) -> str:
    return re.sub(
        r"\.(prt|asm|drw)$",
        lambda m: f".{m.group(1)[0]}.html",
        display_name,
        flags=re.IGNORECASE,
    )


# Characters Windows rejects in file names; Creo detail HTML often omits or replaces them.
_WIN_FILENAME_BAD = re.compile(r'[<>:"|?*\\/]+')


def _detail_type_letter(display_name: str) -> str | None:
    m = re.search(r"\.(prt|asm|drw)$", display_name, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1)[0].upper()


def _model_stem(display_name: str) -> str | None:
    m = re.search(r"\.(prt|asm|drw)$", display_name, flags=re.IGNORECASE)
    if not m:
        return None
    return display_name[: m.start()]


def _alnum_fold(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


def _sanitize_model_stem(stem: str) -> str:
    t = _WIN_FILENAME_BAD.sub("_", stem)
    t = re.sub(r"_+", "_", t).strip("_")
    return t or "model"


_DETAIL_HTML_RE = re.compile(r"^(.+)\.(P|A|D)\.html$", flags=re.IGNORECASE)


def build_more_info_name_index(working_dir: str) -> dict[str, list[str]]:
    """
    Map alphanumeric-only stem fold -> list of ``*.P.html`` / ``*.A.html`` / ``*.D.html``
    basenames in ``working_dir`` (for matching when Creo renames illegal characters).
    """
    idx: dict[str, list[str]] = defaultdict(list)
    try:
        names = os.listdir(working_dir)
    except OSError:
        return {}
    for name in names:
        m = _DETAIL_HTML_RE.match(name)
        if not m:
            continue
        idx[_alnum_fold(m.group(1))].append(name)
    return idx


def resolve_more_info_link(
    working_dir: str, display_name: str, name_index: dict[str, list[str]]
) -> str | None:
    """
    Relative URL (``./`` + percent-encoded basename) to the ModelCHECK detail HTML
    next to the report, or ``None`` if no matching file exists.

    Creo may write ``model.P.html`` while the logical name contains ``<<>>``,
    which Windows cannot store; we try the logical basename, a sanitized stem,
    then a unique match on alphanumeric stem fold.
    """
    letter = _detail_type_letter(display_name)
    stem = _model_stem(display_name)
    if not letter or stem is None:
        return None

    logical = more_info_html_basename(display_name)
    full = os.path.join(working_dir, logical)
    if os.path.isfile(full):
        return "./" + quote(logical)

    safe_stem = _sanitize_model_stem(stem)
    cand = f"{safe_stem}.{letter}.html"
    full2 = os.path.join(working_dir, cand)
    if os.path.isfile(full2):
        return "./" + quote(cand)

    matches = [n for n in name_index.get(_alnum_fold(stem), []) if n.upper().endswith(f".{letter}.HTML")]
    if len(matches) == 1:
        return "./" + quote(matches[0])
    if len(matches) > 1:
        for n in matches:
            m = _DETAIL_HTML_RE.match(n)
            if m and m.group(1).lower() == safe_stem.lower():
                return "./" + quote(n)
        matches.sort(key=len)
        return "./" + quote(matches[0])

    try:
        names = os.listdir(working_dir)
    except OSError:
        return None
    low = logical.lower()
    for fn in names:
        if fn.lower() == low:
            return "./" + quote(fn)
    return None


def name_has_creo_path_ref(display_name: str) -> bool:
    """True for Creo session / generic table names that are not safe as plain ``file:`` links."""
    if "<<" in display_name and ">>" in display_name:
        return True
    if "[[" in display_name and "]]" in display_name:
        return True
    return False


# Inseparable assemblies use double angle brackets (``<<>>``).
# Family-table instances use single brackets (``<>``) / FAMILY_INFO — not handled here.
_CREO_BARE_INSEP_RE = re.compile(
    r"^<<(?P<inner>.+?)>>(?P<ext>\.(?:prt|asm|drw))$",
    re.IGNORECASE,
)
_CREO_COMPOUND_INSEP_RE = re.compile(
    r"^(?P<outer>.+?)<<(?P<inner>.+?)>>(?P<ext>\.(?:prt|asm|drw))$",
    re.IGNORECASE,
)


def creo_angle_file_target(display_name: str) -> str | None:
    """
    Drag / open basename for an inseparable-assembly ``<<>>`` name.

    - ``parent<<child>>.ext`` → ``child.asm`` (no angle brackets)
    - ``<<child>>.ext`` → ``child.asm``
    - otherwise ``None`` (family-table single ``<>`` is not handled here)
    """
    parsed = inseparable_angle_names(display_name)
    return parsed[1] if parsed else None


def inseparable_angle_names(display_name: str) -> tuple[str, str] | None:
    """
    ``(label_file, drag_file)`` for inseparable ``<<>>`` names.

    - ``parent<<child>>.prt`` → ``(parent.prt, child.asm)``
    - ``<<child>>.ext`` → ``(child.asm, child.asm)``
    """
    raw = (display_name or "").strip()
    if not raw:
        return None
    bare = _CREO_BARE_INSEP_RE.match(raw)
    if bare:
        inner = (bare.group("inner") or "").strip()
        if inner:
            target = f"{inner}.asm"
            return (target, target)
        return None
    compound = _CREO_COMPOUND_INSEP_RE.match(raw)
    if compound:
        outer = (compound.group("outer") or "").strip()
        inner = (compound.group("inner") or "").strip()
        ext = compound.group("ext").lower()
        if outer and inner:
            return (outer + ext, f"{inner}.asm")
    return None


def split_creo_angle_session_name(display_name: str) -> tuple[str, str] | None:
    """
    ``parent<<child>>.ext`` → ``(parent.ext, child.ext)``.

    Prefer ``inseparable_angle_names`` / ``creo_angle_file_target`` for report links.
    """
    m = _CREO_COMPOUND_INSEP_RE.match((display_name or "").strip())
    if not m:
        return None
    outer = (m.group("outer") or "").strip()
    inner = (m.group("inner") or "").strip()
    ext = m.group("ext").lower()
    if not outer or not inner:
        return None
    return (outer + ext, inner + ext)


def resolve_drag_and_image_names(
    *,
    file_path: str,
    file_info: dict,
) -> tuple[str, str, str]:
    """
    ``(label_name, drag_name, image_name)`` for issue rows and Model Gallery.

    Inseparable ``parent<<child>>.ext`` → label ``parent.ext``; drag and thumb
    ``child.asm``. Otherwise use ``report_display_name`` (family-table generic
    fallback via FAMILY_INFO).
    """
    path_display = (get_display_name(file_path) or "").strip()
    model_display = model_tag_to_display_name((file_info.get("model") or "").strip())
    report_display = (file_info.get("report_display_name") or path_display or "").strip()

    session = ""
    for candidate in (model_display, path_display, report_display):
        if candidate and inseparable_angle_names(candidate):
            session = candidate
            break

    if session:
        parts = inseparable_angle_names(session)
        if parts:
            label_file, drag_file = parts
            return (label_file, drag_file, drag_file)

    label = report_display or path_display or model_display
    return (label, label, label)


def build_model_href(display_name: str) -> str:
    """URL path for the Creo model link (percent-encoded)."""
    return "./" + quote(display_name)


def model_file_link_href(display_name: str) -> str | None:
    """
    Relative ``./`` link for drag-into-Creo.

    Inseparable ``<<>>`` names use ``creo_angle_file_target``. Other session-style
    names (``[[]]``) return ``None``. Family-table single ``<>`` is not mapped here.
    """
    target = creo_angle_file_target(display_name)
    if target:
        return build_model_href(target)
    if name_has_creo_path_ref(display_name):
        return None
    return build_model_href(display_name)


def display_name_link_text(original_display_name: str, drag_image_display_name: str) -> str:
    """
    Link label shown in the report.

    When family-table fallback swaps drag/image behavior to a generic model, show
    ``instance<generic>`` so readers can tell the row is an instance.

    Inseparable rows use label ``parent.ext`` with thumb/drag ``child.asm`` — show
    the label only (not ``parent.ext<child.asm>``).
    """
    if (
        original_display_name
        and drag_image_display_name
        and original_display_name.casefold() != drag_image_display_name.casefold()
    ):
        orig_ext = re.search(
            r"\.(prt|asm|drw)$", original_display_name, flags=re.IGNORECASE
        )
        img_ext = re.search(
            r"\.(prt|asm|drw)$", drag_image_display_name, flags=re.IGNORECASE
        )
        if (
            orig_ext
            and img_ext
            and orig_ext.group(1).lower() != img_ext.group(1).lower()
            and "<<" not in original_display_name
        ):
            return original_display_name
        return f"{original_display_name}<{drag_image_display_name}>"
    return original_display_name


def safe_file_list_id(check_name: str, model: str) -> str:
    """HTML id / fragment; must not contain characters that break CSS selectors or the DOM."""
    raw = f"{check_name}_{model.replace(os.sep, '_')}"
    if re.search(r"[^A-Za-z0-9_.\-]", raw):
        h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
        return f"mc_{h}"
    return raw


def _section_heading_entity_word(files: list[dict]) -> str:
    """``Drawing`` when every row is a drawing; otherwise ``Model``."""
    pro_types = {(f.get("pro_type") or "").strip().upper() for f in files}
    pro_types.discard("")
    if pro_types == {"DRW"}:
        return "Drawing"
    return "Model"


def _section_ans_total(files: list[dict]) -> int | None:
    """
    Sum of numeric ModelCHECK ``ans`` values across models in a check section.

    Used in the section heading as ``(N Total)``. Skips non-numeric answers
    (YES/NA) and size strings (``12 MB``). Returns ``None`` when nothing to sum.
    """
    total = 0.0
    found = False
    for row in files:
        ans = str(row.get("ans") or "").strip()
        if not ans:
            continue
        if _ISSUE_SORT_SIZE_RE.match(ans):
            continue
        try:
            value = float(ans.replace(",", ""))
        except ValueError:
            continue
        if value < 0:
            continue
        found = True
        total += value
    if not found:
        return None
    return int(round(total))


def get_check_descriptions(model_checks_file: str) -> dict:
    tree = ET.parse(model_checks_file)
    root = tree.getroot()
    descriptions: dict = {}
    for check in root.findall("Check"):
        hide_from_report = check.find("hideFromReport")
        if hide_from_report is not None and (hide_from_report.text or "").strip() == "Y":
            continue

        mcn = check.find("ModelCheckName")
        if mcn is None or not (mcn.text or "").strip():
            continue
        model_check_name = mcn.text.strip()
        name_el = check.find("Name")
        desc_el = check.find("Description")
        cat_el = check.find("Category")
        why_element = check.find("why")
        name = name_el.text if name_el is not None else ""
        description = desc_el.text if desc_el is not None else ""
        category = cat_el.text if cat_el is not None else ""
        why = why_element.text if why_element is not None else ""
        descriptions[model_check_name] = {
            "name": name,
            "description": description,
            "category": category,
            "why": markdown.markdown(why or ""),
        }
    return descriptions


def get_info_check_names(model_checks_file: str) -> frozenset[str]:
    """ModelCheckName values marked ``<info_check>Y</info_check>`` in model_checks.xml."""
    tree = ET.parse(model_checks_file)
    names: set[str] = set()
    for check in tree.getroot().findall("Check"):
        hide_from_report = check.find("hideFromReport")
        if hide_from_report is not None and (hide_from_report.text or "").strip() == "Y":
            continue
        info_el = check.find("info_check")
        if info_el is None or (info_el.text or "").strip().upper() != "Y":
            continue
        mcn = check.find("ModelCheckName")
        if mcn is not None and (mcn.text or "").strip():
            names.add(mcn.text.strip())
    return frozenset(names)


def _section_stat_type_from_dict_key(check_key: str) -> str:
    if check_key.startswith("INFO:"):
        return "INFO"
    if "ERROR" in check_key:
        return "ERRORS"
    return "WARNINGS"


def create_placeholder_image(output_path: str, width: int = 300, height: int = 231) -> None:
    img = Image.new("RGB", (width, height), color="#e0e0e0")
    draw = ImageDraw.Draw(img)
    text = "No Preview Available"
    try:
        draw.text((width / 2, height / 2), text, fill="#666666", anchor="mm", align="center")
    except OSError as e:
        print(f"Warning: Could not add text to placeholder: {e}")
    img.save(output_path, "JPEG", quality=95)


def ensure_shared_placeholder_jpeg(assets_folder: str) -> str:
    """Write ``_mc_no_preview.jpg`` once if missing (used only for ``<<`` / ``>>`` model names)."""
    path = os.path.join(assets_folder, _SHARED_PLACEHOLDER_JPEG)
    if not os.path.isfile(path):
        try:
            create_placeholder_image(path)
        except OSError as e:
            print(f"Warning: Could not create shared placeholder image {_SHARED_PLACEHOLDER_JPEG}: {e}")
    return _SHARED_PLACEHOLDER_JPEG


def thumbnail_basename_for_model(display_name: str, pro_type: str = "") -> str | None:
    """Report thumbnail filename: ``stem.part.jpg``, ``stem.assembly.jpg``, or ``stem.drawing.jpg``."""
    stem = _model_stem(display_name)
    if stem is None:
        return None
    kind = (pro_type or "").strip().upper()
    if not kind:
        m = re.search(r"\.(prt|asm|drw)$", display_name, flags=re.IGNORECASE)
        kind = m.group(1).upper() if m else ""
    if kind == "DRW":
        return f"{stem}.drawing.jpg"
    if kind == "ASM":
        return f"{stem}.assembly.jpg"
    return f"{stem}.part.jpg"


def _thumbnail_report_candidates(display_name: str, pro_type: str = "") -> list[str]:
    """Preferred thumbnail basenames for the report (new names first, then legacy)."""
    primary = thumbnail_basename_for_model(display_name, pro_type)
    if primary is None:
        return []
    stem = _model_stem(display_name)
    if stem is None:
        return [primary]
    kind = (pro_type or "").strip().upper()
    if not kind:
        m = re.search(r"\.(prt|asm|drw)$", display_name, flags=re.IGNORECASE)
        kind = m.group(1).upper() if m else ""
    candidates = [primary]
    if kind in ("PRT", "ASM"):
        legacy = f"{stem}.model.jpg"
        if legacy not in candidates:
            candidates.append(legacy)
    return candidates


def thumbnail_src_for_report(
    report_assets_dir: str,
    working_dir: str,
    display_name: str,
    *,
    pro_type: str = "",
) -> str:
    """
    Return a value suitable for ``<img src="…">`` (relative to the report HTML).

    - Inseparable thumbs use ``child.asm`` (same as drag); label text is ``parent.ext``.
      If a session ``<<>>`` name is passed, lookup uses ``creo_angle_file_target`` /
      bracket-stripped basenames.
    - Other session refs (``[[]]``) use the shared placeholder.
    - Parts use ``stem.part.jpg``; assemblies ``stem.assembly.jpg``; drawings ``stem.drawing.jpg``.
    - Legacy ``stem.model.jpg`` is used when type-specific files are missing.
    - If no thumbnail exists, use the same shared placeholder so the report always shows a thumb.
    """
    report_assets_dir = os.path.abspath(report_assets_dir)
    working_dir = os.path.normpath(os.path.abspath(working_dir))

    def _placeholder_src() -> str:
        ensure_shared_placeholder_jpeg(report_assets_dir)
        return "./" + quote(_SHARED_PLACEHOLDER_JPEG)

    lookup_names: list[str] = []
    angle_target = creo_angle_file_target(display_name)
    if angle_target:
        lookup_names.append(angle_target)
        stripped = angle_target.replace("<<", "").replace(">>", "")
        if stripped and stripped not in lookup_names:
            lookup_names.append(stripped)
        # Inseparable targets are assemblies even when the session label ends in .prt
        if angle_target.lower().endswith(".asm"):
            pro_type = "ASM"
    elif name_has_creo_path_ref(display_name):
        return _placeholder_src()
    else:
        lookup_names.append(display_name)
        # Remapped inseparable thumb is already ``child.asm`` (no brackets).
        if display_name.lower().endswith(".asm"):
            pro_type = "ASM"

    for lookup in lookup_names:
        jpg_candidates = _thumbnail_report_candidates(lookup, pro_type)
        for jpg_base in jpg_candidates:
            for folder in (report_assets_dir, working_dir):
                full = os.path.join(folder, jpg_base)
                if not os.path.isfile(full):
                    continue
                if os.path.normcase(os.path.normpath(folder)) == os.path.normcase(
                    report_assets_dir
                ):
                    return "./" + quote(jpg_base)
                rel = os.path.relpath(full, report_assets_dir).replace("\\", "/")
                return "./" + quote(rel, safe="/")

    return _placeholder_src()


_GALLERY_TYPE_ORDER = {"PRT": 0, "ASM": 1, "DRW": 2}
_GALLERY_TYPE_LABELS = {"PRT": "Parts", "ASM": "Assemblies", "DRW": "Drawings"}
_EMPTY_DSUMM_PHRASES = frozenset(
    {
        "no errors found.",
        "no warnings found.",
    }
)
_DSUMM_SUFFIX_TO_EXT = {
    ".p.dsumm.xml": ".prt",
    ".a.dsumm.xml": ".asm",
    ".d.dsumm.xml": ".drw",
}


def _fix_bare_ampersands(text: str) -> str:
    """ModelCHECK often writes ``GD&T``; make bare ``&`` legal for XML parsers."""
    return re.sub(r"&(?![#a-zA-Z0-9]+;)", "&amp;", text)


def _xml_root_from_path(path: str) -> ET.Element | None:
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        pass
    try:
        with open(path, "rb") as f:
            raw = f.read().decode("utf-8", errors="ignore")
        raw = re.sub(r"[^\x20-\x7E\n\r\t]", "", raw)
        raw = _fix_bare_ampersands(raw)
        return ET.fromstring(raw)
    except (ET.ParseError, OSError, ValueError):
        return None


def _first_xml_text(root: ET.Element, *tags: str) -> str:
    for tag in tags:
        el = root.find(tag)
        if el is not None and (el.text or "").strip():
            return (el.text or "").strip()
        el = root.find(f".//{tag}")
        if el is not None and (el.text or "").strip():
            return (el.text or "").strip()
    return ""


def parse_dsumm_summary(path: str) -> dict | None:
    """Read ModelCHECK detail-summary counts and error/warning lines from a dsumm XML."""
    root = _xml_root_from_path(path)
    if root is None:
        return None

    title = _first_xml_text(root, "mdlname", "hdrmodelname", "model")
    try:
        num_errors = int(_first_xml_text(root, "numerr") or "0")
    except ValueError:
        num_errors = 0
    try:
        num_warnings = int(_first_xml_text(root, "numwrn") or "0")
    except ValueError:
        num_warnings = 0

    errors: list[str] = []
    seen_err: set[str] = set()
    for err in root.findall(".//err-section/errdata"):
        info = err.find("einfo")
        text = (info.text or "").strip() if info is not None else ""
        if text and text.casefold() not in _EMPTY_DSUMM_PHRASES:
            if text.casefold() not in seen_err:
                seen_err.add(text.casefold())
                errors.append(text)

    warnings: list[str] = []
    seen_wrn: set[str] = set()
    for wrn in root.findall(".//wrn-section/wrndata"):
        info = wrn.find("winfo")
        text = (info.text or "").strip() if info is not None else ""
        if text and text.casefold() not in _EMPTY_DSUMM_PHRASES:
            if text.casefold() not in seen_wrn:
                seen_wrn.add(text.casefold())
                warnings.append(text)

    return {
        "title": title,
        "num_errors": num_errors,
        "num_warnings": num_warnings,
        "errors": errors,
        "warnings": warnings,
    }


def build_dsumm_summary_by_model(working_dir: str) -> dict[str, dict]:
    """Load every ``*.p.dsumm.xml`` / ``*.a.dsumm.xml`` / ``*.d.dsumm.xml`` in ``working_dir``.

    Keys are casefolded model names from the file (``mdlname``) and from the
    filename (``0-ring.p.dsumm.xml`` → ``0-ring.prt``). Does not use master.xml.
    """
    out: dict[str, dict] = {}
    wd = os.path.normpath(os.path.abspath(working_dir))
    try:
        names = os.listdir(wd)
    except OSError:
        return {}

    for name in names:
        low = name.lower()
        ext = None
        for suffix, model_ext in _DSUMM_SUFFIX_TO_EXT.items():
            if low.endswith(suffix):
                ext = model_ext
                stem = name[: -len(suffix)]
                break
        if ext is None:
            continue
        path = os.path.join(wd, name)
        try:
            if not os.path.isfile(path):
                continue
        except OSError:
            continue
        summary = parse_dsumm_summary(path)
        if not summary:
            continue
        title = (summary.get("title") or "").strip()
        file_model = f"{stem}{ext}"
        if not title:
            summary = dict(summary)
            summary["title"] = file_model
            title = file_model
        out[title.casefold()] = summary
        out[file_model.casefold()] = summary
    return out


def collect_model_gallery_items(
    files_info: dict,
    report_assets_dir: str,
    working_dir: str,
) -> list[dict]:
    """Unique scanned models for the gallery, ordered PRT → ASM → DRW, then name.

    Missing thumbs use the shared blank placeholder (same as issue rows).
    Popup text comes only from sibling ``*.dsumm.xml`` files (not master.xml).
    """
    seen: set[tuple[str, str]] = set()
    items: list[dict] = []
    dsumm_by_model = build_dsumm_summary_by_model(working_dir)
    for file_path, file_info in files_info.items():
        label_name, drag_name, image_name = resolve_drag_and_image_names(
            file_path=file_path, file_info=file_info
        )
        if not label_name:
            continue
        pro_type = (file_info.get("pro_type") or "").strip().upper()
        if not pro_type:
            m = re.search(r"\.(prt|asm|drw)$", label_name, flags=re.IGNORECASE)
            if not m:
                m = re.search(r"\.(prt|asm|drw)$", image_name, flags=re.IGNORECASE)
            pro_type = m.group(1).upper() if m else ""
        if pro_type not in _GALLERY_TYPE_ORDER:
            continue
        key = (label_name.casefold(), pro_type)
        if key in seen:
            continue
        seen.add(key)
        href = model_file_link_href(drag_name) or ""
        src = thumbnail_src_for_report(
            report_assets_dir, working_dir, image_name, pro_type=pro_type
        )
        dsumm = dsumm_by_model.get(label_name.casefold())
        if dsumm is None:
            dsumm = dsumm_by_model.get(drag_name.casefold())
        if dsumm is None:
            dsumm = dsumm_by_model.get(image_name.casefold())
        if dsumm is None:
            model_tag = (file_info.get("model") or "").strip()
            if model_tag:
                dsumm = dsumm_by_model.get(model_tag.casefold())
        if dsumm is None:
            dsumm = {
                "title": label_name,
                "num_errors": 0,
                "num_warnings": 0,
                "errors": [],
                "warnings": [],
                "missing": True,
            }
        else:
            dsumm = dict(dsumm)
            if not dsumm.get("title"):
                dsumm["title"] = label_name
        items.append(
            {
                "name": label_name,
                "pro_type": pro_type,
                "href": href,
                "image_url": src,
                "dsumm": dsumm,
            }
        )
    items.sort(
        key=lambda row: (
            _GALLERY_TYPE_ORDER.get(row["pro_type"], 9),
            row["name"].casefold(),
        )
    )
    return items


def _gallery_card_html(row: dict) -> str:
    name_esc = html.escape(row["name"])
    name_attr = html.escape(row["name"], quote=True)
    src_esc = html.escape(row["image_url"], quote=True)
    tip = "Click for ModelCHECK summary · Drag into Creo"
    tip_attr = html.escape(tip, quote=True)
    dsumm_json = html.escape(
        json.dumps(row.get("dsumm") or {}, ensure_ascii=False, separators=(",", ":")),
        quote=True,
    )
    img = (
        f'<img loading="lazy" decoding="async" draggable="false" '
        f'title="{tip_attr}" src="{src_esc}" alt="">'
    )
    name_html = f'<span class="mq-gallery-name">{name_esc}</span>'
    if row["href"]:
        href_esc = html.escape(row["href"], quote=True)
        return (
            f'<a class="mq-gallery-card" href="{href_esc}" '
            f'data-mq-gallery-name="{name_attr}" data-mq-dsumm="{dsumm_json}" '
            f'title="{tip_attr}" onclick="void(0); return false;">'
            f"{img}{name_html}</a>"
        )
    plain_tip = html.escape(
        "Click for ModelCHECK summary. No file link: session-style model name "
        "(not used as a file URL).",
        quote=True,
    )
    return (
        f'<div class="mq-gallery-card mq-gallery-card-plain" '
        f'data-mq-gallery-name="{name_attr}" data-mq-dsumm="{dsumm_json}" '
        f'title="{plain_tip}">{img}{name_html}</div>'
    )


def generate_model_gallery_fragment(
    files_info: dict,
    report_assets_dir: str,
    working_dir: str,
) -> str:
    """Sidebar Model Gallery panel HTML, or empty when no scanned models exist."""
    ensure_shared_placeholder_jpeg(report_assets_dir)
    items = collect_model_gallery_items(files_info, report_assets_dir, working_dir)
    if not items:
        return ""

    by_type: dict[str, list[dict]] = {"PRT": [], "ASM": [], "DRW": []}
    other: list[dict] = []
    for item in items:
        bucket = by_type.get(item["pro_type"])
        if bucket is None:
            other.append(item)
        else:
            bucket.append(item)

    sections: list[str] = []
    for pro_type in ("PRT", "ASM", "DRW"):
        rows = by_type[pro_type]
        if not rows:
            continue
        label = _GALLERY_TYPE_LABELS[pro_type]
        cards = [_gallery_card_html(row) for row in rows]
        sections.append(
            f'<section class="mq-gallery-section" data-mq-gallery-type="{pro_type}">'
            f'<h2><span class="mq-gallery-count">{len(rows)}</span> {html.escape(label)}</h2>'
            f'<div class="mq-gallery-grid">{"".join(cards)}</div>'
            "</section>"
        )

    if other:
        cards = [_gallery_card_html(row) for row in other]
        sections.append(
            '<section class="mq-gallery-section" data-mq-gallery-type="OTHER">'
            f'<h2><span class="mq-gallery-count">{len(other)}</span> Other</h2>'
            f'<div class="mq-gallery-grid">{"".join(cards)}</div>'
            "</section>"
        )

    body = "".join(sections)
    type_buttons: list[str] = []
    for pro_type in ("PRT", "ASM", "DRW"):
        if not by_type[pro_type]:
            continue
        label = _GALLERY_TYPE_LABELS[pro_type]
        type_buttons.append(
            f'<button type="button" class="mq-gallery-type-btn" '
            f'data-mq-gallery-type="{pro_type}" aria-pressed="false">'
            f"{html.escape(label)}</button>"
        )
    toggles_html = ""
    if len(type_buttons) >= 2:
        toggles_html = f"""
      <div class="mq-gallery-type-toggles" role="group" aria-label="Model type filter">
        <button type="button" class="mq-gallery-type-btn" data-mq-gallery-type="all"
                aria-pressed="true">Show all</button>
        {"".join(type_buttons)}
      </div>"""
    # Bake-size marker so a rebuilt report can be distinguished from a stale index.html.
    dsumm_hits = sum(1 for row in items if not (row.get("dsumm") or {}).get("missing"))
    return f"""<div class="mq-stats-page mq-stats-embedded mq-gallery-page" id="mq-model-gallery" data-mq-dsumm-hits="{dsumm_hits}">
  <!-- mq-dsumm-hits:{dsumm_hits} -->
  <h1 class="mq-page-title" id="model-gallery">Model Gallery</h1>
  <p class="mq-gallery-intro">Click a model for its ModelCHECK error and warning summary. Drag a card into Creo to open the file. Use search to find models by name, and the type filters to show all models or only parts, assemblies, or drawings.</p>
  <div class="mq-gallery-toolbar">
    <div class="mq-gallery-toolbar-row">
      <input type="search" id="mq-gallery-search" class="mq-gallery-search"
             placeholder="Search models…" autocomplete="off" spellcheck="false">
{toggles_html}
    </div>
    <p id="mq-gallery-empty" class="mq-gallery-empty" hidden>No models match this search.</p>
  </div>
{body}
</div>"""


def _remove_legacy_hash_placeholders(assets_folder: str) -> None:
    """Remove old per-model ``_mcplaceholder_<hash>.jpg`` files from earlier versions."""
    try:
        names = os.listdir(assets_folder)
    except OSError:
        return
    for name in names:
        if not (name.startswith("_mcplaceholder_") and name.endswith(".jpg")):
            continue
        try:
            os.remove(os.path.join(assets_folder, name))
        except OSError:
            pass


def create_html_report(
    files_info: dict,
    descriptions: dict,
    output_file: str,
    summary: dict,
    *,
    bundle_dir: str,
    working_dir: str,
    master_xml_path: str,
    model_checks_path: str,
) -> None:
    category_descriptions = get_category_descriptions(model_checks_path)
    master_root = ET.parse(master_xml_path).getroot()
    issue_summary = scan_visible_issue_summary(master_root, model_checks_path)
    summary_div = generate_adjusted_summary_shell(
        category_descriptions,
        issue_summary=issue_summary,
    )
    statistics_div = generate_statistics_fragment(
        master_root,
        working_dir,
        master_path=master_xml_path,
        embedded=True,
    )

    env = Environment(loader=FileSystemLoader(bundle_dir))
    template = env.get_template("report_template.html.j2")

    report_assets_dir = os.path.dirname(os.path.abspath(output_file))
    if not report_assets_dir:
        report_assets_dir = os.path.abspath(".")

    model_gallery_div = generate_model_gallery_fragment(
        files_info,
        report_assets_dir,
        working_dir,
    )

    check_sections: list = []
    check_dict: dict = defaultdict(list)
    info_check_names = get_info_check_names(model_checks_path)
    more_info_index = build_more_info_name_index(working_dir)
    ensure_shared_placeholder_jpeg(report_assets_dir)
    thumbnail_cache: dict[str, str] = {}
    jump_display_names = collect_report_model_jump_names(files_info)
    for file_path, file_info in files_info.items():
        original_display_name, drag_name, image_name = resolve_drag_and_image_names(
            file_path=file_path, file_info=file_info
        )
        for check in file_info["checks"]:
            check_name = check["name"]
            description_data = descriptions.get(check_name)

            if not description_data:
                continue

            stat = check["stat"]
            is_issue = stat in ("ERROR", "WARNING")
            is_info = stat == "INFO" and check_name in info_check_names
            if is_info and not _info_ans_is_reportable(
                check.get("ans", ""), ans_empty=check.get("ans_empty", False)
            ):
                continue
            if not is_issue and not is_info:
                continue

            pro_type = (file_info.get("pro_type") or "").strip()
            thumb_key = (image_name, pro_type.casefold())
            if thumb_key not in thumbnail_cache:
                thumbnail_cache[thumb_key] = thumbnail_src_for_report(
                    report_assets_dir,
                    working_dir,
                    image_name,
                    pro_type=pro_type,
                )
            image_url = thumbnail_cache[thumb_key]

            duplicate_detail = ""
            duplicate_models = check.get("duplicate_models")
            if duplicate_models:
                duplicate_detail = build_duplicate_models_detail_html(
                    duplicate_models,
                    jump_display_names=jump_display_names,
                )

            check_dict[f"{stat}: {check_name}"].append(
                {
                    "file_path": file_path,
                    "desc": check["desc"],
                    "ans": check.get("ans", ""),
                    "sort_metric": check.get("sort_metric"),
                    "condensed_msg": check["condensed_msg"],
                    "item_details": check.get("item_details", []),
                    "item_details_truncated": check.get("item_details_truncated", False),
                    "duplicate_models_detail_html": duplicate_detail,
                    "stat": stat,
                    "last_saved": file_info["last_saved"],
                    "created": file_info["created"],
                    "file_size": file_info["file_size"],
                    "num_features": file_info["num_features"],
                    "overall_size": file_info["overall_size"],
                    "units_length": file_info["units_length"],
                    # Label uses parent file; thumb/drag may be inseparable child.asm.
                    "display_name": original_display_name,
                    "display_name_link_text": display_name_link_text(
                        original_display_name, image_name
                    ),
                    "model_href": model_file_link_href(drag_name),
                    "image_url": image_url,
                    # Detail HTML may be keyed to the session ``<<>>`` name, not the label.
                    "more_info_link": resolve_more_info_link(
                        working_dir,
                        (
                            model_tag_to_display_name(
                                (file_info.get("model") or "").strip()
                            )
                            or get_display_name(file_path)
                            or original_display_name
                        ),
                        more_info_index,
                    ),
                    "file_list_id": safe_file_list_id(check_name, file_info.get("model") or ""),
                    "category": description_data["category"],
                    "pro_type": (file_info.get("pro_type") or "").strip().upper(),
                }
            )

    for check_index, (check, files) in enumerate(check_dict.items()):
        check_name = check.split(": ", 1)[1]
        description_data = descriptions.get(check_name)

        if not description_data:
            continue

        sorted_files = _sort_issue_files(files)
        check_sections.append(
            {
                "class": f"check-section-{check_index}",
                "model_check_name": check_name,
                "name": description_data["name"],
                "description": description_data["description"],
                "category": description_data["category"],
                "why": description_data["why"],
                "count": len(sorted_files),
                "entity_word": _section_heading_entity_word(sorted_files),
                "ans_total": _section_ans_total(sorted_files),
                "stat_type": _section_stat_type_from_dict_key(check),
                "files": sorted_files,
            }
        )

    check_sections.sort(key=lambda x: x["name"].casefold())

    rendered_html = template.render(
        check_sections=check_sections,
        summary=summary,
        summary_div=summary_div,
        statistics_div=statistics_div,
        model_gallery_div=model_gallery_div,
        report_panel_styles=_MQ_DASHBOARD_CSS + "\n" + _MQ_STATS_CSS,
    )

    out_dir = os.path.dirname(os.path.abspath(output_file))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    how_to_src = os.path.join(bundle_dir, "report_how_to.html")
    if out_dir and os.path.isfile(how_to_src):
        try:
            shutil.copy2(how_to_src, os.path.join(out_dir, "report_how_to.html"))
        except OSError:
            pass
    _remove_legacy_hash_placeholders(report_assets_dir)
    wd_norm = os.path.normcase(os.path.normpath(working_dir))
    if os.path.normcase(os.path.normpath(report_assets_dir)) != wd_norm:
        _remove_legacy_hash_placeholders(working_dir)


def build_errors_warnings_html(
    working_directory: str,
    *,
    master_basename: str = "master.xml",
    output_html: str | None = None,
) -> str:
    """
    Build the full Model Quality Report HTML (sidebar, sections, embedded summary).

    Uses ``model_checks.xml`` and ``report_template.html.j2`` next to this module.
    Reads ``master.xml`` from the given working folder (or a custom name via
    ``master_basename`` if relative).

    Returns the path to the written HTML file. Raises ``FileNotFoundError`` if
    a required file is missing.
    """
    bundle_dir = _app_bundle_dir()
    working_dir = os.path.normpath(os.path.abspath(working_directory))
    master_xml_file = (
        master_basename
        if os.path.isabs(master_basename)
        else os.path.join(working_dir, master_basename)
    )
    model_checks_file = os.path.join(bundle_dir, "model_checks.xml")
    template_path = os.path.join(bundle_dir, "report_template.html.j2")

    if not os.path.isfile(master_xml_file):
        raise FileNotFoundError(f"master XML not found:\n{master_xml_file}")
    if not os.path.isfile(model_checks_file):
        raise FileNotFoundError(f"model checks XML not found:\n{model_checks_file}")
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"report template not found:\n{template_path}")

    if output_html:
        output_file = (
            output_html if os.path.isabs(output_html) else os.path.join(working_dir, output_html)
        )
    else:
        output_file = os.path.join(working_dir, "index.html")

    files_info = read_master_xml(master_xml_file, working_dir)
    descriptions = get_check_descriptions(model_checks_file)

    warning_count = sum(
        1
        for file_info in files_info.values()
        if any(c["stat"] == "WARNING" for c in file_info["checks"])
    )
    error_count = sum(
        1
        for file_info in files_info.values()
        if any(c["stat"] == "ERROR" for c in file_info["checks"])
    )
    summary = {
        "warning_count": warning_count,
        "error_count": error_count,
        "total_files": len(files_info),
    }

    create_html_report(
        files_info,
        descriptions,
        output_file,
        summary,
        bundle_dir=bundle_dir,
        working_dir=working_dir,
        master_xml_path=master_xml_file,
        model_checks_path=model_checks_file,
    )
    return output_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build HTML errors/warnings report from master.xml (uses bundled model_checks.xml).",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Folder containing master.xml (default: current directory)",
    )
    parser.add_argument(
        "--master",
        default="master.xml",
        help="Master XML file name or absolute path (default: master.xml in directory)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Output HTML path (default: index.html in directory)",
    )
    args = parser.parse_args(argv)

    working_dir = os.path.normpath(os.path.abspath(args.directory))
    try:
        build_errors_warnings_html(
            working_dir,
            master_basename=args.master,
            output_html=args.output,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
