import hashlib
import html
import os
from collections import defaultdict
import xml.etree.ElementTree as ET


def get_category_descriptions(model_checks_xml_path: str) -> dict[str, str]:
    model_tree = ET.parse(model_checks_xml_path)
    model_root = model_tree.getroot()
    categories_el = model_root.find("Categories")
    if categories_el is None:
        return {}
    category_descriptions: dict[str, str] = {}
    for category in categories_el.findall("Category"):
        name_el = category.find("Name")
        desc_el = category.find("Description")
        if name_el is None or not (name_el.text or "").strip():
            continue
        name = name_el.text.strip()
        description = desc_el.text if desc_el is not None and desc_el.text else ""
        category_descriptions[name] = description
    return category_descriptions


def category_dom_id(category_name: str) -> str:
    digest = hashlib.sha256(category_name.encode("utf-8")).hexdigest()[:12]
    return f"mq-cat-{digest}"


def _check_hidden_from_report(check_el: ET.Element) -> bool:
    hide = check_el.find("hideFromReport")
    return hide is not None and (hide.text or "").strip() == "Y"


def _check_stat(check_el: ET.Element) -> str:
    stat_el = check_el.find("stat")
    return stat_el.text if stat_el is not None else ""


def _file_report_check_stats(file_element: ET.Element) -> list[str]:
    """Non-INFO, report-visible check stats for one master.xml File entry."""
    stats: list[str] = []
    for check in file_element.findall(".//check"):
        if _check_hidden_from_report(check):
            continue
        stat = _check_stat(check)
        if stat == "INFO":
            continue
        stats.append(stat)
    return stats


def scan_file_stats(master_root: ET.Element) -> tuple[int, int, int]:
    """Counts File entries with at least one non-INFO, report-visible check."""
    total_files = 0
    files_with_warning = 0
    files_with_error = 0
    for file_element in master_root.findall("File"):
        stats = _file_report_check_stats(file_element)
        if not stats:
            continue
        total_files += 1
        if any(s == "WARNING" for s in stats):
            files_with_warning += 1
        if any(s == "ERROR" for s in stats):
            files_with_error += 1
    return total_files, files_with_warning, files_with_error


def scan_pro_type_counts(master_root: ET.Element) -> dict[str, int]:
    """Count report File entries by master.xml ProType (PRT, ASM, DRW)."""
    counts = {"PRT": 0, "ASM": 0, "DRW": 0}
    for file_element in master_root.findall("File"):
        if not _file_report_check_stats(file_element):
            continue
        pro_el = file_element.find("ProType")
        pro = (pro_el.text or "").strip().upper() if pro_el is not None else ""
        if pro in counts:
            counts[pro] += 1
    return counts


def _model_check_category_map(model_checks_xml_path: str) -> dict[str, str]:
    """ModelCheckName -> Category for checks included in the report."""
    model_tree = ET.parse(model_checks_xml_path)
    mapping: dict[str, str] = {}
    for check in model_tree.getroot().findall("Check"):
        hide_from_report = check.find("hideFromReport")
        if hide_from_report is not None and (hide_from_report.text or "").strip() == "Y":
            continue
        mcn = check.find("ModelCheckName")
        cat = check.find("Category")
        if mcn is None or cat is None or not (mcn.text or "").strip() or not (cat.text or "").strip():
            continue
        mapping[mcn.text.strip()] = cat.text.strip()
    return mapping


def scan_visible_issue_summary(master_root: ET.Element, model_checks_xml_path: str) -> dict:
    """
    Counts for the report score dashboard at build time.

    PASS totals are fixed batch baselines (like files scanned). WARNING/ERROR match
    visible issue rows and decrease when the user removes sections in the browser.
    """
    model_check_mapping = _model_check_category_map(model_checks_xml_path)
    pass_issues = 0
    warn_issues = 0
    err_issues = 0
    warn_models: set[str] = set()
    err_models: set[str] = set()
    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "warn": 0, "err": 0})

    for file_element in master_root.findall("File"):
        model = (file_element.findtext("Model") or "").strip()
        for check in file_element.findall(".//check"):
            if _check_hidden_from_report(check):
                continue
            stat = _check_stat(check)
            if stat not in ("PASS", "WARNING", "ERROR"):
                continue
            name = check.get("name") or ""
            if name not in model_check_mapping:
                continue
            category = model_check_mapping[name]
            if stat == "PASS":
                pass_issues += 1
                by_category[category]["pass"] += 1
            elif stat == "WARNING":
                warn_issues += 1
                if model:
                    warn_models.add(model)
                by_category[category]["warn"] += 1
            else:
                err_issues += 1
                if model:
                    err_models.add(model)
                by_category[category]["err"] += 1

    overall_grade = calculate_grade([pass_issues, warn_issues, err_issues])[0]
    return {
        "pass_issues": pass_issues,
        "warn_issues": warn_issues,
        "err_issues": err_issues,
        "warn_models": len(warn_models),
        "err_models": len(err_models),
        "overall_grade": overall_grade,
        "by_category": {k: dict(v) for k, v in by_category.items()},
    }


