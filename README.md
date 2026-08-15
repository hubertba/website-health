# Website Health Report

Mobile-friendly status dashboard for hosted websites. Data lives in `websites.yaml`; a Python script builds static HTML for GitHub Pages.

## Architecture

```mermaid
flowchart LR
  YAML[websites.yaml] --> GEN[generate_report.py]
  GEN --> HTML[docs/index.html]
  HTML --> GHA[GitHub Actions]
  GHA --> PAGES[GitHub Pages]
```

| Component | Purpose |
|-----------|---------|
| `websites.yaml` | Single source of truth: domains, types, ports, status, aliases, fixes |
| `scripts/generate_report.py` | Reads YAML, emits self-contained HTML with search/filter |
| `.github/workflows/pages.yml` | Regenerates and deploys on push to `main` |
| `docs/index.html` | Generated report (committed so it works before first CI run) |

## Quick start

```bash
pip install -r requirements.txt
python scripts/generate_report.py
# Open docs/index.html in a browser
```

## Updating the inventory

1. Edit `websites.yaml` (add/remove sites, change status, ports, issues).
2. Regenerate: `python scripts/generate_report.py`
3. Commit `websites.yaml` and `docs/index.html`, push to `main`.

### Site entry fields

```yaml
- domain: example.com          # required — canonical hostname
  type: docker                 # docker | static | redirect | proxy
  port: 4020                   # backend port (docker/proxy)
  folder: example              # /var/www/pages/<folder>
  path: /var/www/vhosts/...    # static document root
  redirect_to: other.com       # for redirects
  status: ok                   # ok | down
  http_status: 200             # last HTTPS probe result
  issue: "container not running"  # shown when down
  notes: "optional context"
  aliases: [www.example.com]
```

Top-level `meta`, `summary`, and `fixes` sections drive the dashboard header and suggested repair commands.

## GitHub Pages setup

1. Repo **Settings → Pages → Build and deployment**: set source to **GitHub Actions**.
2. Push to `main` (or run the workflow manually). The site is published at  
   `https://<user>.github.io/website-health/` (repo name may vary).

## Current inventory (2026-08-15)

| Status | Count |
|--------|------:|
| OK | 51 |
| Down (503) | 4 |
| **Total** | **55** |

**Down sites:** `fairspeisen.com`, `shophelfer.at`, `historisch.ff-burgau-burgauberg.at`, `ff-burgau-burgauberg.chilicode.at`

Server: `web.chilicode.com` (`37.16.72.137`) · 36 Docker containers running

## Future enhancements

- **Automated checks**: cron job or GitHub Action that curls each domain and updates `status` / `http_status` in YAML.
- **Link checker integration**: ingest `*_link_check_*.txt` results from the host.
- **DNS report**: merge output from `dns_report.py`.
- **History**: commit dated YAML snapshots or a `history/` folder for trend charts.
- **Notifications**: open a GitHub issue when `down` count increases.

## Server-side data sources

On `web.chilicode.com`, inventory is derived from:

- `apachectl -S` (sites-enabled)
- `/var/www/pages/sites.txt` (port map)
- `docker ps` (running backends)
- HTTPS probes (`curl -sI https://…`)

See `all-websites.md` on the server for the full audit that seeded `websites.yaml`.
