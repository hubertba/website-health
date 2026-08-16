#!/usr/bin/env python3
"""Generate a mobile-friendly HTML report from websites.yaml and check_results.json."""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from health_common import build_maintenance_set, build_runbook_map  # noqa: E402

DEFAULT_INPUT = ROOT / "websites.yaml"
DEFAULT_CHECKS = ROOT / "check_results.json"
DEFAULT_TRENDS = ROOT / "history" / "trends.json"
DEFAULT_ALERTS = ROOT / "alerts.json"
DEFAULT_OUTPUT = ROOT / "docs" / "index.html"
DEFAULT_EXPORT_DIR = ROOT / "docs" / "data"

STATUS_LABELS = {
    "ok": "OK",
    "down": "Down",
    "dns_fail": "DNS fail",
    "ssl_fail": "SSL fail",
    "ssl_warn": "SSL expiring",
    "ssl_crit": "SSL critical",
    "slow": "Slow",
    "http_only": "HTTP only",
    "warn": "Warning",
    "unchecked": "Not checked",
}

TABLE_HEADERS = (
    "<th>Domain</th><th>Server</th><th>DNS</th><th>HTTP</th>"
    "<th>ms</th><th>TTFB</th><th>Size</th><th>Enc</th><th>Proto</th><th>C/W</th>"
    "<th>Sec</th><th>Mail</th><th>Content</th><th>SSL</th><th>Trend</th><th>Status</th>"
)


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
        "ssl_crit": "down",
        "slow": "warn",
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
    proxied = dns.get("proxied")
    if proxied == "cloudflare":
        return f'{html.escape(addrs)} <span class="tag proxy">Cloudflare proxy</span>'
    if proxied:
        return f'{html.escape(addrs)} <span class="tag proxy">{html.escape(proxied)} proxy</span>'
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


def fmt_latency(check: dict | None) -> str:
    if not check:
        return "—"
    ms = check.get("http", {}).get("response_ms")
    if ms is None:
        return "—"
    cls = "tag warn" if ms > 3000 else ""
    return f'<span class="{cls}">{ms}</span>' if cls else str(ms)


def fmt_ttfb(check: dict | None) -> str:
    if not check:
        return "—"
    ms = check.get("http", {}).get("ttfb_ms")
    if ms is None:
        return "—"
    cls = "tag warn" if ms > 1500 else ""
    return f'<span class="{cls}">{ms}</span>' if cls else str(ms)


def fmt_size(check: dict | None) -> str:
    if not check:
        return "—"
    size = check.get("http", {}).get("size_bytes")
    if size is None:
        return "—"
    if size >= 1_000_000:
        return f'<span class="tag warn">{size // 1024}K</span>'
    if size >= 1024:
        return f"{size // 1024}K"
    return str(size)


def fmt_compression(check: dict | None) -> str:
    if not check:
        return "—"
    comp = check.get("http", {}).get("compression") or {}
    enc = comp.get("content_encoding")
    if comp.get("compressed"):
        return html.escape(enc or "yes")
    if comp.get("needs_compression"):
        return '<span class="tag warn">none</span>'
    return "—"


def fmt_http_version(check: dict | None) -> str:
    if not check:
        return "—"
    ver = check.get("http", {}).get("http_version")
    return html.escape(ver) if ver else "—"


def fmt_cold_warm(check: dict | None) -> str:
    if not check:
        return "—"
    http = check.get("http", {})
    cold = http.get("cold_ms")
    warm = http.get("warm_ms")
    if cold is None:
        return "—"
    if warm is None:
        return str(cold)
    return f"{cold}/{warm}"


def fmt_probes(check: dict | None) -> str:
    if not check:
        return ""
    probes = check.get("http", {}).get("probes") or []
    if len(probes) <= 1:
        return ""
    parts = []
    for p in probes:
        parts.append(f"{p.get('path')}: {p.get('status')} ({p.get('response_ms')}ms)")
    return f'<div><strong>Probes:</strong> {html.escape(", ".join(parts))}</div>'


