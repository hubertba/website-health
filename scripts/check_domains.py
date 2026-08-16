#!/usr/bin/env python3
"""Check DNS, HTTP status, and SSL certificates for domains in websites.yaml."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import dns.exception
import dns.resolver
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from health_common import (  # noqa: E402
    SLOW_RESPONSE_MS,
    SSL_CRIT_DAYS,
    SSL_WARN_DAYS,
    build_proxy_map,
    detect_proxy_provider,
)

DEFAULT_INPUT = ROOT / "websites.yaml"
DEFAULT_OUTPUT = ROOT / "check_results.json"
TIMEOUT = 12
MAX_REDIRECTS = 10
USER_AGENT = "website-health-checker/2.0"

SECURITY_HEADERS = ("strict-transport-security", "x-frame-options", "x-content-type-options")


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


def _resolve_txt(name: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(name, "TXT")
        return [b"".join(part).decode("utf-8", errors="replace") for rdata in answers for part in [rdata.strings]]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
        return []


def check_mail_dns(domain: str) -> dict:
    """MX, SPF, and DMARC checks for mail-server domains."""
    result: dict = {"mx": [], "spf": None, "dmarc": None, "ok": True, "issues": []}

    try:
        mx_answers = dns.resolver.resolve(domain, "MX")
        result["mx"] = sorted(
            [{"priority": r.preference, "host": str(r.exchange).rstrip(".")} for r in mx_answers],
            key=lambda x: x["priority"],
        )
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException) as exc:
        result["ok"] = False
        result["issues"].append(f"MX missing: {exc}")

    for txt in _resolve_txt(domain):
        if txt.lower().startswith("v=spf1"):
            result["spf"] = txt
            break
    if not result["spf"]:
        result["issues"].append("SPF record not found")

    dmarc_name = f"_dmarc.{domain}"
    for txt in _resolve_txt(dmarc_name):
        if txt.lower().startswith("v=dmarc1"):
            result["dmarc"] = txt
            break
    if not result["dmarc"]:
        result["issues"].append("DMARC record not found")

    if result["issues"]:
        result["ok"] = len(result["mx"]) > 0
    return result


def _request_head(url: str) -> tuple[HTTPError | None, dict | None, float]:
    """Return (error, headers_dict, elapsed_ms) for a HEAD request."""
    start = time.perf_counter()
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            elapsed = round((time.perf_counter() - start) * 1000)
            headers = {k.lower(): v for k, v in response.headers.items()}
            return None, {"status": response.status, "url": response.geturl(), "headers": headers}, elapsed
    except HTTPError as exc:
        elapsed = round((time.perf_counter() - start) * 1000)
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return exc, {"status": exc.code, "url": exc.geturl() or url, "headers": headers}, elapsed
    except URLError as exc:
        elapsed = round((time.perf_counter() - start) * 1000)
        return exc, None, elapsed


def fetch_status(url: str) -> dict:
    chain: list[dict] = []
    current = url
    total_ms = 0
    redirect_codes = {301, 302, 303, 307, 308}

    for hop in range(MAX_REDIRECTS + 1):
        error, info, elapsed = _request_head(current)
        total_ms += elapsed

        if info:
            chain.append({"url": current, "status": info["status"]})
            if error is None or not isinstance(error, HTTPError) or error.code not in redirect_codes:
                security = _check_security_headers(info.get("headers", {}))
                return {
                    "ok": info["status"] < 500,
                    "status": info["status"],
                    "url": info["url"],
                    "final_url": info["url"],
                    "redirects": chain[:-1],
                    "redirect_count": len(chain) - 1,
                    "response_ms": total_ms,
                    "security": security,
                    "error": None if info["status"] < 500 else str(error),
                }

        if isinstance(error, HTTPError) and error.code in redirect_codes:
            location = error.headers.get("Location") if error.headers else None
            if not location:
                return _http_error_result(url, chain, total_ms, f"redirect {error.code} without Location")
            next_url = urljoin(current, location)
            chain.append({"url": current, "status": error.code, "location": next_url})
            current = next_url
            continue

        if isinstance(error, URLError) and ("405" in str(error) or "Method Not Allowed" in str(error)):
            return _fetch_get_fallback(url, chain, total_ms)

        return _http_error_result(url, chain, total_ms, str(error) if error else "unknown error")

    return _http_error_result(url, chain, total_ms, f"more than {MAX_REDIRECTS} redirects")


def _fetch_get_fallback(url: str, chain: list[dict], prior_ms: int) -> dict:
    start = time.perf_counter()
    request = Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            total_ms = prior_ms + round((time.perf_counter() - start) * 1000)
            headers = {k.lower(): v for k, v in response.headers.items()}
            security = _check_security_headers(headers)
            return {
                "ok": True,
                "status": response.status,
                "url": response.geturl(),
                "final_url": response.geturl(),
                "redirects": chain,
                "redirect_count": len(chain),
                "response_ms": total_ms,
                "security": security,
                "error": None,
            }
    except HTTPError as exc:
        total_ms = prior_ms + round((time.perf_counter() - start) * 1000)
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        security = _check_security_headers(headers)
        return {
            "ok": exc.code < 500,
            "status": exc.code,
            "url": exc.geturl() or url,
            "final_url": exc.geturl() or url,
            "redirects": chain,
            "redirect_count": len(chain),
            "response_ms": total_ms,
            "security": security,
            "error": None if exc.code < 500 else str(exc),
        }
    except URLError as exc:
        total_ms = prior_ms + round((time.perf_counter() - start) * 1000)
        return _http_error_result(url, chain, total_ms, str(exc))


def _http_error_result(url: str, chain: list[dict], total_ms: int, error: str) -> dict:
    return {
        "ok": False,
        "status": None,
        "url": url,
        "final_url": url,
        "redirects": chain,
        "redirect_count": len(chain),
        "response_ms": total_ms,
        "security": {},
        "error": error,
    }


def _check_security_headers(headers: dict) -> dict:
    present = {h: headers.get(h) for h in SECURITY_HEADERS if headers.get(h)}
    missing = [h for h in SECURITY_HEADERS if h not in present]
    insecure_redirect = False
    return {
        "present": present,
        "missing": missing,
        "ok": len(missing) == 0,
        "insecure_redirect": insecure_redirect,
    }


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
        crit = 0 <= days_left < SSL_CRIT_DAYS
        warn = SSL_CRIT_DAYS <= days_left < SSL_WARN_DAYS
        return {
            "ok": days_left >= 0,
            "expires": expires.date().isoformat(),
            "days_left": days_left,
            "issuer": issuer.get("organizationName", issuer.get("commonName", "unknown")),
            "error": None if days_left >= 0 else "certificate expired",
            "warn": warn,
            "crit": crit,
        }
    except Exception as exc:  # noqa: BLE001 — collect per-domain errors
        return {
            "ok": False,
            "expires": None,
            "days_left": None,
            "issuer": None,
            "error": str(exc),
            "warn": False,
            "crit": False,
        }


def overall_status(
    dns: dict,
    http: dict,
    ssl_info: dict,
    mail_dns: dict | None = None,
) -> str:
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
    if ssl_info.get("crit"):
        return "ssl_crit"
    if ssl_info.get("warn"):
        return "ssl_warn"
    if http.get("response_ms", 0) > SLOW_RESPONSE_MS:
        return "slow"
    if http.get("redirect_count", 0) > 5:
        return "warn"
    if http["status"] >= 400:
        return "warn"
    return "ok"


def check_domain(
    domain: str,
    server_id: str,
    expected_ip: str | None,
    proxy_provider: str | None = None,
    check_mail: bool = False,
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
    ssl_info = check_ssl(domain)

    if http.get("scheme") == "http" and http.get("ok"):
        ssl_info = {**ssl_info, "ok": None, "error": "not applicable (HTTP only)"}

    mail_dns = check_mail_dns(domain) if check_mail and not domain.startswith("mail.") else None

    status = overall_status(dns, http, ssl_info if ssl_info.get("ok") is not False else ssl_info, mail_dns)
    if http.get("scheme") == "http" and http.get("ok"):
        status = "http_only" if dns.get("ok") else "dns_fail"

    return {
        "domain": domain,
        "server_id": server_id,
        "dns": dns,
        "http": http,
        "ssl": ssl_info,
        "mail_dns": mail_dns,
        "status": status,
    }


def run_checks(data: dict, workers: int = 16, domain_filter: set[str] | None = None) -> dict:
    proxy_map = build_proxy_map(data)
    tasks: list[tuple[str, str, str | None, str | None, bool]] = []
    for server in data.get("servers", []):
        server_id = server.get("id", server.get("hostname", "unknown"))
        expected_ip = server.get("ip")
        check_mail = server_id == "mail"
        for domain in server.get("domains", []):
            if domain_filter and domain not in domain_filter:
                continue
            tasks.append((domain, server_id, expected_ip, proxy_map.get(domain), check_mail))

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(check_domain, domain, server_id, expected_ip, proxy, check_mail): domain
            for domain, server_id, expected_ip, proxy, check_mail in tasks
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
        "ssl_crit": sum(1 for r in results.values() if r["status"] == "ssl_crit"),
        "slow": sum(1 for r in results.values() if r["status"] == "slow"),
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
    parser.add_argument(
        "--filter",
        metavar="DOMAIN",
        help="Comma-separated domain names to check (default: all)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    domain_filter: set[str] | None = None
    if args.filter:
        domain_filter = {d.strip() for d in args.filter.split(",") if d.strip()}

    data = load_inventory(args.input)
    results = run_checks(data, workers=args.workers, domain_filter=domain_filter)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    s = results["summary"]
    print(
        f"Wrote {args.output} — {s['total']} domains: "
        f"{s['ok']} ok, {s['down']} down, {s['dns_fail']} dns fail, "
        f"{s['ssl_fail']} ssl fail, {s['ssl_crit']} ssl crit, {s['ssl_warn']} ssl warn, "
        f"{s['slow']} slow, {s['http_only']} http only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
