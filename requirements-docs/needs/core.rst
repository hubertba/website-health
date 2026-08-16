Core monitoring
===============

.. req:: Domain inventory
   :id: REQ_CORE_001
   :status: implemented
   :tags: core, yaml

   The system shall maintain a YAML inventory listing servers and their canonical
   domains only (no ports, types, or runtime metadata in the inventory file).

.. req:: DNS resolution check
   :id: REQ_CORE_002
   :status: implemented
   :tags: core, dns

   For each domain in the inventory, the checker shall resolve DNS (A/AAAA) and
   record all returned addresses.

.. req:: DNS server IP validation
   :id: REQ_CORE_003
   :status: implemented
   :tags: core, dns

   When a server entry defines an expected ``ip``, the checker shall flag domains
   whose resolved addresses do not include that IP.

.. req:: HTTP status check
   :id: REQ_CORE_004
   :status: implemented
   :tags: core, http

   The checker shall probe HTTPS first, fall back to HTTP, and record the HTTP
   status code and scheme used.

.. req:: SSL certificate validation
   :id: REQ_CORE_005
   :status: implemented
   :tags: core, ssl

   For HTTPS endpoints, the checker shall validate the TLS certificate, record
   expiry date, days remaining, and issuer.

.. req:: SSL expiry warning threshold
   :id: REQ_CORE_006
   :status: implemented
   :tags: core, ssl

   Certificates expiring in less than 30 days shall be assigned status
   ``ssl_warn``. See also :need:`REQ_SEC_004` for the 7-day critical threshold.

.. req:: Mobile-friendly HTML report
   :id: REQ_CORE_007
   :status: implemented
   :tags: core, report

   The report generator shall produce a self-contained HTML page with domain
   overview and per-server drill-down, suitable for mobile browsers.

.. req:: GitHub Pages deployment
   :id: REQ_CORE_008
   :status: implemented
   :tags: core, ci

   Each successful check run shall deploy the generated report to GitHub Pages
   via GitHub Actions.

.. spec:: Check result schema
   :id: SPEC_CORE_001
   :links: REQ_CORE_002, REQ_CORE_004, REQ_CORE_005
   :status: implemented
   :tags: core

   ``check_results.json`` contains ``checked_at``, ``summary`` counts, and per-domain
   objects with ``dns``, ``http``, ``ssl``, and ``status`` fields.

.. impl:: check_domains.py
   :id: IMPL_CORE_001
   :links: REQ_CORE_002, REQ_CORE_003, REQ_CORE_004, REQ_CORE_005, REQ_CORE_006
   :status: implemented
   :tags: core

   Parallel domain checker using stdlib ``socket``, ``ssl``, and ``urllib``.

.. impl:: generate_report.py
   :id: IMPL_CORE_002
   :links: REQ_CORE_007
   :status: implemented
   :tags: core

   Builds static HTML from ``websites.yaml``, ``check_results.json``, trends, and alerts.
