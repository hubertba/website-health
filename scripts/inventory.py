"""Build the effective domain inventory (YAML meta + optional World4You API)."""

from __future__ import annotations

import copy
from collections import defaultdict

from world4you_dns import ProviderData


def yaml_domain_map(data: dict) -> dict[str, dict]:
    """Map domain -> server assignment from websites.yaml."""
    mapping: dict[str, dict] = {}
    for server in data.get("servers", []):
        server_id = server.get("id", server.get("hostname", "unknown"))
        expected_ip = server.get("ip")
        check_mail = server_id == "mail"
        for domain in server.get("domains", []):
            mapping[domain.lower()] = {
                "server_id": server_id,
                "expected_ip": expected_ip,
                "check_mail": check_mail,
            }
    return mapping


def inventory_from_provider_enabled(data: dict, provider_configured: bool) -> bool:
    meta = data.get("meta", {})
    if (meta.get("dns_provider") or "").lower() != "world4you":
        return False
    if meta.get("inventory_from_provider") is False:
        return False
    return provider_configured


def infer_server_id(
    domain: str,
    provider: ProviderData,
    yaml_map: dict[str, dict],
    server_ips: dict[str, str | None],
) -> str:
    if domain in yaml_map:
        return yaml_map[domain]["server_id"]

    addresses = set(provider.address_index.get(domain, []))
    for server_id, ip in server_ips.items():
        if ip and ip in addresses:
            return server_id

    if domain.startswith("mail."):
        return "mail"

    return "world4you"


def build_effective_inventory(data: dict, provider: ProviderData | None, *, provider_configured: bool) -> dict:
    """Merge World4You hostnames into the inventory used for checks and reports."""
    if not provider or not inventory_from_provider_enabled(data, provider_configured):
        return data

    effective = copy.deepcopy(data)
    yaml_map = yaml_domain_map(data)
    server_ips = {
        server.get("id", server.get("hostname", "unknown")): server.get("ip")
        for server in data.get("servers", [])
    }

    all_domains: set[str] = set(provider.hostnames)
    all_domains.update(yaml_map.keys())

    assignments: dict[str, str] = {}
    for domain in all_domains:
        assignments[domain] = infer_server_id(domain, provider, yaml_map, server_ips)

    domains_by_server: dict[str, list[str]] = defaultdict(list)
    for domain in sorted(assignments, key=str.lower):
        domains_by_server[assignments[domain]].append(domain)

    servers = []
    known_ids = set()
    for server in effective.get("servers", []):
        server_id = server.get("id", server.get("hostname", "unknown"))
        known_ids.add(server_id)
        merged = sorted(set(server.get("domains", [])) | set(domains_by_server.get(server_id, [])), key=str.lower)
        servers.append({**server, "domains": merged})

    if "world4you" not in known_ids and domains_by_server.get("world4you"):
        servers.append(
            {
                "id": "world4you",
                "hostname": "world4you-dns",
                "domains": domains_by_server["world4you"],
            }
        )

    effective["servers"] = servers
    return effective


def iter_domain_tasks(data: dict) -> list[tuple[str, str, str | None, bool]]:
    """Yield (domain, server_id, expected_ip, check_mail) from an inventory dict."""
    tasks: list[tuple[str, str, str | None, bool]] = []
    for server in data.get("servers", []):
        server_id = server.get("id", server.get("hostname", "unknown"))
        expected_ip = server.get("ip")
        check_mail = server_id == "mail"
        for domain in server.get("domains", []):
            tasks.append((domain, server_id, expected_ip, check_mail))
    return tasks
