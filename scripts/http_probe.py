"""Detailed HTTP performance probing with timing breakdown."""

from __future__ import annotations

import socket
import ssl
import time
from typing import Any

TIMEOUT = 12
USER_AGENT = "website-health-checker/2.0"
HEAVY_BODY_BYTES = 1_000_000
MIN_COMPRESS_BYTES = 10_240
SLOW_TTFB_MS = 1500
MAX_BODY_READ_BYTES = 65_536

SECURITY_HEADERS = ("strict-transport-security", "x-frame-options", "x-content-type-options")


def normalize_probe_paths(raw_paths: list | None, default_paths: list[dict]) -> list[dict]:
    """Normalize YAML probe definitions to {path, expect_status?, max_ms?}."""
    if not raw_paths:
        return list(default_paths)
    normalized: list[dict] = []
    for item in raw_paths:
        if isinstance(item, str):
            normalized.append({"path": item})
        elif isinstance(item, dict) and item.get("path"):
            normalized.append(dict(item))
    return normalized or list(default_paths)


def _parse_response(raw: bytes) -> tuple[int, dict[str, str], bytes, str]:
    header_end = raw.find(b"\r\n\r\n")
    if header_end < 0:
        return 0, {}, raw, ""
    header_blob = raw[:header_end].decode("iso-8859-1", errors="replace")
    body = raw[header_end + 4 :]
    lines = header_blob.split("\r\n")
    status_line = lines[0] if lines else ""
    status = 0
    parts = status_line.split()
    if len(parts) >= 2 and parts[1].isdigit():
        status = int(parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return status, headers, body, status_line


def _http_version_label(alpn: str | None, status_line: str) -> str:
    if alpn == "h2":
        return "HTTP/2"
    if "HTTP/1.0" in status_line:
        return "HTTP/1.0"
    return "HTTP/1.1"


def _compression_info(headers: dict[str, str], body_size: int) -> dict[str, Any]:
    encoding = headers.get("content-encoding", "").lower()
    compressed = encoding in {"gzip", "br", "deflate"}
    return {
        "content_encoding": encoding or None,
        "compressed": compressed,
        "needs_compression": body_size >= MIN_COMPRESS_BYTES and not compressed,
    }


def _security_from_headers(headers: dict[str, str]) -> dict[str, Any]:
    present = {h: headers[h] for h in SECURITY_HEADERS if headers.get(h)}
    missing = [h for h in SECURITY_HEADERS if h not in present]
    return {"present": present, "missing": missing, "ok": len(missing) == 0}


def _connect_timed(host: str, port: int, use_tls: bool) -> tuple[Any, dict[str, int], str | None]:
    timings: dict[str, int] = {}
    alpn: str | None = None

    t_dns = time.perf_counter()
    addr_info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    timings["dns_ms"] = round((time.perf_counter() - t_dns) * 1000)

    t_conn = time.perf_counter()
    sock = socket.create_connection(addr_info[0][4], timeout=TIMEOUT)
    timings["connect_ms"] = round((time.perf_counter() - t_conn) * 1000)

    if use_tls:
        t_tls = time.perf_counter()
        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(["h2", "http/1.1"])
        tls_sock = ctx.wrap_socket(sock, server_hostname=host)
        timings["tls_ms"] = round((time.perf_counter() - t_tls) * 1000)
        alpn = tls_sock.selected_alpn_protocol()
        return tls_sock, timings, alpn

    return sock, timings, alpn


def _request_on_socket(
    sock: ssl.SSLSocket | socket.socket,
    host: str,
    path: str,
    *,
    connection_close: bool = True,
) -> tuple[bytes, dict[str, int], str | None]:
    timings: dict[str, int] = {}
    alpn = sock.selected_alpn_protocol() if isinstance(sock, ssl.SSLSocket) else None

    conn_hdr = "close" if connection_close else "keep-alive"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"User-Agent: {USER_AGENT}\r\n"
        f"Accept-Encoding: gzip, deflate, br\r\n"
        f"Connection: {conn_hdr}\r\n\r\n"
    )
    t_req = time.perf_counter()
    sock.sendall(request.encode())

    data = b""
    header_end = -1
    while header_end < 0:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        header_end = data.find(b"\r\n\r\n")
    timings["ttfb_ms"] = round((time.perf_counter() - t_req) * 1000)

    t_body = time.perf_counter()
    status, headers, _, _ = _parse_response(data)
    body_start = header_end + 4 if header_end >= 0 else len(data)
    body_len = len(data) - body_start
    length_hdr = headers.get("content-length")
    target = MAX_BODY_READ_BYTES - body_len
    if length_hdr and length_hdr.isdigit():
        target = min(int(length_hdr) - body_len, target)
    if target > 0:
        while target > 0:
            chunk = sock.recv(min(8192, target))
            if not chunk:
                break
            data += chunk
            target -= len(chunk)
    timings["download_ms"] = round((time.perf_counter() - t_body) * 1000)
    return data, timings, alpn


