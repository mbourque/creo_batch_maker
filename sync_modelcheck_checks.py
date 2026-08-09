#!/usr/bin/env python3
"""
Synchronize custom ModelCHECK checks from report XML into companion JavaScript.

Check names come from ``CHECK`` lines in ``config/custom_checks.txt``::

    DEF_<name> …
    CHECK CHK_<name>_ASM

``CHECK CHK_<name>_ASM`` (or ``_PRT`` / ``_DRW``) syncs the XML/JS check
``CHK_<name>`` — the type suffix is stripped — and only scans matching reports
(``_ASM`` → ``*.a.xml``, ``_PRT`` → ``*.p.xml``, ``_DRW`` → ``*.d.xml``).
Multiple ``CHECK`` lines are all synced. ``DEF_`` lines select which
``chk_<name>.py`` scripts run at report time; this sync tool keys off ``CHECK`` only.

The report folder is ``working_directory`` from ``app_settings.json`` next to this script
(no command-line path argument).

- Scans ``*.a.xml`` / ``*.p.xml`` / ``*.d.xml`` per CHECK type suffix (no recurse).
- Ignores XML files that do not contain any configured check.
- Updates only the companion ``.js`` file (e.g. ``model.a.xml`` → ``model.a.js``).
- If the companion ``.js`` has no block for that check (ModelCHECK never emitted the
  CUSTOM stub), skips quietly — common when Python inserted the check into XML only.
- Does not modify XML or HTML.
- Does not create backups.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


_PRO_SUFFIX_TO_XML = {
    "_ASM": ".a.xml",
    "_PRT": ".p.xml",
    "_DRW": ".d.xml",
}
_DOCTYPE_RE = re.compile(r"<!DOCTYPE\b[\s\S]*?\]\s*>", re.IGNORECASE)
# ModelCHECK sometimes embeds binary junk in <info2> (illegal in XML 1.0).
_ILLEGAL_XML_CHARS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


@dataclass(frozen=True)
class SyncJob:
    """One CHECK line: XML/JS check name plus which report files to scan."""

    xml_name: str
    file_suffix: str  # .a.xml / .p.xml / .d.xml


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


def split_check_token(token: str) -> tuple[str, str]:
    """
    ``CHK_<name>_ASM`` → (``CHK_<name>``, ``.a.xml``).

    Requires a trailing ``_ASM`` / ``_PRT`` / ``_DRW`` suffix.
    """
    name = token.strip()
    upper = name.upper()
    for suf, file_suffix in _PRO_SUFFIX_TO_XML.items():
        if upper.endswith(suf):
            return name[: -len(suf)], file_suffix
    raise ValueError(
        f"CHECK name must end with _ASM, _PRT, or _DRW (got {token!r})"
    )


def load_sync_jobs(path: Path) -> list[SyncJob]:
    """
    Read ``CHECK <name>`` lines from custom_checks.txt.

    Strips ``_ASM`` / ``_PRT`` / ``_DRW`` for the XML/JS name and records which
    report files to scan. Other lines are ignored.
    """
    if not path.is_file():
        raise FileNotFoundError(f"custom checks file not found: {path}")

    jobs: list[SyncJob] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        parts = line.split()
        if parts[0].upper() != "CHECK" or len(parts) < 2:
            continue
        xml_name, file_suffix = split_check_token(parts[1])
        if not xml_name:
            continue
        key = f"{xml_name.casefold()}|{file_suffix.casefold()}"
        if key in seen:
            continue
        seen.add(key)
        jobs.append(SyncJob(xml_name=xml_name, file_suffix=file_suffix))
    return jobs


def iter_report_xml_files(
    report_dir: Path, suffixes: set[str] | None = None
) -> list[Path]:
    """
    List ModelCHECK report XML in report_dir (not recursive).

    ``suffixes`` is lower-case endings such as ``{".a.xml"}``.
    When None, all ``.a.xml`` / ``.p.xml`` / ``.d.xml`` are included.
    """
    allowed = suffixes or {".a.xml", ".p.xml", ".d.xml"}
    found: dict[str, Path] = {}
    try:
        entries = list(report_dir.iterdir())
    except OSError as exc:
        raise OSError(f"Cannot list {report_dir}: {exc}") from exc

    for path in entries:
        if not path.is_file():
            continue
        name = path.name.casefold()
        if any(name.endswith(suf) for suf in allowed):
            found[name] = path
    return sorted(found.values(), key=lambda p: p.name.casefold())


def jobs_for_xml_file(xml_path: Path, jobs: list[SyncJob]) -> list[SyncJob]:
    """Jobs whose CHECK type suffix matches this report file."""
    name = xml_path.name.casefold()
    return [job for job in jobs if name.endswith(job.file_suffix.casefold())]


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
    """Parse ModelCHECK XML; strip DOCTYPE subset and illegal control characters."""
    cleaned = _DOCTYPE_RE.sub("", text, count=1)
    cleaned = _ILLEGAL_XML_CHARS_RE.sub("", cleaned)
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


def update_report(xml_path: Path, check: ET.Element, check_name: str) -> str:
    """
    Sync one check from XML into companion JS.

    Returns ``"ok"``, ``"skip"`` (no JS block to update), or ``"error"``.
    """
    # model.a.xml → model.a.js (with_suffix replaces only the final .xml)
    js_path = xml_path.with_suffix(".js")

    if not js_path.is_file():
        print(f"ERROR     {xml_path.name}: missing {js_path.name}", file=sys.stderr)
        return "error"

    try:
        javascript = js_path.read_text(encoding="utf-8-sig")
        block = find_block(javascript, check_name)

        if block is None:
            # XML has the check (often inserted by chk_*.py) but ModelCHECK never
            # wrote a matching CUSTOM block into the .js — nothing to sync.
            return "skip"

        start, end, index, render_type, check_top = block

        updated = (
            javascript[:start]
            + build_block(check, index, render_type, check_top)
            + javascript[end:]
        )

        if updated != javascript:
            temp_path = js_path.with_name(js_path.name + ".tmp")
            temp_path.write_text(updated, encoding="utf-8", newline="")
            temp_path.replace(js_path)

        return "ok"

    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR     {js_path.name}: {exc}", file=sys.stderr)
        return "error"


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

    checks_file = custom_checks_path()
    try:
        jobs = load_sync_jobs(checks_file)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Could not read {checks_file}: {exc}", file=sys.stderr)
        return 2

    if not jobs:
        print(
            f"No CHECK entries found in {checks_file}",
            file=sys.stderr,
        )
        return 2

    matched = 0
    synchronized = 0
    skipped = 0
    errors = 0

    try:
        needed = {job.file_suffix.casefold() for job in jobs}
        xml_files = iter_report_xml_files(report_dir, needed)
    except OSError as exc:
        print(f"Could not list report folder: {exc}", file=sys.stderr)
        return 2

    for xml_path in xml_files:
        file_jobs = jobs_for_xml_file(xml_path, jobs)
        if not file_jobs:
            continue

        try:
            text = read_xml_text(xml_path)
        except OSError as exc:
            print(f"ERROR     {xml_path.name}: {exc}", file=sys.stderr)
            errors += 1
            continue

        if not any(job.xml_name in text for job in file_jobs):
            continue

        try:
            root = parse_mc_xml(text)
        except ET.ParseError as exc:
            print(f"ERROR     {xml_path.name}: invalid XML: {exc}", file=sys.stderr)
            errors += 1
            continue

        for job in file_jobs:
            check = find_check(root, job.xml_name)
            if check is None:
                continue

            matched += 1
            result = update_report(xml_path, check, job.xml_name)
            if result == "ok":
                synchronized += 1
            elif result == "skip":
                skipped += 1
            else:
                errors += 1

    if errors:
        print(
            f"sync_modelcheck_checks: {synchronized} ok, {skipped} skipped, "
            f"{errors} error(s) ({matched} check occurrences).",
            file=sys.stderr,
        )
        return 1

    if skipped:
        print(
            f"sync_modelcheck_checks: ok "
            f"({synchronized} synchronized, {skipped} skipped — no JS block)."
        )
    else:
        print(f"sync_modelcheck_checks: ok ({synchronized} synchronized).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
