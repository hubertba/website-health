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


def normalize_data(data: dict) -> dict:
    """Support legacy single-server YAML and multi-server format."""
    if "servers" in data:
        return data

    meta = data.get("meta", {})
    return {
        "meta": {"checked_at": meta.get("checked_at", "")},
        "servers": [
            {
                "id": "web",
                "hostname": meta.get("server_hostname", "unknown"),
                "ip": meta.get("server_ip", ""),
                "role": "Web hosting",
                "apache_status": meta.get("apache_status"),
                "running_containers": meta.get("running_containers"),
                "sources": meta.get("sources", []),
                "summary": data.get("summary", {}),
                "websites": data.get("websites", []),
                "fixes": data.get("fixes", []),
            }
        ],
    }


def site_url(site: dict) -> str:
    scheme = "http" if site.get("http_only") else "https"
    return f"{scheme}://{site['domain']}"


def status_label(site: dict) -> str:
    if site.get("probed") is False:
        return "inventory"
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
    if site.get("probed") is False:
        return "inventory"
    if site.get("http_only") and site.get("status") != "down":
        return "warn"
    return "down" if site.get("status") == "down" else "ok"


def type_badge(site_type: str) -> str:
    colors = {
        "docker": "badge-docker",
        "static": "badge-static",
        "redirect": "badge-redirect",
        "proxy": "badge-proxy",
        "mail": "badge-mail",
        "app": "badge-app",
    }
    return colors.get(site_type, "badge-default")


def server_summary(server: dict) -> dict:
    sites = server.get("websites", [])
    explicit = server.get("summary", {})
    down = [s for s in sites if s.get("status") == "down"]
    ok = [s for s in sites if s.get("status") != "down"]
    return {
        "total": explicit.get("total", len(sites)),
        "ok": explicit.get("ok", len(ok)),
        "down": explicit.get("down", len(down)),
        "inventory": sum(1 for s in sites if s.get("probed") is False),
    }


def render_site_card(site: dict, server_id: str) -> str:
    domain = html.escape(site["domain"])
    site_type = html.escape(site.get("type", "unknown"))
    badge_cls = type_badge(site.get("type", ""))
    st_cls = status_class(site)
    label = html.escape(status_label(site))
    url = html.escape(site_url(site))

    details: list[str] = []
    if category := site.get("category"):
        details.append(html.escape(category))
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
    <article class="site-card {st_cls}" data-status="{st_cls}" data-type="{site_type}" data-server="{html.escape(server_id)}" data-domain="{domain.lower()}">
      <header class="site-header">
        <a class="domain" href="{url}" target="_blank" rel="noopener">{domain}</a>
        <span class="status-pill {st_cls}">{label}</span>
      </header>
      <div class="site-meta">
        <span class="badge {badge_cls}">{site_type}</span>
        {" · ".join(details) if details else ""}
      </div>
      {alias_html}
    </article>
    """


def render_service_card(service: dict) -> str:
    name = html.escape(service.get("name", "Service"))
    svc_type = html.escape(service.get("type", "backend"))
    port = service.get("port", "")
    path = html.escape(service.get("path", ""))
    bind = html.escape(service.get("bind", ""))
    notes = html.escape(service.get("notes", ""))

    details = []
    if bind:
        details.append(bind)
    elif port:
        details.append(f"Port {port}")
    if path:
        details.append(path)
    if notes:
        details.append(notes)

    return f"""
    <article class="site-card inventory service-card">
      <header class="site-header">
        <span class="domain">{name}</span>
        <span class="status-pill inventory">backend</span>
      </header>
      <div class="site-meta">
        <span class="badge badge-api">{svc_type}</span>
        {" · ".join(details) if details else ""}
      </div>
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


