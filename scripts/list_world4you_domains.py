#!/usr/bin/env python3
"""Print domains discovered from World4You (requires credentials)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from inventory import build_effective_inventory  # noqa: E402
from world4you_dns import credentials_from_env, load_provider_data  # noqa: E402

DEFAULT_INPUT = ROOT / "websites.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json", action="store_true", help="Output JSON instead of plain text")
    args = parser.parse_args()

    if credentials_from_env() is None:
        print("WORLD4YOU_USERNAME and WORLD4YOU_PASSWORD must be set", file=sys.stderr)
        return 1

    with args.input.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    provider = load_provider_data()
    effective = build_effective_inventory(data, provider, provider_configured=True)

    if args.json:
        payload = {
            "packages": provider.packages,
            "hostnames": provider.hostnames,
            "servers": effective.get("servers", []),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Packages ({len(provider.packages)}):")
    for package in provider.packages:
        print(f"  {package}")
    print(f"\nCheckable hostnames ({len(provider.hostnames)}):")
    for hostname in provider.hostnames:
        print(f"  {hostname}")
    print("\nEffective inventory by server:")
    for server in effective.get("servers", []):
        domains = server.get("domains", [])
        print(f"  {server.get('id')}: {len(domains)} domains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
