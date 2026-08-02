#!/usr/bin/env python3
"""
Update custom ModelCHECK placeholder checks in report XML from FEATURE_INFO data.

Reads ``config/custom_checks.txt`` for the ``DEF_ASSEMBLY_CUTS`` section::

    DEF_ASSEMBLY_CUTS ASM_FEATURES
    CND_ASSEMBLY_CUTS GTE 0
    CHECK CHK_ASSEMBLY_CUTS_ASM
    MSG_ASSEMBLY_CUTS Number of assembly cuts:

``CHECK`` is the ``*.mch`` row name (4th column W/E). The report XML check is
without the ``_ASM`` / ``_PRT`` / ``_DRW`` suffix (``CHK_ASSEMBLY_CUTS``).

The CHECK suffix selects which report files to edit:

- ``_ASM`` → ``*.a.xml``
- ``_PRT`` → ``*.p.xml``
- ``_DRW`` → ``*.d.xml``

Feature matching is fixed in this script (not in custom_checks.txt):

- Source check: FEATURE_INFO
- Types: CUT, HOLE (sum ``info2`` → ``ans``; one ``<item>`` per type)
- When items exist, also sets ``<title1>Type</title1>`` / ``<title2>Count</title2>``

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

# Owned DEF_ section in config/custom_checks.txt (DEF_ASSEMBLY_CUTS).
THIS_DEF = "ASSEMBLY_CUTS"
# Hard-coded FIND (not read from custom_checks.txt).
SOURCE_CHECK = "FEATURE_INFO"
KEYWORDS = ("CUT", "HOLE")

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
    """CHECK line may be CHK_…_ASM (MCH row); XML check is usually without the type suffix."""

    mch_name: str
    xml_name: str
    file_suffix: str  # .a.xml / .p.xml / .d.xml
    source_check: str
    keywords: tuple[str, ...]


_PRO_SUFFIX_TO_XML = {
    "_ASM": ".a.xml",
    "_PRT": ".p.xml",
    "_DRW": ".d.xml",
}


def split_check_names(check_token: str) -> tuple[str, str, str]:
    """
    CHECK token → (mch_name, xml_name, file_suffix).

    ``CHK_ASSEMBLY_CUTS_ASM`` → mch row that name, XML check ``CHK_ASSEMBLY_CUTS``,
    files ``*.a.xml``. ``_PRT`` → ``*.p.xml``, ``_DRW`` → ``*.d.xml``.
    """
    mch_name = check_token.strip()
    upper = mch_name.upper()
    for suf, file_suffix in _PRO_SUFFIX_TO_XML.items():
        if upper.endswith(suf):
            return mch_name, mch_name[: -len(suf)], file_suffix
    raise ValueError(
        f"CHECK name must end with _ASM, _PRT, or _DRW (got {check_token!r})"
    )


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
    """
    Load the CHECK name from the ``DEF_ASSEMBLY_CUTS`` section of custom_checks.txt.

    FEATURE_INFO / CUT,HOLE are fixed in this script (not from a FIND line).
    """
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
            keywords=KEYWORDS,
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
    Look up CHECK name in ``*.mch`` (e.g. CHK_ASSEMBLY_CUTS_ASM).

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


def feature_counts_in_check_inner(
    inner: str, keywords: tuple[str, ...]
) -> list[tuple[str, int]]:
    """
    Per-type counts from FEATURE_INFO-style items, in FIND keyword order.

    Only types with qty > 0 are returned.
    """
    want_order = [k.strip().upper() for k in keywords if k.strip()]
    want = set(want_order)
    if not want:
        return []

    found: dict[str, int] = {}
    for m in ITEM_RE.finditer(inner):
        type_name = m.group(1).strip().upper()
        if type_name not in want:
            continue
        count_raw = m.group(2).strip()
        try:
            qty = int(float(count_raw)) if count_raw else 1
        except ValueError:
            qty = 1
        found[type_name] = found.get(type_name, 0) + qty

    return [(name, found[name]) for name in want_order if found.get(name, 0) > 0]


def feature_counts_from_source(
    raw_xml: str, source_check: str, keywords: tuple[str, ...]
) -> list[tuple[str, int]]:
    span = find_check_span(raw_xml, source_check)
    if span is None:
        return []
    _bs, inner_start, inner_end, _be = span
    return feature_counts_in_check_inner(raw_xml[inner_start:inner_end], keywords)


def update_check_block(
    raw_xml: str,
    check_name: str,
    stat: str,
    ans: str,
    items: list[tuple[str, int]],
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

    # Drop previous titles/items, then insert after </ans> when there are rows.
    new_inner = TITLE_BLOCK_RE.sub("", new_inner)
    new_inner = ITEM_BLOCK_RE.sub("", new_inner)
    indent_m = re.search(r"\n([ \t]+)<", new_inner)
    indent = indent_m.group(1) if indent_m else "   "
    extra = ""
    if items:
        extra += (
            f"\n{indent}<title1>Type</title1>"
            f"\n{indent}<title2>Count</title2>"
        )
        extra += "".join(
            f"\n{indent}<item><info1>{typ}</info1><info2>{qty}</info2></item>"
            for typ, qty in items
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
    """
    List ModelCHECK report XML in report_dir (not recursive).

    ``suffixes`` is a set of lower-case endings such as ``{".a.xml"}``.
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


def jobs_for_xml_file(xml_path: Path, jobs: list[CustomJob]) -> list[CustomJob]:
    """Jobs whose CHECK suffix matches this report file type."""
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

            items = feature_counts_from_source(out, job.source_check, job.keywords)
            if find_check_span(out, job.source_check) is None:
                print(
                    f"NOTE      {xml_path.name}: {job.source_check} not found; "
                    f"count=0 for {job.xml_name}"
                )

            count = sum(qty for _typ, qty in items)
            if count <= 0:
                stat = "PASS"
                ans = "0"
                items = []
            else:
                sev = severity_from_mch(mch_path, job.mch_name)
                stat = "PASS" if sev == "PASS" else sev
                ans = str(count)

            new_out = update_check_block(out, job.xml_name, stat, ans, items)
            if new_out == out:
                print(
                    f"OK        {xml_path.name}: {job.xml_name} "
                    f"already stat={stat} ans={ans} (no write)"
                )
                unchanged += 1
            else:
                out = new_out
                detail = ",".join(f"{t}={q}" for t, q in items) or "none"
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
            "Usage: python chk_assembly_cuts.py [report_dir]\n"
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
            f"({','.join(job.keywords)}); mch {job.mch_name}; "
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