def render_server_section(server: dict) -> str:
    server_id = server.get("id", "unknown")
    hostname = html.escape(server.get("hostname", server_id))
    role = html.escape(server.get("role", ""))
    ip = html.escape(str(server.get("ip", "")))
    summary = server_summary(server)
    sites = server.get("websites", [])
    services = server.get("services", [])
    fixes = server.get("fixes", [])

    extras: list[str] = []
    if containers := server.get("running_containers"):
        extras.append(f"{containers} Docker containers")
    if server.get("docker_containers") == 0:
        extras.append("no Docker web containers")
    if apache := server.get("apache_vhosts"):
        extras.append(f"{apache} Apache vhosts")
    extra_line = " · ".join(extras)

    down_sites = [s for s in sites if s.get("status") == "down"]
    down_cards = "".join(render_site_card(s, server_id) for s in down_sites)
    all_cards = "".join(render_site_card(s, server_id) for s in sites)
    service_cards = "".join(render_service_card(s) for s in services)
    fix_blocks = "".join(render_fix(f) for f in fixes)

    down_section = ""
    if down_sites:
        down_section = f"""
        <div class="server-subsection">
          <h3>Sites that are down</h3>
          <div class="site-list">{down_cards}</div>
        </div>
        """

    services_section = ""
    if services:
        services_section = f"""
        <div class="server-subsection">
          <h3>Backend services (not Apache)</h3>
          <div class="site-list">{service_cards}</div>
        </div>
        """

    fixes_section = ""
    if fixes:
        fixes_section = f"""
        <div class="server-subsection">
          <h3>Suggested fixes</h3>
          {fix_blocks}
        </div>
        """

    return f"""
    <section class="server-section" id="server-{html.escape(server_id)}" data-server="{html.escape(server_id)}">
      <div class="server-header">
        <h2>{hostname}</h2>
        <p class="server-meta">{role}{f" · {ip}" if ip else ""}{f" · {extra_line}" if extra_line else ""}</p>
        <div class="summary-grid server-stats">
          <div class="stat-card"><div class="value">{summary['total']}</div><div class="label">Sites</div></div>
          <div class="stat-card ok"><div class="value">{summary['ok']}</div><div class="label">OK</div></div>
          <div class="stat-card down"><div class="value">{summary['down']}</div><div class="label">Down</div></div>
          <div class="stat-card"><div class="value">{summary['inventory']}</div><div class="label">Inventory</div></div>
        </div>
      </div>
      {down_section}
      <div class="server-subsection">
        <h3>All sites</h3>
        <div class="site-list server-sites">{all_cards}</div>
      </div>
      {services_section}
      {fixes_section}
    </section>
    """


def aggregate_summary(servers: list[dict]) -> dict:
    totals = {"total": 0, "ok": 0, "down": 0, "inventory": 0, "servers": len(servers)}
    for server in servers:
        s = server_summary(server)
        totals["total"] += s["total"]
        totals["ok"] += s["ok"]
        totals["down"] += s["down"]
        totals["inventory"] += s["inventory"]
    return totals


