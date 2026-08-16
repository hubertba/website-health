"""Tests for HTML content baseline comparison."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from content_baseline import analyze_html, compare_content, detect_error_patterns  # noqa: E402


class ContentBaselineTests(unittest.TestCase):
    def test_detect_wordpress_db_error(self) -> None:
        html = "<html><title>Error</title><body>Error establishing a database connection</body></html>"
        matched = detect_error_patterns(html, "Database Error")
        self.assertIn("wp_db", matched)

    def test_detect_size_shrink(self) -> None:
        baseline = {
            "domain": "example.com",
            "size_bytes": 50000,
            "stylesheet_count": 2,
            "content_hash": "abc123",
        }
        page = {
            "ok": True,
            "status": 200,
            "size_bytes": 1200,
            "html": "<html><head><title>OK</title></head><body>Short</body></html>",
        }
        result = compare_content("example.com", page, baseline)
        self.assertFalse(result["ok"])
        self.assertTrue(any(i.startswith("size_shrink") for i in result["issues"]))

    def test_healthy_page_matches_baseline(self) -> None:
        html = (
            "<html><head><title>Shop</title>"
            '<link rel="stylesheet" href="/style.css"></head>'
            "<body><h1>Welcome to our shop with many products</h1></body></html>"
        )
        analysis = analyze_html(html)
        baseline = {
            "domain": "shop.example.com",
            "size_bytes": len(html),
            "stylesheet_count": analysis["stylesheet_count"],
            "content_hash": analysis["content_hash"],
        }
        page = {"ok": True, "status": 200, "size_bytes": len(html), "html": html}
        result = compare_content("shop.example.com", page, baseline)
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])

    def test_skip_roundcube_webmail_domains(self) -> None:
        from content_baseline import skip_content_check

        self.assertTrue(skip_content_check("mail.example.com", "mail"))
        self.assertFalse(skip_content_check("trustlens.tech", "mail"))
        self.assertFalse(skip_content_check("postfixadmin.chilicode.com", "mail"))

    def test_baseline_files_are_valid(self) -> None:
        baselines_dir = ROOT / "baselines"
        if not baselines_dir.is_dir():
            self.skipTest("baselines not captured yet")
        files = sorted(baselines_dir.glob("*.json"))
        self.assertGreater(len(files), 0, "expected baseline files")
        required = {"domain", "size_bytes", "html_snippet", "content_hash", "title"}
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            missing = required - set(data)
            self.assertFalse(missing, f"{path.name} missing {missing}")
            self.assertEqual(data["domain"], path.stem)


if __name__ == "__main__":
    unittest.main()
