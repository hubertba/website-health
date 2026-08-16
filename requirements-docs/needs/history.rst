History and trends
==================

.. req:: Snapshot persistence
   :id: REQ_HIST_001
   :status: implemented
   :tags: history

   After each check run, the system shall append a compact snapshot of all domain
   statuses to ``history/snapshots/`` with a UTC timestamp filename.

.. req:: Snapshot retention
   :id: REQ_HIST_002
   :status: implemented
   :tags: history

   The system shall retain at most 90 snapshots and delete older files automatically.

.. req:: Per-domain uptime percentage
   :id: REQ_HIST_003
   :status: implemented
   :tags: history, trends

   For each domain, the system shall compute uptime as the percentage of snapshots
   where status was ``ok`` over the retained history window.

.. req:: Status duration tracking
   :id: REQ_HIST_004
   :status: implemented
   :tags: history, trends

   The system shall record ``status_since`` — the timestamp of the earliest
   consecutive snapshot with the current status.

.. req:: Status change detection
   :id: REQ_HIST_005
   :status: implemented
   :tags: history, trends

   Trends shall indicate when a domain's status changed between the last two
   snapshots (``previous_status`` → ``current_status``).

.. req:: History report tab
   :id: REQ_HIST_006
   :status: implemented
   :tags: history, report

   The HTML report shall include a **History** tab listing domains with less than
   100% uptime or recent status changes.

.. req:: Trend column in domain table
   :id: REQ_HIST_007
   :status: implemented
   :tags: history, report

   Each domain row shall show uptime percentage and status-change or duration info
   in a **Trend** column.

.. spec:: Slim snapshot format
   :id: SPEC_HIST_001
   :links: REQ_HIST_001
   :status: implemented
   :tags: history

   Snapshots store ``checked_at``, ``summary``, and per-domain ``status``,
   ``http_status``, ``http_scheme``, ``ssl_days_left``, and ``server_id`` only.

.. spec:: Trends file
   :id: SPEC_HIST_002
   :links: REQ_HIST_003, REQ_HIST_004, REQ_HIST_005
   :status: implemented
   :tags: history

   ``history/trends.json`` is regenerated after each run with ``computed_at``,
   ``snapshot_count``, and per-domain trend objects.

.. impl:: history.py
   :id: IMPL_HIST_001
   :links: REQ_HIST_001, REQ_HIST_002, REQ_HIST_003, REQ_HIST_004, REQ_HIST_005
   :status: implemented
   :tags: history

   Appends snapshots, prunes old files, writes ``history/trends.json``.

.. test:: Snapshot round-trip
   :id: TEST_HIST_001
   :links: REQ_HIST_001, IMPL_HIST_001
   :status: open
   :tags: history, test

   Given a ``check_results.json``, running ``history.py --append`` shall create a
   snapshot file and update ``history/index.json``.
