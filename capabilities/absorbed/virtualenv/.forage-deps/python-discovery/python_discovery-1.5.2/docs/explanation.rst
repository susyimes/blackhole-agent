How it works
============

Where does python-discovery look?
---------------------------------

When you call :func:`~python_discovery.get_interpreter`, the library checks several locations in
order. It stops as soon as it finds an interpreter that matches your spec.

.. mermaid::

    flowchart TD
        Start["get_interpreter()"] --> AbsPath{"Is spec an<br>absolute path?"}
        AbsPath -->|Yes| TryAbs["Use path directly"]
        AbsPath -->|No| TryFirst["try_first_with paths"]
        TryFirst --> RelPath{"Is spec a<br>relative path?"}
        RelPath -->|Yes| TryRel["Resolve relative to cwd"]
        RelPath -->|No| Current["Current interpreter"]
        Current --> Win{"Windows?"}
        Win -->|Yes| PEP514["PEP 514 registry"]
        Win -->|No| PATH
        PEP514 --> PATH["PATH search"]
        PATH --> Shims["Version-manager shims<br>(pyenv / mise / asdf)"]
        Shims --> UV["uv-managed Pythons"]

        TryAbs --> Verify
        TryRel --> Verify
        UV --> Verify

        Verify{{"Verify candidate<br>(subprocess call)"}}
        Verify -->|Matches spec| Cache["Cache and return"]
        Verify -->|No match| Next["Try next candidate"]

        style Start fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Verify fill:#d9904a,stroke:#8f5f2a,color:#fff
        style Cache fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Next fill:#d94a4a,stroke:#8f2a2a,color:#fff

Each candidate is verified by running it as a subprocess and collecting its metadata (version,
architecture, platform, sysconfig values, etc.). This subprocess call is the expensive part, which
is why results are cached.

How version-manager shims are handled
-----------------------------------------

Version managers like `pyenv <https://github.com/pyenv/pyenv>`_ install thin wrapper scripts called
**shims** (e.g., ``~/.pyenv/shims/python3.12``) that redirect to the real interpreter. python-discovery
detects these shims and resolves them to the actual binary.

.. mermaid::

    flowchart TD
        Shim["Shim detected"] --> EnvVar{"PYENV_VERSION<br>set?"}
        EnvVar -->|Yes| Use["Use that version"]
        EnvVar -->|No| File{".python-version<br>file exists?"}
        File -->|Yes| Use
        File -->|No| Global{"pyenv global<br>version exists?"}
        Global -->|Yes| Use
        Global -->|No| Skip["Skip shim"]

        style Shim fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Use fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Skip fill:#d94a4a,stroke:#8f2a2a,color:#fff

`mise <https://mise.jdx.dev/>`_ and `asdf <https://asdf-vm.com/>`_ work similarly, using the
``MISE_DATA_DIR`` and ``ASDF_DATA_DIR`` environment variables to locate their installations.

How uv-managed Pythons are discovered
---------------------------------------

`uv <https://docs.astral.sh/uv/>`_ installs Python interpreters under a single root directory. ``UV_PYTHON_INSTALL_DIR``
overrides it; otherwise the store is the ``python`` bucket of uv's state directory, which uv derives as follows:

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Platform
     - Legacy state directory
     - Current state directory
   * - Windows
     - ``%APPDATA%\uv\data``
     - ``%APPDATA%\uv`` (roaming, not local)
   * - macOS
     - ``~/Library/Application Support/uv``
     - ``$XDG_DATA_HOME/uv`` or ``~/.local/share/uv``
   * - Other
     - same as current
     - ``$XDG_DATA_HOME/uv`` or ``~/.local/share/uv``

uv follows the XDG convention on macOS too, and falls back to the legacy directory only when that directory already
exists. python-discovery searches both, in the same order, so a leftover legacy directory cannot hide the store uv
installs into. A relative ``XDG_DATA_HOME`` does not count, as the XDG specification requires, and Windows ignores it
outright. Every one of these variables comes from the ``env`` mapping passed to
:func:`~python_discovery.get_interpreter`, rather than from the process environment.

