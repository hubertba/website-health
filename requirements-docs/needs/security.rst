Security & performance
======================

.. req:: HTTP response latency
   :id: REQ_SEC_001
   :status: implemented
   :tags: security, performance

   The checker shall measure end-to-end HTTP response time in milliseconds and
   flag domains slower than 3000 ms with status ``slow``.

.. req:: Redirect chain validation
   :id: REQ_SEC_002
   :status: implemented
   :tags: security, http

   The checker shall follow redirects manually (up to 10 hops) and record the
   redirect chain. More than five redirects shall contribute to status ``warn``.

.. req:: Security headers check
   :id: REQ_SEC_003
   :status: implemented
   :tags: security, http

   For HTTPS responses, the checker shall verify presence of
   ``Strict-Transport-Security``, ``X-Frame-Options``, and
   ``X-Content-Type-Options``. Results are shown in the report; they do not
   change overall status unless combined with other HTTP issues.

.. req:: SSL critical threshold
   :id: REQ_SEC_004
   :status: implemented
   :tags: security, ssl

   Certificates expiring in less than 7 days shall be assigned status
   ``ssl_crit`` (critical alert severity).

.. req:: SSL expiry warning threshold
   :id: REQ_SEC_005
   :status: implemented
   :tags: security, ssl

   Certificates expiring in 7–29 days shall retain status ``ssl_warn``.

.. req:: Maintenance mode
   :id: REQ_SEC_006
   :status: implemented
   :tags: security, yaml

   Domains listed under ``meta.maintenance`` in ``websites.yaml`` shall be
   checked and shown in the report with a maintenance badge, but alerts shall
   be suppressed.

.. req:: Runbook metadata
   :id: REQ_SEC_007
   :status: implemented
   :tags: security, yaml

   Remediation commands under ``meta.runbooks`` shall appear in alert details
   and GitHub issues created by ``--create-issues``.

.. req:: Dark/light theme toggle
   :id: REQ_SEC_008
   :status: implemented
   :tags: security, report

   The HTML report shall provide a theme toggle that persists the user's
   preference in ``localStorage``, defaulting to the system color scheme.

.. spec:: Extended check result fields
   :id: SPEC_SEC_001
   :links: REQ_SEC_001, REQ_SEC_002, REQ_SEC_003
   :status: implemented
   :tags: security

   Per-domain HTTP objects include ``response_ms``, ``redirect_count``,
   ``redirects``, and ``security`` (present/missing headers).

.. impl:: check_domains.py (extended)
   :id: IMPL_SEC_001
   :links: REQ_SEC_001, REQ_SEC_002, REQ_SEC_003, REQ_SEC_004, REQ_SEC_005
   :status: implemented
   :tags: security

   Extended HTTP probing with timing, redirect tracking, and header analysis.

.. impl:: generate_report.py (theme + columns)
   :id: IMPL_SEC_002
   :links: REQ_SEC_008
   :status: implemented
   :tags: security

   Report table columns for latency, redirects, and security headers.
