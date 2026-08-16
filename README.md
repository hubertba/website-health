# Website Health Report

Domain overview with DNS, HTTP, SSL, security headers, mail DNS, latency, and redirect checks. Inventory is a minimal YAML; checks run at build time.

## Quick start

```bash
pip install -r requirements.txt
python3 scripts/check_domains.py      # DNS + HTTP + SSL + mail DNS → check_results.json
python3 scripts/alerts.py --summary # Compare with previous snapshot → alerts.json
python3 scripts/history.py --append   # Save snapshot + trends
python3 scripts/generate_report.py  # → docs/index.html + docs/data/export.{json,csv}
```

Check a single domain:

```bash
python3 scripts/check_domains.py --filter example.com
```

## Requirements documentation (sphinx-needs)

```bash
pip install -r requirements-docs.txt
python3 -m sphinx -b html requirements-docs docs/docs
open docs/docs/index.html
```

Published at **https://hubertba.github.io/website-health/docs/** (Mermaid diagrams in `diagrams.rst`).

See `requirements-docs/needs/` for requirements covering core checks, security/performance, mail DNS, history/trends, alerts, and exports.

## `websites.yaml` (server + domains + meta)

```yaml
meta:
  checked_at: "2026-08-15"
  maintenance:               # suppress alerts, show maint badge
    - shophelfer.at
  runbooks:                  # shown in alerts and GitHub issues
    shophelfer.at:
      - cd /var/www/pages/shophelfer && docker compose up -d
  proxied:
    cloudflare:              # DNS points at CDN, not origin IP — expected
      - astro-lernstern.at

servers:
  - id: web
    hostname: web.chilicode.com
    ip: 37.16.72.137          # optional — flag DNS mismatches
    domains:
      - example.com

  - id: mail
    hostname: mail.chilicode.com
    ip: 37.16.72.84
    domains:
      - mail.example.com
```

## Checks

| Check | What it does |
|-------|----------------|
| **DNS** | Resolves A/AAAA records; compares to server `ip` when set |
| **HTTP** | Tries HTTPS first, falls back to HTTP; reports status code |
| **Latency** | DNS/connect/TLS/TTFB/download breakdown; `slow` when total > 3000 ms or TTFB > 1500 ms |
| **Size** | Response body size; warns when > 1 MB |
| **Compression** | Detects gzip/br; flags large uncompressed bodies |
| **HTTP version** | Records HTTP/1.1 or HTTP/2 (ALPN) |
| **Multi-URL** | Probes `/` + `/favicon.ico`; custom paths in `meta.probes` |
| **Cold/warm** | First vs second request on same connection |
| **Latency trends** | avg/p95/baseline in history; regression alert at +50% |
| **Content** | Baseline size + error-page patterns (WordPress/502/503); alerts on sharp size drop |

## Content baselines

Each domain has a compact baseline in `baselines/<domain>.json` (snippet + fingerprint, not full HTML).

```bash
python3 scripts/capture_baselines.py   # refresh after redesigns
python3 -m unittest tests.test_content_baseline
```

Full HTML diff is avoided — dynamic sites change too often. Checks use **size ratio**, **error signatures**, and optional `meta.content_markers` in YAML.
| **Redirects** | Follows up to 10 hops; warns if &gt; 5 |
| **Security** | HSTS, X-Frame-Options, X-Content-Type-Options on HTTPS |
| **SSL** | Certificate expiry; `ssl_crit` &lt; 7 days, `ssl_warn` &lt; 30 days |
| **Mail DNS** | MX, SPF, DMARC for domains on the mail server |

## Report views

1. **All domains** — flat overview (filter by name, server, status)
2. **By server** — drill into `web.chilicode.com` or `mail.chilicode.com`
3. **History** — uptime trends from snapshots

Also: **theme toggle**, **JSON/CSV export** links, **clickable alerts** with runbooks.

## GitHub Pages

Workflow runs checks daily (06:00 UTC), on push, and via **workflow_dispatch** (optional domain filter). Critical regressions open GitHub issues (`website-health` label).

Live report: **https://hubertba.github.io/website-health/**

## Inventory

| Server | Domains |
|--------|--------:|
| `web.chilicode.com` | 55 |
| `mail.chilicode.com` | 37 |
| **Total** | **92** |
