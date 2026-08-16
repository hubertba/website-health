#!/usr/bin/env python3
"""Check DNS, HTTP status, and SSL certificates for domains in websites.yaml."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from health_common import build_proxy_map, detect_proxy_provider

DEFAULT_INPUT = ROOT / "websites.yaml"
DEFAULT_OUTPUT = ROOT / "check_results.json"
TIMEOUT = 12
SSL_WARN_DAYS = 30
USER_AGENT = "website-health-checker/1.0"


def load_inventory(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_dns(domain: str) -> dict:
    try:
        infos = socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM)
        addresses = sorted({item[4][0] for item in infos})
        return {"ok": True, "addresses": addresses, "error": None}
    except socket.gaierror as exc:
        return {"ok": False, "addresses": [], "error": str(exc)}


def fetch_status(url: str) -> dict:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return {
                "ok": True,
                "status": response.status,
                "url": response.geturl(),
                "error": None,
            }
    except HTTPError as exc:
        return {
            "ok": exc.code < 500,
            "status": exc.code,
            "url": exc.geturl() if exc.geturl() else url,
            "error": None if exc.code < 500 else str(exc),
        }
    except URLError as exc:
        # Some servers reject HEAD — retry with GET
        if "405" in str(exc) or "Method Not Allowed" in str(exc):
            request = Request(url, method="GET", headers={"User-Agent": USER_AGENT})
            try:
                with urlopen(request, timeout=TIMEOUT) as response:
                    return {
                        "ok": True,
                        "status": response.status,
                        "url": response.geturl(),
                        "error": None,
                    }
            except HTTPError as get_exc:
                return {
                    "ok": get_exc.code < 500,
                    "status": get_exc.code,
                    "url": get_exc.geturl() if get_exc.geturl() else url,
                    "error": None if get_exc.code < 500 else str(get_exc),
                }
            except URLError as get_exc:
                return {"ok": False, "status": None, "url": url, "error": str(get_exc)}
        return {"ok": False, "status": None, "url": url, "error": str(exc)}


def check_http(domain: str) -> dict:
    https = fetch_status(f"https://{domain}/")
    if https["ok"] and https.get("status"):
        https["scheme"] = "https"
        return https

    http = fetch_status(f"http://{domain}/")
    http["scheme"] = "http"
    if http["ok"] and http.get("status"):
        return http

    if https.get("status"):
        https["scheme"] = "https"
        return https
    return http


def check_ssl(domain: str) -> dict:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
        expires = parsedate_to_datetime(cert["notAfter"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_left = (expires - now).days
        issuer = dict(x[0] for x in cert.get("issuer", ()))
        return {
            "ok": days_left >= 0,
            "expires": expires.date().isoformat(),
            "days_left": days_left,
            "issuer": issuer.get("organizationName", issuer.get("commonName", "unknown")),
            "error": None if days_left >= 0 else "certificate expired",
            "warn": 0 <= days_left < SSL_WARN_DAYS,
        }
    except Exception as exc:  # noqa: BLE001 — collect per-domain errors
        return {
            "ok": False,
            "expires": None,
            "days_left": None,
            "issuer": None,
            "error": str(exc),
            "warn": False,
        }


def overall_status(dns: dict, http: dict, ssl_info: dict) -> str:
    if not dns.get("ok"):
        return "dns_fail"
    if http.get("status") and http["status"] >= 500:
        return "down"
    if not http.get("ok") or not http.get("status"):
        return "down"
    if not ssl_info.get("ok"):
        if http.get("scheme") == "http":
            return "http_only"
        return "ssl_fail"
    if ssl_info.get("warn"):
        return "ssl_warn"
    if http["status"] >= 400:
        return "warn"
    return "ok"


def check_domain(
    domain: str,
    server_id: str,
    expected_ip: str | None,
    proxy_provider: str | None = None,
) -> dict:
    dns = check_dns(domain)
    if expected_ip and dns.get("ok"):
        addresses = dns.get("addresses", [])
        if proxy_provider:
            dns["proxied"] = proxy_provider
            dns["matches_server"] = None
        elif detect_proxy_provider(addresses):
            dns["proxied"] = detect_proxy_provider(addresses)
            dns["matches_server"] = None
        else:
            dns["matches_server"] = expected_ip in addresses
    else:
        dns["matches_server"] = None
        if dns.get("ok") and (proxy_provider or detect_proxy_provider(dns.get("addresses", []))):
            dns["proxied"] = proxy_provider or detect_proxy_provider(dns.get("addresses", []))

    http = check_http(domain)
    ssl_info = check_ssl(domain) if http.get("scheme") == "https" or http.get("status") else check_ssl(domain)

    # If site is HTTP-only, SSL failure is expected
    if http.get("scheme") == "http" and http.get("ok"):
        ssl_info = {**ssl_info, "ok": None, "error": "not applicable (HTTP only)"}

    status = overall_status(dns, http, ssl_info if ssl_info.get("ok") is not False else ssl_info)
    if http.get("scheme") == "http" and http.get("ok"):
        status = "http_only" if dns.get("ok") else "dns_fail"

    return {
        "domain": domain,
        "server_id": server_id,
        "dns": dns,
        "http": http,
        "ssl": ssl_info,
        "status": status,
    }


def run_checks(data: dict, workers: int = 16) -> dict:
    proxy_map = build_proxy_map(data)
    tasks: list[tuple[str, str, str | None, str | None]] = []
    for server in data.get("servers", []):
        server_id = server.get("id", server.get("hostname", "unknown"))
        expected_ip = server.get("ip")
        for domain in server.get("domains", []):
            tasks.append((domain, server_id, expected_ip, proxy_map.get(domain)))

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(check_domain, domain, server_id, expected_ip, proxy): domain
            for domain, server_id, expected_ip, proxy in tasks
        }
        for future in as_completed(futures):
            domain = futures[future]
            results[domain] = future.result()

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results.values() if r["status"] == "ok"),
        "down": sum(1 for r in results.values() if r["status"] == "down"),
        "dns_fail": sum(1 for r in results.values() if r["status"] == "dns_fail"),
        "ssl_fail": sum(1 for r in results.values() if r["status"] == "ssl_fail"),
        "ssl_warn": sum(1 for r in results.values() if r["status"] == "ssl_warn"),
        "http_only": sum(1 for r in results.values() if r["status"] == "http_only"),
        "warn": sum(1 for r in results.values() if r["status"] == "warn"),
    }

    return {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "summary": summary,
        "domains": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("-w", "--workers", type=int, default=16)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    data = load_inventory(args.input)
    results = run_checks(data, workers=args.workers)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    s = results["summary"]
    print(
        f"Wrote {args.output} — {s['total']} domains: "
        f"{s['ok']} ok, {s['down']} down, {s['dns_fail']} dns fail, "
        f"{s['ssl_fail']} ssl fail, {s['ssl_warn']} ssl warn, {s['http_only']} http only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
