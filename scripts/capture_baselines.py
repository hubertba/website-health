#!/usr/bin/env python3
"""Capture HTML baseline snippets for all domains in websites.yaml."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from content_baseline import build_baseline_record, fetch_homepage, save_baseline  # noqa: E402

DEFAULT_INPUT = ROOT / "websites.yaml"
DEFAULT_OUTPUT = ROOT / "baselines"


def all_domains(data: dict) -> list[str]:
    domains: list[str] = []
    for server in data.get("servers", []):
        domains.extend(server.get("domains", []))
    return sorted(set(domains), key=str.lower)


def capture_domain(domain: str) -> tuple[str, dict | None, str | None]:
    page = fetch_homepage(domain)
    if not page.get("html"):
        return domain, None, page.get("error") or "empty body"
    record = build_baseline_record(domain, page)
    record["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return domain, record, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("-w", "--workers", type=int, default=12)
    parser.add_argument("--filter", metavar="DOMAIN", help="Comma-separated domains")
    args = parser.parse_args()

    data = yaml.safe_load(args.input.read_text(encoding="utf-8"))
    domains = all_domains(data)
    if args.filter:
        wanted = {d.strip() for d in args.filter.split(",") if d.strip()}
        domains = [d for d in domains if d in wanted]

    ok = 0
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(capture_domain, domain): domain for domain in domains}
        for future in as_completed(futures):
            domain, record, error = future.result()
            if record:
                save_baseline(args.output, record)
                ok += 1
            else:
                failed.append(f"{domain}: {error}")

    print(f"Captured {ok}/{len(domains)} baselines in {args.output}")
    if failed:
        print("Failed:", ", ".join(failed[:10]), "..." if len(failed) > 10 else "")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
