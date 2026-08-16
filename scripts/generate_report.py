#!/usr/bin/env python3
"""Generate a mobile-friendly HTML report from websites.yaml and check_results.json."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "websites.yaml"
DEFAULT_CHECKS = ROOT / "check_results.json"
DEFAULT_TRENDS = ROOT / "history" / "trends.json"
DEFAULT_ALERTS = ROOT / "alerts.json"
DEFAULT_OUTPUT = ROOT / "docs" / "index.html"

STATUS_LABELS = {
    "ok": "OK",
    "down": "Down",
    "dns_fail": "DNS fail",
    "ssl_fail": "SSL fail",
    "ssl_warn": "SSL expiring",
    "http_only": "HTTP only",
    "warn": "Warning",
    "unchecked": "Not checked",
}


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_checks(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def status_class(status: str) -> str:
    return {
        "ok": "ok",
        "http_only": "warn",
        "ssl_warn": "warn",
        "warn": "warn",
        "unchecked": "inventory",
    }.get(status, "down")


def fmt_dns(check: dict | None) -> str:
    if not check:
        return "—"
    dns = check.get("dns", {})
    if not dns.get("ok"):
        return html.escape(dns.get("error") or "NXDOMAIN")
    addrs = ", ".join(dns.get("addresses", []))
    if dns.get("matches_server") is False:
        return f'{html.escape(addrs)} <span class="tag warn">≠ server IP</span>'
    return html.escape(addrs)


def fmt_http(check: dict | None) -> str:
    if not check:
        return "—"
    http = check.get("http", {})
    if not http.get("status"):
        return html.escape(http.get("error") or "unreachable")
    scheme = http.get("scheme", "https")
    return f'{scheme.upper()} {http["status"]}'


def fmt_trend(domain: str, trends: dict | None) -> str:
    if not trends:
        return "—"
    info = trends.get("domains", {}).get(domain)
    if not info:
        return "—"
    parts = [f'{info.get("uptime_pct", 0)}% uptime']
    if info.get("changed") and info.get("previous_status"):
        parts.append(f'{info["previous_status"]}→{info["current_status"]}')
    elif info.get("current_status") not in {"ok", "http_only"}:
        parts.append(f'since {html.escape(str(info.get("status_since", "")))}')
    return " · ".join(parts)


def render_alerts(alerts: dict | None) -> str:
    if not alerts or not alerts.get("alerts"):
        return ""
    items = []
    for alert in alerts["alerts"][:15]:
        sev = alert.get("severity", "info")
        items.append(
            f'<li class="alert-item {html.escape(sev)}">'
            f'<strong>{html.escape(alert["domain"])}</strong> '
            f'({html.escape(alert.get("server_id", ""))}) — '
            f'{html.escape(alert.get("message", ""))}</li>'
        )
    more = ""
    if alerts["alert_count"] > 15:
        more = f'<p class="muted">…and {alerts["alert_count"] - 15} more alerts</p>'
    return f"""
    <section class="alerts-panel">
      <h2>Alerts ({alerts['alert_count']})</h2>
      <ul class="alert-list">{"".join(items)}</ul>
      {more}
    </section>
    """


def render_history_summary(trends: dict | None) -> str:
    if not trends or not trends.get("domains"):
        return '<p class="muted">No history yet — trends appear after multiple scheduled checks.</p>'

    rows = []
    for domain, info in sorted(trends["domains"].items(), key=lambda x: x[1].get("uptime_pct", 0)):
        if info.get("uptime_pct", 100) >= 100 and not info.get("changed"):
            continue
        st = info.get("current_status", "unknown")
        rows.append(
            f"<tr><td>{html.escape(domain)}</td>"
            f'<td>{info.get("uptime_pct")}%</td>'
            f"<td>{info.get('checks')}</td>"
            f'<td><code>{html.escape(st)}</code></td>'
            f'<td>{html.escape(str(info.get("status_since", "")))}</td></tr>'
        )
        if len(rows) >= 25:
            break

    if not rows:
        return '<p class="muted">All tracked domains at 100% uptime over recent checks.</p>'

    return f"""
    <p class="muted">Based on {trends.get('snapshot_count', 0)} snapshots · computed {html.escape(str(trends.get('computed_at', '')))}</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Domain</th><th>Uptime</th><th>Checks</th><th>Status</th><th>Since</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    """


def fmt_ssl(check: dict | None) -> str:
    if not check:
        return "—"
    ssl_info = check.get("ssl", {})
    if ssl_info.get("ok") is None:
        return html.escape(ssl_info.get("error") or "n/a")
    if not ssl_info.get("ok"):
        return html.escape(ssl_info.get("error") or "invalid")
    days = ssl_info.get("days_left")
    expires = ssl_info.get("expires", "")
    label = f'valid · {expires}'
    if ssl_info.get("warn"):
        return f'{html.escape(label)} <span class="tag warn">{days}d left</span>'
    return html.escape(label)


def domain_row(domain: str, server_id: str, check: dict | None, trends: dict | None = None) -> str:
    status = check.get("status", "unchecked") if check else "unchecked"
    st_cls = status_class(status)
    label = STATUS_LABELS.get(status, status)
    scheme = "https"
    if check and check.get("http", {}).get("scheme") == "http":
        scheme = "http"

    return f"""
    <tr class="domain-row {st_cls}" data-domain="{html.escape(domain.lower())}"
        data-server="{html.escape(server_id)}" data-status="{st_cls}">
      <td><a href="{scheme}://{html.escape(domain)}" target="_blank" rel="noopener">{html.escape(domain)}</a></td>
      <td><code>{html.escape(server_id)}</code></td>
      <td class="mono">{fmt_dns(check)}</td>
      <td class="mono">{fmt_http(check)}</td>
      <td class="mono">{fmt_ssl(check)}</td>
      <td class="mono">{fmt_trend(domain, trends)}</td>
      <td><span class="status-pill {st_cls}">{html.escape(label)}</span></td>
    </tr>
    """


def server_block(server: dict, checks: dict | None, trends: dict | None) -> str:
    server_id = server.get("id", "")
    hostname = html.escape(server.get("hostname", server_id))
    ip = server.get("ip")
    domains = server.get("domains", [])
    domain_checks = (checks or {}).get("domains", {})

    rows = "".join(
        domain_row(d, server_id, domain_checks.get(d), trends) for d in sorted(domains, key=str.lower)
    )

    stats = {"ok": 0, "issue": 0, "unchecked": 0}
    for d in domains:
        c = domain_checks.get(d)
        if not c:
            stats["unchecked"] += 1
        elif c.get("status") == "ok":
            stats["ok"] += 1
        else:
            stats["issue"] += 1

    ip_line = f' · expected IP <code>{html.escape(ip)}</code>' if ip else ""

    return f"""
    <section class="server-section" id="server-{html.escape(server_id)}" data-server="{html.escape(server_id)}">
      <div class="server-header">
        <h2>{hostname}</h2>
        <p class="server-meta"><code>{html.escape(server_id)}</code>{ip_line} · {len(domains)} domains · {stats['ok']} ok · {stats['issue']} issues</p>
      </div>
      <div class="table-wrap">
        <table class="domain-table">
          <thead>
            <tr>
              <th>Domain</th><th>Server</th><th>DNS</th><th>HTTP</th><th>SSL</th><th>Trend</th><th>Status</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """


def generate_html(inventory: dict, checks: dict | None, trends: dict | None, alerts: dict | None) -> str:
    servers = inventory.get("servers", [])
    checked_at = (checks or {}).get("checked_at") or inventory.get("meta", {}).get("checked_at", "—")
    summary = (checks or {}).get("summary", {})

    all_domains: list[tuple[str, str]] = []
    domain_checks = (checks or {}).get("domains", {})
    for server in servers:
        sid = server.get("id", "")
        for domain in server.get("domains", []):
            all_domains.append((domain, sid))
    all_domains.sort(key=lambda x: x[0].lower())

    overview_rows = "".join(
        domain_row(d, sid, domain_checks.get(d), trends) for d, sid in all_domains
    )
    server_sections = "".join(server_block(s, checks, trends) for s in servers)
    alerts_html = render_alerts(alerts)
    history_html = render_history_summary(trends)

    server_options = "".join(
        f'<option value="{html.escape(s.get("id", ""))}">{html.escape(s.get("hostname", ""))}</option>'
        for s in servers
    )

    total = summary.get("total", len(all_domains))
    ok = summary.get("ok", "—")
    down = summary.get("down", "—")
    ssl_warn = summary.get("ssl_warn", "—")
    dns_fail = summary.get("dns_fail", "—")

    unchecked_note = ""
    if not checks:
        unchecked_note = '<div class="verdict warn">No check_results.json — run <code>python3 scripts/check_domains.py</code> first.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Domain Health — {html.escape(str(checked_at))}</title>
  <style>
    :root {{
      --bg: #f4f6f9; --surface: #fff; --text: #1a1d26; --muted: #5c6578;
      --border: #e2e8f0; --accent: #2563eb; --ok: #059669; --ok-bg: #ecfdf5;
      --down: #dc2626; --down-bg: #fef2f2; --warn: #d97706; --warn-bg: #fffbeb;
      --inv: #6366f1; --inv-bg: #eef2ff; --radius: 10px;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1419; --surface: #1a2332; --text: #e8edf5; --muted: #94a3b8;
        --border: #2d3a4f; --accent: #60a5fa; --ok-bg: #064e3b33; --down-bg: #7f1d1d33;
        --warn-bg: #78350f33; --inv-bg: #312e8133;
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: var(--bg); color: var(--text);
      line-height: 1.45; padding: 1rem; max-width: 1100px; margin: 0 auto; }}
    h1 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
    .subtitle {{ color: var(--muted); font-size: .9rem; margin-bottom: 1rem; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(2,1fr); gap: .6rem; margin-bottom: 1rem; }}
    @media (min-width: 600px) {{ .summary-grid {{ grid-template-columns: repeat(5,1fr); }} }}
    .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
      padding: .7rem; text-align: center; }}
    .stat-card .value {{ font-size: 1.4rem; font-weight: 700; }}
    .stat-card .label {{ font-size: .68rem; color: var(--muted); text-transform: uppercase; }}
    .stat-card.ok .value {{ color: var(--ok); }}
    .stat-card.down .value {{ color: var(--down); }}
    .verdict {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
      padding: .7rem 1rem; margin-bottom: 1rem; font-size: .9rem; }}
    .verdict.warn {{ border-color: var(--warn); background: var(--warn-bg); }}
    .tabs {{ display: flex; gap: .4rem; margin-bottom: 1rem; flex-wrap: wrap; }}
    .tab {{ border: 1px solid var(--border); background: var(--surface); color: var(--text);
      padding: .45rem .8rem; border-radius: 999px; cursor: pointer; font-size: .85rem; }}
    .tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .controls {{ display: flex; flex-direction: column; gap: .45rem; margin-bottom: 1rem; }}
    @media (min-width: 600px) {{ .controls {{ flex-direction: row; flex-wrap: wrap; }} }}
    .controls input, .controls select {{ flex: 1; min-width: 9rem; padding: .55rem .7rem;
      border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text); }}
    .view {{ display: none; }}
    .view.active {{ display: block; }}
    section {{ margin-bottom: 2rem; }}
    h2 {{ font-size: 1.1rem; margin-bottom: .3rem; }}
    .server-meta {{ color: var(--muted); font-size: .82rem; margin-bottom: .6rem; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }}
    table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
    th, td {{ padding: .55rem .65rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }}
    th {{ background: var(--bg); font-size: .72rem; text-transform: uppercase; color: var(--muted); }}
    tr:last-child td {{ border-bottom: none; }}
    tr.hidden {{ display: none; }}
    td.mono {{ font-family: ui-monospace, monospace; font-size: .78rem; }}
    a {{ color: var(--accent); text-decoration: none; word-break: break-all; }}
    a:hover {{ text-decoration: underline; }}
    .status-pill {{ font-size: .68rem; font-weight: 700; padding: .15rem .45rem; border-radius: 999px; white-space: nowrap; }}
    .status-pill.ok {{ background: var(--ok-bg); color: var(--ok); }}
    .status-pill.down {{ background: var(--down-bg); color: var(--down); }}
    .status-pill.warn {{ background: var(--warn-bg); color: var(--warn); }}
    .status-pill.inventory {{ background: var(--inv-bg); color: var(--inv); }}
    .tag {{ font-size: .65rem; padding: .05rem .3rem; border-radius: 4px; }}
    .tag.warn {{ background: var(--warn-bg); color: var(--warn); }}
    .alerts-panel {{ background: var(--down-bg); border: 1px solid var(--down); border-radius: var(--radius);
      padding: .85rem 1rem; margin-bottom: 1rem; }}
    .alerts-panel h2 {{ font-size: 1rem; margin-bottom: .5rem; color: var(--down); }}
    .alert-list {{ list-style: none; font-size: .85rem; }}
    .alert-item {{ padding: .25rem 0; }}
    .alert-item.critical {{ color: var(--down); }}
    .alert-item.warning {{ color: var(--warn); }}
    .alert-item.info {{ color: var(--muted); }}
    .muted {{ color: var(--muted); font-size: .85rem; }}
    footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border);
      font-size: .75rem; color: var(--muted); text-align: center; }}
  </style>
</head>
<body>
  <header>
    <h1>Domain Health Report</h1>
    <p class="subtitle">Checked <strong>{html.escape(str(checked_at))}</strong> · {len(all_domains)} domains · {len(servers)} servers</p>
  </header>

  <div class="summary-grid">
    <div class="stat-card"><div class="value">{total}</div><div class="label">Total</div></div>
    <div class="stat-card ok"><div class="value">{ok}</div><div class="label">OK</div></div>
    <div class="stat-card down"><div class="value">{down}</div><div class="label">Down</div></div>
    <div class="stat-card"><div class="value">{dns_fail}</div><div class="label">DNS fail</div></div>
    <div class="stat-card"><div class="value">{ssl_warn}</div><div class="label">SSL warn</div></div>
  </div>

  {unchecked_note}

  {alerts_html}

  <div class="tabs">
    <button class="tab active" data-view="overview">All domains</button>
    <button class="tab" data-view="servers">By server</button>
    <button class="tab" data-view="history">History</button>
  </div>

  <div class="controls">
    <input type="search" id="search" placeholder="Filter domain…" autocomplete="off">
    <select id="filter-server">
      <option value="all">All servers</option>
      {server_options}
    </select>
    <select id="filter-status">
      <option value="all">All statuses</option>
      <option value="ok">OK</option>
      <option value="warn">Warnings</option>
      <option value="down">Issues</option>
      <option value="inventory">Not checked</option>
    </select>
  </div>

  <div id="view-overview" class="view active">
    <section>
      <h2>All domains</h2>
      <div class="table-wrap">
        <table class="domain-table" id="table-overview">
          <thead>
            <tr><th>Domain</th><th>Server</th><th>DNS</th><th>HTTP</th><th>SSL</th><th>Trend</th><th>Status</th></tr>
          </thead>
          <tbody>{overview_rows}</tbody>
        </table>
      </div>
    </section>
  </div>

  <div id="view-servers" class="view">
    {server_sections}
  </div>

  <div id="view-history" class="view">
    <section>
      <h2>History &amp; trends</h2>
      {history_html}
    </section>
  </div>

  <footer>Generated from <code>websites.yaml</code> + <code>check_results.json</code> + <code>history/trends.json</code>
    · <a href="docs/">Requirements docs</a></footer>

  <script>
    const tabs = document.querySelectorAll('.tab');
    const views = document.querySelectorAll('.view');
    const search = document.getElementById('search');
    const filterServer = document.getElementById('filter-server');
    const filterStatus = document.getElementById('filter-status');

    tabs.forEach(tab => tab.addEventListener('click', () => {{
      tabs.forEach(t => t.classList.remove('active'));
      views.forEach(v => v.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('view-' + tab.dataset.view).classList.add('active');
      applyFilters();
    }}));

    function applyFilters() {{
      const q = search.value.toLowerCase().trim();
      const srv = filterServer.value;
      const st = filterStatus.value;
      const activeView = document.querySelector('.view.active');
      const rows = activeView.querySelectorAll('.domain-row');

      rows.forEach(row => {{
        const domain = row.dataset.domain || '';
        const matchQ = !q || domain.includes(q);
        const matchSrv = srv === 'all' || row.dataset.server === srv;
        let matchSt = st === 'all';
        if (!matchSt) {{
          const rs = row.dataset.status;
          if (st === 'warn') matchSt = rs === 'warn';
          else if (st === 'down') matchSt = rs === 'down';
          else matchSt = rs === st;
        }}
        row.classList.toggle('hidden', !(matchQ && matchSrv && matchSt));
      }});

      if (activeView.id === 'view-servers') {{
        activeView.querySelectorAll('.server-section').forEach(section => {{
          if (srv !== 'all' && section.dataset.server !== srv) {{
            section.style.display = 'none';
            return;
          }}
          section.style.display = '';
          const visible = section.querySelectorAll('.domain-row:not(.hidden)').length;
          section.style.display = visible ? '' : 'none';
        }});
      }}
    }}

    [search, filterServer, filterStatus].forEach(el => {{
      el.addEventListener('input', applyFilters);
      el.addEventListener('change', applyFilters);
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-c", "--checks", type=Path, default=DEFAULT_CHECKS)
    parser.add_argument("-t", "--trends", type=Path, default=DEFAULT_TRENDS)
    parser.add_argument("-a", "--alerts", type=Path, default=DEFAULT_ALERTS)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    inventory = load_yaml(args.input)
    checks = load_checks(args.checks)
    trends = load_optional_json(args.trends)
    alerts = load_optional_json(args.alerts)
    out = generate_html(inventory, checks, trends, alerts)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out, encoding="utf-8")
    n = sum(len(s.get("domains", [])) for s in inventory.get("servers", []))
    print(f"Wrote {args.output} ({n} domains)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
