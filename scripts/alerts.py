#!/usr/bin/env python3
"""Compare check results with previous snapshot and emit alerts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from health_common import ALERT_STATUSES, is_recovery, is_regression

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKS = ROOT / "check_results.json"
DEFAULT_OUTPUT = ROOT / "alerts.json"
HISTORY_DIR = ROOT / "history"
SNAPSHOTS_DIR = HISTORY_DIR / "snapshots"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_snapshot_before_current() -> dict | None:
    """Return the most recent snapshot (previous run)."""
    if not SNAPSHOTS_DIR.is_dir():
        return None
    snapshots = sorted(SNAPSHOTS_DIR.glob("*.json"))
    if not snapshots:
        return None
    return load_json(snapshots[-1])


def build_alerts(current: dict, previous: dict | None) -> dict:
    alerts: list[dict] = []
    curr_domains = current.get("domains", {})
    prev_domains = (previous or {}).get("domains", {})

    for domain, entry in curr_domains.items():
        status = entry.get("status", "unknown")
        prev_entry = prev_domains.get(domain, {})
        prev_status = prev_entry.get("status")

        if prev_status is None:
            if status in ALERT_STATUSES:
                alerts.append(_alert("new_issue", domain, entry, status, "First check — already in bad state"))
            continue

        if is_regression(prev_status, status):
            alerts.append(
                _alert(
                    "regression",
                    domain,
                    entry,
                    status,
                    f"Status worsened: {prev_status} → {status}",
                    previous=prev_status,
                )
            )
        elif is_recovery(prev_status, status):
            alerts.append(
                _alert(
                    "recovered",
                    domain,
                    entry,
                    status,
                    f"Recovered: {prev_status} → {status}",
                    previous=prev_status,
                    severity="info",
                )
            )
        elif status in ALERT_STATUSES and status == prev_status:
            alerts.append(
                _alert(
                    "ongoing",
                    domain,
                    entry,
                    status,
                    f"Still {status}",
                    previous=prev_status,
                    severity=_severity(status),
                )
            )

    alerts.sort(key=lambda a: (_severity_rank(a["severity"]), a["domain"]))
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "checked_at": current.get("checked_at"),
        "has_previous": previous is not None,
        "alert_count": len(alerts),
        "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
        "alerts": alerts,
    }


def _severity(status: str) -> str:
    if status in {"down", "dns_fail", "ssl_fail"}:
        return "critical"
    if status in {"ssl_warn", "warn"}:
        return "warning"
    return "info"


def _severity_rank(severity: str) -> int:
    return {"critical": 0, "warning": 1, "info": 2}.get(severity, 3)


def _alert(
    kind: str,
    domain: str,
    entry: dict,
    status: str,
    message: str,
    previous: str | None = None,
    severity: str | None = None,
) -> dict:
    return {
        "kind": kind,
        "domain": domain,
        "server_id": entry.get("server_id"),
        "status": status,
        "previous_status": previous,
        "severity": severity or _severity(status),
        "message": message,
        "http_status": entry.get("http", {}).get("status"),
        "ssl_days_left": entry.get("ssl", {}).get("days_left"),
    }


def write_github_step_summary(alerts_data: dict) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    lines = [
        "## Domain health alerts",
        "",
        f"**{alerts_data['alert_count']}** alert(s) "
        f"({alerts_data['critical_count']} critical) · checked {alerts_data.get('checked_at', '—')}",
        "",
    ]

    if not alerts_data["alerts"]:
        lines.append("No alerts — all domains stable or improved.")
    else:
        lines.append("| Severity | Domain | Message |")
        lines.append("|----------|--------|---------|")
        for alert in alerts_data["alerts"][:30]:
            lines.append(
                f"| {alert['severity']} | `{alert['domain']}` | {alert['message']} |"
            )
        if alerts_data["alert_count"] > 30:
            lines.append(f"\n_…and {alerts_data['alert_count'] - 30} more in alerts.json_")

    Path(summary_file).write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_github_issues(alerts_data: dict) -> None:
    """Create issues for new regressions (optional, CI only)."""
    import subprocess

    for alert in alerts_data["alerts"]:
        if alert["kind"] not in {"regression", "new_issue"}:
            continue
        if alert["severity"] != "critical":
            continue

        title = f"[{alert['status']}] {alert['domain']}"
        body = (
            f"**Automated alert** from website-health checker\n\n"
            f"- Domain: `{alert['domain']}`\n"
            f"- Server: `{alert['server_id']}`\n"
            f"- Message: {alert['message']}\n"
            f"- HTTP status: {alert.get('http_status')}\n"
            f"- Checked at: {alerts_data.get('checked_at')}\n"
        )
        label = "website-health"

        existing = subprocess.run(
            ["gh", "issue", "list", "--label", label, "--state", "open", "--search", alert["domain"]],
            capture_output=True,
            text=True,
            check=False,
        )
        if alert["domain"] in existing.stdout:
            continue

        subprocess.run(
            [
                "gh", "issue", "create",
                "--title", title,
                "--body", body,
                "--label", label,
            ],
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--checks", type=Path, default=DEFAULT_CHECKS)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--create-issues", action="store_true", help="Open GitHub issues for new critical alerts")
    parser.add_argument("--summary", action="store_true", help="Write GitHub Actions step summary")
    args = parser.parse_args()

    if not args.checks.is_file():
        print(f"Checks not found: {args.checks}", file=sys.stderr)
        return 1

    current = load_json(args.checks)
    previous = latest_snapshot_before_current()
    alerts_data = build_alerts(current, previous)

    args.output.write_text(json.dumps(alerts_data, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.output} — {alerts_data['alert_count']} alerts "
        f"({alerts_data['critical_count']} critical)"
    )

    if args.summary:
        write_github_step_summary(alerts_data)
    if args.create_issues and alerts_data["critical_count"]:
        create_github_issues(alerts_data)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
