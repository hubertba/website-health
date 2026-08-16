Architecture diagrams
=====================

System overview
---------------

.. mermaid::

   flowchart TB
     subgraph inventory["Inventory"]
       YAML["websites.yaml<br/>servers + domains"]
     end

     subgraph checks["Health checks"]
       CHECK["check_domains.py"]
       DNS["DNS resolve"]
       HTTP["HTTP probe + timing"]
       PERF["Size / compression / HTTP version"]
       SSL["SSL certificate"]
       SEC["Security headers"]
       MAIL["Mail DNS (MX/SPF/DMARC)"]
     end

     subgraph pipeline["CI pipeline"]
       ALERTS["alerts.py"]
       HIST["history.py"]
       REPORT["generate_report.py"]
       SPHINX["Sphinx docs"]
     end

     subgraph output["Outputs"]
       JSON["check_results.json"]
       SNAP["history/snapshots/"]
       TRENDS["history/trends.json"]
       ALERTJSON["alerts.json"]
       HTML["docs/index.html"]
       DATA["docs/data/export.*"]
       DOCS["docs/docs/"]
     end

     subgraph pages["GitHub Pages"]
       ROOT["/website-health/"]
       DOCPATH["/website-health/docs/"]
     end

     YAML --> CHECK
     CHECK --> DNS & HTTP & SSL & SEC & MAIL & PERF
     CHECK --> JSON
     JSON --> ALERTS
     SNAP --> ALERTS
     ALERTS --> ALERTJSON
     JSON --> HIST
     HIST --> SNAP & TRENDS
     JSON --> REPORT
     TRENDS --> REPORT
     ALERTJSON --> REPORT
     REPORT --> HTML
     REPORT --> DATA
     YAML --> SPHINX
     SPHINX --> DOCS
     HTML --> ROOT
     DOCS --> DOCPATH

CI/CD pipeline
--------------

.. mermaid::

   sequenceDiagram
     participant GHA as GitHub Actions
     participant Check as check_domains.py
     participant Alert as alerts.py
     participant Hist as history.py
     participant Gen as generate_report.py
     participant Sphinx as Sphinx build
     participant Git as main branch
     participant Pages as GitHub Pages

     GHA->>Check: Run DNS / HTTP / SSL / mail checks
     Check-->>GHA: check_results.json
     GHA->>Alert: Compare vs last snapshot
     Alert-->>GHA: alerts.json + step summary
     GHA->>Hist: Append snapshot + trends
     Hist-->>GHA: history/snapshots/*.json
     GHA->>Gen: Build health report
     Gen-->>GHA: docs/index.html
     GHA->>Sphinx: Build requirements docs
     Sphinx-->>GHA: docs/docs/
     GHA->>Git: Commit history updates
     GHA->>Pages: Deploy docs/ artifact
     Note over Pages: / → report<br/>/docs/ → requirements

Alert flow
----------

.. mermaid::

   stateDiagram-v2
     [*] --> LoadCurrent: check_results.json
     LoadCurrent --> LoadPrevious: history/snapshots/latest
     LoadPrevious --> Compare: For each domain

     Compare --> Regression: status worsened
     Compare --> Recovery: status improved
     Compare --> Ongoing: still unhealthy
     Compare --> NoAlert: ok / unchanged ok

     Regression --> Critical: down / dns_fail / ssl_fail
     Regression --> Warning: ssl_warn / warn
     Recovery --> Info: recovered alert
     Ongoing --> Critical
     Ongoing --> Warning

     Critical --> WriteAlerts
     Warning --> WriteAlerts
     Info --> WriteAlerts
     NoAlert --> WriteAlerts

     WriteAlerts --> [*]: alerts.json

History and trends
----------------

.. mermaid::

   flowchart LR
     RUN["Check run"] --> SLIM["Slim snapshot"]
     SLIM --> SAVE["history/snapshots/<br/>YYYY-MM-DDTHHMMSSZ.json"]
     SAVE --> PRUNE["Prune > 90 files"]
     PRUNE --> COMPUTE["compute_trends()"]
     COMPUTE --> TRENDS["history/trends.json"]

     subgraph perDomain["Per domain"]
       UPTIME["uptime %"]
       SINCE["status_since"]
       CHANGE["previous → current"]
     end

     TRENDS --> perDomain
     perDomain --> REPORT["History tab + Trend column"]

Domain status severity
----------------------

Used by alerts to detect regressions and recoveries.

.. mermaid::

   flowchart LR
     ok["ok (0)"] --> http_only["http_only (1)"]
     http_only --> warn["warn / slow (2)"]
     warn --> ssl_warn["ssl_warn (3)"]
     ssl_warn --> ssl_crit["ssl_crit (4)"]
     ssl_crit --> dns_fail["dns_fail (5)"]
     dns_fail --> ssl_fail["ssl_fail (6)"]
     ssl_fail --> down["down (7)"]

     style ok fill:#d1fae5
     style down fill:#fecaca
     style ssl_warn fill:#fef3c7

Server layout
-------------

.. mermaid::

   flowchart TB
     subgraph web["web.chilicode.com · 37.16.72.137"]
       W1["55 domains"]
       W2["Docker / static / redirect"]
     end

     subgraph mail["mail.chilicode.com · 37.16.72.84"]
       M1["37 domains"]
       M2["Webmail mail.*"]
       M3["Apps: trustlens, postfixadmin"]
     end

     INV["websites.yaml"] --> web & mail