def fmt_timing_detail(check: dict | None) -> str:
    if not check:
        return ""
    timing = check.get("http", {}).get("timing") or {}
    if not timing:
        return ""
    keys = ("dns_ms", "connect_ms", "tls_ms", "ttfb_ms", "download_ms", "total_ms")
    parts = [f"{k.replace('_ms', '')}={timing[k]}" for k in keys if timing.get(k) is not None]
    return f'<div><strong>Timing:</strong> {html.escape(", ".join(parts))}</div>' if parts else ""


def fmt_content(check: dict | None) -> str:
    if not check:
        return "—"
    content = check.get("content")
    if not content:
        return "—"
    if content.get("skipped"):
        return '<span class="tag proxy">webmail</span>'
    if content.get("ok"):
        ratio = content.get("size_ratio")
        if ratio is not None:
            return f'<span class="tag ok">{int(ratio * 100)}%</span>'
        return '<span class="tag ok">ok</span>'
    issues = content.get("issues") or []
    if not issues:
        return "—"
    title = "; ".join(issues[:2])
    return f'<span class="tag warn" title="{html.escape(title)}">!</span>'


def fmt_redirects(check: dict | None) -> str:
    if not check:
        return "—"
    http = check.get("http", {})
    count = http.get("redirect_count", 0)
    if not count:
        return "0"
    chain = http.get("redirects") or []
    title = " → ".join(f'{h.get("status")}:{h.get("url", "")}' for h in chain)
    return f'<span class="tag warn" title="{html.escape(title)}">{count}</span>'


def fmt_security(check: dict | None) -> str:
    if not check:
        return "—"
    http = check.get("http", {})
    if http.get("scheme") != "https":
        return "n/a"
    security = http.get("security") or {}
    if security.get("ok"):
        return '<span class="tag ok">ok</span>'
    missing = security.get("missing") or []
    if not missing:
        return "—"
    return f'<span class="tag warn" title="{html.escape(", ".join(missing))}">-{len(missing)}</span>'


def fmt_mail_dns(check: dict | None) -> str:
    if not check:
        return "—"
    mail = check.get("mail_dns")
    if mail is None:
        return "—"
    parts = []
    if mail.get("mx"):
        parts.append(f'MX:{len(mail["mx"])}')
    parts.append("SPF" if mail.get("spf") else "no SPF")
    parts.append("DMARC" if mail.get("dmarc") else "no DMARC")
    label = " · ".join(parts)
    if mail.get("issues"):
        return f'<span class="tag warn" title="{html.escape("; ".join(mail["issues"]))}">{html.escape(label)}</span>'
    return html.escape(label)


def fmt_trend(domain: str, trends: dict | None) -> str:
    if not trends:
        return "—"
    info = trends.get("domains", {}).get(domain)
    if not info:
        return "—"
    parts = [f'{info.get("uptime_pct", 0)}% uptime']
    if info.get("latency_avg_ms") is not None:
        lat = f'avg {info["latency_avg_ms"]}ms'
        if info.get("latency_p95_ms") is not None:
            lat += f' p95 {info["latency_p95_ms"]}ms'
        if info.get("latency_regression"):
            lat = f'<span class="tag warn">{lat} ↑</span>'
        parts.append(lat)
    if info.get("changed") and info.get("previous_status"):
        parts.append(f'{info["previous_status"]}→{info["current_status"]}')
    elif info.get("current_status") not in {"ok", "http_only"}:
        parts.append(f'since {html.escape(str(info.get("status_since", "")))}')
    return " · ".join(parts)


def domain_id(domain: str) -> str:
    return "domain-" + domain.lower().replace(".", "-")


def fmt_runbook(runbook: list[str] | None) -> str:
    if not runbook:
        return ""
    items = "".join(f"<li><code>{html.escape(step)}</code></li>" for step in runbook)
    return f'<div class="runbook"><strong>Runbook:</strong><ul>{items}</ul></div>'


