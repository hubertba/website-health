# HTML content baselines

One JSON file per domain with a **compact snapshot** of the healthy homepage — not the full HTML (which changes too often and would bloat the repo).

Each file stores:

- `size_bytes`, `title`, `stylesheet_count`, `content_hash`
- `html_snippet` — first 2 KB of HTML (for human review)
- `text_snippet` — first 400 chars of visible text

## Why not full-page HTML diff?

Dynamic sites (WordPress, news, dates, CSRF tokens) change on every request. Comparing full HTML causes false positives. This approach combines:

1. **Size drop detection** — alert when page shrinks below 50% of baseline
2. **Error pattern matching** — WordPress DB errors, 502/503 pages, etc.
3. **CSS loss detection** — baseline had stylesheets, current page has none
4. **Optional markers** — `meta.content_markers` in `websites.yaml`

## Refresh baselines

After intentional site redesigns:

```bash
python3 scripts/capture_baselines.py
# or one domain:
python3 scripts/capture_baselines.py --filter example.com
```

Commit updated files under `baselines/`.
