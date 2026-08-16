"""Sphinx configuration for website-health requirements (sphinx-needs)."""

project = "website-health"
copyright = "2026, ChiliCode"
author = "ChiliCode"
extensions = ["sphinx_needs"]
needs_types = [
    {"directive": "req", "title": "Requirement", "prefix": "REQ_", "color": "#BFD8D2"},
    {"directive": "spec", "title": "Specification", "prefix": "SPEC_", "color": "#FEDCD2"},
    {"directive": "impl", "title": "Implementation", "prefix": "IMPL_", "color": "#DF744A"},
    {"directive": "test", "title": "Test", "prefix": "TEST_", "color": "#DCB239"},
]
needs_id_regex = r"^[A-Z]+_[A-Z0-9]+$"
needs_build_json = True
exclude_patterns = ["_build"]
