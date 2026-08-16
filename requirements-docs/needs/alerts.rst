Alerts
======

.. req:: Compare with previous snapshot
   :id: REQ_ALERT_001
   :status: implemented
   :tags: alerts

   Before appending a new history snapshot, the alert engine shall compare the
   current check results with the most recent snapshot in ``history/snapshots/``.

.. req:: Regression alerts
   :id: REQ_ALERT_002
   :status: implemented
   :tags: alerts

   When a domain status worsens (e.g. ``ok`` → ``down``), the system shall emit a
   **regression** alert with severity ``critical`` or ``warning``.

.. req:: Recovery notifications
   :id: REQ_ALERT_003
   :status: implemented
   :tags: alerts

   When a domain transitions from a non-healthy status back to ``ok`` or
   ``http_only``, the system shall emit a **recovered** alert with severity
   ``info``.

.. req:: Ongoing issue alerts
   :id: REQ_ALERT_004
   :status: implemented
   :tags: alerts

   Domains that remain in a non-healthy state across consecutive runs shall
   generate **ongoing** alerts until recovered.

.. req:: Alert output file
   :id: REQ_ALERT_005
   :status: implemented
   :tags: alerts

   All alerts for a run shall be written to ``alerts.json`` with counts and
   per-alert metadata (domain, server, message, HTTP/SSL details).

.. req:: GitHub Actions step summary
   :id: REQ_ALERT_006
   :status: implemented
   :tags: alerts, ci

   In CI, alerts shall be written to ``$GITHUB_STEP_SUMMARY`` as a Markdown table
   visible on the workflow run page.

.. req:: Report alerts panel
   :id: REQ_ALERT_007
   :status: implemented
   :tags: alerts, report

   The HTML report shall show an alerts panel at the top when active alerts exist.

.. req:: GitHub issue on critical regression
   :id: REQ_ALERT_008
   :status: implemented
   :tags: alerts, ci
   :collapse: false

   When invoked with ``--create-issues``, the system shall open a GitHub issue
   (label ``website-health``) for each new **critical** regression, skipping
   domains that already have an open issue.

.. spec:: Alert severity mapping
   :id: SPEC_ALERT_001
   :links: REQ_ALERT_002
   :status: implemented
   :tags: alerts

   ``down``, ``dns_fail``, ``ssl_fail`` → critical; ``ssl_warn``, ``warn`` →
   warning; ``recovered`` → info.

.. spec:: Status severity ordering
   :id: SPEC_ALERT_002
   :links: REQ_ALERT_002, REQ_ALERT_003
   :status: implemented
   :tags: alerts

   Statuses are ordered: ``ok`` < ``http_only`` < ``warn`` < ``ssl_warn`` <
   ``dns_fail`` < ``ssl_fail`` < ``down``.

.. impl:: alerts.py
   :id: IMPL_ALERT_001
   :links: REQ_ALERT_001, REQ_ALERT_002, REQ_ALERT_003, REQ_ALERT_004, REQ_ALERT_005, REQ_ALERT_006, REQ_ALERT_008
   :status: implemented
   :tags: alerts

   Compares snapshots, writes ``alerts.json``, optional GitHub summary and issues.

.. impl:: health_common.py
   :id: IMPL_ALERT_002
   :links: SPEC_ALERT_002
   :status: implemented
   :tags: alerts

   Shared status severity helpers and slim snapshot builder.

.. test:: Regression detection
   :id: TEST_ALERT_001
   :links: REQ_ALERT_002, IMPL_ALERT_001
   :status: open
   :tags: alerts, test

   Given previous status ``ok`` and current ``down``, ``alerts.json`` shall
   contain one regression alert for that domain.

.. test:: Recovery detection
   :id: TEST_ALERT_002
   :links: REQ_ALERT_003, IMPL_ALERT_001
   :status: open
   :tags: alerts, test

   Given previous status ``down`` and current ``ok``, ``alerts.json`` shall
   contain one recovered alert for that domain.