def calculate_grade(sizes: list[int]) -> tuple[str, str]:
    total = sum(sizes)
    if total == 0:
        return "A", "Pass: 0%, Warning: 0%, Error: 0%"

    green, yellow, red = sizes
    green_ratio = green / total
    yellow_ratio = yellow / total
    red_ratio = red / total

    breakdown = (
        f"Pass: {green_ratio * 100:.2f}%, "
        f"Warning: {yellow_ratio * 100:.2f}%, "
        f"Error: {red_ratio * 100:.2f}%"
    )

    if red > 0:
        return "D", breakdown
    if yellow_ratio > 0.25:
        return "C", breakdown
    if yellow_ratio >= 0.05:
        return "B", breakdown
    return "A", breakdown


def grade_css_class(letter: str) -> str:
    return {
        "A": "mq-grade-a",
        "B": "mq-grade-b",
        "C": "mq-grade-c",
        "D": "mq-grade-d",
        "N/A": "mq-grade-na",
    }.get(letter, "mq-grade-na")


_MQ_DASHBOARD_CSS = """
<style>
.mq-dashboard { font-family: "Segoe UI", Arial, sans-serif; background: #e8eaed; color: #1a1a1a;
  padding: 16px; border-radius: 8px; box-sizing: border-box; }
.mq-dashboard * { box-sizing: border-box; }
.mq-page-title { font-size: 1.75rem; font-weight: 700; margin: 0 0 16px 0; letter-spacing: 0.02em; }
.mq-grid { display: grid; grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.1fr); gap: 20px; align-items: start; }
@media (max-width: 900px) { .mq-grid { grid-template-columns: 1fr; } }
.mq-left { display: flex; flex-direction: column; gap: 16px; }
.mq-hero-card { background: #fff; border-radius: 12px; padding: 20px 22px;
  box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.mq-hero-card h2 { margin: 0 0 14px 0; font-size: 1.25rem; font-weight: 700; }
.mq-hero-top { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; justify-content: space-between; }
.mq-stats { background: #e8f4fc; border-radius: 10px; padding: 14px 16px; flex: 1; min-width: 200px; }
.mq-stats p { margin: 6px 0; font-size: 0.95rem; }
.mq-stats strong { color: #0f172a; }
.mq-overall { text-align: center; flex-shrink: 0; }
.mq-overall-label { font-size: 0.75rem; color: #64748b; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .06em; }
.mq-grade-ring { width: 72px; height: 72px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 1.75rem; font-weight: 800; color: #fff; margin: 0 auto; }
.mq-grade-a { background: #16a34a; }
.mq-grade-b { background: #65a30d; }
.mq-grade-c { background: #ca8a04; }
.mq-grade-d { background: #dc2626; }
.mq-grade-na { background: #94a3b8; }
.mq-scale { margin-top: 18px; padding-top: 14px; border-top: 1px solid #e2e8f0; }
.mq-scale-title { font-size: 0.8rem; font-weight: 600; color: #475569; margin-bottom: 10px; }
.mq-scale-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; font-size: 0.82rem; line-height: 1.35; }
.mq-scale-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; margin-top: 3px; }
.mq-dot-a { background: #16a34a; }
.mq-dot-b { background: #65a30d; }
.mq-dot-c { background: #ca8a04; }
.mq-dot-d { background: #dc2626; }
.mq-right { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
@media (max-width: 700px) { .mq-right { grid-template-columns: 1fr; } }
.mq-cat-card { background: #fff; border-radius: 12px; padding: 16px 16px 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.08); position: relative; }
.mq-cat-card.mq-cat-empty { display: none; }
.mq-cat-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
.mq-cat-title { font-size: 1rem; font-weight: 700; margin: 0; color: #0f172a; }
.mq-cat-badge { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 1rem; color: #fff; flex-shrink: 0; }
.mq-cat-desc { font-size: 0.82rem; color: #475569; line-height: 1.45; margin: 0 0 12px 0; }
.mq-stack { display: flex; height: 14px; border-radius: 6px; overflow: hidden; background: #f1f5f9; margin-bottom: 10px; }
.mq-stack span { height: 100%; }
.mq-seg-pass { background: #16a34a; }
.mq-seg-warn { background: #eab308; }
.mq-seg-err { background: #dc2626; }
.mq-legend { font-size: 0.78rem; color: #334155; display: flex; flex-wrap: wrap; gap: 10px 14px; }
.mq-legend span { display: inline-flex; align-items: center; gap: 5px; }
.mq-sq { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.mq-rationale { background: #fff; border-radius: 12px; padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.08); font-size: 0.88rem; line-height: 1.5; color: #334155; }
.mq-rationale h3 { margin: 0 0 10px 0; font-size: 1rem; color: #0f172a; }
.mq-rationale ul { margin: 8px 0 0 1.1em; padding: 0; }
.mq-rationale li { margin-bottom: 8px; }
</style>"""


