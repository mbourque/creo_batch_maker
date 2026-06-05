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
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from urllib.parse import quote

import markdown
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw

from make_html_summary import generate_adjusted_summary_shell, get_category_descriptions


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


def _mb_from_file_size_check(check_el: ET.Element) -> float | None:
    """Creo FILE_SIZE check: <ans> is size in bytes when it is all digits."""
    ans_el = _direct_child_ans(check_el)
    if ans_el is None or not ans_el.text:
        return None
    text = ans_el.text.strip()
    if not text.isdigit():
        return None
    return round(int(text) / (1024 * 1024), 2)


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


def model_file_exists_on_disk(working_dir: str, model_tag: str, xml_path: str) -> bool:
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
        pattern = os.path.join(wd, stem + ext + ".*")
        if glob.glob(pattern):
            return True

    want = model_tag.casefold()
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


def resolve_report_display_name(
    *,
    working_dir: str,
    file_path: str,
    file_info: dict,
    family_map: dict[str, str],
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

    if model_file_exists_on_disk(working_dir, model_tag, xml_path):
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
    if model_file_exists_on_disk(working_dir, generic_model, ""):
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
                ans_el = check.find("ans")
                desc = desc_el.text if desc_el is not None else ""
                msg = msg_el.text if msg_el is not None else ""
                ans = ans_el.text if ans_el is not None else ""
                condensed_msg = f"{msg.strip()} {ans.strip()}" if msg and ans else msg.strip()

                file_info["checks"].append(
                    {
                        "stat": stat,
                        "name": name,
                        "desc": desc,
                        "condensed_msg": condensed_msg,
                    }
                )

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
            for file_path, file_info in files_info.items():
                file_info["report_display_name"] = resolve_report_display_name(
                    working_dir=wd,
                    file_path=file_path,
                    file_info=file_info,
                    family_map=family_map,
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


def build_model_href(display_name: str) -> str:
    """URL path for the Creo model link (percent-encoded)."""
    return "./" + quote(display_name)


def model_file_link_href(display_name: str) -> str | None:
    """``None`` when the name has Creo session-style ``<<>>`` or ``[[]]`` segments."""
    if name_has_creo_path_ref(display_name):
        return None
    return build_model_href(display_name)


def display_name_link_text(original_display_name: str, drag_image_display_name: str) -> str:
    """
    Link label shown in the report.

    When family-table fallback swaps drag/image behavior to a generic model, show
    ``instance<generic>`` so readers can tell the row is an instance.
    """
    if (
        original_display_name
        and drag_image_display_name
        and original_display_name.casefold() != drag_image_display_name.casefold()
    ):
        return f"{original_display_name}<{drag_image_display_name}>"
    return original_display_name


def safe_file_list_id(check_name: str, model: str) -> str:
    """HTML id / fragment; must not contain characters that break CSS selectors or the DOM."""
    raw = f"{check_name}_{model.replace(os.sep, '_')}"
    if re.search(r"[^A-Za-z0-9_.\-]", raw):
        h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
        return f"mc_{h}"
    return raw


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


def thumbnail_src_for_report(report_assets_dir: str, working_dir: str, display_name: str) -> str:
    """
    Return a value suitable for ``<img src="…">`` (relative to the report HTML).

    - Models with Creo session refs (``<<`` / ``>>``) use the shared placeholder (Windows-safe).
    - Other models use an existing ``.jpg`` next to the report or in ``working_dir`` if found.
    - If no ``.jpg`` exists, use the same shared placeholder so the report always shows a thumb.
    """
    report_assets_dir = os.path.abspath(report_assets_dir)
    working_dir = os.path.normpath(os.path.abspath(working_dir))

    def _placeholder_src() -> str:
        ensure_shared_placeholder_jpeg(report_assets_dir)
        return "./" + quote(_SHARED_PLACEHOLDER_JPEG)

    if name_has_creo_path_ref(display_name):
        return _placeholder_src()

    jpg_base = os.path.basename(
        re.sub(r"\.(prt|asm|drw)$", ".jpg", display_name, flags=re.IGNORECASE)
    )
    if not jpg_base or not jpg_base.lower().endswith(".jpg"):
        return _placeholder_src()

    for folder in (report_assets_dir, working_dir):
        full = os.path.join(folder, jpg_base)
        if not os.path.isfile(full):
            continue
        if os.path.normcase(os.path.normpath(folder)) == os.path.normcase(report_assets_dir):
            return "./" + quote(jpg_base)
        rel = os.path.relpath(full, report_assets_dir).replace("\\", "/")
        return "./" + quote(rel, safe="/")

    return _placeholder_src()


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
    summary_div = generate_adjusted_summary_shell(category_descriptions)

    env = Environment(loader=FileSystemLoader(bundle_dir))
    template = env.get_template("report_template.html.j2")

    report_assets_dir = os.path.dirname(os.path.abspath(output_file))
    if not report_assets_dir:
        report_assets_dir = os.path.abspath(".")

    check_sections: list = []
    check_dict: dict = defaultdict(list)
    more_info_index = build_more_info_name_index(working_dir)
    for file_path, file_info in files_info.items():
        original_display_name = get_display_name(file_path)
        drag_image_display_name = file_info.get("report_display_name") or original_display_name
        for check in file_info["checks"]:
            check_name = check["name"]
            description_data = descriptions.get(check_name)

            if not description_data:
                continue

            if check["stat"] in ("ERROR", "WARNING"):
                image_url = thumbnail_src_for_report(
                    report_assets_dir, working_dir, drag_image_display_name
                )

                check_dict[f"{check['stat']}: {check['name']}"].append(
                    {
                        "file_path": file_path,
                        "desc": check["desc"],
                        "condensed_msg": check["condensed_msg"],
                        "stat": check["stat"],
                        "last_saved": file_info["last_saved"],
                        "created": file_info["created"],
                        "file_size": file_info["file_size"],
                        "num_features": file_info["num_features"],
                        "overall_size": file_info["overall_size"],
                        "units_length": file_info["units_length"],
                        # Keep report text on the original model, but allow drag/image fallback.
                        "display_name": original_display_name,
                        "display_name_link_text": display_name_link_text(
                            original_display_name, drag_image_display_name
                        ),
                        "model_href": model_file_link_href(drag_image_display_name),
                        "image_url": image_url,
                        # Keep detail HTML lookup tied to the original model entry.
                        "more_info_link": resolve_more_info_link(
                            working_dir, original_display_name, more_info_index
                        ),
                        "file_list_id": safe_file_list_id(check_name, file_info.get("model") or ""),
                        "category": description_data["category"],
                    }
                )

    for check_index, (check, files) in enumerate(check_dict.items()):
        check_name = check.split(": ", 1)[1]
        description_data = descriptions.get(check_name)

        if not description_data:
            continue

        check_sections.append(
            {
                "class": f"check-section-{check_index}",
                "name": description_data["name"],
                "description": description_data["description"],
                "category": description_data["category"],
                "why": description_data["why"],
                "count": len(files),
                "stat_type": "ERRORS" if "ERROR" in check else "WARNINGS",
                "files": files,
            }
        )

    check_sections.sort(key=lambda x: x["name"].casefold())

    rendered_html = template.render(
        check_sections=check_sections,
        summary=summary,
        summary_div=summary_div,
    )

    out_dir = os.path.dirname(os.path.abspath(output_file))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    _remove_legacy_hash_placeholders(report_assets_dir)
    wd_norm = os.path.normcase(os.path.normpath(working_dir))
    if os.path.normcase(os.path.normpath(report_assets_dir)) != wd_norm:
        _remove_legacy_hash_placeholders(working_dir)
    print(f"Output file written: {os.path.abspath(output_file)}")


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
