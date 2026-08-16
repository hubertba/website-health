#!/usr/bin/env python3
"""Persist check snapshots and compute per-domain history trends."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from health_common import LATENCY_REGRESSION_FACTOR, OK_STATUS, percentile, slim_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKS = ROOT / "check_results.json"
HISTORY_DIR = ROOT / "history"
SNAPSHOTS_DIR = HISTORY_DIR / "snapshots"
INDEX_FILE = HISTORY_DIR / "index.json"
TRENDS_FILE = HISTORY_DIR / "trends.json"
MAX_SNAPSHOTS = 90


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def snapshot_filename(checked_at: str) -> str:
    # checked_at format: "2026-08-16 19:05 UTC"
    try:
        dt = datetime.strptime(checked_at, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H%M%SZ.json")


def list_snapshots() -> list[Path]:
    if not SNAPSHOTS_DIR.is_dir():
        return []
    return sorted(SNAPSHOTS_DIR.glob("*.json"))


def load_snapshot(path: Path) -> dict:
    return load_json(path)


def append_snapshot(results: dict) -> Path:
    slim = slim_snapshot(results)
    name = snapshot_filename(slim.get("checked_at", ""))
    path = SNAPSHOTS_DIR / name
    # Avoid duplicate writes within the same minute
    if path.exists():
        return path
    save_json(path, slim)

    snapshots = list_snapshots()
    index = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "snapshot_count": len(snapshots),
        "latest": snapshots[-1].name if snapshots else None,
        "oldest": snapshots[0].name if snapshots else None,
    }
    save_json(INDEX_FILE, index)

    if len(snapshots) > MAX_SNAPSHOTS:
        for old in snapshots[: len(snapshots) - MAX_SNAPSHOTS]:
            old.unlink(missing_ok=True)
        snapshots = list_snapshots()
        index["snapshot_count"] = len(snapshots)
        index["oldest"] = snapshots[0].name if snapshots else None
        save_json(INDEX_FILE, index)

    return path


def previous_snapshot() -> dict | None:
    snapshots = list_snapshots()
    if not snapshots:
        return None
    return load_snapshot(snapshots[-1])


def compute_trends(limit: int = MAX_SNAPSHOTS) -> dict:
    snapshots = list_snapshots()
    if not snapshots:
        return {"snapshot_count": 0, "domains": {}}

    selected = snapshots[-limit:]
    all_domains: set[str] = set()
    for snap_path in selected:
        snap = load_snapshot(snap_path)
        all_domains.update(snap.get("domains", {}).keys())

    trends: dict[str, dict] = {}
    for domain in sorted(all_domains):
        history: list[dict] = []
        latency_samples: list[int] = []
        for snap_path in selected:
            snap = load_snapshot(snap_path)
            entry = snap.get("domains", {}).get(domain)
            if entry:
                history.append({"at": snap.get("checked_at"), "status": entry.get("status")})
                if entry.get("response_ms") is not None:
                    latency_samples.append(int(entry["response_ms"]))

        if not history:
            continue

        current = history[-1]["status"]
        previous = history[-2]["status"] if len(history) >= 2 else None
        ok_count = sum(1 for h in history if h["status"] == OK_STATUS)
        uptime_pct = round(100 * ok_count / len(history), 1)

        since = history[-1]["at"]
        for point in reversed(history):
            if point["status"] == current:
                since = point["at"]
            else:
                break

        latency_avg = round(sum(latency_samples) / len(latency_samples)) if latency_samples else None
        latency_p95 = percentile(latency_samples, 95)
        latency_current = latency_samples[-1] if latency_samples else None
        baseline_samples = latency_samples[:-1][-7:]
        latency_baseline = round(sum(baseline_samples) / len(baseline_samples)) if len(baseline_samples) >= 2 else None
        latency_regression = False
        if latency_baseline and latency_current:
            latency_regression = latency_current > latency_baseline * LATENCY_REGRESSION_FACTOR

        trends[domain] = {
            "current_status": current,
            "previous_status": previous,
            "uptime_pct": uptime_pct,
            "checks": len(history),
            "status_since": since,
            "changed": previous is not None and previous != current,
            "latency_avg_ms": latency_avg,
            "latency_p95_ms": latency_p95,
            "latency_current_ms": latency_current,
            "latency_baseline_ms": latency_baseline,
            "latency_regression": latency_regression,
        }

    return {
        "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "snapshot_count": len(selected),
        "domains": trends,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--checks", type=Path, default=DEFAULT_CHECKS)
    parser.add_argument("--append", action="store_true", help="Append current check_results to history")
    parser.add_argument("--trends-only", action="store_true", help="Recompute trends.json only")
    args = parser.parse_args()

    if args.trends_only:
        trends = compute_trends()
        save_json(TRENDS_FILE, trends)
        print(f"Wrote {TRENDS_FILE} ({trends['snapshot_count']} snapshots, {len(trends['domains'])} domains)")
        return 0

    if args.append:
        if not args.checks.is_file():
            print(f"Checks not found: {args.checks}", file=sys.stderr)
            return 1
        results = load_json(args.checks)
        path = append_snapshot(results)
        print(f"Appended snapshot {path.name}")

    trends = compute_trends()
    save_json(TRENDS_FILE, trends)
    print(
        f"Wrote {TRENDS_FILE} — {trends['snapshot_count']} snapshots, "
        f"{len(trends['domains'])} domains tracked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