def render_alerts(
    alerts: dict | None,
    domain_checks: dict | None,
    trends: dict | None,
    runbooks: dict,
) -> str:
    if not alerts or not alerts.get("alerts"):
        suppressed = alerts.get("suppressed_count", 0) if alerts else 0
        if suppressed:
            return f'<p class="muted">No active alerts ({suppressed} domain(s) in maintenance).</p>'
        return ""
    items = []
    for alert in alerts["alerts"][:15]:
        sev = alert.get("severity", "info")
        domain = alert["domain"]
        did = domain_id(domain)
        check = (domain_checks or {}).get(domain)
        runbook = alert.get("runbook") or runbooks.get(domain)
        details = _alert_details(alert, check, trends, domain, runbook)
        items.append(
            f'<li class="alert-item {html.escape(sev)}">'
            f'<button type="button" class="alert-link" data-domain="{html.escape(domain.lower())}" '
            f'aria-expanded="false" aria-controls="alert-detail-{html.escape(did)}">'
            f'<strong>{html.escape(domain)}</strong> '
            f'({html.escape(alert.get("server_id", ""))}) — '
            f'{html.escape(alert.get("message", ""))}'
            f'</button>'
            f'<div class="alert-details" id="alert-detail-{html.escape(did)}" hidden>{details}</div>'
            f'</li>'
        )
    more = ""
    if alerts["alert_count"] > 15:
        more = f'<p class="muted">…and {alerts["alert_count"] - 15} more alerts</p>'
    suppressed_note = ""
    if alerts.get("suppressed_count"):
        suppressed_note = (
            f'<p class="muted">{alerts["suppressed_count"]} domain(s) in maintenance — alerts suppressed.</p>'
        )
    return f"""
    <section class="alerts-panel">
      <h2>Alerts ({alerts['alert_count']})</h2>
      <p class="muted alert-hint">Tap an alert for details or to jump to the domain in the table.</p>
      {suppressed_note}
      <ul class="alert-list">{"".join(items)}</ul>
      {more}
    </section>
    """


def _alert_details(
    alert: dict,
    check: dict | None,
    trends: dict | None,
    domain: str,
    runbook: list[str] | None,
) -> str:
    lines = [
        f'<div><strong>Kind:</strong> {html.escape(alert.get("kind", ""))}</div>',
        f'<div><strong>Severity:</strong> {html.escape(alert.get("severity", ""))}</div>',
    ]
    if prev := alert.get("previous_status"):
        lines.append(f'<div><strong>Previous:</strong> <code>{html.escape(prev)}</code></div>')
    if check:
        lines.append(f'<div><strong>DNS:</strong> {fmt_dns(check)}</div>')
        lines.append(f'<div><strong>HTTP:</strong> {fmt_http(check)}</div>')
        lines.append(f'<div><strong>Latency:</strong> {fmt_latency(check)} ms · TTFB {fmt_ttfb(check)} ms</div>')
        lines.append(fmt_timing_detail(check))
        lines.append(f'<div><strong>Size:</strong> {fmt_size(check)} · Enc {fmt_compression(check)} · {fmt_http_version(check)}</div>')
        lines.append(f'<div><strong>Cold/Warm:</strong> {fmt_cold_warm(check)} ms</div>')
        lines.append(fmt_probes(check))
        lines.append(f'<div><strong>Security:</strong> {fmt_security(check)}</div>')
        lines.append(f'<div><strong>Content:</strong> {fmt_content(check)}</div>')
        if (check.get("content") or {}).get("issues"):
            lines.append(
                f'<div class="muted">{html.escape("; ".join((check.get("content") or {})["issues"]))}</div>'
            )
        if check.get("mail_dns"):
            lines.append(f'<div><strong>Mail DNS:</strong> {fmt_mail_dns(check)}</div>')
        lines.append(f'<div><strong>SSL:</strong> {fmt_ssl(check)}</div>')
    if trends and (info := trends.get("domains", {}).get(domain)):
        lines.append(f'<div><strong>Trend:</strong> {fmt_trend(domain, trends)}</div>')
    lines.append(fmt_runbook(runbook))
    lines.append(
        f'<button type="button" class="jump-to-domain" data-domain="{html.escape(domain.lower())}">'
        f'Scroll to table row</button>'
    )
    return "".join(lines)


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
    if ssl_info.get("crit"):
        return f'{html.escape(label)} <span class="tag down">{days}d left</span>'
    if ssl_info.get("warn"):
        return f'{html.escape(label)} <span class="tag warn">{days}d left</span>'
    return html.escape(label)