def generate_adjusted_summary_shell(
    category_descriptions: dict[str, str],
    *,
    files_scanned: int = 0,
    issue_summary: dict | None = None,
) -> str:
    """
    Dashboard shell for the full report. Scan totals are fixed at build time; issue counts and
    grades are baked from master.xml when ``issue_summary`` is provided so the browser does not
    need a full DOM scan on first load. Client-side JS recalculates after removals or filters.
    """
    summary = issue_summary or {}
    pass_issues = summary.get("pass_issues", 0)
    visible_issues = summary.get("warn_issues", 0) + summary.get("err_issues", 0)
    warn_models = summary.get("warn_models", 0)
    err_models = summary.get("err_models", 0)
    overall_grade = summary.get("overall_grade", "A")
    by_category = summary.get("by_category") or {}
    baked_attr = ' data-mq-summary-baked="1"' if issue_summary else ""
    pass_attr = f' data-mq-pass-issues="{pass_issues}"' if issue_summary else ""
    parts = [
        _MQ_DASHBOARD_CSS,
        f"""
<div class="mq-dashboard"{baked_attr}{pass_attr}>
  <h1 class="mq-page-title" id="mq-page-title">Score</h1>
  <div class="mq-grid">
    <div class="mq-left">
      <div class="mq-hero-card">
        <div class="mq-hero-top">
          <div class="mq-stats">
            <p><strong>Files scanned:</strong> <span id="mq-stat-models" data-mq-scan-fixed="1">{files_scanned}</span></p>
            <p><strong>Total issues:</strong> <span id="mq-stat-issues">{visible_issues}</span></p>
            <p><strong>Models with warnings:</strong> <span id="mq-stat-warn-models">{warn_models}</span></p>
            <p><strong>Models with errors:</strong> <span id="mq-stat-err-models">{err_models}</span></p>
          </div>
          <div class="mq-overall">
            <div class="mq-overall-label">Overall grade</div>
            <div id="mq-overall-grade" class="mq-grade-ring {grade_css_class(overall_grade)}">{html.escape(overall_grade)}</div>
          </div>
        </div>
        <div class="mq-scale">
          <div class="mq-scale-title">Grading scale</div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-a"></span><div><strong>A</strong> — Warnings under 5% of checks, no errors.</div></div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-b"></span><div><strong>B</strong> — Moderate warnings (5–25% of checks), no errors.</div></div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-c"></span><div><strong>C</strong> — Higher warnings (&gt;25% of checks), no errors.</div></div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-d"></span><div><strong>D</strong> — Any remaining errors.</div></div>
        </div>
      </div>
      <div class="mq-rationale">
        <h3>How the grade works</h3>
        <p>Files scanned and PASS check totals stay fixed from the batch. Grades use PASS plus the WARNING and ERROR rows still shown; remove sections or models to update the score.</p>
        <ul>
          <li><strong>Grade A:</strong> Warnings under 5% of checks (PASS + visible issues), no errors.</li>
          <li><strong>Grade B:</strong> Warnings are 5% to 25% of checks, no errors.</li>
          <li><strong>Grade C:</strong> Warnings are over 25% of checks, no errors.</li>
          <li><strong>Grade D:</strong> Any remaining errors.</li>
        </ul>
      </div>
    </div>
    <div class="mq-right" id="mq-categories">
""",
    ]

    categories_with_issues = [
        cat
        for cat in sorted(category_descriptions.keys(), key=str.casefold)
        if (by_category.get(cat, {}).get("warn", 0) + by_category.get(cat, {}).get("err", 0)) > 0
    ]
    if issue_summary is None:
        categories_with_issues = sorted(category_descriptions.keys(), key=str.casefold)

    for category in categories_with_issues:
        desc = category_descriptions.get(category, "No description available.")
        cat_esc = html.escape(category, quote=False)
        desc_esc = html.escape(desc, quote=False)
        dom_id = category_dom_id(category)
        counts = by_category.get(category, {"pass": 0, "warn": 0, "err": 0})
        p = counts.get("pass", 0)
        w = counts.get("warn", 0)
        e = counts.get("err", 0)
        total = p + w + e
        letter = calculate_grade([p, w, e])[0] if total else "A"
        g_pct = (p / total * 100) if total else 0.0
        y_pct = (w / total * 100) if total else 0.0
        r_pct = (e / total * 100) if total else 0.0
        pass_attr_cat = f' data-mq-pass="{p}"' if issue_summary else ""
        empty_class = "" if (w + e) > 0 else " mq-cat-empty"
        parts.append(f"""
      <div class="mq-cat-card{empty_class}" id="{dom_id}" data-mq-category="{cat_esc}"{pass_attr_cat}>
        <div class="mq-cat-head">
          <h3 class="mq-cat-title">{cat_esc}</h3>
          <div class="mq-cat-badge {grade_css_class(letter)}" data-mq-role="badge">{html.escape(letter)}</div>
        </div>
        <p class="mq-cat-desc">{desc_esc}</p>
        <div class="mq-stack" data-mq-role="stack" title="{g_pct:.2f}% pass, {y_pct:.2f}% warning, {r_pct:.2f}% error">
          <span class="mq-seg-pass" data-mq-role="seg-pass" style="width:{g_pct:.4f}%"></span>
          <span class="mq-seg-warn" data-mq-role="seg-warn" style="width:{y_pct:.4f}%"></span>
          <span class="mq-seg-err" data-mq-role="seg-err" style="width:{r_pct:.4f}%"></span>
        </div>
        <div class="mq-legend" data-mq-role="legend">
          <span><span class="mq-sq mq-seg-warn"></span> Warning: <span data-mq-role="warn-count">{w}</span></span>
          <span><span class="mq-sq mq-seg-err"></span> Error: <span data-mq-role="err-count">{e}</span></span>
        </div>
      </div>""")

    if not category_descriptions:
        parts.append("""
      <div class="mq-cat-card">
        <p class="mq-cat-desc">No categories found in model_checks.xml.</p>
      </div>""")

    parts.append("""
    </div>
  </div>
</div>""")
    return "".join(parts)


