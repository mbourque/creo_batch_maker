#!/usr/bin/env python3
"""
Update custom ModelCHECK placeholder checks in report XML from RELATION_INFO.

Reads ``config/custom_checks.txt`` for the ``DEF_RELATION_MP_MASS`` section::

    DEF_RELATION_MP_MASS RELATION_INFO
    CND_RELATION_MP_MASS GTE 0
    CHECK CHK_RELATION_MP_MASS_PRT
    MSG_RELATION_MP_MASS Legacy relation setting for mp_mass("")

``CHECK`` is the ``*.mch`` row name (4th column W/E). The report XML check is
without the ``_PRT`` suffix (``CHK_RELATION_MP_MASS``).

Only part reports are updated (``_PRT`` → ``*.p.xml``).

Matching is fixed in this script (not in custom_checks.txt):

- Source check: RELATION_INFO
- Look for ``mp_mass`` in ``info1`` / ``info2`` (case-insensitive)
- Found → ``ans=1`` and severity from ``*.mch``; not found → PASS / ``ans=0``

Severity from ``condition.mcc`` → ``*.mch``. Does not modify companion ``.js``
(use ``sync_modelcheck_checks.py`` afterward).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# Owned DEF_ section in config/custom_checks.txt (DEF_RELATION_MP_MASS).
THIS_DEF = "RELATION_MP_MASS"
SOURCE_CHECK = "RELATION_INFO"
SEARCH_TOKEN = "mp_mass"
FILE_SUFFIX = ".p.xml"

CHECK_OPEN_RE = re.compile(
    r"<check\b[^>]*\bname\s*=\s*(?P<q>['\"])(?P<name>[^'\"]+)(?P=q)[^>]*>",
    re.IGNORECASE,
)
CHECK_CLOSE_RE = re.compile(r"</check\s*>", re.IGNORECASE)
ITEM_RE = re.compile(
    r"<item>\s*<info1>\s*([^<]*?)\s*</info1>\s*<info2>\s*([^<]*?)\s*</info2>\s*</item>",
    re.IGNORECASE | re.DOTALL,
)
STAT_RE = re.compile(r"(<stat\b[^>]*>)(.*?)(</stat\s*>)", re.IGNORECASE | re.DOTALL)
ANS_RE = re.compile(r"(<ans\b[^>]*>)(.*?)(</ans\s*>)", re.IGNORECASE | re.DOTALL)
ITEM_BLOCK_RE = re.compile(r"[ \t]*<item\b.*?</item>\s*", re.IGNORECASE | re.DOTALL)
TITLE_BLOCK_RE = re.compile(
    r"[ \t]*<title[12]\b[^>]*>.*?</title[12]\s*>\s*",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class CustomJob:
    """CHECK line is CHK_…_PRT (MCH row); XML check is without the type suffix."""

    mch_name: str
    xml_name: str
    file_suffix: str  # .p.xml
    source_check: str


def split_check_names(check_token: str) -> tuple[str, str, str]:
    """
    CHECK token → (mch_name, xml_name, file_suffix).

    ``CHK_RELATION_MP_MASS_PRT`` → mch that name, XML ``CHK_RELATION_MP_MASS``,
    files ``*.p.xml`` only.
    """
    mch_name = check_token.strip()
    upper = mch_name.upper()
    if not upper.endswith("_PRT"):
        raise ValueError(
            f"CHECK name must end with _PRT for this script (got {check_token!r})"
        )
    return mch_name, mch_name[:-4], FILE_SUFFIX


def app_settings_path() -> Path:
    return ROOT / "app_settings.json"


def custom_checks_path() -> Path:
    return ROOT / "config" / "custom_checks.txt"


def condition_mcc_path() -> Path:
    return ROOT / "config" / "condition.mcc"


def load_working_directory(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"app settings not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid app settings (expected object): {path}")
    raw = str(data.get("working_directory") or "").strip()
    if not raw:
        raise ValueError(f"working_directory is empty in {path}")
    return Path(raw).expanduser().resolve()


def load_custom_jobs(path: Path) -> list[CustomJob]:
    """Load the CHECK name from the ``DEF_RELATION_MP_MASS`` section."""
    if not path.is_file():
        raise FileNotFoundError(f"custom checks file not found: {path}")

    in_section = False
    check_token: str | None = None
    want_def = THIS_DEF.casefold()

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue

        parts = line.split()
        head = parts[0]
        head_u = head.upper()

        if head_u.startswith("DEF_"):
            suffix = head[4:]
            in_section = suffix.casefold() == want_def
            continue

        if not in_section:
            continue

        if head_u == "CHECK" and len(parts) >= 2:
            check_token = parts[1].strip()
            continue

    if not check_token:
        raise ValueError(
            f"No CHECK line in DEF_{THIS_DEF} section of {path}"
        )

    mch_name, xml_name, file_suffix = split_check_names(check_token)
    return [
        CustomJob(
            mch_name=mch_name,
            xml_name=xml_name,
            file_suffix=file_suffix,
            source_check=SOURCE_CHECK,
        )
    ]


def resolve_mch_path(condition_path: Path) -> Path:
    if not condition_path.is_file():
        raise FileNotFoundError(f"condition file not found: {condition_path}")

    text = condition_path.read_text(encoding="utf-8-sig")
    else_mch: str | None = None
    first_mch: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "config=" not in line.casefold():
            continue
        found = re.findall(r"\(([^)]+\.mch)\)", line, flags=re.IGNORECASE)
        if not found:
            continue
        name = found[0].strip()
        if line.upper().startswith("ELSE"):
            else_mch = name
        elif first_mch is None:
            first_mch = name

    mch_name = else_mch or first_mch
    if not mch_name:
        raise ValueError(f"No *.mch config= entry found in {condition_path}")

    mch_path = ROOT / "config" / Path(mch_name).name
    if not mch_path.is_file():
        raise FileNotFoundError(f"check config not found: {mch_path}")
    return mch_path


def severity_from_mch(mch_path: Path, mch_name: str) -> str:
    """
    Look up CHECK name in ``*.mch`` (e.g. CHK_RELATION_MP_MASS_PRT).

    4th column (Batch): E→ERROR, W→WARNING, else PASS.
    """
    want = mch_name.strip().casefold()
    for raw in mch_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        parts = line.split()
        if not parts or parts[0].casefold() != want:
            continue
        if len(parts) < 4:
            raise ValueError(f"MCH line for {mch_name} has fewer than 4 columns: {line}")
        flag = parts[3].strip().upper()
        if flag == "E":
            return "ERROR"
        if flag == "W":
            return "WARNING"
        return "PASS"
    raise ValueError(f"No MCH row for {mch_name} in {mch_path.name}")


def find_check_span(raw_xml: str, check_name: str) -> tuple[int, int, int, int] | None:
    """
    Return (block_start, inner_start, inner_end, block_end) for a named check.

    Works with ``name='…'`` or ``name=\"…\"``; does not require full-file XML parse.
    """
    want = check_name.casefold()
    for open_m in CHECK_OPEN_RE.finditer(raw_xml):
        if open_m.group("name").strip().casefold() != want:
            continue
        close_m = CHECK_CLOSE_RE.search(raw_xml, open_m.end())
        if close_m is None:
            raise ValueError(f"Unclosed <check name={check_name!r}>")
        return open_m.start(), open_m.end(), close_m.start(), close_m.end()
    return None


def mp_mass_items_in_check_inner(inner: str) -> list[tuple[str, str]]:
    """
    RELATION_INFO items whose info1 or info2 contains ``mp_mass``.

    Returns (info1, info2) pairs; presence alone matters (ans is always 1).
    """
    needle = SEARCH_TOKEN.casefold()
    found: list[tuple[str, str]] = []
    for m in ITEM_RE.finditer(inner):
        info1 = m.group(1).strip()
        info2 = m.group(2).strip()
        if needle in info1.casefold() or needle in info2.casefold():
            found.append((info1, info2))
    return found


def mp_mass_items_from_source(raw_xml: str, source_check: str) -> list[tuple[str, str]]:
    span = find_check_span(raw_xml, source_check)
    if span is None:
        return []
    _bs, inner_start, inner_end, _be = span
    return mp_mass_items_in_check_inner(raw_xml[inner_start:inner_end])


def update_check_block(
    raw_xml: str,
    check_name: str,
    stat: str,
    ans: str,
    items: list[tuple[str, str]],
) -> str:
    """Rewrite <stat>, <ans>, optional title1/title2, and <item> rows."""
    span = find_check_span(raw_xml, check_name)
    if span is None:
        raise ValueError(f"check name={check_name!r} not found in XML text")
    _block_start, inner_start, inner_end, _block_end = span
    inner = raw_xml[inner_start:inner_end]

    new_inner, n_stat = STAT_RE.subn(rf"\g<1>{stat}\g<3>", inner, count=1)
    if n_stat == 0:
        raise ValueError(f"No <stat> inside check name={check_name!r}")
    new_inner, n_ans = ANS_RE.subn(rf"\g<1>{ans}\g<3>", new_inner, count=1)
    if n_ans == 0:
        raise ValueError(f"No <ans> inside check name={check_name!r}")

    new_inner = TITLE_BLOCK_RE.sub("", new_inner)
    new_inner = ITEM_BLOCK_RE.sub("", new_inner)
    indent_m = re.search(r"\n([ \t]+)<", new_inner)
    indent = indent_m.group(1) if indent_m else "   "
    extra = ""
    if items:
        extra += (
            f"\n{indent}<title1>Scope</title1>"
            f"\n{indent}<title2>Relation</title2>"
        )
        extra += "".join(
            f"\n{indent}<item><info1>{info1}</info1><info2>{info2}</info2></item>"
            for info1, info2 in items
        )
    ans_close = re.search(r"</ans\s*>", new_inner, re.IGNORECASE)
    if ans_close is None:
        raise ValueError(f"No </ans> inside check name={check_name!r}")
    pos = ans_close.end()
    new_inner = new_inner[:pos] + extra + new_inner[pos:]

    return raw_xml[:inner_start] + new_inner + raw_xml[inner_end:]


def iter_report_xml_files(
    report_dir: Path, suffixes: set[str] | None = None
) -> list[Path]:
    """List ModelCHECK report XML in report_dir (not recursive)."""
    allowed = suffixes or {FILE_SUFFIX}
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


def jobs_for_xml_file(xml_path: Path, jobs: list[CustomJob]) -> list[CustomJob]:
    name = xml_path.name.casefold()
    return [job for job in jobs if name.endswith(job.file_suffix.casefold())]


def read_xml_bytes(path: Path) -> tuple[str, str]:
    """Return (text, encoding) for ModelCHECK XML (utf-8 / utf-8-sig / utf-16)."""
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if b"\x00" in data[:200]:
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeError:
            pass
    return data.decode("utf-8", errors="replace"), "utf-8"


def write_xml_text(path: Path, text: str, encoding: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding, newline="")
    tmp.replace(path)


def process_xml_file(
    xml_path: Path,
    jobs: list[CustomJob],
    mch_path: Path,
) -> tuple[int, int, int]:
    try:
        raw, encoding = read_xml_bytes(xml_path)
    except OSError as exc:
        print(f"ERROR     {xml_path.name}: {exc}")
        return 0, 0, 1

    relevant = [
        job
        for job in jobs_for_xml_file(xml_path, jobs)
        if job.xml_name in raw
    ]
    if not relevant:
        return 0, 0, 0

    updated = 0
    unchanged = 0
    errors = 0
    out = raw

    for job in relevant:
        try:
            if find_check_span(out, job.xml_name) is None:
                print(f"ERROR     {xml_path.name}: {job.xml_name} open/close tags not found")
                errors += 1
                continue

            items = mp_mass_items_from_source(out, job.source_check)
            if find_check_span(out, job.source_check) is None:
                print(
                    f"NOTE      {xml_path.name}: {job.source_check} not found; "
                    f"PASS for {job.xml_name}"
                )

            if not items:
                stat = "PASS"
                ans = "0"
                items = []
            else:
                sev = severity_from_mch(mch_path, job.mch_name)
                stat = "PASS" if sev == "PASS" else sev
                ans = "1"

            new_out = update_check_block(out, job.xml_name, stat, ans, items)
            if new_out == out:
                print(
                    f"OK        {xml_path.name}: {job.xml_name} "
                    f"already stat={stat} ans={ans} (no write)"
                )
                unchanged += 1
            else:
                out = new_out
                detail = "; ".join(f"{a}={b}" for a, b in items) or "none"
                print(
                    f"UPDATED   {xml_path.name}: {job.xml_name} "
                    f"stat={stat} ans={ans} items={detail} (mch {job.mch_name})"
                )
                updated += 1
        except (OSError, ValueError) as exc:
            print(f"ERROR     {xml_path.name}: {job.xml_name}: {exc}")
            errors += 1

    if updated and out != raw:
        try:
            write_xml_text(xml_path, out, encoding)
        except OSError as exc:
            print(f"ERROR     {xml_path.name}: write failed: {exc}")
            return 0, unchanged, errors + 1

    return updated, unchanged, errors


def resolve_report_dir(argv: list[str]) -> Path:
    if len(argv) > 2:
        raise ValueError(
            "Usage: python chk_relation_mp_mass.py [report_dir]\n"
            "  report_dir optional; default is working_directory from app_settings.json"
        )
    if len(argv) == 2:
        return Path(argv[1]).expanduser().resolve()
    return load_working_directory(app_settings_path())


def main() -> int:
    try:
        report_dir = resolve_report_dir(sys.argv)
        jobs = load_custom_jobs(custom_checks_path())
        mch_path = resolve_mch_path(condition_mcc_path())
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    if not report_dir.is_dir():
        print(f"Working directory not found: {report_dir}", file=sys.stderr)
        return 2
    if not jobs:
        print(
            f"No CHECK for DEF_{THIS_DEF} in {custom_checks_path()}",
            file=sys.stderr,
        )
        return 2

    try:
        needed = {job.file_suffix.casefold() for job in jobs}
        xml_files = iter_report_xml_files(report_dir, needed)
    except OSError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    print(f"Working directory: {report_dir}")
    print(f"XML files:         {len(xml_files)}")
    for job in jobs:
        print(
            f"Job: XML {job.xml_name} ← {job.source_check} "
            f"(find {SEARCH_TOKEN!r}); mch {job.mch_name}; "
            f"files *{job.file_suffix}"
        )
    print()

    if not xml_files:
        kinds = ", ".join(sorted(f"*{s}" for s in needed))
        print(
            f"No {kinds} in that folder.\n"
            "Point working_directory at the folder that contains the report XML."
        )
        return 2

    total_u = total_n = total_e = 0
    for xml_path in xml_files:
        u, n, e = process_xml_file(xml_path, jobs, mch_path)
        total_u += u
        total_n += n
        total_e += e

    print()
    print(f"Updated:    {total_u}")
    print(f"Already OK: {total_n}")
    print(f"Errors:     {total_e}")
    return 1 if total_e else 0


if __name__ == "__main__":
    raise SystemExit(main())
