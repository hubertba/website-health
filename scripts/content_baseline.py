"""HTML content analysis, error-page detection, and baseline comparison."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from health_common import CONTENT_SHRINK_RATIO, MIN_BASELINE_SIZE_BYTES

USER_AGENT = "website-health-checker/2.0"
HTML_SNIPPET_LIMIT = 2048
TEXT_SNIPPET_LIMIT = 400
FETCH_LIMIT = 65_536

# Common WordPress / server error signatures (lowercase match).
ERROR_PATTERNS: tuple[tuple[str, str], ...] = (
    ("wp_db", r"error establishing a database connection"),
    ("wp_maintenance", r"briefly unavailable for scheduled maintenance"),
    ("wp_critical", r"there has been a critical error on this website"),
    ("wp_fatal", r"fatal error"),
    ("nginx_502", r"502 bad gateway"),
    ("nginx_503", r"503 service unavailable"),
    ("nginx_504", r"504 gateway timeout"),
    ("generic_500", r"internal server error"),
    ("docker_down", r"service unavailable"),
    ("php_error", r"parse error|stack trace"),
)

ERROR_TITLE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("title_error", r"\berror\b"),
    ("title_503", r"503|service unavailable"),
    ("title_502", r"502|bad gateway"),
)


def skip_content_check(domain: str, server_id: str | None = None) -> bool:
    """Roundcube webmail login pages vary with sessions and are poor baseline targets."""
    if domain.startswith("mail."):
        return True
    return False


def is_roundcube_page(html: str, title: str = "") -> bool:
    haystack = f"{title}\n{html}".lower()
    return "roundcube webmail" in haystack


def baseline_path(baselines_dir: Path, domain: str) -> Path:
    return baselines_dir / f"{domain}.json"


def safe_domain_filename(domain: str) -> str:
    return domain.lower()


def analyze_html(html: str) -> dict[str, Any]:
    title_match = re.search(r"<title[^>]*>([^<]*)</title>", html, re.IGNORECASE)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

    stylesheet_count = len(re.findall(r'<link[^>]+rel=["\']stylesheet["\']', html, re.IGNORECASE))
    script_count = len(re.findall(r"<script\b", html, re.IGNORECASE))

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text_snippet = text[:TEXT_SNIPPET_LIMIT]

    normalized = text.lower()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    return {
        "title": title,
        "stylesheet_count": stylesheet_count,
        "script_count": script_count,
        "text_snippet": text_snippet,
        "html_snippet": html[:HTML_SNIPPET_LIMIT],
        "content_hash": content_hash,
        "text_length": len(text),
    }


def detect_error_patterns(html: str, title: str = "") -> list[str]:
    haystack = f"{title}\n{html}".lower()
    matched: list[str] = []
    for name, pattern in ERROR_PATTERNS:
        if re.search(pattern, haystack, re.IGNORECASE):
            matched.append(name)
    title_lower = title.lower()
    for name, pattern in ERROR_TITLE_PATTERNS:
        if title_lower and re.search(pattern, title_lower, re.IGNORECASE):
            if name not in matched:
                matched.append(name)
    return matched


def fetch_homepage(domain: str, scheme: str = "https") -> dict[str, Any]:
    """Fetch homepage HTML with urllib (handles gzip/br decompression)."""
    for try_scheme in (scheme, "https", "http"):
        url = f"{try_scheme}://{domain}/"
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=12) as response:
                raw = response.read(FETCH_LIMIT)
                html = raw.decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "scheme": try_scheme,
                    "status": response.status,
                    "size_bytes": len(raw),
                    "html": html,
                    "error": None,
                }
        except HTTPError as exc:
            if exc.code < 500:
                body = exc.read(FETCH_LIMIT).decode("utf-8", errors="replace")
                return {
                    "ok": exc.code < 400,
                    "scheme": try_scheme,
                    "status": exc.code,
                    "size_bytes": len(body),
                    "html": body,
                    "error": None,
                }
            return {"ok": False, "scheme": try_scheme, "status": exc.code, "html": "", "size_bytes": 0, "error": str(exc)}
        except URLError:
            continue
    return {"ok": False, "scheme": scheme, "status": None, "html": "", "size_bytes": 0, "error": "unreachable"}


def build_baseline_record(domain: str, page: dict[str, Any]) -> dict[str, Any]:
    html = page.get("html") or ""
    analysis = analyze_html(html)
    return {
        "domain": domain,
        "captured_at": None,  # filled by caller
        "http_status": page.get("status"),
        "scheme": page.get("scheme"),
        "size_bytes": page.get("size_bytes"),
        **analysis,
    }


def load_baseline(baselines_dir: Path, domain: str) -> dict[str, Any] | None:
    path = baseline_path(baselines_dir, domain)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_baseline(baselines_dir: Path, record: dict[str, Any]) -> Path:
    baselines_dir.mkdir(parents=True, exist_ok=True)
    path = baseline_path(baselines_dir, record["domain"])
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def compare_content(
    domain: str,
    page: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    history_size_baseline: int | None = None,
    must_contain: list[str] | None = None,
) -> dict[str, Any]:
    """Compare fetched page against stored baseline and heuristics."""
    if skip_content_check(domain):
        return {
            "ok": True,
            "skipped": True,
            "reason": "roundcube_webmail",
            "issues": [],
            "matched_patterns": [],
        }

    html = page.get("html") or ""
    analysis = analyze_html(html)
    issues: list[str] = []
    matched_patterns = detect_error_patterns(html, analysis.get("title", ""))

    if matched_patterns:
        issues.append(f"error_page: {', '.join(matched_patterns)}")

    size_bytes = page.get("size_bytes") or 0
    reference_size = None
    if baseline and baseline.get("size_bytes"):
        reference_size = int(baseline["size_bytes"])
    elif history_size_baseline:
        reference_size = history_size_baseline

    size_ratio = None
    if reference_size and reference_size >= MIN_BASELINE_SIZE_BYTES:
        size_ratio = round(size_bytes / reference_size, 3)
        if size_ratio < CONTENT_SHRINK_RATIO:
            issues.append(
                f"size_shrink: {size_bytes}B vs {reference_size}B baseline ({int(size_ratio * 100)}%)"
            )

    if baseline:
        base_styles = baseline.get("stylesheet_count", 0)
        if (
            base_styles >= 1
            and analysis.get("stylesheet_count", 0) == 0
            and reference_size
            and size_bytes < reference_size * 0.7
        ):
            issues.append("missing_stylesheets: had CSS links in baseline, none now")

        base_hash = baseline.get("content_hash")
        if base_hash and analysis.get("content_hash") != base_hash and size_ratio and size_ratio < CONTENT_SHRINK_RATIO:
            issues.append("content_changed: hash differs with large size drop")

    for needle in must_contain or []:
        if needle and needle.lower() not in html.lower():
            issues.append(f"missing_marker: {needle!r}")

    ok = not any(i.startswith("error_page") for i in issues) and not any(
        i.startswith("size_shrink") for i in issues
    )

    return {
        "ok": ok,
        "issues": issues,
        "matched_patterns": matched_patterns,
        "size_bytes": size_bytes,
        "size_ratio": size_ratio,
        "reference_size_bytes": reference_size,
        **analysis,
    }
