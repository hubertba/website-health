#!/usr/bin/env python3
"""Generate a mobile-friendly HTML status report from websites.yaml."""

from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "websites.yaml"
DEFAULT_OUTPUT = ROOT / "docs" / "index.html"


def load_data(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def status_label(site: dict) -> str:
    status = site.get("status", "unknown")
    code = site.get("http_status")
    if status == "down":
        return f"DOWN {code or ''}".strip()
    if code == 301:
        return "OK 301→200"
    if code:
        return f"OK {code}"
    return status.upper()


def status_class(site: dict) -> str:
    return "down" if site.get("status") == "down" else "ok"


def type_badge(site_type: str) -> str:
    colors = {
        "docker": "badge-docker",
        "static": "badge-static",
        "redirect": "badge-redirect",
        "proxy": "badge-proxy",
    }
    return colors.get(site_type, "badge-default")


def render_site_card(site: dict) -> str:
    domain = html.escape(site["domain"])
    site_type = html.escape(site.get("type", "unknown"))
    badge_cls = type_badge(site.get("type", ""))
    st_cls = status_class(site)
    label = html.escape(status_label(site))

    details: list[str] = []
    if port := site.get("port"):
        details.append(f"Port {port}")
    if folder := site.get("folder"):
        details.append(html.escape(folder))
    if path := site.get("path"):
        details.append(html.escape(path))
    if redirect := site.get("redirect_to"):
        details.append(f"→ {html.escape(redirect)}")
    if issue := site.get("issue"):
        details.append(html.escape(issue))
    if notes := site.get("notes"):
        details.append(html.escape(notes))

    aliases = site.get("aliases") or []
    alias_html = ""
    if aliases:
        alias_items = "".join(f"<li>{html.escape(a)}</li>" for a in aliases)
        alias_html = f'<ul class="aliases">{alias_items}</ul>'

    return f"""
    <article class="site-card {st_cls}" data-status="{st_cls}" data-type="{site_type}" data-domain="{domain.lower()}">
      <header class="site-header">
        <a class="domain" href="https://{domain}" target="_blank" rel="noopener">{domain}</a>
        <span class="status-pill {st_cls}">{label}</span>
      </header>
      <div class="site-meta">
        <span class="badge {badge_cls}">{site_type}</span>
        {" · ".join(details) if details else ""}
      </div>
      {alias_html}
    </article>
    """


def render_fix(fix: dict) -> str:
    domain = html.escape(fix["domain"])
    cmds = fix.get("commands", [])
    cmd_html = "\n".join(html.escape(c) for c in cmds)
    return f"""
    <div class="fix-block">
      <h3>{domain}</h3>
      <pre><code>{cmd_html}</code></pre>
    </div>
    """


def generate_html(data: dict) -> str:
    meta = data.get("meta", {})
    summary = data.get("summary", {})
    sites: list[dict] = data.get("websites", [])
    fixes: list[dict] = data.get("fixes", [])

    down_sites = [s for s in sites if s.get("status") == "down"]
    ok_count = summary.get("ok", sum(1 for s in sites if s.get("status") != "down"))
    down_count = summary.get("down", len(down_sites))
    total = summary.get("total", len(sites))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    down_cards = "".join(render_site_card(s) for s in down_sites)
    all_cards = "".join(render_site_card(s) for s in sites)
    fix_blocks = "".join(render_fix(f) for f in fixes)

    checked = html.escape(str(meta.get("checked_at", "")))
    server = html.escape(str(meta.get("server_hostname", "")))
    server_ip = html.escape(str(meta.get("server_ip", "")))
    containers = meta.get("running_containers", "—")

    verdict = "All sites healthy" if down_count == 0 else f"{down_count} site(s) need attention"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Website Health — {checked}</title>
  <style>
    :root {{
      --bg: #f4f6f9;
      --surface: #ffffff;
      --text: #1a1d26;
      --muted: #5c6578;
      --border: #e2e8f0;
      --accent: #2563eb;
      --ok: #059669;
      --ok-bg: #ecfdf5;
      --down: #dc2626;
      --down-bg: #fef2f2;
      --shadow: 0 1px 3px rgba(0,0,0,.08);
      --radius: 12px;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1419;
        --surface: #1a2332;
        --text: #e8edf5;
        --muted: #94a3b8;
        --border: #2d3a4f;
        --accent: #60a5fa;
        --ok-bg: #064e3b33;
        --down-bg: #7f1d1d33;
        --shadow: 0 1px 3px rgba(0,0,0,.3);
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 1rem;
      max-width: 960px;
      margin: 0 auto;
    }}
    header.page-header {{
      margin-bottom: 1.5rem;
    }}
    header.page-header h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      margin-bottom: .25rem;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: .9rem;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: .75rem;
      margin-bottom: 1.5rem;
    }}
    @media (min-width: 480px) {{
      .summary-grid {{ grid-template-columns: repeat(4, 1fr); }}
    }}
    .stat-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem;
      text-align: center;
      box-shadow: var(--shadow);
    }}
    .stat-card .value {{
      font-size: 1.75rem;
      font-weight: 700;
      line-height: 1.2;
    }}
    .stat-card .label {{
      font-size: .75rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .stat-card.ok .value {{ color: var(--ok); }}
    .stat-card.down .value {{ color: var(--down); }}
    .verdict {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: .75rem 1rem;
      margin-bottom: 1.5rem;
      font-size: .95rem;
    }}
    .verdict.warn {{
      border-color: var(--down);
      background: var(--down-bg);
    }}
    .controls {{
      display: flex;
      flex-direction: column;
      gap: .5rem;
      margin-bottom: 1rem;
    }}
    @media (min-width: 480px) {{
      .controls {{ flex-direction: row; flex-wrap: wrap; }}
    }}
    .controls input, .controls select {{
      flex: 1;
      min-width: 0;
      padding: .6rem .75rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      color: var(--text);
      font-size: 1rem;
    }}
    section {{ margin-bottom: 2rem; }}
    section h2 {{
      font-size: 1.1rem;
      margin-bottom: .75rem;
      padding-bottom: .35rem;
      border-bottom: 2px solid var(--border);
    }}
    .site-list {{
      display: flex;
      flex-direction: column;
      gap: .6rem;
    }}
    .site-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: .85rem 1rem;
      box-shadow: var(--shadow);
    }}
    .site-card.down {{
      border-left: 4px solid var(--down);
      background: var(--down-bg);
    }}
    .site-header {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: .5rem;
      margin-bottom: .35rem;
    }}
    .domain {{
      font-weight: 600;
      color: var(--accent);
      text-decoration: none;
      word-break: break-all;
    }}
    .domain:hover {{ text-decoration: underline; }}
    .status-pill {{
      font-size: .7rem;
      font-weight: 700;
      padding: .2rem .5rem;
      border-radius: 999px;
      white-space: nowrap;
    }}
    .status-pill.ok {{
      background: var(--ok-bg);
      color: var(--ok);
    }}
    .status-pill.down {{
      background: var(--down-bg);
      color: var(--down);
    }}
    .site-meta {{
      font-size: .8rem;
      color: var(--muted);
    }}
    .badge {{
      display: inline-block;
      font-size: .65rem;
      font-weight: 600;
      text-transform: uppercase;
      padding: .1rem .4rem;
      border-radius: 4px;
      margin-right: .25rem;
    }}
    .badge-docker {{ background: #dbeafe; color: #1e40af; }}
    .badge-static {{ background: #fef3c7; color: #92400e; }}
    .badge-redirect {{ background: #ede9fe; color: #5b21b6; }}
    .badge-proxy {{ background: #fce7f3; color: #9d174d; }}
    @media (prefers-color-scheme: dark) {{
      .badge-docker {{ background: #1e3a5f; color: #93c5fd; }}
      .badge-static {{ background: #78350f; color: #fde68a; }}
      .badge-redirect {{ background: #4c1d95; color: #c4b5fd; }}
      .badge-proxy {{ background: #831843; color: #f9a8d4; }}
    }}
    .aliases {{
      margin-top: .4rem;
      padding-left: 1.2rem;
      font-size: .75rem;
      color: var(--muted);
    }}
    .fix-block {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: .75rem 1rem;
      margin-bottom: .75rem;
    }}
    .fix-block h3 {{
      font-size: .9rem;
      margin-bottom: .5rem;
    }}
    pre {{
      overflow-x: auto;
      font-size: .75rem;
      background: var(--bg);
      padding: .5rem;
      border-radius: 6px;
    }}
    footer {{
      margin-top: 2rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      font-size: .75rem;
      color: var(--muted);
      text-align: center;
    }}
    .hidden {{ display: none !important; }}
  </style>
</head>
<body>
  <header class="page-header">
    <h1>Website Health Report</h1>
    <p class="subtitle">
      Checked <strong>{checked}</strong> ·
      <code>{server}</code> ({server_ip}) ·
      {containers} containers running
    </p>
  </header>

  <div class="summary-grid">
    <div class="stat-card">
      <div class="value">{total}</div>
      <div class="label">Total</div>
    </div>
    <div class="stat-card ok">
      <div class="value">{ok_count}</div>
      <div class="label">OK</div>
    </div>
    <div class="stat-card down">
      <div class="value">{down_count}</div>
      <div class="label">Down</div>
    </div>
    <div class="stat-card">
      <div class="value">{len([s for s in sites if s.get('type') == 'docker'])}</div>
      <div class="label">Docker</div>
    </div>
  </div>

  <div class="verdict{" warn" if down_count else ""}">
    {html.escape(verdict)}
  </div>

  {"<section id='down-section'><h2>Sites that are down</h2><div class='site-list'>" + down_cards + "</div></section>" if down_sites else ""}

  <section>
    <h2>All websites</h2>
    <div class="controls">
      <input type="search" id="search" placeholder="Search domain…" autocomplete="off">
      <select id="filter-status">
        <option value="all">All statuses</option>
        <option value="ok">OK only</option>
        <option value="down">Down only</option>
      </select>
      <select id="filter-type">
        <option value="all">All types</option>
        <option value="docker">Docker</option>
        <option value="static">Static</option>
        <option value="redirect">Redirect</option>
        <option value="proxy">Proxy</option>
      </select>
    </div>
    <div class="site-list" id="all-sites">
      {all_cards}
    </div>
  </section>

  {"<section><h2>Suggested fixes</h2>" + fix_blocks + "</section>" if fixes else ""}

  <footer>
    Generated {generated} from <code>websites.yaml</code>
  </footer>

  <script>
    const search = document.getElementById('search');
    const filterStatus = document.getElementById('filter-status');
    const filterType = document.getElementById('filter-type');
    const cards = document.querySelectorAll('#all-sites .site-card');

    function applyFilters() {{
      const q = search.value.toLowerCase().trim();
      const st = filterStatus.value;
      const ty = filterType.value;
      cards.forEach(card => {{
        const domain = card.dataset.domain || '';
        const matchQ = !q || domain.includes(q);
        const matchSt = st === 'all' || card.dataset.status === st;
        const matchTy = ty === 'all' || card.dataset.type === ty;
        card.classList.toggle('hidden', !(matchQ && matchSt && matchTy));
      }});
    }}
    search.addEventListener('input', applyFilters);
    filterStatus.addEventListener('change', applyFilters);
    filterType.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    data = load_data(args.input)
    html_out = generate_html(data)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_out, encoding="utf-8")
    print(f"Wrote {args.output} ({len(data.get('websites', []))} sites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