Each install lives in its own subdirectory, but the actual binary location varies by OS and implementation:

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Implementation
     - Unix layout
     - Windows layout
   * - CPython
     - ``<root>/<key>/bin/python``
     - ``<root>/<key>/python.exe``
   * - PyPy
     - ``<root>/<key>/bin/pypy*``
     - ``<root>/<key>/pypy*.exe``
   * - GraalPy
     - ``<root>/<key>/bin/graalpy``
     - ``<root>/<key>/bin/graalpy.exe``

GraalPy keeps its ``bin/`` segment on Windows (an upstream choice in uv); PyPy and CPython do not. python-discovery
globs all of these patterns regardless of the host OS, because globs that do not match anything are essentially
free, and the cross-platform list is short. Symlinked aliases inside an install (``bin/python``,
``bin/python3``, ``bin/python3.14`` all pointing at the same real file) are deduplicated by resolved path before
the subprocess interrogation, so each install is interrogated once. python-discovery also follows the ``install``
subdirectory some distributions unpack into, as uv does.

Which uv installs get interrogated
------------------------------------

Interrogating an interpreter costs a subprocess, and a uv install directory announces what it holds in its own name:
``<implementation>-<version>[+<variant>]-<os>-<arch>-<libc>``, for example
``cpython-3.14.6+freethreaded-macos-aarch64-none``. python-discovery reads that name and skips the installs the spec
already rules out, then probes what is left in uv's preference order:

.. mermaid::

    flowchart LR
        Dirs[/"store subdirectories"/] --> Parse{"name is a uv key?"}
        Parse -->|"no"| Last["probe last"]
        Parse -->|"yes"| Filter["drop what the spec rules out:<br>implementation, version, free-threaded, debug"]
        Filter --> Sort["CPython → PyPy → GraalPy,<br>newest version first,<br>default build before variants"]
        Sort --> Interrogate(["subprocess interrogation"])
        Last --> Interrogate

        style Dirs fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Parse fill:#d9904a,stroke:#8f5f2a,color:#fff
        style Filter fill:#9f4ad9,stroke:#5f2a8f,color:#fff
        style Sort fill:#c2873a,stroke:#7a4c1f,color:#fff
        style Interrogate fill:#4a9f4a,stroke:#2a6f2a,color:#fff

python-discovery reads the variant suffix the same way :class:`~python_discovery.PythonSpec` does: ``3.14t`` wants
``+freethreaded``, ``3.14d`` wants ``+debug``. A spec that says nothing about a variant leaves it unconstrained, so
``3.14`` still reaches a ``+debug`` install, after the default build rather than instead of it.

A bare version spec such as ``3.8`` matches CPython only, which is what uv resolves it to and what the equivalent
``python3.8`` probe on ``PATH`` finds in practice. Ask for ``pypy3.8`` or enumerate with
:func:`~python_discovery.iter_interpreters` to reach the other implementations - PyPy ships a ``bin/python`` symlink,
so a store-wide glob would otherwise hand back PyPy for ``3.8`` whenever the filesystem listed it first.

Two names carry less information than they appear to. GraalPy keys named after the GraalVM release
(``graalpy-24.1.1``, from older uv versions) do not constrain the version, and uv's minor version links
(``cpython-3.15`` pointing at ``cpython-3.15.0b3``) move on the next patch release, so the concrete install ranks
ahead of the link. Anything that is not a uv key - a hand-made ``UV_PYTHON_INSTALL_DIR`` layout, say - stays in
the running, at the back of the queue.

Selecting one interpreter vs. enumerating all of them
-------------------------------------------------------

:func:`~python_discovery.get_interpreter` and :func:`~python_discovery.iter_interpreters` walk the same candidate
sources, but they answer different questions and behave differently in three ways.

