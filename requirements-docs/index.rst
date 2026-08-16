Website Health — Requirements
=============================

Requirements for the domain health monitoring tool, documented with `sphinx-needs`.

.. toctree::
   :maxdepth: 2
   :caption: Requirements

   needs/core
   needs/history
   needs/alerts

Build locally::

   pip install -r requirements-docs.txt
   python3 -m sphinx -b html requirements-docs requirements-docs/_build