def domain_row(
    domain: str,
    server_id: str,
    check: dict | None,
    trends: dict | None = None,
    maintenance: set[str] | None = None,
) -> str:
    status = check.get("status", "unchecked") if check else "unchecked"
    st_cls = status_class(status)
    label = STATUS_LABELS.get(status, status)
    if maintenance and domain in maintenance:
        label = f"{label} · maint"
    scheme = "https"
    if check and check.get("http", {}).get("scheme") == "http":
        scheme = "http"

    maint_tag = ' <span class="tag maint">maint</span>' if maintenance and domain in maintenance else ""

    return f"""
    <tr class="domain-row {st_cls}" id="{domain_id(domain)}"
        data-domain="{html.escape(domain.lower())}"
        data-server="{html.escape(server_id)}" data-status="{st_cls}">
      <td><a href="{scheme}://{html.escape(domain)}" target="_blank" rel="noopener">{html.escape(domain)}</a>{maint_tag}</td>
      <td><code>{html.escape(server_id)}</code></td>
      <td class="mono">{fmt_dns(check)}</td>
      <td class="mono">{fmt_http(check)}</td>
      <td class="mono">{fmt_latency(check)}</td>
      <td class="mono">{fmt_ttfb(check)}</td>
      <td class="mono">{fmt_size(check)}</td>
      <td class="mono">{fmt_compression(check)}</td>
      <td class="mono">{fmt_http_version(check)}</td>
      <td class="mono">{fmt_cold_warm(check)}</td>
      <td class="mono">{fmt_security(check)}</td>
      <td class="mono">{fmt_mail_dns(check)}</td>
      <td class="mono">{fmt_content(check)}</td>
      <td class="mono">{fmt_ssl(check)}</td>
      <td class="mono">{fmt_trend(domain, trends)}</td>
      <td><span class="status-pill {st_cls}">{html.escape(label)}</span></td>
    </tr>
    """