def generate_summary_div(master_xml_path, model_checks_xml_path):
    master_tree = ET.parse(master_xml_path)
    master_root = master_tree.getroot()

    model_tree = ET.parse(model_checks_xml_path)
    model_root = model_tree.getroot()

    def categorize_checks(master_root, model_root):
        categories = {}
        model_check_mapping = {}
        for check in model_root.findall("Check"):
            model_check_mapping[check.find("ModelCheckName").text] = check.find("Category").text

        for file_element in master_root.findall("File"):
            for check in file_element.findall(".//check"):
                if _check_hidden_from_report(check):
                    continue
                name = check.get("name")
                stat = _check_stat(check)
                if stat == "INFO":
                    continue
                if name in model_check_mapping:
                    category = model_check_mapping[name]
                    if category not in categories:
                        categories[category] = {"PASS": 0, "WARNING": 0, "ERROR": 0}
                    categories[category][stat] += 1
        return categories

    def generate_div_content(
        categories,
        category_descriptions,
        file_stats,
        visible_issues,
        overall_letter,
    ):
        total_f, warn_f, err_f = file_stats
        grade_class = grade_css_class(overall_letter)
        grade_letter = html.escape(overall_letter)
        parts = [
            _MQ_DASHBOARD_CSS,
            f"""
<div class="mq-dashboard">
  <h1 class="mq-page-title">SCORE</h1>
  <div class="mq-grid">
    <div class="mq-left">
      <div class="mq-hero-card">
        <h2>Model Quality Report</h2>
        <div class="mq-hero-top">
          <div class="mq-stats">
            <p><strong>Files scanned:</strong> {total_f}</p>
            <p><strong>Total issues:</strong> {visible_issues}</p>
            <p><strong>Models with warnings:</strong> {warn_f}</p>
            <p><strong>Models with errors:</strong> {err_f}</p>
          </div>
          <div class="mq-overall">
            <div class="mq-overall-label">Overall grade</div>
            <div class="mq-grade-ring {grade_class}">{grade_letter}</div>
          </div>
        </div>
        <div class="mq-scale">
          <div class="mq-scale-title">Grading scale</div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-a"></span><div><strong>A</strong> — Very high proportion of PASS checks, under 5% warnings, no errors.</div></div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-b"></span><div><strong>B</strong> — Moderate warnings (5–25%), no errors.</div></div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-c"></span><div><strong>C</strong> — Higher warnings (&gt;25%), no errors.</div></div>
          <div class="mq-scale-row"><span class="mq-scale-dot mq-dot-d"></span><div><strong>D</strong> — Any errors; errors must be fixed.</div></div>
        </div>
      </div>
      <div class="mq-rationale">
        <h3>How the grade is determined</h3>
        <p>The grade for each category uses the proportion of PASS, WARNING, and ERROR checks:</p>
        <ul>
          <li><strong>Grade A:</strong> Very high proportion of PASS, minimal warnings (under 5%), no errors.</li>
          <li><strong>Grade B:</strong> Moderate warnings (5% to 25%), no errors.</li>
          <li><strong>Grade C:</strong> Higher warnings (over 25%), no errors.</li>
          <li><strong>Grade D:</strong> Any errors — critical and must be fixed.</li>
        </ul>
      </div>
    </div>
    <div class="mq-right">
""",
        ]

        for category in sorted(categories.keys(), key=str.casefold):
            checks = categories[category]
            sizes = [checks["PASS"], checks["WARNING"], checks["ERROR"]]
            total = sum(sizes)
            grade = "N/A" if total == 0 else calculate_grade(sizes)[0]
            g_pct = (sizes[0] / total * 100) if total else 0.0
            y_pct = (sizes[1] / total * 100) if total else 0.0
            r_pct = (sizes[2] / total * 100) if total else 0.0
            desc = category_descriptions.get(category, "No description available.")
            desc_esc = html.escape(desc, quote=False)
            cat_esc = html.escape(category, quote=False)

            parts.append(f"""
      <div class="mq-cat-card">
        <div class="mq-cat-head">
          <h3 class="mq-cat-title">{cat_esc}</h3>
          <div class="mq-cat-badge {grade_css_class(grade)}">{html.escape(grade)}</div>
        </div>
        <p class="mq-cat-desc">{desc_esc}</p>
        <div class="mq-stack" title="{g_pct:.2f}% pass, {y_pct:.2f}% warning, {r_pct:.2f}% error">
          <span class="mq-seg-pass" style="width:{g_pct:.4f}%"></span>
          <span class="mq-seg-warn" style="width:{y_pct:.4f}%"></span>
          <span class="mq-seg-err" style="width:{r_pct:.4f}%"></span>
        </div>
        <div class="mq-legend">
          <span><span class="mq-sq mq-seg-pass"></span> Pass: {g_pct:.2f}%</span>
          <span><span class="mq-sq mq-seg-warn"></span> Warning: {y_pct:.2f}%</span>
          <span><span class="mq-sq mq-seg-err"></span> Error: {r_pct:.2f}%</span>
        </div>
      </div>""")

        if not categories:
            parts.append("""
      <div class="mq-cat-card">
        <p class="mq-cat-desc">No categorized checks found in master.xml for the checks listed in model_checks.xml.</p>
      </div>""")

        parts.append("""
    </div>
  </div>
</div>""")
        return "".join(parts)

    category_descriptions = get_category_descriptions(model_checks_xml_path)
    categories = categorize_checks(master_root, model_root)
    file_stats = scan_file_stats(master_root)

    agg_pass = sum(c["PASS"] for c in categories.values())
    agg_warn = sum(c["WARNING"] for c in categories.values())
    agg_err = sum(c["ERROR"] for c in categories.values())
    agg_total = agg_pass + agg_warn + agg_err
    overall_letter = "N/A" if agg_total == 0 else calculate_grade([agg_pass, agg_warn, agg_err])[0]

    visible_issues = agg_warn + agg_err
    return generate_div_content(
        categories,
        category_descriptions,
        file_stats,
        visible_issues,
        overall_letter,
    )


def write_summary_html_file(master_xml_path: str, model_checks_xml_path: str, output_path: str) -> str:
    """
    Run ``generate_summary_div`` and save the result as a minimal standalone HTML file.

    Returns the path written (``output_path``).
    """
    fragment = generate_summary_div(master_xml_path, model_checks_xml_path)
    doc = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "  <title>Modelcheck summary</title>\n"
        "</head>\n<body>\n"
        f"{fragment}\n"
        "</body>\n</html>\n"
    )
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return output_path