def generate_html(data: dict) -> str:
    data = normalize_data(data)
    meta = data.get("meta", {})
    servers: list[dict] = data.get("servers", [])
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    checked = html.escape(str(meta.get("checked_at", "")))
    agg = aggregate_summary(servers)

    server_sections = "".join(render_server_section(s) for s in servers)
    server_options = "".join(
        f'<option value="{html.escape(s.get("id", ""))}">{html.escape(s.get("hostname", s.get("id", "")))}</option>'
        for s in servers
    )

    verdict = "All probed sites healthy" if agg["down"] == 0 else f"{agg['down']} site(s) need attention"
    if agg["inventory"]:
        verdict += f" · {agg['inventory']} inventory-only (not probed)"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Hosted Services — {checked}</title>
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
      --warn: #d97706;
      --warn-bg: #fffbeb;
      --inv: #6366f1;
      --inv-bg: #eef2ff;
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
        --warn-bg: #78350f33;
        --inv-bg: #312e8133;
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
    header.page-header {{ margin-bottom: 1.5rem; }}
    header.page-header h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: .25rem; }}
    .subtitle {{ color: var(--muted); font-size: .9rem; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: .75rem;
      margin-bottom: 1rem;
    }}
    @media (min-width: 480px) {{ .summary-grid {{ grid-template-columns: repeat(5, 1fr); }} }}
    .server-stats {{ margin-top: .75rem; }}
    .stat-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: .75rem;
      text-align: center;
      box-shadow: var(--shadow);
    }}
    .stat-card .value {{ font-size: 1.5rem; font-weight: 700; line-height: 1.2; }}
    .stat-card .label {{ font-size: .7rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
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
    .verdict.warn {{ border-color: var(--down); background: var(--down-bg); }}
    .controls {{
      display: flex;
      flex-direction: column;
      gap: .5rem;
      margin-bottom: 1.5rem;
      position: sticky;
      top: 0;
      z-index: 10;
      background: var(--bg);
      padding: .5rem 0;
    }}
    @media (min-width: 480px) {{ .controls {{ flex-direction: row; flex-wrap: wrap; }} }}
    .controls input, .controls select {{
      flex: 1;
      min-width: 8rem;
      padding: .6rem .75rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      color: var(--text);
      font-size: 1rem;
    }}
    .server-section {{
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 2px solid var(--border);
    }}
    .server-section:last-of-type {{ border-bottom: none; }}
    .server-header h2 {{ font-size: 1.2rem; margin-bottom: .2rem; }}
    .server-meta {{ color: var(--muted); font-size: .85rem; margin-bottom: .5rem; }}
    .server-subsection {{ margin-top: 1.25rem; }}
    .server-subsection h3 {{
      font-size: 1rem;
      margin-bottom: .6rem;
      color: var(--muted);
    }}
    .site-list {{ display: flex; flex-direction: column; gap: .6rem; }}
    .site-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: .85rem 1rem;
      box-shadow: var(--shadow);
    }}
    .site-card.down {{ border-left: 4px solid var(--down); background: var(--down-bg); }}
    .site-card.warn {{ border-left: 4px solid var(--warn); background: var(--warn-bg); }}
    .site-card.inventory {{ border-left: 4px solid var(--inv); }}
    .site-header {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: .5rem;
      margin-bottom: .35rem;
    }}
    .domain {{ font-weight: 600; color: var(--accent); text-decoration: none; word-break: break-all; }}
    a.domain:hover {{ text-decoration: underline; }}
    .status-pill {{
      font-size: .7rem;
      font-weight: 700;
      padding: .2rem .5rem;
      border-radius: 999px;
      white-space: nowrap;
    }}
    .status-pill.ok {{ background: var(--ok-bg); color: var(--ok); }}
    .status-pill.down {{ background: var(--down-bg); color: var(--down); }}
    .status-pill.warn {{ background: var(--warn-bg); color: var(--warn); }}
    .status-pill.inventory {{ background: var(--inv-bg); color: var(--inv); }}
    .site-meta {{ font-size: .8rem; color: var(--muted); }}
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
    .badge-mail {{ background: #d1fae5; color: #065f46; }}
    .badge-app {{ background: #e0e7ff; color: #3730a3; }}
    .badge-api {{ background: #f3e8ff; color: #6b21a8; }}
    @media (prefers-color-scheme: dark) {{
      .badge-docker {{ background: #1e3a5f; color: #93c5fd; }}
      .badge-static {{ background: #78350f; color: #fde68a; }}
      .badge-redirect {{ background: #4c1d95; color: #c4b5fd; }}
      .badge-proxy {{ background: #831843; color: #f9a8d4; }}
      .badge-mail {{ background: #064e3b; color: #6ee7b7; }}
      .badge-app {{ background: #312e81; color: #a5b4fc; }}
      .badge-api {{ background: #581c87; color: #d8b4fe; }}
    }}
    .aliases {{ margin-top: .4rem; padding-left: 1.2rem; font-size: .75rem; color: var(--muted); }}
    .fix-block {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: .75rem 1rem;
      margin-bottom: .75rem;
    }}
    .fix-block h3 {{ font-size: .9rem; margin-bottom: .5rem; }}
    pre {{ overflow-x: auto; font-size: .75rem; background: var(--bg); padding: .5rem; border-radius: 6px; }}
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
    <h1>Hosted Services Report</h1>
    <p class="subtitle">Checked <strong>{checked}</strong> · {agg['servers']} servers · {agg['total']} sites</p>
  </header>

  <div class="summary-grid">
    <div class="stat-card"><div class="value">{agg['total']}</div><div class="label">Total</div></div>
    <div class="stat-card ok"><div class="value">{agg['ok']}</div><div class="label">OK</div></div>
    <div class="stat-card down"><div class="value">{agg['down']}</div><div class="label">Down</div></div>
    <div class="stat-card"><div class="value">{agg['inventory']}</div><div class="label">Inventory</div></div>
    <div class="stat-card"><div class="value">{agg['servers']}</div><div class="label">Servers</div></div>
  </div>

  <div class="verdict{" warn" if agg['down'] else ""}">
    {html.escape(verdict)}
  </div>

  <div class="controls">
    <input type="search" id="search" placeholder="Search domain…" autocomplete="off">
    <select id="filter-server">
      <option value="all">All servers</option>
      {server_options}
    </select>
    <select id="filter-status">
      <option value="all">All statuses</option>
      <option value="ok">OK / probed</option>
      <option value="down">Down</option>
      <option value="inventory">Inventory only</option>
      <option value="warn">HTTP-only / warnings</option>
    </select>
    <select id="filter-type">
      <option value="all">All types</option>
      <option value="docker">Docker</option>
      <option value="static">Static</option>
      <option value="redirect">Redirect</option>
      <option value="proxy">Proxy</option>
      <option value="mail">Mail webmail</option>
      <option value="app">App / admin</option>
    </select>
  </div>

  {server_sections}

  <footer>Generated {generated} from <code>websites.yaml</code></footer>

  <script>
    const search = document.getElementById('search');
    const filterServer = document.getElementById('filter-server');
    const filterStatus = document.getElementById('filter-status');
    const filterType = document.getElementById('filter-type');
    const cards = document.querySelectorAll('.site-card[data-domain]');
    const sections = document.querySelectorAll('.server-section');

    function applyFilters() {{
      const q = search.value.toLowerCase().trim();
      const srv = filterServer.value;
      const st = filterStatus.value;
      const ty = filterType.value;

      cards.forEach(card => {{
        const domain = card.dataset.domain || '';
        const matchQ = !q || domain.includes(q);
        const matchSrv = srv === 'all' || card.dataset.server === srv;
        const matchSt = st === 'all' || card.dataset.status === st;
        const matchTy = ty === 'all' || card.dataset.type === ty;
        card.classList.toggle('hidden', !(matchQ && matchSrv && matchSt && matchTy));
      }});

      sections.forEach(section => {{
        if (srv !== 'all' && section.dataset.server !== srv) {{
          section.classList.add('hidden');
          return;
        }}
        section.classList.remove('hidden');
        const visible = section.querySelectorAll('.site-card[data-domain]:not(.hidden)');
        const subs = section.querySelectorAll('.server-subsection');
        subs.forEach(sub => {{
          const subCards = sub.querySelectorAll('.site-card[data-domain]');
          if (!subCards.length) return;
          const anyVisible = [...subCards].some(c => !c.classList.contains('hidden'));
          sub.classList.toggle('hidden', !anyVisible);
        }});
      }});
    }}

    [search, filterServer, filterStatus, filterType].forEach(el =>
      el.addEventListener('input', applyFilters));
    [filterServer, filterStatus, filterType].forEach(el =>
      el.addEventListener('change', applyFilters));
  </script>
</body>
</html>
"""


def count_sites(data: dict) -> int:
    data = normalize_data(data)
    return sum(len(s.get("websites", [])) for s in data.get("servers", []))


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
    print(f"Wrote {args.output} ({count_sites(data)} sites across {len(normalize_data(data).get('servers', []))} servers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
