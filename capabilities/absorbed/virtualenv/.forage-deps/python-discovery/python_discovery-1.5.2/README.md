# [`python-discovery`](https://python-discovery.readthedocs.io/en/latest/)

[![PyPI](https://img.shields.io/pypi/v/python-discovery?style=flat-square)](https://pypi.org/project/python-discovery/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/python-discovery.svg)](https://pypi.org/project/python-discovery/)
[![Downloads](https://static.pepy.tech/badge/python-discovery/month)](https://pepy.tech/project/python-discovery)
[![check](https://github.com/tox-dev/python-discovery/actions/workflows/check.yaml/badge.svg)](https://github.com/tox-dev/python-discovery/actions/workflows/check.yaml)
[![Documentation Status](https://readthedocs.org/projects/python-discovery/badge/?version=latest)](https://python-discovery.readthedocs.io/en/latest/?badge=latest)

## What is python-discovery?

`python-discovery` is a library for discovering Python interpreters installed on your machine. You may have multiple
Python versions from system packages, [pyenv](https://github.com/pyenv/pyenv), [mise](https://mise.jdx.dev/),
[asdf](https://asdf-vm.com/), [uv](https://docs.astral.sh/uv/), or the Windows registry (PEP 514). This library finds
the right one for you.

Give it a requirement like `python3.12` or `>=3.11,<3.13`, and it searches all known locations, verifies each candidate,
and returns detailed metadata about the match. Results are cached to disk so repeated lookups are fast.

The library runs on Python 3.8+ and discovers interpreters as old as Python 3.6; anything older is skipped with a
warning naming the version it found.

## Usage

```python
from pathlib import Path

from python_discovery import DiskCache, get_interpreter

cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())
result = get_interpreter("python3.12", cache=cache)
if result is not None:
    print(result.executable)  # /usr/bin/python3.12
    print(result.implementation)  # CPython
    print(result.version_info[:3])  # (3, 12, 1)
```

The `get_interpreter()` function accepts various specification formats:

- Absolute path: `/usr/bin/python3.12`
- Version: `3.12`
- Implementation prefix: `cpython3.12`
- [Version specifier](https://packaging.python.org/en/latest/specifications/version-specifiers/): `>=3.10`,
  `>=3.11,<3.13`

## Documentation

Full documentation is available at [python-discovery.readthedocs.io](https://python-discovery.readthedocs.io/en/latest/)
