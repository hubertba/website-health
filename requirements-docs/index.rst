Website Health — Requirements
=============================

Requirements for the domain health monitoring tool, documented with `sphinx-needs`.

.. toctree::
   :maxdepth: 2
   :caption: Documentation

   diagrams
   needs/core
   needs/security
   needs/performance
   needs/mail
   needs/history
   needs/alerts
   needs/export

Live reports
------------

* `Domain health report <../>`_
* `Requirements documentation <./>`_ (this site)

Build locally::

   pip install -r requirements-docs.txt
   python3 -m sphinx -b html requirements-docs docs/docs

The HTML output is written to ``docs/docs/`` so GitHub Pages serves it at ``/docs/``.
