#!/usr/bin/env python3
"""Tests for inventory merging with World4You provider data."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inventory import build_effective_inventory, infer_server_id, iter_domain_tasks, yaml_domain_map  # noqa: E402
from world4you_dns import ProviderData  # noqa: E402

SAMPLE_YAML = {
    "meta": {"dns_provider": "world4you"},
    "servers": [
        {"id": "web", "hostname": "web.example", "ip": "1.2.3.4", "domains": ["known.example"]},
        {"id": "mail", "hostname": "mail.example", "ip": "5.6.7.8", "domains": ["mail.known.example"]},
    ],
}

PROVIDER = ProviderData(
    packages=["known.example", "other.example"],
    hostnames=["known.example", "www.other.example", "mail.other.example", "extra.example"],
    address_index={
        "known.example": ["1.2.3.4"],
        "www.other.example": ["1.2.3.4"],
        "mail.other.example": ["5.6.7.8"],
        "extra.example": ["9.9.9.9"],
    },
)


class InventoryMergeTests(unittest.TestCase):
    def test_yaml_domain_map(self):
        mapping = yaml_domain_map(SAMPLE_YAML)
        self.assertEqual(mapping["known.example"]["server_id"], "web")
        self.assertTrue(mapping["mail.known.example"]["check_mail"])

    def test_build_effective_inventory_adds_provider_hostnames(self):
        effective = build_effective_inventory(SAMPLE_YAML, PROVIDER, provider_configured=True)
        tasks = iter_domain_tasks(effective)
        domains = {task[0] for task in tasks}
        self.assertIn("www.other.example", domains)
        self.assertIn("extra.example", domains)
        self.assertIn("known.example", domains)

    def test_infer_server_from_provider_ip(self):
        yaml_map = yaml_domain_map(SAMPLE_YAML)
        server_ips = {"web": "1.2.3.4", "mail": "5.6.7.8"}
        self.assertEqual(
            infer_server_id("www.other.example", PROVIDER, yaml_map, server_ips),
            "web",
        )
        self.assertEqual(
            infer_server_id("mail.other.example", PROVIDER, yaml_map, server_ips),
            "mail",
        )

    def test_unknown_domain_gets_world4you_server(self):
        effective = build_effective_inventory(SAMPLE_YAML, PROVIDER, provider_configured=True)
        server_ids = {server["id"] for server in effective["servers"]}
        self.assertIn("world4you", server_ids)
        world4you = next(server for server in effective["servers"] if server["id"] == "world4you")
        self.assertIn("extra.example", world4you["domains"])

    def test_without_provider_returns_yaml_unchanged(self):
        effective = build_effective_inventory(SAMPLE_YAML, None, provider_configured=False)
        self.assertEqual(effective["servers"], SAMPLE_YAML["servers"])

    def test_inventory_disabled_by_meta_flag(self):
        data = copy.deepcopy(SAMPLE_YAML)
        data["meta"]["inventory_from_provider"] = False
        effective = build_effective_inventory(data, PROVIDER, provider_configured=True)
        self.assertEqual(len(effective["servers"][0]["domains"]), 1)


if __name__ == "__main__":
    unittest.main()