.. mermaid::

    flowchart LR
        Sources["candidate sources<br>(try_first_with → current →<br>PEP 514 → PATH → uv)"]
        Sources --> Get["get_interpreter()<br>first match wins, returns one"]
        Sources --> Iter["iter_interpreters()<br>yields every match"]

        style Get fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Iter fill:#4a90d9,stroke:#2a5f8f,color:#fff

**Implementation coverage on PATH.** :func:`~python_discovery.get_interpreter` matches only ``python*`` filenames on
PATH unless the spec names another implementation explicitly (``pypy3.12``, ``graalpy3.11``). This keeps backwards
compatibility with tools that have always read "no implementation in the spec" as "give me CPython."
:func:`~python_discovery.iter_interpreters` with no spec broadens the search to every name in
:data:`~python_discovery.KNOWN_IMPLEMENTATIONS` -- otherwise an "all interpreters" call would silently miss every
PyPy and GraalPy on the system. When you pass a spec to :func:`~python_discovery.iter_interpreters`, it falls back
to the same narrow regex as :func:`~python_discovery.get_interpreter`, so behavior is consistent across the two
APIs whenever a spec is given.

**Deduplication.** :func:`~python_discovery.get_interpreter` deduplicates per call so it does not interrogate the
same binary twice while searching, and stops as soon as a match is found. :func:`~python_discovery.iter_interpreters`
deduplicates by the resolved real path of each candidate's ``system_executable`` (falling back to ``executable``).
That means symlinked aliases like ``/bin/python3`` and ``/usr/bin/python3``, or a virtualenv whose ``python``
symlinks to its base interpreter, collapse to a single yield. The semantic is "one entry per distinct install,"
which is what callers building choosers or version-range pickers usually want.

**Iteration order.** Yields come back in *priority order*: ``try_first_with`` first, then the running interpreter,
then :pep:`514` entries on Windows, then PATH left-to-right, then UV-managed installs. This matches what
:func:`~python_discovery.get_interpreter` would have returned at each step. If your ordering differs (newest
version first, smallest install root, etc.), wrap the call in :func:`sorted` -- the API deliberately does not
include a ``sort_by`` parameter because keeping discovery order preserves the priority signal for callers who
want it.

How caching works
-------------------

Querying an interpreter requires a subprocess call, which is slow. The cache avoids repeating this
work by storing the result as a JSON file keyed by the interpreter's path.

.. mermaid::

    flowchart TD
        Lookup["py_info(path)"] --> Exists{"Cache hit?"}
        Exists -->|Yes| Read["Read JSON"]
        Exists -->|No| Run["Run subprocess"]
        Run --> Write["Write JSON<br>(with filelock)"]
        Write --> Return["Return PythonInfo"]
        Read --> Return

        style Lookup fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Return fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Run fill:#d9904a,stroke:#8f5f2a,color:#fff

The built-in :class:`~python_discovery.DiskCache` stores files under ``<root>/py_info/4/<sha256>.json``
with `filelock <https://py-filelock.readthedocs.io/>`_-based locking for safe concurrent access. You
can also pass ``cache=None`` to disable caching, or implement your own backend (see
:doc:`/how-to/standalone-usage`).

Subprocess timeout behavior
----------------------------

When python-discovery verifies an interpreter candidate, it runs a subprocess to query its metadata.
On slow systems (especially Windows), Python startup can take significant time. The default timeout
is **15 seconds** to balance responsiveness with accommodation for real-world conditions.

If your system consistently hits timeouts, you can customize the timeout via the
``PY_DISCOVERY_TIMEOUT`` environment variable (in seconds):

.. code-block:: console

   # Increase timeout to 30 seconds
   export PY_DISCOVERY_TIMEOUT=30
   python -c "from python_discovery import get_interpreter; get_interpreter('python3.12')"

The timeout applies to each individual interpreter being queried. If you set a value that is too low,
legitimate interpreters may be skipped; if too high, the discovery process may take longer to fail
when encountering problematic interpreters.

Supported Python versions
-------------------------

Two floors apply: python-discovery itself runs on Python 3.8+ (``requires-python``), while discovery
reaches down to Python 3.6 - old enough to cover RHEL 8's system Python.

