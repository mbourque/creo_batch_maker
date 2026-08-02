#!/usr/bin/env python3
"""
Synchronize custom ModelCHECK checks from report XML into companion JavaScript.

Check names come from ``CHECK`` lines in ``config/custom_checks.txt``::

    DEF_<name> …
    CHECK CHK_<name>_ASM

``CHECK CHK_<name>_ASM`` (or ``_PRT`` / ``_DRW``) syncs the XML/JS check
``CHK_<name>`` — the type suffix is stripped. Multiple ``CHECK`` lines are all
synced. ``DEF_`` lines select which ``chk_<name>.py`` scripts run at report time;
this sync tool keys off ``CHECK`` only.

The report folder is ``working_directory`` from ``app_settings.json`` next to this script
(no command-line path argument).

- Scans only ``*.a.xml`` / ``*.p.xml`` / ``*.d.xml`` (no recurse).
- Ignores XML files that do not contain any configured check.
- Updates only the companion ``.js`` file (e.g. ``model.a.xml`` → ``model.a.js``).
- Does not modify XML or HTML.
- Does not create backups.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


_PRO_SUFFIXES = ("_ASM", "_PRT", "_DRW")
_REPORT_SUFFIXES = (".a.xml", ".p.xml", ".d.xml")
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\b[\s\S]*?\]\s*>", re.IGNORECASE)


def custom_checks_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "custom_checks.txt"


def app_settings_path() -> Path:
    return Path(__file__).resolve().parent / "app_settings.json"


def load_working_directory(path: Path) -> Path:
    """Read ``working_directory`` from ``app_settings.json``."""
    if not path.is_file():
        raise FileNotFoundError(f"app settings not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid app settings (expected object): {path}")

    raw = str(data.get("working_directory") or "").strip()
    if not raw:
        raise ValueError(f"working_directory is empty in {path}")

    return Path(raw).expanduser().resolve()


def xml_check_name_from_check_token(token: str) -> str:
    """``CHK_<name>_ASM`` (or ``_PRT`` / ``_DRW``) → ``CHK_<name>``."""
    name = token.strip()
    upper = name.upper()
    for suf in _PRO_SUFFIXES:
        if upper.endswith(suf):
            return name[: -len(suf)]
    return name


def load_check_names(path: Path) -> list[str]:
    """
    Read ``CHECK <name>`` lines from custom_checks.txt → XML/JS check names.

    Strips trailing ``_ASM`` / ``_PRT`` / ``_DRW`` so names match report XML.
    Other lines (``DEF_``, ``CND_``, ``MSG_``, comments) are ignored.
    """
    if not path.is_file():
        raise FileNotFoundError(f"custom checks file not found: {path}")

    names: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        parts = line.split()
        if parts[0].upper() != "CHECK" or len(parts) < 2:
            continue
        check_name = xml_check_name_from_check_token(parts[1])
        if not check_name:
            continue
        key = check_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(check_name)
    return names


def iter_report_xml_files(report_dir: Path) -> list[Path]:
    """List ``*.a.xml`` / ``*.p.xml`` / ``*.d.xml`` in report_dir (not recursive)."""
    found: dict[str, Path] = {}
    try:
        entries = list(report_dir.iterdir())
    except OSError as exc:
        raise OSError(f"Cannot list {report_dir}: {exc}") from exc

    for path in entries:
        if not path.is_file():
            continue
        name = path.name.casefold()
        if name.endswith(_REPORT_SUFFIXES):
            found[name] = path
    return sorted(found.values(), key=lambda p: p.name.casefold())


def read_xml_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if b"\x00" in data[:200]:
        try:
            return data.decode("utf-16")
        except UnicodeError:
            pass
    return data.decode("utf-8", errors="replace")


def parse_mc_xml(text: str) -> ET.Element:
    """Parse ModelCHECK XML; strip internal DOCTYPE subset that breaks ElementTree."""
    cleaned = _DOCTYPE_RE.sub("", text, count=1)
    return ET.fromstring(cleaned)


def xml_value(node: ET.Element, name: str) -> str | None:
    child = node.find(name)
    return (child.text or "") if child is not None else node.get(name)


def js_string(value: str | None) -> str:
    if value is None:
        return "null"

    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )

    return f'"{escaped}"'


def find_check(root: ET.Element, check_name: str) -> ET.Element | None:
    want = check_name.casefold()
    for check in root.findall("./mc_checks/check"):
        name = check.get("name") or ""
        if name.casefold() == want:
            return check
    return None


def build_items(check: ET.Element) -> str:
    items = list(check.findall("./item"))
    items.extend(check.findall("./items/item"))

    if not items:
        return "null"

    rows: list[str] = []

    for item in items:
        args = [
            js_string(xml_value(item, "info1")),
            js_string(xml_value(item, "info2")),
        ]

        update_message = xml_value(item, "update_message")
        update_status = xml_value(item, "update_status")

        if update_message is not None or update_status is not None:
            args.extend(
                [
                    js_string(update_message),
                    js_string(update_status),
                ]
            )

        rows.append(f"new mcItem({', '.join(args)})")

    return "new Array(\n        " + ",\n        ".join(rows) + "\n    )"


def find_block(javascript: str, check_name: str) -> tuple[int, int, str, str, str] | None:
    # Prefer mcCheckTop ("CHK_…") so we do not latch onto an earlier string match.
    top_pat = re.compile(
        rf'new\s+mcCheckTop\s*\(\s*"{re.escape(check_name)}"',
        re.IGNORECASE,
    )
    top_m = top_pat.search(javascript)
    if top_m is not None:
        name_pos = top_m.start()
    else:
        name_pos = javascript.find(f'"{check_name}"')
        if name_pos < 0:
            return None

    starts = list(
        re.finditer(
            r"^check\[(\d+)\]\s*=",
            javascript[:name_pos],
            re.MULTILINE,
        )
    )

    if not starts:
        raise ValueError(f"Could not find start of JavaScript check block for {check_name}.")

    start_match = starts[-1]
    block_start = start_match.start()
    index = start_match.group(1)

    remaining = javascript[start_match.end() :]

    end_match = re.search(
        r"^(?:check\[\d+\]\s*=|count\s*=)",
        remaining,
        re.MULTILINE,
    )

    if end_match is None:
        raise ValueError(f"Could not find end of JavaScript check block for {check_name}.")

    block_end = start_match.end() + end_match.start()
    block = javascript[block_start:block_end]

    prefix_match = re.search(
        r"new\s+mcCheck\s*\(\s*"
        r"(?P<render_type>[^,]+?)\s*,\s*"
        r"(?P<check_top>new\s+mcCheckTop\s*\(.*?\))\s*,",
        block,
        re.DOTALL,
    )

    if prefix_match is None:
        raise ValueError(f"Could not parse JavaScript check block for {check_name}.")

    return (
        block_start,
        block_end,
        index,
        prefix_match.group("render_type").strip(),
        prefix_match.group("check_top").strip(),
    )


def build_block(
    check: ET.Element,
    index: str,
    render_type: str,
    check_top: str,
) -> str:
    status = (xml_value(check, "stat") or "").strip().upper()

    if status not in {"PASS", "ERROR", "WARNING", "INFO"}:
        raise ValueError(f"Unsupported status: {status!r}")

    return (
        f"check[{index}] = new mcCheck(\n"
        f"    {render_type},\n"
        f"    {check_top},\n"
        f"    {js_string(status)},\n"
        f"    {js_string(xml_value(check, 'desc'))},\n"
        f"    {js_string(xml_value(check, 'msg'))},\n"
        f"    {js_string(xml_value(check, 'ans'))},\n"
        f"    {js_string(xml_value(check, 'title1'))},\n"
        f"    {js_string(xml_value(check, 'title2'))},\n"
        f"    {js_string(xml_value(check, 'func'))},\n"
        f"    {js_string(xml_value(check, 'func_str'))},\n"
        f"    {build_items(check)}\n"
        f")\n\n"
    )


def update_report(xml_path: Path, check: ET.Element, check_name: str) -> bool:
    # model.a.xml → model.a.js (with_suffix replaces only the final .xml)
    js_path = xml_path.with_suffix(".js")

    if not js_path.is_file():
        print(f"ERROR     {xml_path.name}: missing {js_path.name}")
        return False

    try:
        javascript = js_path.read_text(encoding="utf-8-sig")
        block = find_block(javascript, check_name)

        if block is None:
            print(f"ERROR     {js_path.name}: {check_name} not found")
            return False

        start, end, index, render_type, check_top = block

        updated = (
            javascript[:start]
            + build_block(check, index, render_type, check_top)
            + javascript[end:]
        )

        status = xml_value(check, "stat") or ""
        result = xml_value(check, "ans") or ""

        if updated == javascript:
            print(
                f"UNCHANGED {js_path.name} "
                f"(from {xml_path.name}, {check_name}): "
                f"status={status}, result={result}"
            )
            return True

        temp_path = js_path.with_name(js_path.name + ".tmp")
        temp_path.write_text(updated, encoding="utf-8", newline="")
        temp_path.replace(js_path)

        print(
            f"UPDATED   {js_path.name} "
            f"(from {xml_path.name}, {check_name}): "
            f"status={status}, result={result}"
        )
        return True

    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR     {js_path.name}: {exc}")
        return False


def main() -> int:
    if len(sys.argv) != 1:
        print(
            "Usage: python sync_modelcheck_checks.py\n"
            "Uses working_directory from app_settings.json next to this script.",
            file=sys.stderr,
        )
        return 2

    settings_path = app_settings_path()
    try:
        report_dir = load_working_directory(settings_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not read working directory from {settings_path}: {exc}", file=sys.stderr)
        return 2

    if not report_dir.is_dir():
        print(f"Working directory not found: {report_dir}", file=sys.stderr)
        return 2

    print(f"Working directory:  {report_dir}")
    print(f"(from {settings_path})")
    print()

    checks_file = custom_checks_path()
    try:
        check_names = load_check_names(checks_file)
    except (OSError, UnicodeError) as exc:
        print(f"Could not read {checks_file}: {exc}", file=sys.stderr)
        return 2

    if not check_names:
        print(
            f"No CHECK entries found in {checks_file}",
            file=sys.stderr,
        )
        return 2

    print(f"Custom checks file: {checks_file}")
    print(f"Syncing: {', '.join(check_names)}")
    print()

    check_bytes = [name.encode("ascii", errors="ignore") for name in check_names]

    matched = 0
    synchronized = 0
    errors = 0

    try:
        xml_files = iter_report_xml_files(report_dir)
    except OSError as exc:
        print(f"Could not list report folder: {exc}", file=sys.stderr)
        return 2

    for xml_path in xml_files:
        try:
            text = read_xml_text(xml_path)
        except OSError as exc:
            print(f"ERROR     {xml_path.name}: {exc}")
            errors += 1
            continue

        raw_probe = text.encode("utf-8", errors="ignore")
        if not any(needle and needle in raw_probe for needle in check_bytes):
            # Also allow direct substring on decoded text (non-ASCII names).
            if not any(name in text for name in check_names):
                continue

        try:
            root = parse_mc_xml(text)
        except ET.ParseError as exc:
            print(f"ERROR     {xml_path.name}: invalid XML: {exc}")
            errors += 1
            continue

        for check_name in check_names:
            check = find_check(root, check_name)
            if check is None:
                continue

            matched += 1

            if update_report(xml_path, check, check_name):
                synchronized += 1
            else:
                errors += 1

    print()
    print(f"Check occurrences found:   {matched}")
    print(f"Successfully synchronized: {synchronized}")
    print(f"Errors:                    {errors}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
