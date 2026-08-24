"""Sphinx configuration for python-discovery documentation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from python_discovery import __version__

company = "tox-dev"
name = "python-discovery"
version = ".".join(__version__.split(".")[:2])
release = __version__
copyright = f"2026-{datetime.now(tz=timezone.utc).year}, {company}"  # ruff:ignore[builtin-variable-shadowing]

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.mermaid",
    "sphinxcontrib.towncrier.ext",
]

towncrier_draft_autoversion_mode = "draft"
towncrier_draft_include_empty = True
towncrier_draft_working_directory = Path(__file__).parent.parent

extlinks = {
    "issue": ("https://github.com/tox-dev/python-discovery/issues/%s", "#%s"),
    "pull": ("https://github.com/tox-dev/python-discovery/pull/%s", "PR #%s"),
    "user": ("https://github.com/%s", "@%s"),
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = []
source_suffix = ".rst"
exclude_patterns = ["_build", "changelog/*"]

main_doc = "index"
pygments_style = "default"
always_document_param_types = True
project = name

html_theme = "furo"
html_title = project
html_last_updated_fmt = datetime.now(tz=timezone.utc).isoformat()
pygments_dark_style = "monokai"
html_show_sourcelink = False
html_static_path = ["_static"]
html_theme_options = {
    "light_logo": "logo.svg",
    "dark_logo": "logo.svg",
    "sidebar_hide_name": True,
}
html_css_files = ["custom.css"]
