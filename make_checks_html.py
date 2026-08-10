"""
Build checks.html from model_checks.xml (Name, Description, why/How), A–Z with search.
"""
from __future__ import annotations

import html
import os
import sys
import xml.etree.ElementTree as ET

import markdown

BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_XML = os.path.join(BUNDLE_DIR, "model_checks.xml")
DEFAULT_OUT = os.path.join(BUNDLE_DIR, "checks.html")


def _elem_text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    parts: list[str] = [el.text or ""]
    for child in list(el):
        parts.append(ET.tostring(child, encoding="unicode"))
        parts.append(child.tail or "")
    return "".join(parts).strip()


def _child_text(parent: ET.Element, tag: str) -> str:
    return (_elem_text(parent.find(tag)) or "").strip()


def load_checks(xml_path: str) -> list[dict]:
    root = ET.parse(xml_path).getroot()
    checks: list[dict] = []
    for check in root.findall("Check"):
        name = _child_text(check, "Name")
        if not name:
            continue
        why_raw = _child_text(check, "why")
        checks.append(
            {
                "name": name,
                "category": _child_text(check, "Category"),
                "mcn": _child_text(check, "ModelCheckName"),
                "description": _child_text(check, "Description"),
                "how_html": markdown.markdown(why_raw) if why_raw else "",
            }
        )
    checks.sort(key=lambda c: c["name"].casefold())
    return checks


