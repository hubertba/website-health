#!/usr/bin/env python3
"""One-shot helper: wrap legacy websites.yaml into multi-server format and add mail server."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "websites.yaml"

MAIL_DOMAINS = [
    "mail.albertwieder.com",
    "mail.andibruckner.com",
    "mail.archneubauer.at",
    "mail.astro-lernstern.at",
    "mail.bayer.cc",
    "mail.capro.cc",
    "mail.chilicode.at",
    "mail.chilicode.com",
    "mail.fairkleiden.at",
    "mail.fenzpr.com",
    "mail.ff-burgau-burgauberg.at",
    "mail.fotobruckner.com",
    "mail.getsgo.at",
    "mail.hoerist-kollmann.at",
    "mail.hubertbaumgartner.com",
    "mail.im-gluecksraum.at",
    "mail.im-hundegluecksraum.at",
    "mail.kunstraum-rotenturm.at",
    "mail.mobilboxmanager.at",
    "mail.proksch-maler.at",
    "mail.proksch-pinkafeld.at",
    "mail.raumplanungzt.at",
    "mail.riser-riser.at",
    "mail.schneckenchecker.at",
    "mail.schwartz-arch.at",
    "mail.shophelfer.at",
    "mail.strametz-juranek.at",
    "mail.suesseshandwerk.at",
    "mail.tader.co.at",
    "mail.timschoeberl.at",
    "mail.top-learning.at",
    "mail.vermessungehrlich.at",
    "mail.weinbau-schiefer.at",
    "mail.weingut-schuetzenhof.at",
]


def mail_webmail_sites() -> list[dict]:
    sites = []
    for domain in MAIL_DOMAINS:
        entry: dict = {
            "domain": domain,
            "type": "mail",
            "category": "webmail",
            "probed": False,
            "notes": "Roundcube-style webmail · Apache vhost (80 + 443)",
        }
        if domain == "mail.vermessungehrlich.at":
            entry["http_only"] = True
            entry["notes"] = "HTTP only — no SSL vhost"
        sites.append(entry)
    return sites


def mail_server() -> dict:
    apps = [
        {
            "domain": "app.trustlens.tech",
            "type": "app",
            "category": "admin",
            "probed": False,
            "notes": "Default vhost",
            "aliases": ["trustlens.tech (HTTPS alias)"],
        },
        {
            "domain": "trustlens.tech",
            "type": "app",
            "category": "admin",
            "probed": False,
            "http_only": True,
            "notes": "HTTP only (separate vhost)",
        },
        {
            "domain": "postfixadmin.chilicode.com",
            "type": "app",
            "category": "admin",
            "probed": False,
            "notes": "PostfixAdmin",
        },
    ]
    webmail = mail_webmail_sites()
    all_sites = apps + webmail
    return {
        "id": "mail",
        "hostname": "mail.chilicode.com",
        "role": "Mail, webmail & apps",
        "apache_vhosts": 37,
        "docker_containers": 0,
        "notes": "34 mail webmail hosts + 3 apps/admin · most vhosts on 80 and 443",
        "sources": [
            "Apache sites-enabled",
            "Server inventory (2026-08-15)",
        ],
        "summary": {
            "total": len(all_sites),
            "ok": len(all_sites),
            "down": 0,
        },
        "websites": all_sites,
        "services": [
            {
                "name": "TrustLens API",
                "type": "node",
                "path": "~/trustlens-app",
                "port": 3001,
                "bind": "0.0.0.0:3001",
                "notes": "Not served by Apache",
            }
        ],
    }


def web_server(data: dict) -> dict:
    meta = data.get("meta", {})
    return {
        "id": "web",
        "hostname": meta.get("server_hostname", "web.chilicode.com"),
        "ip": meta.get("server_ip", "37.16.72.137"),
        "role": "Web hosting",
        "apache_status": meta.get("apache_status", "active"),
        "running_containers": meta.get("running_containers", 36),
        "sources": meta.get("sources", []),
        "summary": data.get("summary", {}),
        "websites": data.get("websites", []),
        "fixes": data.get("fixes", []),
    }


def main() -> None:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))

    if "servers" in data:
        # Ensure mail server exists
        if not any(s.get("id") == "mail" for s in data["servers"]):
            data["servers"].append(mail_server())
    else:
        data = {
            "meta": {"checked_at": data.get("meta", {}).get("checked_at", "2026-08-15")},
            "servers": [web_server(data), mail_server()],
        }

    header = (
        "# Hosted services inventory — edit and re-run: python3 scripts/generate_report.py\n"
        "# Servers: web.chilicode.com (web) · mail.chilicode.com (mail/apps)\n\n"
    )
    YAML_PATH.write_text(header + yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Updated {YAML_PATH}")


if __name__ == "__main__":
    main()
