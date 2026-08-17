#!/usr/bin/env python3
"""Tests for World4You DNS provider comparison."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from world4you_dns import (  # noqa: E402
    build_address_index,
    compare_provider_dns,
    credentials_from_env,
    skipped_result,
)


class FakeRecord:
    def __init__(self, rr_type: str, fqdn: str, value: str):
        self.type = rr_type
        self.fqdn = fqdn
        self.value = value


class FakePackage:
    def __init__(self, records: list[FakeRecord]):
        self._records = records

    @property
    def resource_records(self):
        return self._records


class FakeSession:
    def __init__(self, packages: list[FakePackage]):
        self.packages = packages


class CredentialsTests(unittest.TestCase):
    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(credentials_from_env())

    def test_credentials_present(self):
        env = {"WORLD4YOU_USERNAME": "12345", "WORLD4YOU_PASSWORD": "secret"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(credentials_from_env(), ("12345", "secret"))


class CompareProviderDnsTests(unittest.TestCase):
    def test_skipped_without_credentials(self):
        result = compare_provider_dns("example.com", ["1.2.3.4"], None)
        self.assertTrue(result["skipped"])
        self.assertFalse(result["configured"])

    def test_unmanaged_domain(self):
        index = {"other.example": ["1.2.3.4"]}
        result = compare_provider_dns("example.com", ["1.2.3.4"], index, expected_ip="1.2.3.4")
        self.assertFalse(result["managed"])
        self.assertEqual(result["issues"], [])

    def test_provider_matches_live_and_server(self):
        index = {"example.com": ["37.16.72.137"]}
        result = compare_provider_dns(
            "example.com",
            ["37.16.72.137"],
            index,
            expected_ip="37.16.72.137",
        )
        self.assertTrue(result["managed"])
        self.assertTrue(result["matches_live"])
        self.assertTrue(result["matches_server"])
        self.assertEqual(result["issues"], [])

    def test_provider_live_mismatch(self):
        index = {"example.com": ["37.16.72.137"]}
        result = compare_provider_dns("example.com", ["8.8.8.8"], index)
        self.assertFalse(result["matches_live"])
        self.assertTrue(any("mismatch" in issue for issue in result["issues"]))

    def test_proxied_skips_ip_checks(self):
        index = {"example.com": ["37.16.72.137"]}
        result = compare_provider_dns(
            "example.com",
            ["104.16.0.1"],
            index,
            expected_ip="37.16.72.137",
            proxied="cloudflare",
        )
        self.assertIsNone(result["matches_live"])
        self.assertIsNone(result["matches_server"])
        self.assertEqual(result["issues"], [])


class BuildIndexTests(unittest.TestCase):
    def test_build_address_index(self):
        session = FakeSession(
            [
                FakePackage(
                    [
                        FakeRecord("A", "example.com", "1.2.3.4"),
                        FakeRecord("MX", "example.com", "mail.example.com"),
                        FakeRecord("AAAA", "example.com", "2001:db8::1"),
                    ]
                )
            ]
        )
        index = build_address_index(session)
        self.assertEqual(index["example.com"], ["1.2.3.4", "2001:db8::1"])


class SkippedResultTests(unittest.TestCase):
    def test_shape(self):
        result = skipped_result("test")
        self.assertEqual(result["provider"], "world4you")
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "test")


if __name__ == "__main__":
    unittest.main()