def render_html(checks: list[dict]) -> str:
    cards: list[str] = []
    for i, c in enumerate(checks):
        cid = f"check-{i + 1}"
        cat = html.escape(c["category"]) if c["category"] else ""
        mcn = html.escape(c["mcn"]) if c["mcn"] else ""
        name = html.escape(c["name"])
        desc = html.escape(c["description"]) if c["description"] else ""
        meta_bits = []
        if cat:
            meta_bits.append(f'<span class="meta-cat">{cat}</span>')
        if mcn:
            meta_bits.append(f'<code class="meta-mcn">{mcn}</code>')
        meta = " · ".join(meta_bits)
        how_block = ""
        if c["how_html"]:
            how_block = (
                '<div class="how">'
                "<h3>How</h3>"
                f'{c["how_html"]}'
                "</div>"
            )
        desc_block = ""
        if desc:
            desc_block = (
                '<div class="description">'
                "<h3>Description</h3>"
                f"<p>{desc}</p>"
                "</div>"
            )
        cards.append(
            f'<article class="check-card" id="{cid}">'
            f'<header><h2 class="check-name">{name}</h2>'
            f'{f"<p class=meta>{meta}</p>" if meta else ""}'
            "</header>"
            f"{desc_block}"
            f"{how_block}"
            "</article>"
        )

    count = len(checks)
    cards_html = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ModelCHECK checks reference</title>
  <style>
    :root {{
      --ink: #0f172a;
      --muted: #475569;
      --line: #d8dee8;
      --paper: #f4f6f9;
      --card: #ffffff;
      --accent: #0b6bcb;
      --accent-soft: #e8f2fc;
      --shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
      --font: "Segoe UI", "Candara", "Calibri", sans-serif;
      --mono: "Cascadia Mono", "Consolas", monospace;
      --max: 46rem;
    }}

    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: var(--font);
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 10% -10%, #dbeafe 0%, transparent 55%),
        radial-gradient(900px 400px at 100% 0%, #e2e8f0 0%, transparent 50%),
        var(--paper);
      line-height: 1.55;
      font-size: 1.02rem;
    }}

    .wrap {{
      max-width: 52rem;
      margin: 0 auto;
      padding: 2.5rem 1.25rem 4rem;
    }}

    header.hero {{
      margin-bottom: 1.25rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--line);
    }}
    header.hero p.kicker {{
      margin: 0 0 0.4rem;
      font-size: 0.8rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 600;
    }}
    header.hero h1 {{
      margin: 0 0 0.75rem;
      font-size: clamp(1.75rem, 4vw, 2.35rem);
      line-height: 1.15;
      font-weight: 750;
      letter-spacing: -0.02em;
    }}
    header.hero .lede {{
      margin: 0;
      max-width: var(--max);
      color: var(--muted);
      font-size: 1.08rem;
    }}

    .search-bar {{
      position: sticky;
      top: 0;
      z-index: 5;
      background: rgba(244, 246, 249, 0.92);
      backdrop-filter: blur(6px);
      padding: 0.75rem 0 0.85rem;
      margin: 0 0 1.25rem;
      border-bottom: 1px solid var(--line);
    }}
    .search-bar label {{
      display: block;
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 0.35rem;
    }}
    .search-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: stretch;
      max-width: 40rem;
    }}
    .mq-gallery-search {{
      flex: 1 1 14rem;
      min-width: 0;
      padding: 0.55rem 0.75rem;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
      background: var(--card);
      box-shadow: var(--shadow);
    }}
    .mq-gallery-search:focus {{
      outline: 2px solid #2563eb;
      outline-offset: 1px;
    }}
    .mq-checks-field {{
      flex: 0 0 auto;
      padding: 0.55rem 0.75rem;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
      background: var(--card);
      box-shadow: var(--shadow);
      color: var(--ink);
    }}
    .mq-checks-field:focus {{
      outline: 2px solid #2563eb;
      outline-offset: 1px;
    }}
    .search-meta {{
      margin: 0.45rem 0 0;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .search-empty {{
      display: none;
      margin: 1rem 0 0;
      padding: 0.85rem 1rem;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--muted);
    }}
    .search-empty.show {{ display: block; }}

    .check-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 1.1rem 1.2rem 1.15rem;
      margin: 0 0 1rem;
      box-shadow: var(--shadow);
      scroll-margin-top: 5.5rem;
    }}
    .check-card[hidden] {{ display: none !important; }}
    .check-card header h2,
    .check-card .check-name {{
      margin: 0 0 0.35rem;
      font-size: 1.2rem;
      letter-spacing: -0.015em;
    }}
    .check-card .meta {{
      margin: 0 0 0.85rem;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .meta-mcn {{
      font-family: var(--mono);
      font-size: 0.85em;
      background: #eef2f7;
      padding: 0.05em 0.3em;
      border-radius: 4px;
    }}
    .check-card h3 {{
      margin: 0.85rem 0 0.4rem;
      font-size: 0.8rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .check-card .description p {{
      margin: 0;
      max-width: var(--max);
    }}
    .check-card .how {{
      margin-top: 0.35rem;
      padding-top: 0.15rem;
      border-top: 1px solid transparent;
    }}
    .check-card .how > :first-child {{ margin-top: 0; }}
    .check-card .how p,
    .check-card .how ul,
    .check-card .how ol {{
      margin: 0 0 0.75rem;
      max-width: var(--max);
    }}
    .check-card .how ul,
    .check-card .how ol {{ padding-left: 1.3rem; }}
    .check-card .how li {{ margin: 0.25rem 0; }}
    .check-card .how h3 {{ margin-top: 0.85rem; }}
    .check-card .how h4 {{
      margin: 0.9rem 0 0.35rem;
      font-size: 1.02rem;
    }}
    .check-card .how a {{ color: var(--accent); }}
    .check-card .how img {{ max-width: 100%; }}
    .check-card .how code {{
      font-family: var(--mono);
      font-size: 0.9em;
      background: #eef2f7;
      padding: 0.05em 0.3em;
      border-radius: 4px;
    }}

    footer {{
      margin-top: 2.5rem;
      padding-top: 1rem;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.92rem;
    }}
    footer a {{ color: var(--accent); text-decoration: none; }}
    footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <p class="kicker">PDSVISION Cad Assessment</p>
      <h1>Checks reference</h1>
      <p class="lede">
        Descriptions and how-to guidance for each check defined in
        <span class="meta-mcn">model_checks.xml</span>, listed A–Z.
      </p>
    </header>

    <div class="search-bar">
      <label for="mq-checks-search">Search checks</label>
      <div class="search-controls">
        <input type="search" id="mq-checks-search" class="mq-gallery-search"
               placeholder="Filter checks…"
               autocomplete="off" spellcheck="false">
        <select id="mq-checks-field" class="mq-checks-field" aria-label="Search in">
          <option value="all" selected>All fields</option>
          <option value="title">Title</option>
          <option value="name">Check name</option>
          <option value="category">Category</option>
          <option value="description">Description</option>
        </select>
      </div>
      <p class="search-meta" id="mq-checks-count">{count} checks</p>
      <p class="search-empty" id="mq-checks-empty">No checks match this search.</p>
    </div>

    <main id="mq-checks-list">
{cards_html}
    </main>

    <footer>
      <p>
        Generated from <code class="meta-mcn">model_checks.xml</code>.
        See also <a href="report_how_to.html">How to use this report</a>.
      </p>
    </footer>
  </div>
  <script>
    (function () {{
      var input = document.getElementById('mq-checks-search');
      var fieldSel = document.getElementById('mq-checks-field');
      var list = document.getElementById('mq-checks-list');
      var countEl = document.getElementById('mq-checks-count');
      var emptyEl = document.getElementById('mq-checks-empty');
      if (!input || !list) {{ return; }}
      var cards = list.querySelectorAll('.check-card');
      var total = cards.length;

      function fieldText(card, field) {{
        if (field === 'title') {{
          var titleEl = card.querySelector('.check-name');
          return titleEl ? (titleEl.textContent || '') : '';
        }}
        if (field === 'name') {{
          var mcnEl = card.querySelector('header .meta-mcn');
          return mcnEl ? (mcnEl.textContent || '') : '';
        }}
        if (field === 'category') {{
          var catEl = card.querySelector('.meta-cat');
          return catEl ? (catEl.textContent || '') : '';
        }}
        if (field === 'description') {{
          var descEl = card.querySelector('.description p');
          return descEl ? (descEl.textContent || '') : '';
        }}
        return card.textContent || '';
      }}

      function applyFilter() {{
        var q = (input.value || '').trim().toLowerCase();
        var field = fieldSel ? (fieldSel.value || 'all') : 'all';
        var visible = 0;
        for (var i = 0; i < cards.length; i++) {{
          var card = cards[i];
          var blob = fieldText(card, field).toLowerCase();
          var show = !q || blob.indexOf(q) !== -1;
          card.hidden = !show;
          if (show) {{ visible++; }}
        }}
        if (countEl) {{
          countEl.textContent = q
            ? (visible + ' of ' + total + ' checks')
            : (total + ' checks');
        }}
        if (emptyEl) {{
          if (visible === 0) {{ emptyEl.classList.add('show'); }}
          else {{ emptyEl.classList.remove('show'); }}
        }}
      }}

      input.addEventListener('input', applyFilter);
      input.addEventListener('search', applyFilter);
      if (fieldSel) {{ fieldSel.addEventListener('change', applyFilter); }}
    }})();
  </script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    xml_path = argv[0] if len(argv) >= 1 else DEFAULT_XML
    out_path = argv[1] if len(argv) >= 2 else DEFAULT_OUT
    if not os.path.isfile(xml_path):
        print(f"ERROR: model checks XML not found:\n{xml_path}", file=sys.stderr)
        return 1
    checks = load_checks(xml_path)
    html_out = render_html(checks)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html_out)
    print(f"Wrote {len(checks)} checks to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
