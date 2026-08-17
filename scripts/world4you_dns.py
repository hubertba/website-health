"""World4You DNS provider integration (read-only).

Credentials are read from environment variables — never commit them:

- ``WORLD4YOU_USERNAME`` — World4You customer number
- ``WORLD4YOU_PASSWORD`` — account password

See README.md § Secrets for Cursor Cloud and GitHub Actions setup.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

THIRD_PARTY = Path(__file__).resolve().parent / "third_party"
if str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))

if TYPE_CHECKING:
    from World4YouApi import MyWorld4You

PROVIDER_NAME = "world4you"
ADDRESS_TYPES = frozenset({"A", "AAAA"})


def credentials_from_env() -> tuple[str, str] | None:
    username = os.environ.get("WORLD4YOU_USERNAME", "").strip()
    password = os.environ.get("WORLD4YOU_PASSWORD", "").strip()
    if not username or not password:
        return None
    return username, password


def connect() -> MyWorld4You | None:
    """Log in to World4You when credentials are configured."""
    creds = credentials_from_env()
    if not creds:
        return None

    from World4YouApi import MyWorld4You

    username, password = creds
    session = MyWorld4You()
    try:
        session.login(int(username), password)
    except (PermissionError, ValueError) as exc:
        raise RuntimeError(f"World4You login failed: {exc}") from exc
    return session


def build_address_index(session: MyWorld4You) -> dict[str, list[str]]:
    """Map FQDN -> sorted list of A/AAAA values from all packages."""
    index: dict[str, set[str]] = {}
    for package in session.packages:
        for record in package.resource_records:
            if record.type not in ADDRESS_TYPES:
                continue
            index.setdefault(record.fqdn, set()).add(record.value)
    return {fqdn: sorted(addresses) for fqdn, addresses in index.items()}


def skipped_result(reason: str) -> dict:
    return {
        "provider": PROVIDER_NAME,
        "configured": False,
        "skipped": True,
        "reason": reason,
        "addresses": [],
        "managed": False,
        "matches_live": None,
        "matches_server": None,
        "issues": [],
    }


def compare_provider_dns(
    domain: str,
    live_addresses: list[str],
    provider_index: dict[str, list[str]] | None,
    *,
    expected_ip: str | None = None,
    proxied: str | None = None,
) -> dict:
    """Compare authoritative World4You records with live resolution."""
    if provider_index is None:
        return skipped_result("credentials not configured")

    provider_addresses = provider_index.get(domain.lower())
    if provider_addresses is None:
        return {
            "provider": PROVIDER_NAME,
            "configured": True,
            "skipped": False,
            "managed": False,
            "addresses": [],
            "matches_live": None,
            "matches_server": None,
            "issues": [],
        }

    issues: list[str] = []
    live_set = set(live_addresses)
    provider_set = set(provider_addresses)

    matches_live: bool | None
    if proxied:
        matches_live = None
    elif not live_set:
        matches_live = False
        issues.append("live DNS has no addresses")
    else:
        matches_live = live_set == provider_set
        if not matches_live:
            issues.append(
                f"provider/live mismatch: world4you={sorted(provider_set)} live={sorted(live_set)}"
            )

    matches_server: bool | None
    if proxied or not expected_ip:
        matches_server = None
    else:
        matches_server = expected_ip in provider_set
        if not matches_server:
            issues.append(f"provider missing expected server IP {expected_ip}")

    return {
        "provider": PROVIDER_NAME,
        "configured": True,
        "skipped": False,
        "managed": True,
        "addresses": provider_addresses,
        "matches_live": matches_live,
        "matches_server": matches_server,
        "issues": issues,
        "ok": not issues,
    }


def load_provider_index() -> dict[str, list[str]] | None:
    """Fetch all A/AAAA records from World4You, or None when credentials are absent."""
    if credentials_from_env() is None:
        return None
    session = connect()
    if session is None:
        return None
    return build_address_index(session)
