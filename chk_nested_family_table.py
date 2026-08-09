#!/usr/bin/env python3
"""
Update custom ModelCHECK placeholder checks in report XML from FAMILY_INFO.

Reads ``config/custom_checks.txt`` for the ``DEF_NESTED_FAMILY_TABLE`` section::

    DEF_NESTED_FAMILY_TABLE FEATURE_INFO
    CND_FEATURE_INFO GTE 0
    CHECK CHK_NESTED_FAMILY_TABLE_PRT
    CHECK CHK_NESTED_FAMILY_TABLE_ASM
    MSG_NESTED_FAMILY_TABLE Nested family table

``FEATURE_INFO`` is only so ModelCHECK emits a CUSTOM stub (``FAMILY_INFO`` ``ans``
is text like GENERIC, so a ``GTE`` condition on it does not work). Scoring still
uses ``FAMILY_INFO`` as below.

Each ``CHECK`` is the ``*.mch`` row name (4th column W/E). The report XML check
is without the type suffix (``CHK_NESTED_FAMILY_TABLE``).

- ``_PRT`` → ``*.p.xml``
- ``_ASM`` → ``*.a.xml``
- ``_DRW`` → ``*.d.xml`` (supported if added later)

Matching is fixed in this script (not in custom_checks.txt):

- Score from: FAMILY_INFO
- Nested family tables appear as pipe-separated instance paths in ``info1``,
  for example ``INST2|INST2_CHILD`` or ``INST2||INST2_CHILD|LEAF``
- Non-empty segments before the leaf are nested generics
- Found → ``ans`` = root generic + unique nested generics, severity from ``*.mch``;
  not found → PASS / ``ans=0``
- If ModelCHECK omitted the CUSTOM placeholder, this script inserts one before
  ``</mc_checks>``.

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

THIS_DEF = "NESTED_FAMILY_TABLE"
SOURCE_CHECK = "FAMILY_INFO"

_PRO_SUFFIX_TO_XML = {
    "_ASM": ".a.xml",
    "_PRT": ".p.xml",
    "_DRW": ".d.xml",
}

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
    mch_name: str
    xml_name: str
    file_suffix: str
    source_check: str
    msg: str


DEFAULT_MSG = "Nested family table"
MC_CHECKS_CLOSE_RE = re.compile(r"</mc_checks\s*>", re.IGNORECASE)


def split_check_names(check_token: str) -> tuple[str, str, str]:
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
    """Load all CHECK names from the ``DEF_NESTED_FAMILY_TABLE`` section."""
    if not path.is_file():
        raise FileNotFoundError(f"custom checks file not found: {path}")

    in_section = False
    check_tokens: list[str] = []
    seen: set[str] = set()
    msg = DEFAULT_MSG
    want_def = THIS_DEF.casefold()
    want_msg = f"MSG_{THIS_DEF}".casefold()

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

        if head.casefold() == want_msg and len(parts) >= 2:
            text = line[len(parts[0]) :].strip()
            if text:
                msg = text
            continue

        if head_u == "CHECK" and len(parts) >= 2:
            token = parts[1].strip()
            if not token:
                continue
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            check_tokens.append(token)

    if not check_tokens:
        raise ValueError(
            f"No CHECK line in DEF_{THIS_DEF} section of {path}"
        )

    jobs: list[CustomJob] = []
    for check_token in check_tokens:
        mch_name, xml_name, file_suffix = split_check_names(check_token)
        jobs.append(
            CustomJob(
                mch_name=mch_name,
                xml_name=xml_name,
                file_suffix=file_suffix,
                source_check=SOURCE_CHECK,
                msg=msg,
            )
        )
    return jobs


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
    want = check_name.casefold()
    for open_m in CHECK_OPEN_RE.finditer(raw_xml):
        if open_m.group("name").strip().casefold() != want:
            continue
        close_m = CHECK_CLOSE_RE.search(raw_xml, open_m.end())
        if close_m is None:
            raise ValueError(f"Unclosed <check name={check_name!r}>")
        return open_m.start(), open_m.end(), close_m.start(), close_m.end()
    return None


MODEL_TAG_RE = re.compile(
    r"<model\b[^>]*>\s*([^<]+?)\s*</model\s*>",
    re.IGNORECASE,
)


def model_stem_from_xml(raw_xml: str) -> str:
    """Generic model name without ``.prt`` / ``.asm`` / ``.drw`` (from ``<model>``)."""
    m = MODEL_TAG_RE.search(raw_xml)
    if m is None:
        return ""
    name = m.group(1).strip()
    lower = name.casefold()
    for suf in (".prt", ".asm", ".drw"):
        if lower.endswith(suf):
            return name[: -len(suf)]
    return name


def nested_generics_from_instance_labels(instance_names: list[str]) -> list[tuple[str, int]]:
    """
    Nested family-table generics from FAMILY_INFO instance ``info1`` paths.

    Creo lists nested instances as ``parent|child`` (empty segments from ``||``
    are ignored). Every non-empty segment before the leaf is a nested generic.
    Returns ``(name, depth)`` with depth 1 = first nesting under the root.
    """
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    for name in instance_names:
        parts = [segment.strip() for segment in (name or "").split("|") if segment.strip()]
        if len(parts) < 2:
            continue
        for depth, parent in enumerate(parts[:-1], start=1):
            key = parent.casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append((parent, depth))
    return found


def nested_generics_in_check_inner(inner: str) -> list[tuple[str, int]]:
    names: list[str] = []
    for m in ITEM_RE.finditer(inner):
        names.append(m.group(1).strip())
    return nested_generics_from_instance_labels(names)


def nested_generics_from_source(raw_xml: str, source_check: str) -> list[tuple[str, int]]:
    span = find_check_span(raw_xml, source_check)
    if span is None:
        return []
    _bs, inner_start, inner_end, _be = span
    return nested_generics_in_check_inner(raw_xml[inner_start:inner_end])


def ensure_check_placeholder(raw_xml: str, check_name: str, msg: str) -> str:
    """
    Insert a CUSTOM stub before ``</mc_checks>`` when ModelCHECK omitted it.

    FAMILY_INFO answers are text (e.g. GENERIC), so ModelCHECK often skips
    emitting this custom check even when it is listed in ``*.mch``.
    """
    if find_check_span(raw_xml, check_name) is not None:
        return raw_xml
    close_m = MC_CHECKS_CLOSE_RE.search(raw_xml)
    if close_m is None:
        raise ValueError(f"No </mc_checks> while inserting {check_name!r}")

    indent = "  "
    line_indent = "   "
    # Match quote style used by neighboring checks when possible.
    quote = "'"
    sample = CHECK_OPEN_RE.search(raw_xml)
    if sample is not None:
        quote = sample.group("q")

    safe_msg = (msg or DEFAULT_MSG).replace("&", "&amp;").replace("<", "&lt;")
    block = (
        f"{indent}<check name={quote}{check_name}{quote} "
        f"tab={quote}CUSTOM{quote} type={quote}NONE{quote}>\n"
        f"{line_indent}<stat>PASS</stat>\n"
        f"{line_indent}<desc>{check_name}</desc>\n"
        f"{line_indent}<msg>{safe_msg}</msg>\n"
        f"{line_indent}<ans>0</ans>\n"
        f"{indent}</check>\n"
    )
    return raw_xml[: close_m.start()] + block + raw_xml[close_m.start() :]


def update_check_block(
    raw_xml: str,
    check_name: str,
    stat: str,
    ans: str,
    items: list[tuple[str, str]],
) -> str:
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
            f"\n{indent}<title1>Nested generic</title1>"
            f"\n{indent}<title2>Detail</title2>"
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
    allowed = suffixes or set(_PRO_SUFFIX_TO_XML.values())
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
        print(f"ERROR     {xml_path.name}: {exc}", file=sys.stderr)
        return 0, 0, 1

    file_jobs = jobs_for_xml_file(xml_path, jobs)
    if not file_jobs:
        return 0, 0, 0

    has_source = find_check_span(raw, SOURCE_CHECK) is not None
    has_any_placeholder = any(
        find_check_span(raw, job.xml_name) is not None for job in file_jobs
    )
    # Skip files with neither FAMILY_INFO nor an existing custom placeholder.
    if not has_source and not has_any_placeholder:
        return 0, 0, 0

    updated = 0
    unchanged = 0
    errors = 0
    out = raw

    for job in file_jobs:
        try:
            if find_check_span(out, job.xml_name) is None:
                if not has_source:
                    continue
                out = ensure_check_placeholder(out, job.xml_name, job.msg)

            nested = nested_generics_from_source(out, job.source_check)

            if not nested:
                stat = "PASS"
                ans = "0"
                items: list[tuple[str, str]] = []
            else:
                sev = severity_from_mch(mch_path, job.mch_name)
                stat = "PASS" if sev == "PASS" else sev
                root = model_stem_from_xml(out) or "GENERIC"
                # Root + each nested generic (e.g. root, INST2, INST2_INST3 → 3).
                ans = str(len(nested) + 1)
                items = [(root, "Root family table")]
                items.extend(
                    (name, f"Nested family table (depth {depth})")
                    for name, depth in nested
                )

            new_out = update_check_block(out, job.xml_name, stat, ans, items)
            if new_out == out:
                unchanged += 1
            else:
                out = new_out
                updated += 1
        except (OSError, ValueError) as exc:
            print(f"ERROR     {xml_path.name}: {job.xml_name}: {exc}", file=sys.stderr)
            errors += 1

    if out != raw:
        try:
            write_xml_text(xml_path, out, encoding)
            if updated == 0:
                updated = 1
        except OSError as exc:
            print(f"ERROR     {xml_path.name}: write failed: {exc}", file=sys.stderr)
            return 0, unchanged, errors + 1

    return updated, unchanged, errors


def resolve_report_dir(argv: list[str]) -> Path:
    if len(argv) > 2:
        raise ValueError(
            "Usage: python chk_nested_family_table.py [report_dir]\n"
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

    if not xml_files:
        kinds = ", ".join(sorted(f"*{s}" for s in needed))
        print(
            f"No {kinds} in that folder.\n"
            "Point working_directory at the folder that contains the report XML.",
            file=sys.stderr,
        )
        return 2

    total_u = total_n = total_e = 0
    for xml_path in xml_files:
        u, n, e = process_xml_file(xml_path, jobs, mch_path)
        total_u += u
        total_n += n
        total_e += e

    if total_e:
        print(
            f"chk_nested_family_table: {total_u} updated, {total_n} ok, {total_e} error(s).",
            file=sys.stderr,
        )
        return 1

    print(f"chk_nested_family_table: ok ({total_u} updated, {total_n} unchanged).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
