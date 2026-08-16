Performance monitoring
========================

.. req:: Timing breakdown
   :id: REQ_PERF_001
   :status: implemented
   :tags: performance

   Each HTTP probe shall record ``dns_ms``, ``connect_ms``, ``tls_ms``,
   ``ttfb_ms``, ``download_ms``, and ``total_ms`` in the ``timing`` object.

.. req:: Response size
   :id: REQ_PERF_002
   :status: implemented
   :tags: performance

   The checker shall record downloaded body size in bytes (``size_bytes``) and
   flag responses larger than 1 MB with status ``warn``.

.. req:: Compression check
   :id: REQ_PERF_003
   :status: implemented
   :tags: performance

   The checker shall detect ``Content-Encoding`` (gzip, br, deflate) and flag
   uncompressed bodies ≥ 10 KB with ``needs_compression``.

.. req:: HTTP version detection
   :id: REQ_PERF_004
   :status: implemented
   :tags: performance

   The checker shall record negotiated protocol as ``HTTP/1.1`` or ``HTTP/2``
   (via TLS ALPN when available).

.. req:: Latency trends
   :id: REQ_PERF_005
   :status: implemented
   :tags: performance, history

   ``history/trends.json`` shall include per-domain ``latency_avg_ms``,
   ``latency_p95_ms``, ``latency_baseline_ms`` (7-run average), and
   ``latency_regression`` when current latency exceeds 150% of baseline.

.. req:: Multi-URL probes
   :id: REQ_PERF_006
   :status: implemented
   :tags: performance

   By default each domain is probed at ``/`` and ``/favicon.ico``. Additional
   paths may be defined under ``meta.probes`` in ``websites.yaml`` with
   optional ``expect_status`` and ``max_ms``.

.. req:: Cold vs warm timing
   :id: REQ_PERF_007
   :status: implemented
   :tags: performance

   The primary probe (``/``) shall record ``cold_ms`` (first request) and
   ``warm_ms`` (second request on the same connection when keep-alive works).

.. req:: Latency regression alerts
   :id: REQ_PERF_008
   :status: implemented
   :tags: performance, alerts

   When current latency exceeds 150% of the 7-run baseline while status is
   ``ok``, the alert engine shall emit a ``latency_regression`` warning.

.. spec:: Performance result fields
   :id: SPEC_PERF_001
   :links: REQ_PERF_001, REQ_PERF_002, REQ_PERF_003, REQ_PERF_004
   :status: implemented
   :tags: performance

   HTTP objects include ``timing``, ``ttfb_ms``, ``size_bytes``, ``compression``,
   ``http_version``, ``cold_ms``, ``warm_ms``, and ``probes`` array.

.. impl:: http_probe.py
   :id: IMPL_PERF_001
   :links: REQ_PERF_001, REQ_PERF_002, REQ_PERF_003, REQ_PERF_004, REQ_PERF_006, REQ_PERF_007
   :status: implemented
   :tags: performance

   Raw-socket HTTP probing with phase timings and multi-path support.

.. impl:: history.py (latency trends)
   :id: IMPL_PERF_002
   :links: REQ_PERF_005
   :status: implemented
   :tags: performance

   Computes avg, p95, baseline, and regression flags from snapshot history.

.. impl:: alerts.py (latency regression)
   :id: IMPL_PERF_003
   :links: REQ_PERF_008
   :status: implemented
   :tags: performance

   Compares current ``response_ms`` against ``trends.json`` baseline.
