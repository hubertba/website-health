DNS provider (World4You)
==========================

.. req:: World4You DNS provider integration
   :id: REQ_DNS_001
   :status: implemented
   :tags: dns, provider

   When ``meta.dns_provider`` is set to ``world4you`` and credentials are
   available, the checker shall fetch authoritative A/AAAA records from
   World4You and compare them with live DNS resolution and the expected server
   IP from ``websites.yaml``.

.. req:: Graceful skip without credentials
   :id: REQ_DNS_002
   :status: implemented
   :tags: dns, provider, secrets

   If World4You credentials are not configured, public DNS/HTTP/SSL checks shall
   still run. Provider comparison is skipped without failing the workflow.

.. req:: Cloudflare proxy exemption
   :id: REQ_DNS_003
   :status: implemented
   :tags: dns, provider

   For domains listed under ``meta.proxied`` (or auto-detected CDN proxy
   addresses), provider/live and provider/server IP comparisons are skipped
   because proxied domains intentionally resolve to CDN edge IPs.

.. spec:: DNS provider result schema
   :id: SPEC_DNS_001
   :links: REQ_DNS_001
   :status: implemented
   :tags: dns, provider

   Each domain may include a ``dns_provider`` object:

   - ``provider``: ``world4you``
   - ``configured``: credentials were present
   - ``managed``: domain exists in the World4You account
   - ``addresses``: A/AAAA values at the provider
   - ``matches_live`` / ``matches_server``: booleans or ``null`` when skipped
   - ``issues``: human-readable drift messages

   Top-level ``check_results.json`` also includes ``dns_provider`` metadata
   (login status, managed domain count).

.. impl:: world4you_dns.py
   :id: IMPL_DNS_001
   :links: REQ_DNS_001, REQ_DNS_002
   :status: implemented
   :tags: dns, provider

   Uses the vendored `World4YouApi <https://github.com/NerLOR/World4YouApi>`_
   client. Credentials are read from ``WORLD4YOU_USERNAME`` (customer number) and
   ``WORLD4YOU_PASSWORD``.

.. impl:: Secrets handling
   :id: IMPL_DNS_002
   :links: REQ_DNS_002
   :status: implemented
   :tags: dns, secrets

   **Cursor Cloud:** add secrets in the `Cloud Agents dashboard
   <https://cursor.com/dashboard/cloud-agents>`_ → Secrets. Use type
   **Runtime Secret** for ``WORLD4YOU_PASSWORD``. Never commit credentials to
   ``environment.json``, Dockerfiles, or the repository.

   **GitHub Actions:** add repository secrets ``WORLD4YOU_USERNAME`` and
   ``WORLD4YOU_PASSWORD`` under Settings → Secrets and variables → Actions.
