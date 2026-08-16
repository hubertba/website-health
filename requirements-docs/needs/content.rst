Content baselines
=================

.. req:: HTML baseline per domain
   :id: REQ_CONTENT_001
   :status: implemented
   :tags: content

   The repository shall store a compact baseline file per domain under
   ``baselines/<domain>.json`` with size, title, stylesheet count, content hash,
   and HTML/text snippets.

.. req:: Error page pattern detection
   :id: REQ_CONTENT_002
   :status: implemented
   :tags: content

   The checker shall flag known error signatures (WordPress DB errors, 502/503
   pages, fatal PHP errors) even when HTTP status is 200.

.. req:: Page size shrink alert
   :id: REQ_CONTENT_003
   :status: implemented
   :tags: content, alerts

   When homepage size drops below 50% of the stored baseline (and baseline ≥
   2 KB), the checker shall raise a ``content_shrink`` warning.

.. req:: Missing stylesheet detection
   :id: REQ_CONTENT_004
   :status: implemented
   :tags: content

   When the baseline had CSS ``<link rel="stylesheet">`` tags and the current
   page has none with a concurrent size drop, the checker shall warn about
   missing stylesheets.

.. req:: Optional content markers
   :id: REQ_CONTENT_005
   :status: implemented
   :tags: content, yaml

   Domains may define required substrings under ``meta.content_markers`` in
   ``websites.yaml``.

.. req:: Roundcube webmail exclusion
   :id: REQ_CONTENT_006
   :status: implemented
   :tags: content

   HTML content checks shall be skipped for ``mail.*`` Roundcube webmail vhosts.

.. spec:: Baseline vs full HTML diff
   :id: SPEC_CONTENT_001
   :links: REQ_CONTENT_001
   :status: implemented
   :tags: content

   Full HTML byte-for-byte comparison is intentionally **not** used — dynamic
   sites produce false positives. Baselines store fingerprints + snippets; checks
   combine size ratio, error patterns, and optional markers.

.. impl:: content_baseline.py
   :id: IMPL_CONTENT_001
   :links: REQ_CONTENT_002, REQ_CONTENT_003, REQ_CONTENT_004
   :status: implemented
   :tags: content

   HTML analysis, error detection, and baseline comparison.

.. impl:: capture_baselines.py
   :id: IMPL_CONTENT_002
   :links: REQ_CONTENT_001
   :status: implemented
   :tags: content

   Fetches live pages and writes ``baselines/*.json``.

.. test:: Baseline file validation
   :id: TEST_CONTENT_001
   :links: REQ_CONTENT_001, IMPL_CONTENT_002
   :status: implemented
   :tags: content, test

   ``tests/test_content_baseline.py`` validates baseline JSON schema and
   comparison logic using fixtures.