python-discovery skips candidates below 3.6 with one warning naming the executable, the version
found, and the floor; the verdict is cached, so the interpreter is not queried again. Candidates too
old to run the version check at all (before Python 2.7) fail as a generic query error. An
absolute-path spec for a below-floor interpreter raises :class:`RuntimeError` with the same message.
The floor moves only in a major release.

Spec format reference
-----------------------

A spec string follows the pattern ``[impl][version][t][d][-arch][-machine]``. Every part is optional.

.. mermaid::

    flowchart TD
        Spec["Spec string"] --> Impl["impl<br>(optional)"]
        Impl --> Version["version<br>(optional)"]
        Version --> T["t<br>(optional)"]
        T --> D["d / -dbg / -debug<br>(optional)"]
        D --> Arch["-arch<br>(optional)"]
        Arch --> Machine["-machine<br>(optional)"]

        style Impl fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Version fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style T fill:#d9904a,stroke:#8f5f2a,color:#fff
        style D fill:#4ad9c4,stroke:#2a8f7f,color:#fff
        style Arch fill:#d94a4a,stroke:#8f2a2a,color:#fff
        style Machine fill:#904ad9,stroke:#5f2a8f,color:#fff

**Parts explained:**

- **impl** -- the Python implementation name. ``python`` and ``py`` both mean "any implementation"
  (usually CPython). Use ``cpython``, ``pypy``, or ``graalpy`` to be explicit.
- **version** -- dotted version number (``3``, ``3.12``, or ``3.12.1``). You can also write
  ``312`` as shorthand for ``3.12``.
- **t** -- appended directly after the version. Matches free-threaded (no-GIL) builds only.
- **d** -- require a debug (``Py_DEBUG``) build. Written as ``d`` right after the version (the ABI flag
  form, as in ``python3.13d``) or as Debian's ``-dbg`` / ``-debug`` suffix (``python3.13-dbg``). When
  omitted the build type is unconstrained.
- **-arch** -- ``-32`` or ``-64`` for 32-bit or 64-bit interpreters.
- **-machine** -- the CPU instruction set: ``-arm64``, ``-x86_64``, ``-aarch64``, ``-riscv64``, etc.

Order matters: the parts appear in the sequence shown above. Combine the ABI flags as ``python3.13td``
(free-threaded then debug, the order CPython uses in ``sys.abiflags``), and keep ``-arch`` before
``-machine`` as in ``python3.13d-64-arm64``. Mixing ``d`` with ``-dbg`` in one spec, or swapping the arch
and machine segments, leaves the string unrecognized, so it falls back to a literal executable-name match.

**Full examples:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Spec
     - Meaning
   * - ``3.12``
     - Any Python 3.12
   * - ``python3.12``
     - CPython 3.12
   * - ``cpython3.12``
     - Explicitly CPython 3.12
   * - ``pypy3.9``
     - PyPy 3.9
   * - ``python3.13t``
     - Free-threaded (no-GIL) CPython 3.13
   * - ``python3.13-dbg``
     - Debug (``Py_DEBUG``) CPython 3.13 (``python3.13d`` also works)
   * - ``python3.13td``
     - Free-threaded debug CPython 3.13
   * - ``python3.12-64``
     - 64-bit CPython 3.12
   * - ``python3.12-64-arm64``
     - 64-bit CPython 3.12 on ARM64
   * - ``/usr/bin/python3``
     - Absolute path, used directly (no search)
   * - ``>=3.11,<3.13``
     - `Version specifier <https://packaging.python.org/en/latest/specifications/version-specifiers/>`_
       (any Python in range)
   * - ``cpython>=3.11``
     - `Version specifier <https://packaging.python.org/en/latest/specifications/version-specifiers/>`_
       restricted to CPython

`Version specifiers <https://packaging.python.org/en/latest/specifications/version-specifiers/>`_
(``>=``, ``<=``, ``~=``, ``!=``, ``==``, ``===``) are supported. Multiple specifiers can be comma-separated,
for example ``>=3.11,<3.13``.