def _probe_once(
    host: str,
    path: str,
    scheme: str,
    *,
    cold_warm: bool = False,
) -> dict[str, Any]:
    port = 443 if scheme == "https" else 80
    use_tls = scheme == "https"
    result: dict[str, Any] = {"path": path, "scheme": scheme, "ok": False, "status": None, "error": None}
    connect_timing: dict[str, int] = {}

    try:
        sock, connect_timing, alpn = _connect_timed(host, port, use_tls)
    except OSError as exc:
        result["error"] = str(exc)
        result["timing"] = connect_timing
        return result

    try:
        raw, req_timing, alpn = _request_on_socket(sock, host, path, connection_close=not cold_warm)
        status, headers, body, status_line = _parse_response(raw)
        content_length = headers.get("content-length")
        size_bytes = int(content_length) if content_length and content_length.isdigit() else len(body)
        compression = _compression_info(headers, size_bytes)
        timing = {**connect_timing, **req_timing}
        timing["total_ms"] = sum(timing.values())

        warm_ms = None
        if cold_warm:
            try:
                warm_raw, warm_timing, _ = _request_on_socket(sock, host, path, connection_close=True)
                warm_status, _, _, _ = _parse_response(warm_raw)
                if warm_status:
                    warm_ms = warm_timing.get("ttfb_ms")
            except OSError:
                warm_ms = None

        result.update(
            {
                "ok": status > 0 and status < 500,
                "status": status,
                "timing": timing,
                "ttfb_ms": timing.get("ttfb_ms"),
                "response_ms": timing.get("total_ms"),
                "size_bytes": size_bytes,
                "http_version": _http_version_label(alpn, status_line),
                "compression": compression,
                "cold_ms": timing.get("total_ms"),
                "warm_ms": warm_ms,
                "response_headers": headers,
            }
        )
    except OSError as exc:
        result["error"] = str(exc)
        result["timing"] = connect_timing
    finally:
        try:
            sock.close()
        except OSError:
            pass

    return result


def probe_domain(host: str, paths: list[dict]) -> dict[str, Any]:
    """Run multi-path probes with HTTPS-first fallback to HTTP."""
    if not paths:
        paths = [{"path": "/"}]

    probes: list[dict] = []
    scheme = "https"

    for index, spec in enumerate(paths):
        path = spec["path"]
        if not path.startswith("/"):
            path = "/" + path
        attempt = _probe_once(host, path, "https", cold_warm=(index == 0))
        if index == 0 and not attempt.get("status"):
            http_attempt = _probe_once(host, path, "http", cold_warm=True)
            if http_attempt.get("status"):
                attempt = http_attempt
                scheme = "http"
        elif index == 0 and attempt.get("status"):
            scheme = "https"
        probes.append({**attempt, **{k: v for k, v in spec.items() if k != "path"}})

    ranked = [p for p in probes if p.get("response_ms") is not None]
    primary_probe = probes[0] if probes else {}
    worst = max(ranked, key=lambda p: p.get("response_ms", 0)) if ranked else primary_probe
    summary = primary_probe
    summary_headers = summary.get("response_headers") or {}

    http_result: dict[str, Any] = {
        "ok": summary.get("ok", False),
        "status": summary.get("status"),
        "scheme": summary.get("scheme", scheme),
        "url": f"{summary.get('scheme', scheme)}://{host}{summary.get('path', '/')}",
        "final_url": f"{summary.get('scheme', scheme)}://{host}{summary.get('path', '/')}",
        "redirects": [],
        "redirect_count": 0,
        "response_ms": summary.get("response_ms"),
        "ttfb_ms": summary.get("ttfb_ms"),
        "timing": summary.get("timing", {}),
        "size_bytes": summary.get("size_bytes"),
        "http_version": summary.get("http_version"),
        "compression": summary.get("compression", {}),
        "cold_ms": summary.get("cold_ms"),
        "warm_ms": summary.get("warm_ms"),
        "security": _security_from_headers(summary_headers),
        "probes": [{k: v for k, v in p.items() if k != "response_headers"} for p in probes],
        "worst_probe_ms": worst.get("response_ms"),
        "error": summary.get("error"),
    }

    for probe in probes:
        expect = probe.get("expect_status")
        if expect is not None and probe.get("status") != expect:
            http_result["ok"] = False
            http_result["error"] = f"{probe.get('path')}: expected {expect}, got {probe.get('status')}"
        max_ms = probe.get("max_ms")
        if max_ms and (probe.get("response_ms") or 0) > max_ms:
            http_result["ok"] = False
            http_result["error"] = f"{probe.get('path')}: {probe.get('response_ms')}ms > {max_ms}ms"

    if http_result["status"] and http_result["status"] >= 400:
        http_result["ok"] = http_result["status"] < 500

    return http_result
