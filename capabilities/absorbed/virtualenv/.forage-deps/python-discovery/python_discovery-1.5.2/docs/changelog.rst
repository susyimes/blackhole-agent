#################
 Release History
#################

.. towncrier-draft-entries::

.. towncrier release notes start

********************
 v1.5.1 (2026-07-31)
********************

Bug fixes - 1.5.1
=================
- Locate uv's interpreter store the way uv does, using XDG on macOS (``~/.local/share/uv/python``) and roaming
  ``%APPDATA%\uv\python`` on Windows, neither of which ``platformdirs`` reported. The uv variables now come from the
  ``env`` mapping rather than ``os.environ`` - by :user:`gaborbernat`. (:issue:`109`)
- Pick uv-managed interpreters by install directory name instead of globbing the store. A bare ``3.8`` now means
  CPython, the way uv resolves it, rather than whichever implementation the filesystem happened to list first, and
  probing runs newest version first - by :user:`gaborbernat`. (:issue:`110`)

Packaging updates and notes for downstreams - 1.5.1
===================================================
- Drop the ``platformdirs`` runtime dependency; locating uv's store was the only thing it did - by
  :user:`gaborbernat`. (:issue:`109`)

********************
 v1.5.0 (2026-07-21)
********************

Packaging updates and notes for downstreams - 1.5.0
===================================================
- Declare support for Python 3.15 and run the test suite against it, currently in beta. (:issue:`104`)

********************
 v1.4.4 (2026-07-08)
********************

Bug fixes - 1.4.4
=================
- Parse the debug build flag in interpreter specs - ``python3.13d`` and Debian's ``python3.13-dbg`` /
  ``python3.13-debug`` now select a ``Py_DEBUG`` interpreter instead of being misread as an ISA named ``dbg``.
  Resolving a virtualenv to its base interpreter also checks the free-threaded and debug ABI flags, so a debug or
  free-threaded environment no longer resolves to a release build of the same version - by :user:`gaborbernat`. (:issue:`96`)

********************
 v1.4.3 (2026-07-03)
********************

Packaging updates and notes for downstreams - 1.4.3
===================================================
- Constrain the ``hatchling`` build requirement per Python version so sdist builds resolve a compatible backend on the
  declared ``>=3.8`` floor - ``hatchling>=1.28`` dropped Python 3.9, leaving 3.8/3.9 unbuildable from source - by
  :user:`gaborbernat`. (:issue:`92`)

********************
 v1.4.2 (2026-06-11)
********************

Bug fixes - 1.4.2
=================
- Stop executable symlink resolution once the stdlib landmark is reachable and keep macOS framework builds untouched,
  matching ``getpath`` - Homebrew interpreters no longer get version-pinned ``Cellar`` paths recorded and stable
  aliases such as Debian's ``/usr/bin/python3`` are preserved - by :user:`gaborbernat`. (:issue:`86`)

********************
 v1.4.1 (2026-06-11)
********************

Bug fixes - 1.4.1
=================
- Resolve executable-only symlinks when computing ``system_executable``, mirroring CPython's ``getpath.realpath``
  (python/cpython#115237): a symlink to the interpreter binary now resolves to the real interpreter, while a fully
  symlinked interpreter tree is kept as-is - by :user:`gaborbernat`. (:issue:`84`)

********************
 v1.4.0 (2026-05-28)
********************

Features - 1.4.0
================
- Add ``debug_build`` attribute to :class:`PythonInfo` exposing whether the interpreter is a debug build
  (``Py_DEBUG``) - by :user:`gaborbernat`. (:issue:`80`)

********************
 v1.3.2 (2026-05-27)
********************

No significant changes.


********************
 v1.3.1 (2026-05-12)
********************

Bug fixes - 1.3.1
=================
- export normalize_isa and deprecate KNOWN_ARCHITECTURES - by :user:`rahuldevikar`. (:issue:`59`)
- discover uv-managed Pythons on Windows. Previously the glob assumed Unix layout (``<root>/<key>/bin/python``) and
  silently found nothing on Windows, where uv places ``python.exe`` directly under the install root - by
  :user:`gaborbernat`. (:issue:`65`)
- Canonicalize GraalVM to match GraalPy Python interpreter in PythonSpec and PythonInfo. - by :user:`timfel`. (:issue:`73`)

********************
 v1.3.0 (2026-05-05)
********************

Features - 1.3.0
================

- Add :func:`~python_discovery.iter_interpreters` for enumerating every discovered interpreter, with PATH and
  UV-install support for non-CPython implementations listed in :data:`~python_discovery.KNOWN_IMPLEMENTATIONS`
  (:pull:`71`)

********************
 v1.2.2 (2026-04-06)
********************

Features - 1.2.2
================

- Export ``normalize_isa`` and deprecate ``KNOWN_ARCHITECTURES`` (:pull:`62`)

********************
 v1.2.1 (2026-03-26)
********************

Features - 1.2.1
================

- Expose ``KNOWN_ARCHITECTURES`` as public API (:pull:`56`)

Contributor-facing changes - 1.2.1
==================================

- Add zizmor security auditing for workflows (:pull:`55`)

********************
 v1.2.0 (2026-03-18)
********************

Features - 1.2.0
================

- Increase interpreter query timeout to 15s, with an override (:pull:`53`)

********************
 v1.1.3 (2026-03-10)
********************

Bug fixes - 1.1.3
=================

- Add ``loongarch64`` to known ISAs (:pull:`50`)

********************
 v1.1.2 (2026-03-09)
********************

Bug fixes - 1.1.2
=================

- Match prerelease versions against ``major.minor`` specs (:pull:`48`)
- Drain pipes after killing a timed-out interpreter probe (:pull:`49`)

Improved documentation - 1.1.2
==============================

- Add package description and usage to the README (:pull:`46`)

********************
 v1.1.1 (2026-03-06)
********************

Bug fixes - 1.1.1
=================

- Add a timeout to interpreter probing (:pull:`42`)
- Add ``i686`` to known ISAs (:pull:`43`)

Contributor-facing changes - 1.1.1
==================================

- Add a security policy and workflow permissions hardening (:pull:`33`)

********************
 v1.1.0 (2026-02-26)
********************

Features - 1.1.0
================

- Add a ``predicate`` parameter to :func:`~python_discovery.get_interpreter` (:pull:`31`)

Improved documentation - 1.1.0
==============================

- Fix the ReadTheDocs build (:pull:`29`)
- Add ``:param:`` descriptions to all public APIs (:pull:`32`)

********************
 v1.0.0 (2026-02-25)
********************

Features - 1.0.0
================

- Initial release as a standalone package, extracted from ``virtualenv`` (:pull:`28`)