def server_block(
    server: dict,
    checks: dict | None,
    trends: dict | None,
    maintenance: set[str],
) -> str:
    server_id = server.get("id", "")
    hostname = html.escape(server.get("hostname", server_id))
    ip = server.get("ip")
    domains = server.get("domains", [])
    domain_checks = (checks or {}).get("domains", {})

    rows = "".join(
        domain_row(d, server_id, domain_checks.get(d), trends, maintenance)
        for d in sorted(domains, key=str.lower)
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
            <tr>{TABLE_HEADERS}</tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
    """


def write_exports(checks: dict | None, inventory: dict, export_dir: Path) -> None:
    """Write flat JSON and CSV exports for downstream tools."""
    export_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    domain_checks = (checks or {}).get("domains", {})
    maintenance = build_maintenance_set(inventory)

    for server in inventory.get("servers", []):
        server_id = server.get("id", "")
        for domain in server.get("domains", []):
            entry = domain_checks.get(domain, {})
            http = entry.get("http", {})
            ssl_info = entry.get("ssl", {})
            mail = entry.get("mail_dns") or {}
            rows.append({
                "domain": domain,
                "server_id": server_id,
                "status": entry.get("status", "unchecked"),
                "maintenance": domain in maintenance,
                "dns_ok": entry.get("dns", {}).get("ok"),
                "dns_addresses": ",".join(entry.get("dns", {}).get("addresses", [])),
                "http_status": http.get("status"),
                "http_scheme": http.get("scheme"),
                "response_ms": http.get("response_ms"),
                "ttfb_ms": http.get("ttfb_ms"),
                "cold_ms": http.get("cold_ms"),
                "warm_ms": http.get("warm_ms"),
                "size_bytes": http.get("size_bytes"),
                "http_version": http.get("http_version"),
                "compressed": (http.get("compression") or {}).get("compressed"),
                "content_ok": (entry.get("content") or {}).get("ok"),
                "content_issues": ";".join((entry.get("content") or {}).get("issues") or []),
                "redirect_count": http.get("redirect_count"),
                "ssl_days_left": ssl_info.get("days_left"),
                "ssl_expires": ssl_info.get("expires"),
                "mx_count": len(mail.get("mx", [])),
                "has_spf": bool(mail.get("spf")),
                "has_dmarc": bool(mail.get("dmarc")),
            })

    export_data = {
        "checked_at": (checks or {}).get("checked_at"),
        "summary": (checks or {}).get("summary", {}),
        "domains": rows,
    }
    (export_dir / "export.json").write_text(json.dumps(export_data, indent=2), encoding="utf-8")

    if rows:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        (export_dir / "export.csv").write_text(buf.getvalue(), encoding="utf-8")


def generate_html(
    inventory: dict,
    checks: dict | None,
    trends: dict | None,
    alerts: dict | None,
) -> str:
    servers = inventory.get("servers", [])
    maintenance = build_maintenance_set(inventory)
    runbooks = build_runbook_map(inventory)
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
        domain_row(d, sid, domain_checks.get(d), trends, maintenance) for d, sid in all_domains
    )
    server_sections = "".join(server_block(s, checks, trends, maintenance) for s in servers)
    alerts_html = render_alerts(alerts, domain_checks, trends, runbooks)
    history_html = render_history_summary(trends)

    server_options = "".join(
        f'<option value="{html.escape(s.get("id", ""))}">{html.escape(s.get("hostname", ""))}</option>'
        for s in servers
    )

    total = summary.get("total", len(all_domains))
    ok = summary.get("ok", "—")
    down = summary.get("down", "—")
    ssl_warn = summary.get("ssl_warn", "—")
    ssl_crit = summary.get("ssl_crit", "—")
    dns_fail = summary.get("dns_fail", "—")
    slow = summary.get("slow", "—")

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
    :root, [data-theme="light"] {{
      --bg: #f4f6f9; --surface: #fff; --text: #1a1d26; --muted: #5c6578;
      --border: #e2e8f0; --accent: #2563eb; --ok: #059669; --ok-bg: #ecfdf5;
      --down: #dc2626; --down-bg: #fef2f2; --warn: #d97706; --warn-bg: #fffbeb;
      --inv: #6366f1; --inv-bg: #eef2ff; --radius: 10px;
    }}
    [data-theme="dark"] {{
      --bg: #0f1419; --surface: #1a2332; --text: #e8edf5; --muted: #94a3b8;
      --border: #2d3a4f; --accent: #60a5fa; --ok-bg: #064e3b33; --down-bg: #7f1d1d33;
      --warn-bg: #78350f33; --inv-bg: #312e8133;
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
        --bg: #0f1419; --surface: #1a2332; --text: #e8edf5; --muted: #94a3b8;
        --border: #2d3a4f; --accent: #60a5fa; --ok-bg: #064e3b33; --down-bg: #7f1d1d33;
        --warn-bg: #78350f33; --inv-bg: #312e8133;
      }}
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: var(--bg); color: var(--text);
      line-height: 1.45; padding: 1rem; max-width: 1400px; margin: 0 auto; }}
    .top-bar {{ display: flex; justify-content: space-between; align-items: flex-start; gap: .5rem; margin-bottom: .5rem; }}
    h1 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
    .subtitle {{ color: var(--muted); font-size: .9rem; margin-bottom: 1rem; }}
    .theme-btn {{ border: 1px solid var(--border); background: var(--surface); color: var(--text);
      padding: .4rem .65rem; border-radius: 8px; cursor: pointer; font-size: .85rem; white-space: nowrap; }}
    .export-links {{ font-size: .8rem; margin-bottom: 1rem; }}
    .export-links a {{ margin-right: .75rem; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(2,1fr); gap: .6rem; margin-bottom: 1rem; }}
    @media (min-width: 600px) {{ .summary-grid {{ grid-template-columns: repeat(4,1fr); }} }}
    @media (min-width: 900px) {{ .summary-grid {{ grid-template-columns: repeat(7,1fr); }} }}
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
    .tag.down {{ background: var(--down-bg); color: var(--down); }}
    .tag.ok {{ background: var(--ok-bg); color: var(--ok); }}
    .tag.proxy {{ background: #dbeafe; color: #1d4ed8; }}
    .tag.maint {{ background: #e0e7ff; color: #4338ca; }}
    [data-theme="dark"] .tag.proxy {{ background: #1e3a5f; color: #93c5fd; }}
    [data-theme="dark"] .tag.maint {{ background: #312e81; color: #c7d2fe; }}
    .alerts-panel {{ background: var(--down-bg); border: 1px solid var(--down); border-radius: var(--radius);
      padding: .85rem 1rem; margin-bottom: 1rem; }}
    .alerts-panel h2 {{ font-size: 1rem; margin-bottom: .35rem; color: var(--down); }}
    .alert-hint {{ margin-bottom: .5rem; font-size: .78rem; }}
    .alert-list {{ list-style: none; font-size: .85rem; }}
    .alert-item {{ padding: .35rem 0; border-bottom: 1px solid var(--border); }}
    .alert-item:last-child {{ border-bottom: none; }}
    .alert-link {{
      display: block; width: 100%; text-align: left; background: none; border: none;
      padding: .35rem 0; font: inherit; color: inherit; cursor: pointer;
    }}
    .alert-link:hover {{ text-decoration: underline; }}
    .alert-link[aria-expanded="true"] {{ font-weight: 600; }}
    .alert-details {{
      margin: .35rem 0 .5rem .75rem; padding: .55rem .65rem; font-size: .78rem;
      background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    }}
    .alert-details div {{ margin-bottom: .25rem; }}
    .runbook ul {{ margin: .25rem 0 0 1rem; }}
    .jump-to-domain {{
      margin-top: .45rem; padding: .35rem .6rem; font-size: .75rem; border-radius: 6px;
      border: 1px solid var(--border); background: var(--bg); color: var(--accent); cursor: pointer;
    }}
    .domain-row.highlight td {{ animation: highlight-row 2s ease; }}
    @keyframes highlight-row {{
      0%, 100% {{ background: transparent; }}
      30% {{ background: var(--warn-bg); }}
    }}
    .alert-item.critical {{ color: var(--down); }}
    .alert-item.warning {{ color: var(--warn); }}
    .alert-item.info {{ color: var(--muted); }}
    .muted {{ color: var(--muted); font-size: .85rem; }}
    footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border);
      font-size: .75rem; color: var(--muted); text-align: center; }}
  </style>
</head>
<body>
  <div class="top-bar">
    <header>
      <h1>Domain Health Report</h1>
      <p class="subtitle">Checked <strong>{html.escape(str(checked_at))}</strong> · {len(all_domains)} domains · {len(servers)} servers</p>
    </header>
    <button type="button" class="theme-btn" id="theme-toggle" aria-label="Toggle light/dark theme">Theme</button>
  </div>

  <p class="export-links">
    <a href="data/export.json" download>Export JSON</a>
    <a href="data/export.csv" download>Export CSV</a>
    <a href="docs/">Requirements docs</a>
  </p>

  <div class="summary-grid">
    <div class="stat-card"><div class="value">{total}</div><div class="label">Total</div></div>
    <div class="stat-card ok"><div class="value">{ok}</div><div class="label">OK</div></div>
    <div class="stat-card down"><div class="value">{down}</div><div class="label">Down</div></div>
    <div class="stat-card"><div class="value">{dns_fail}</div><div class="label">DNS fail</div></div>
    <div class="stat-card down"><div class="value">{ssl_crit}</div><div class="label">SSL crit</div></div>
    <div class="stat-card"><div class="value">{ssl_warn}</div><div class="label">SSL warn</div></div>
    <div class="stat-card"><div class="value">{slow}</div><div class="label">Slow</div></div>
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
            <tr>{TABLE_HEADERS}</tr>
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

  <footer>Generated from <code>websites.yaml</code> + <code>check_results.json</code> + <code>history/trends.json</code></footer>

  <script>
    const tabs = document.querySelectorAll('.tab');
    const views = document.querySelectorAll('.view');
    const search = document.getElementById('search');
    const filterServer = document.getElementById('filter-server');
    const filterStatus = document.getElementById('filter-status');
    const themeToggle = document.getElementById('theme-toggle');
    const root = document.documentElement;

    function applyTheme(theme) {{
      if (theme === 'light' || theme === 'dark') {{
        root.setAttribute('data-theme', theme);
      }} else {{
        root.removeAttribute('data-theme');
      }}
      localStorage.setItem('health-theme', theme || 'system');
      themeToggle.textContent = theme === 'dark' ? 'Light' : theme === 'light' ? 'Dark' : 'Theme';
    }}

    const savedTheme = localStorage.getItem('health-theme');
    if (savedTheme && savedTheme !== 'system') applyTheme(savedTheme);
    else applyTheme(null);

    themeToggle.addEventListener('click', () => {{
      const current = root.getAttribute('data-theme');
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const effective = current || (prefersDark ? 'dark' : 'light');
      applyTheme(effective === 'dark' ? 'light' : 'dark');
    }});

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

    function showOverview() {{
      tabs.forEach(t => t.classList.remove('active'));
      views.forEach(v => v.classList.remove('active'));
      document.querySelector('.tab[data-view="overview"]').classList.add('active');
      document.getElementById('view-overview').classList.add('active');
    }}

    function scrollToDomain(domain) {{
      showOverview();
      search.value = domain;
      filterServer.value = 'all';
      filterStatus.value = 'all';
      applyFilters();

      const row = document.getElementById('domain-' + domain.replace(/\\./g, '-'));
      if (!row) return;

      row.classList.remove('hidden');
      row.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      row.classList.remove('highlight');
      void row.offsetWidth;
      row.classList.add('highlight');
      setTimeout(() => row.classList.remove('highlight'), 2200);
    }}

    document.querySelectorAll('.alert-link').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const domain = btn.dataset.domain;
        const details = document.getElementById('alert-detail-domain-' + domain.replace(/\\./g, '-'));
        const expanded = btn.getAttribute('aria-expanded') === 'true';

        document.querySelectorAll('.alert-link[aria-expanded="true"]').forEach(other => {{
          if (other !== btn) {{
            other.setAttribute('aria-expanded', 'false');
            const otherDetails = document.getElementById(other.getAttribute('aria-controls'));
            if (otherDetails) otherDetails.hidden = true;
          }}
        }});

        if (details) {{
          details.hidden = expanded;
          btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        }}
        scrollToDomain(domain);
      }});
    }});

    document.querySelectorAll('.jump-to-domain').forEach(btn => {{
      btn.addEventListener('click', (e) => {{
        e.stopPropagation();
        scrollToDomain(btn.dataset.domain);
      }});
    }});

    if (location.hash.startsWith('#domain-')) {{
      const row = document.querySelector(location.hash);
      if (row) {{
        setTimeout(() => {{
          showOverview();
          search.value = row.dataset.domain || '';
          applyFilters();
          row.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          row.classList.add('highlight');
          setTimeout(() => row.classList.remove('highlight'), 2200);
        }}, 100);
      }}
    }}
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
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
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
    write_exports(checks, inventory, args.export_dir)

    n = sum(len(s.get("domains", [])) for s in inventory.get("servers", []))
    print(f"Wrote {args.output} ({n} domains) + exports in {args.export_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
