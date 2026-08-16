# Website Health Report

Domain overview with DNS, HTTP, and SSL checks. Inventory is a minimal YAML; checks run at build time.

## Quick start

```bash
pip install -r requirements.txt
python3 scripts/check_domains.py      # DNS + HTTP + SSL → check_results.json
python3 scripts/alerts.py --summary # Compare with previous snapshot → alerts.json
python3 scripts/history.py --append   # Save snapshot + trends
python3 scripts/generate_report.py  # → docs/index.html
```

## Requirements documentation (sphinx-needs)

```bash
pip install -r requirements-docs.txt
python3 -m sphinx -b html requirements-docs docs/docs
open docs/docs/index.html
```

Published at **https://hubertba.github.io/website-health/docs/** (Mermaid diagrams in `diagrams.rst`).

See `requirements-docs/needs/` for **REQ_***, **SPEC_***, **IMPL_***, and **TEST_*** items covering core checks, history/trends, and alerts.

## `websites.yaml` (server + domains only)

```yaml
meta:
  checked_at: "2026-08-15"
  proxied:
    cloudflare:            # DNS points at CDN, not origin IP — expected
      - astro-lernstern.at
      - fenzpr.com

servers:
  - id: web
    hostname: web.chilicode.com
    ip: 37.16.72.137          # optional — flag DNS mismatches
    domains:
      - example.com
      - another.example.com

  - id: mail
    hostname: mail.chilicode.com
    domains:
      - mail.example.com
```

## Checks

| Check | What it does |
|-------|----------------|
| **DNS** | Resolves A/AAAA records; compares to server `ip` when set |
| **HTTP** | Tries HTTPS first, falls back to HTTP; reports status code |
| **SSL** | Certificate expiry, days remaining, issuer; warns &lt; 30 days |

## Report views

1. **All domains** — flat overview across servers (filter by name, server, status)
2. **By server** — drill into `web.chilicode.com` or `mail.chilicode.com`

## GitHub Pages

Workflow runs checks daily (06:00 UTC) and on push, then deploys `docs/` to `gh-pages`.

Enable Pages: **Settings → Pages → branch `gh-pages` / root**.

## Inventory

| Server | Domains |
|--------|--------:|
| `web.chilicode.com` | 55 |
| `mail.chilicode.com` | 37 |
| **Total** | **92** |
