python-discovery
================

You may have multiple Python versions installed on your machine -- system Python, versions from
`pyenv <https://github.com/pyenv/pyenv>`_, `mise <https://mise.jdx.dev/>`_,
`asdf <https://asdf-vm.com/>`_, `uv <https://docs.astral.sh/uv/>`_, or the Windows registry
(:pep:`514`). ``python-discovery`` finds the right one for you.

Give it a requirement like ``python3.12`` or ``>=3.11,<3.13``, and it searches all known locations,
verifies each candidate, and returns detailed metadata about the match. Results are cached to disk so
repeated lookups are fast.

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, get_interpreter

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())
   result = get_interpreter("python3.12", cache=cache)
   if result is not None:
       print(result.executable)       # /usr/bin/python3.12
       print(result.implementation)   # CPython
       print(result.version_info[:3]) # (3, 12, 1)

.. toctree::
   :caption: Tutorials
   :hidden:

   tutorial/getting-started

.. toctree::
   :caption: How-to Guides
   :hidden:

   how-to/standalone-usage

.. toctree::
   :caption: Reference
   :hidden:

   reference/api
   reference/environment-variables

.. toctree::
   :caption: Explanation
   :hidden:

   explanation

.. toctree::
   :caption: Project
   :hidden:

   changelog
