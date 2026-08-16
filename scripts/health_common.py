"""Shared helpers for domain health checks, history, and alerts."""

from __future__ import annotations

OK_STATUS = "ok"
HTTP_ONLY_STATUS = "http_only"

# Lower number = healthier (used for regression detection).
STATUS_SEVERITY: dict[str, int] = {
    OK_STATUS: 0,
    HTTP_ONLY_STATUS: 1,
    "warn": 2,
    "ssl_warn": 3,
    "dns_fail": 4,
    "ssl_fail": 5,
    "down": 6,
}

ALERT_STATUSES = frozenset({"down", "dns_fail", "ssl_fail", "ssl_warn", "warn"})


def is_healthy(status: str) -> bool:
    return status in {OK_STATUS, HTTP_ONLY_STATUS}


def is_regression(old_status: str, new_status: str) -> bool:
    return STATUS_SEVERITY.get(new_status, 99) > STATUS_SEVERITY.get(old_status, 0)


def is_recovery(old_status: str, new_status: str) -> bool:
    return not is_healthy(old_status) and is_healthy(new_status)


def looks_like_cloudflare(ip: str) -> bool:
    """Heuristic check for Cloudflare anycast/proxy addresses."""
    if ":" in ip:
        lower = ip.lower()
        return lower.startswith("2606:4700:") or lower.startswith("2a06:98c0:")
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        first, second = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    if first == 104 and 16 <= second <= 31:
        return True
    return first == 172 and 64 <= second <= 71


def detect_proxy_provider(addresses: list[str]) -> str | None:
    if not addresses:
        return None
    if all(looks_like_cloudflare(addr) for addr in addresses):
        return "cloudflare"
    return None


def build_proxy_map(data: dict) -> dict[str, str]:
    """Domain -> proxy provider from meta.proxied in websites.yaml."""
    proxied: dict[str, str] = {}
    for provider, domains in (data.get("meta", {}).get("proxied") or {}).items():
        for domain in domains or []:
            proxied[domain] = provider
    return proxied


def slim_snapshot(results: dict) -> dict:
    """Compact snapshot for history storage."""
    domains = {}
    for domain, entry in results.get("domains", {}).items():
        http = entry.get("http", {})
        domains[domain] = {
            "status": entry.get("status"),
            "server_id": entry.get("server_id"),
            "http_status": http.get("status"),
            "http_scheme": http.get("scheme"),
            "ssl_days_left": entry.get("ssl", {}).get("days_left"),
        }
    return {
        "checked_at": results.get("checked_at"),
        "summary": results.get("summary", {}),
        "domains": domains,
    }
