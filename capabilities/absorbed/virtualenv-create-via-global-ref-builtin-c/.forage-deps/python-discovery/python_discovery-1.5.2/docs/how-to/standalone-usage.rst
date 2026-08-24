How-to guides
=============

Search specific directories first
-----------------------------------

If you know a likely location for the interpreter, pass it via ``try_first_with`` to check there
before the normal search. This is useful when you have a custom Python install outside the
standard locations.

.. code-block:: python

   from python_discovery import get_interpreter

   info = get_interpreter("python3.12", try_first_with=["/opt/python/bin"])
   if info is not None:
       print(info.executable)

Select a debug build
----------------------

To require a debug (``Py_DEBUG``) interpreter, add the debug marker to the spec. Both the ABI-flag form
``python3.13d`` and the Debian package name ``python3.13-dbg`` work, and each resolves to the same
interpreter (Debian ships ``/usr/bin/python3.13d`` and ``/usr/bin/python3.13-dbg`` side by side). A spec with no
marker keeps matching either build, so reach for the marker only when you need the debug build.

.. code-block:: python

   from python_discovery import get_interpreter

   info = get_interpreter("python3.13-dbg")
   if info is not None:
       assert info.debug_build

Combine the marker with the free-threaded ``t`` flag to select a free-threaded debug build, written
``python3.13td`` (ABI-flag order is ``t`` then ``d``) or ``python3.13t-dbg``.

Restrict the search environment
---------------------------------

By default, python-discovery reads environment variables like ``PATH`` and ``PYENV_ROOT`` from your
shell. You can override these to control exactly where the library looks.

.. mermaid::

    flowchart TD
        Env["Custom env dict"] --> Call["get_interpreter(spec, env=env)"]
        Call --> PATH["PATH"]
        Call --> Pyenv["PYENV_ROOT"]
        Call --> UV["UV_PYTHON_INSTALL_DIR"]
        Call --> Mise["MISE_DATA_DIR"]

        style Env fill:#4a90d9,stroke:#2a5f8f,color:#fff

.. code-block:: python

   import os

   from python_discovery import get_interpreter

   env = {**os.environ, "PATH": "/usr/local/bin:/usr/bin"}
   result = get_interpreter("python3.12", env=env)

Customize interpreter query timeout
-------------------------------------

On slower systems (especially Windows), Python startup can take more than the default 15 seconds.
If your discovery process times out when looking for interpreters, you can extend the timeout via
the ``PY_DISCOVERY_TIMEOUT`` environment variable.

.. code-block:: python

   import os

   from python_discovery import get_interpreter

   # Increase timeout to 30 seconds for slow environments
   env = {**os.environ, "PY_DISCOVERY_TIMEOUT": "30"}
   result = get_interpreter("python3.12", env=env)

The timeout value should be a number in seconds. Each interpreter candidate is given this much time
to respond. If a timeout occurs, the candidate is skipped and the search continues with the next one.

List every interpreter on the system
--------------------------------------

Use :func:`~python_discovery.iter_interpreters` to enumerate every Python python-discovery can find. With no spec
it yields all known implementations (CPython, PyPy, GraalPy -- see
:data:`~python_discovery.KNOWN_IMPLEMENTATIONS`). Pass a spec to filter, exactly like
:func:`~python_discovery.get_interpreter`.

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, iter_interpreters

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())

   # Every interpreter, no filter
   for info in iter_interpreters(cache=cache):
       print(info.executable, info.version_str, info.implementation)

   # Every CPython 3.10 or newer, newest first
   newest_first = sorted(
       iter_interpreters("cpython>=3.10", cache=cache),
       key=lambda info: info.version_info,
       reverse=True,
   )

Enumeration interrogates every candidate as a subprocess on a cold cache. Always pass a
:class:`~python_discovery.DiskCache` if you call this more than once.

Pick an interpreter from a range, preferring newer
----------------------------------------------------

A common need: search a version range and prefer newer interpreters when more than one matches. Sort the result of
:func:`~python_discovery.iter_interpreters` and take the first.

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, iter_interpreters

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())

   matches = sorted(
       iter_interpreters("cpython>=3.10,<3.15", cache=cache),
       key=lambda info: info.version_info,
       reverse=True,
   )
   info = matches[0] if matches else None

Use :func:`get_interpreter` instead when you only need the first PATH-priority hit; use the sort-and-take pattern
when *your* ordering differs from PATH order (newest version, smallest install size, preferred install root, etc.).

Read interpreter metadata
---------------------------

Once you have a :class:`~python_discovery.PythonInfo`, you can inspect everything about the interpreter.

.. mermaid::

    classDiagram
        class PythonInfo {
            +executable: str
            +system_executable: str
            +implementation: str
            +version_info: VersionInfo
            +architecture: int
            +platform: str
            +sysconfig_vars: dict
            +sysconfig_paths: dict
            +machine: str
            +free_threaded: bool
            +debug_build: bool
        }

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, get_interpreter

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())
   info = get_interpreter("python3.12", cache=cache)

   info.executable           # Resolved path to the binary.
   info.system_executable    # The underlying system interpreter (outside any venv).
   info.implementation       # "CPython", "PyPy", "GraalPy", etc.
   info.version_info         # VersionInfo(major, minor, micro, releaselevel, serial).
   info.architecture         # 64 or 32.
   info.platform             # sys.platform value ("linux", "darwin", "win32").
   info.machine              # ISA: "arm64", "x86_64", etc.
   info.free_threaded        # True if this is a no-GIL build.
   info.debug_build          # True if this is a Py_DEBUG build.
   info.sysconfig_vars       # All sysconfig.get_config_vars() values.
   info.sysconfig_paths      # All sysconfig.get_paths() values.

Implement a custom cache backend
-----------------------------------

The built-in :class:`~python_discovery.DiskCache` stores results as JSON files with
`filelock <https://py-filelock.readthedocs.io/>`_-based locking. If you need a different storage
strategy (e.g., in-memory, database-backed), implement the :class:`~python_discovery.PyInfoCache`
protocol.

.. mermaid::

    classDiagram
        class PyInfoCache {
            <<Protocol>>
            +py_info(path) ContentStore
            +py_info_clear() None
        }
        class ContentStore {
            <<Protocol>>
            +exists() bool
            +read() dict | None
            +write(content) None
            +remove() None
            +locked() context
        }
        class DiskCache {
            +root: Path
        }
        PyInfoCache <|.. DiskCache
        PyInfoCache --> ContentStore

.. code-block:: python

   from pathlib import Path

   from python_discovery import ContentStore, PyInfoCache


   class MyContentStore:
       def __init__(self, path: Path) -> None:
           self._path = path

       def exists(self) -> bool: ...

       def read(self) -> dict | None: ...

       def write(self, content: dict) -> None: ...

       def remove(self) -> None: ...

       def locked(self): ...


   class MyCache:
       def py_info(self, path: Path) -> MyContentStore: ...

       def py_info_clear(self) -> None: ...

Any object that matches the protocol works -- no inheritance required.
