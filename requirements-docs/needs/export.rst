Export & CI
===========

.. req:: JSON export
   :id: REQ_EXPORT_001
   :status: implemented
   :tags: export, report

   The report generator shall write ``docs/data/export.json`` with a flat list
   of domain check results suitable for downstream tooling.

.. req:: CSV export
   :id: REQ_EXPORT_002
   :status: implemented
   :tags: export, report

   The report generator shall write ``docs/data/export.csv`` with the same
   fields as the JSON export.

.. req:: Export download links
   :id: REQ_EXPORT_003
   :status: implemented
   :tags: export, report

   The HTML report shall link to JSON and CSV exports at the top of the page.

.. req:: Domain filter for manual runs
   :id: REQ_EXPORT_004
   :status: implemented
   :tags: export, ci

   ``check_domains.py --filter`` and the GitHub Actions ``workflow_dispatch``
   input shall limit checks to a comma-separated list of domains.

.. req:: Auto-create GitHub issues
   :id: REQ_EXPORT_005
   :status: implemented
   :tags: export, ci

   CI shall invoke ``alerts.py --create-issues`` to open issues for new
   critical regressions (label ``website-health``).

.. spec:: Export fields
   :id: SPEC_EXPORT_001
   :links: REQ_EXPORT_001, REQ_EXPORT_002
   :status: implemented
   :tags: export

   Each row includes domain, server, status, maintenance flag, DNS/HTTP/SSL
   summary, response time, redirect count, and mail DNS flags.

.. impl:: generate_report.py (exports)
   :id: IMPL_EXPORT_001
   :links: REQ_EXPORT_001, REQ_EXPORT_002, REQ_EXPORT_003
   :status: implemented
   :tags: export

   ``write_exports()`` writes JSON and CSV to ``docs/data/``.

.. impl:: pages.yml workflow
   :id: IMPL_EXPORT_002
   :links: REQ_EXPORT_004, REQ_EXPORT_005
   :status: implemented
   :tags: export, ci

   Workflow supports ``workflow_dispatch`` domain filter and ``--create-issues``.
