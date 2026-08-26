"""Capability foraging plane: zero-spec autonomous acquisition.

The acquisition plane still needs a human to write the declarative kernel of
each ``AcquisitionSpec``: import name, entry callable, state keys, and probe
inputs. This module removes that last human input — **foraging**:

- a forage request names only a package: a local source (directory or
  sdist/npm tarball) or a live PyPI / npm registry name plus an optional
  version;
- the runtime is detected from the staged tree (Python import layout vs
  ``package.json`` / ``.mjs`` entry), never declared unless the request
  pins it;
- Python import root/name and Node entry modules are detected from the
  staged tree layout, never declared;
- candidate callables are enumerated by sandboxed introspection — a
  subprocess imports the package (CPython or Node) and reflects its
  exported functions, including a Node default export when that is a
  single function, a namespace object of functions, a constructable
  with instance methods, a class whose callable API is static
  ``Class.method``, a named class export such as ``Base64.encode``,
  ``new Parser().parse``, or ``new Parser(options).parse`` (constructor
  arguments and instance-own methods visible only after construction),
  or a nested namespace class such as ``buffer.Buffer.byteLength``,
  Python class instance methods such as ``Parser(opts).loads``
  (constructed with ``()``, ``{}``, or ``""``, including methods that
  exist only on the instance after construction), Python class
  static methods such as ``Class.method`` / ``HTMLRenderer.escape_html``
  (``@staticmethod`` / ``@classmethod`` called on the class, including
  when the constructor cannot be satisfied), Python nested-namespace
  class statics such as ``package.submodule.Class.method`` /
  ``api.String.from_raw`` (class statics on a submodule that is not a
  top-level ``Class.method``), Python nested-namespace class
  statics two submodule levels down such as
  ``package.subpackage.submodule.Class.method`` /
  ``dev.helpers.File.exists`` (class statics that are not a
  one-level ``package.submodule.Class.method``), Python nested-namespace class
  statics three submodule levels down such as
  ``package.subpackage.subpackage.submodule.Class.method`` (class statics that
  are not a two-level ``package.subpackage.submodule.Class.method``), Python nested-namespace class
  statics four submodule levels down such as
  ``package.subpackage.subpackage.subpackage.submodule.Class.method`` (class
  statics that are not a three-level
  ``package.subpackage.subpackage.submodule.Class.method``), Python nested-namespace class
  statics five submodule levels down such as
  ``package.subpackage.subpackage.subpackage.subpackage.submodule.Class.method``
  / ``create.via_global_ref.builtin.cpython.common.CPython.exe_stem`` (a
  covering ``Class.method`` that returns a cwd-independent JSON scalar,
  including a nullary class static, rather than an inherited path
  validator such as ``CPython.validate_dest``), Python nested-namespace class
  statics six submodule levels down such as
  ``package.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class.method``
  (class statics that are not a five-level
  ``package.subpackage.subpackage.subpackage.subpackage.submodule.Class.method``), Python nested-namespace class
  instance methods such as ``package.submodule.Class(opts).method``
  (constructed nested classes that are not a top-level
  ``Class(opts).method``), Python nested-namespace class
  instance methods two submodule levels down such as
  ``package.subpackage.submodule.Class(opts).method`` (constructed
  classes that are not a one-level ``package.submodule.Class(opts).method``),
  Python nested-namespace class instance methods five submodule levels
  down, Python nested-namespace class instance methods six submodule
  levels down such as
  ``package.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
  / ``providers.amazon.aws.executors.batch.utils.BatchJobCollection.failure_count_by_id``
  (constructable instance methods that are not a six-level
  ``Class.method`` static), and Python nested-namespace class instance
  methods seven submodule levels down such as
  ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
  (constructable instance methods that are not a six-level nested
  ``Class().method`` instance), Python nested-namespace class instance
  methods eight submodule levels down such as
  ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
  (constructable instance methods that are not a seven-level nested
  ``Class().method`` instance),
  and Python nested-submodule functions such as
  ``package.submodule.func`` / ``package.subpackage.submodule.func``
  (module-level callables exported only on a nested submodule, not a
  class method; two-level ``package.subpackage.submodule.func`` is
  selected ahead of one-level ``package.submodule.func`` so a deeper
  module function is not shadowed)
  — filtered to
  JSON-scalar signatures, and ordered deterministically;
- probe inputs are derived from a fixed, task-independent sample vocabulary
  (plain text, TOML, JSON, and markdown string domains; fixed scalar
  samples for int/float/bool), split into selection and held-out probes; no
  expected output is ever written or consulted;
- candidate selection is split-honest: a candidate must satisfy every
  selection probe of one sample domain and then generalize to that domain's
  held-out probe the selector never used; rejected candidates are recorded
  with their reason;
- every held-out-honest callable becomes an ``AcquisitionSpec``: the first
  winner is the primary leaf and additional winners are a multi-callable
  bundle; extras that fail acquisition (for example a provides key already
  covered by another absorbed leaf) are recorded and skipped, and do not
  refuse a covering primary;
- the live lane fetches a package from the PyPI JSON API or the npm
  registry, verifies its digest, and forages it through the identical
  inference path;
- declared runtime dependencies are closed into the staged tree: Python
  ``install_requires`` / Requires-Dist into ``.forage-deps`` on ``sys.path``,
  Node ``package.json`` ``dependencies`` into ``.forage-deps`` then materialized
  as ``node_modules`` so ESM imports resolve; isolated introspection without
  those deps stays an honest refusal;
- falsification: a package with no viable candidate is refused before any
  ledger write; a candidate that only fits the selection probes fails the
  held-out probe; a tampered or forged foraging report fails verification;
- a digest-sealed report under ``artifacts/capability-foraging/`` whose
  grade is a pure function of the recorded verdicts; verification
  re-grades, re-checks the digest, and re-proves every foraged capability
  live.

Determinism contract: candidate order, probe vocabulary, selection, and
every verdict must be reproducible on the same checkout and package source.
Durations and timestamps are diagnostics only and are excluded from every
digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from blackhole_agent.capability_absorption import (
    _STATE_KEY_PATTERN,
    _digest,
    capability_id_for_slug,
    prove_absorbed_capability,
)
from blackhole_agent.capability_acquisition import (
    STEWARDSHIP_ROOT,
    AcquisitionSpec,
    RUNTIMES,
    _STAGE_SKIP_PARTS,
    _run_probe,
    acquire_capability,
    adapter_name_for,
    os_fs_path,
    stage_acquisition_source,
    synthesize_adapter_source,
)
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    load_ledger,
    prove_capability,
    register_capability,
    save_ledger,
    slugify_capability_id,
    utc_now_iso,
)

SCHEMA_VERSION = 1

# Depth 0 is a top-level Class.method; depth 33 is a tretrigintuple nested Class().method.
PYTHON_NESTED_CLASS_DEPTH_PREFIXES: tuple[str, ...] = (
    "python_class",
    "python_nested_namespace_class",
    "python_deep_nested_namespace_class",
    "python_triple_nested_namespace_class",
    "python_quadruple_nested_namespace_class",
    "python_quintuple_nested_namespace_class",
    "python_sextuple_nested_namespace_class",
    "python_septuple_nested_namespace_class",
    "python_octuple_nested_namespace_class",
    "python_nonuple_nested_namespace_class",
    "python_decuple_nested_namespace_class",
    "python_undecuple_nested_namespace_class",
    "python_duodecuple_nested_namespace_class",
    "python_tredecuple_nested_namespace_class",
    "python_quattuordecuple_nested_namespace_class",
    "python_quindecuple_nested_namespace_class",
    "python_sexdecuple_nested_namespace_class",
    "python_septendecuple_nested_namespace_class",
    "python_octodecuple_nested_namespace_class",
    "python_novemdecuple_nested_namespace_class",
    "python_vigintuple_nested_namespace_class",
    "python_unvigintuple_nested_namespace_class",
    "python_duovigintuple_nested_namespace_class",
    "python_trevigintuple_nested_namespace_class",
    "python_quattuorvigintuple_nested_namespace_class",
    "python_quinvigintuple_nested_namespace_class",
    "python_sexvigintuple_nested_namespace_class",
    "python_septemvigintuple_nested_namespace_class",
    "python_octovigintuple_nested_namespace_class",
    "python_novemvigintuple_nested_namespace_class",
    "python_trigintuple_nested_namespace_class",
    "python_untrigintuple_nested_namespace_class",
    "python_duotrigintuple_nested_namespace_class",
    "python_tretrigintuple_nested_namespace_class",
)
PYTHON_NESTED_FUNCTION_DEPTH_PREFIXES: tuple[str, ...] = (
    "python_nested_namespace_function",
    "python_deep_nested_namespace_function",
    "python_triple_nested_namespace_function",
    "python_quadruple_nested_namespace_function",
    "python_quintuple_nested_namespace_function",
    "python_sextuple_nested_namespace_function",
    "python_septuple_nested_namespace_function",
    "python_octuple_nested_namespace_function",
    "python_nonuple_nested_namespace_function",
    "python_decuple_nested_namespace_function",
    "python_undecuple_nested_namespace_function",
    "python_duodecuple_nested_namespace_function",
    "python_tredecuple_nested_namespace_function",
    "python_quattuordecuple_nested_namespace_function",
    "python_quindecuple_nested_namespace_function",
    "python_sexdecuple_nested_namespace_function",
    "python_septendecuple_nested_namespace_function",
    "python_octodecuple_nested_namespace_function",
    "python_novemdecuple_nested_namespace_function",
    "python_vigintuple_nested_namespace_function",
    "python_unvigintuple_nested_namespace_function",
    "python_duovigintuple_nested_namespace_function",
    "python_trevigintuple_nested_namespace_function",
    "python_quattuorvigintuple_nested_namespace_function",
    "python_quinvigintuple_nested_namespace_function",
    "python_sexvigintuple_nested_namespace_function",
    "python_septemvigintuple_nested_namespace_function",
    "python_octovigintuple_nested_namespace_function",
    "python_novemvigintuple_nested_namespace_function",
    "python_trigintuple_nested_namespace_function",
    "python_untrigintuple_nested_namespace_function",
    "python_duotrigintuple_nested_namespace_function",
    "python_tretrigintuple_nested_namespace_function",
)


def python_nested_depth_flag_names() -> tuple[str, ...]:
    names: list[str] = []
    for prefix in PYTHON_NESTED_CLASS_DEPTH_PREFIXES:
        names.append(f"{prefix}_static")
        names.append(f"{prefix}_instance")
    names.extend(PYTHON_NESTED_FUNCTION_DEPTH_PREFIXES)
    return tuple(names)


def python_nested_depth_flags(item: Mapping[str, Any]) -> dict[str, bool]:
    """Copy nested-namespace depth flags off an introspected candidate or record."""

    return {name: bool(item.get(name)) for name in python_nested_depth_flag_names()}


def _prefer_deeper_nested_class(item: Mapping[str, Any], kind: str, *, start: int) -> tuple[int, ...]:
    """Rank deeper nested Class.method kinds first. ``start`` skips shallow prefixes."""

    return tuple(
        0 if item.get(f"{prefix}_{kind}") else 1
        for prefix in reversed(PYTHON_NESTED_CLASS_DEPTH_PREFIXES[start:])
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-foraging"
DEFAULT_DOWNLOAD_DIR = DEFAULT_ARTIFACT_DIR / "downloads"
EXTRACT_CACHE_DIR = DEFAULT_ARTIFACT_DIR / "extracted"
FIXTURE_FORAGE_PACKAGE = REPO_ROOT / "tests" / "fixtures" / "external_packages" / "forage-lab"
FIXTURE_EMPTY_PACKAGE = REPO_ROOT / "tests" / "fixtures" / "external_packages" / "forage-empty"
FIXTURE_NODE_FORAGE_PACKAGE = REPO_ROOT / "tests" / "fixtures" / "external_packages" / "forage-js"
FIXTURE_NODE_EMPTY_PACKAGE = REPO_ROOT / "tests" / "fixtures" / "external_packages" / "forage-js-empty"
_NODE_ENTRY_NAMES = ("index.mjs", "index.js", "main.mjs", "main.js")
_NODE_SKIP_DIR_NAMES = frozenset({"node_modules", "__pycache__", ".git", "test", "tests", ".forage-deps"})
FORAGE_DEPS_DIR = ".forage-deps"
_DEV_REQUIREMENT_NAMES = frozenset(
    {
        "pip",
        "setuptools",
        "wheel",
        "pytest",
        "coverage",
        "sphinx",
        "black",
        "flake8",
        "mypy",
        "tox",
        "hatch",
        "flit",
        "build",
        "twine",
    }
)
# Py2/3 backports that shadow stdlib names when placed on sys.path. The
# ``typing`` backport reads ``Callable._abc_registry``, which modern
# ``collections.abc.Callable`` no longer exposes.
_STDLIB_SHADOW_REQUIREMENT_NAMES = frozenset(
    {
        "typing",
        "enum34",
        "pathlib2",
        "configparser",
        "contextlib2",
        "funcsigs",
        "ipaddress",
        "futures",
        "functools32",
    }
)
_REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_INSTALL_REQUIRES_ASSIGN = re.compile(r"install_requires\s*=\s*\[(.*?)\]", re.DOTALL)
_QUOTED_REQUIREMENT = re.compile(r"""['"]([^'"]+)['"]""")

_SKIP_MODULE_NAMES = frozenset({"setup", "conftest", "test", "tests", "__init__"})
_SKIP_REQUIRE_DIRS = frozenset(
    {
        "tests",
        "test",
        "testing",
        "docs",
        "doc",
        "examples",
        "example",
        "benchmarks",
        "benchmark",
        "samples",
        "fixtures",
    }
)
_SCALAR_ANNOTATIONS = frozenset({"", "str", "int", "float", "bool"})
_NON_SCALAR_RETURN_ROOTS = frozenset(
    {
        "dict",
        "list",
        "tuple",
        "set",
        "frozenset",
        "mapping",
        "mutablemapping",
        "sequence",
        "iterable",
        "bytes",
        "bytearray",
        "memoryview",
        "object",
        "type",
        "callable",
        "deque",
        "defaultdict",
        "ordereddict",
        "counter",
        "chainmap",
    }
)
_DEFAULT_LIVE_TARGETS = ("inflection",)
_INFER_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Fixed, task-independent probe vocabulary. No expected outputs anywhere.
# ---------------------------------------------------------------------------

_NULLARY_DOMAINS: tuple[dict[str, Any], ...] = (
    {
        "domain": "nullary",
        "selection": [None, None, None],
        "held_out": [None],
    },
)

_STRING_DOMAINS: tuple[dict[str, Any], ...] = (
    {
        "domain": "plain-text",
        "selection": ["Hello World", "blackhole unbound", "MiXeD CaSe"],
        "held_out": [""],
    },
    {
        "domain": "toml",
        "selection": [
            'title = "blackhole"\n',
            "[tool.unbound]\nenabled = true\n",
            "values = [1, 2, 3]\n",
        ],
        "held_out": ["# comment only\n"],
    },
    {
        "domain": "json",
        "selection": ['{"b": 1, "a": 2}', '{"z": [3, 1]}', "[1, 2]"],
        "held_out": ["{}"],
    },
    {
        "domain": "markdown",
        "selection": ["# Blackhole\n", "**unbound** growth\n", "1. absorb\n2. prove\n"],
        "held_out": ["plain paragraph\n"],
    },
)

_SCALAR_DOMAINS: dict[str, tuple[dict[str, Any], ...]] = {
    "int": ({"domain": "int", "selection": [3, -7, 0], "held_out": [1024]},),
    "float": ({"domain": "float", "selection": [1.5, -2.25, 0.0], "held_out": [3.14159]},),
    "bool": ({"domain": "bool", "selection": [True, False, True], "held_out": [False]},),
}


def probe_domains_for(annotation: str) -> tuple[dict[str, Any], ...]:
    """Return the fixed sample domains for one parameter annotation."""

    if annotation in ("", "str"):
        return _STRING_DOMAINS
    return _SCALAR_DOMAINS.get(annotation, ())


# ---------------------------------------------------------------------------
# Import-root detection and sandboxed introspection.
# ---------------------------------------------------------------------------


def _is_importable_dir(entry: Path, *, depth: int = 0) -> bool:
    """True for a regular package or a PEP 420 namespace that contains one."""

    if not entry.is_dir() or entry.name.startswith((".", "_")):
        return False
    if not entry.name.isidentifier():
        return False
    if entry.name in _SKIP_MODULE_NAMES or entry.name in _SKIP_REQUIRE_DIRS:
        return False
    if (entry / "__init__.py").is_file():
        return True
    if depth >= 3:
        return False
    try:
        children = list(entry.iterdir())
    except OSError:
        return False
    if any(
        child.is_file()
        and child.suffix == ".py"
        and child.stem.isidentifier()
        and not child.name.startswith("_")
        for child in children
    ):
        return True
    return any(_is_importable_dir(child, depth=depth + 1) for child in children if child.is_dir())


def _importable_names(root: Path) -> set[str]:
    names = {entry.name for entry in root.iterdir() if _is_importable_dir(entry)}
    names |= {
        entry.stem
        for entry in root.glob("*.py")
        if entry.stem not in _SKIP_MODULE_NAMES and not entry.name.startswith("_")
    }
    return names


def _candidate_roots(staged_dir: Path) -> list[Path]:
    roots = [staged_dir]
    for child in sorted(
        entry for entry in staged_dir.iterdir() if entry.is_dir() and not entry.name.startswith(".")
    ):
        if child.name.endswith((".dist-info", ".egg-info", ".data")):
            continue
        # Importable packages at the staging root are the import root. Scanning
        # their internals leaks submodule names (grpc.aio) into uniqueness.
        if _is_importable_dir(child):
            continue
        roots.append(child)
        src = child / "src"
        if src.is_dir():
            roots.append(src)
    return roots


def detect_import_root(staged_dir: Path, hint: str = "") -> tuple[str, str]:
    """Detect ``(path_root, import_name)`` from the staged tree layout.

    The distribution-name hint wins when it matches an importable package or
    module; otherwise exactly one unique importable name across the
    candidate roots must exist. Anything else is an honest refusal.
    """

    normalized_hint = re.sub(r"[^a-z0-9]+", "_", hint.lower()).strip("_")
    discoveries: list[tuple[Path, set[str]]] = []
    for root in _candidate_roots(staged_dir):
        names = _importable_names(root)
        if not names:
            continue
        if normalized_hint and normalized_hint in names:
            return root.relative_to(staged_dir).as_posix(), normalized_hint
        discoveries.append((root, names))
    unique_names = {name for _, names in discoveries for name in names}
    if len(unique_names) == 1:
        name = next(iter(unique_names))
        for root, names in discoveries:
            if name in names:
                return root.relative_to(staged_dir).as_posix(), name
    raise ValueError(
        f"cannot detect a unique import root under {staged_dir}: "
        f"hint={normalized_hint!r} names={sorted(unique_names)}"
    )


_INTROSPECT_SCRIPT = '''"""Sandboxed module reflector for capability foraging."""

import importlib
import importlib.util
import inspect
import json
import os
import pkgutil
import re
import sys
import types

if not hasattr(os, "register_at_fork"):
    os.register_at_fork = lambda *args, **kwargs: None


def _fs_path(path):
    text = os.path.abspath(path)
    prefix = chr(92) * 2 + "?" + chr(92)
    unc = prefix + "UNC" + chr(92)
    if os.name != "nt" or text.startswith(prefix):
        return text
    if text.startswith(chr(92) * 2):
        return unc + text[2:]
    return prefix + text


def _norm_fs(path):
    text = os.path.abspath(os.path.realpath(path))
    prefix = chr(92) * 2 + "?" + chr(92)
    unc = prefix + "UNC" + chr(92)
    if text.startswith(unc):
        text = chr(92) * 2 + text[len(unc):]
    elif text.startswith(prefix):
        text = text[len(prefix):]
    return os.path.normcase(text)


root, import_name = sys.argv[1], sys.argv[2]
extras = []
if len(sys.argv) > 3:
    extra_arg = sys.argv[3]
    if extra_arg.endswith(".paths") and os.path.isfile(extra_arg):
        with open(extra_arg, encoding="utf-8") as handle:
            extras = [line.strip() for line in handle if line.strip()]
    else:
        extras = [item for item in sys.argv[3:] if item]
_STDLIB_SHADOW = {
    "typing",
    "enum34",
    "pathlib2",
    "configparser",
    "contextlib2",
    "funcsigs",
    "ipaddress",
    "futures",
    "functools32",
}
for extra in extras:
    parts = extra.replace(os.sep, "/").split("/")
    if any(part.lower() in _STDLIB_SHADOW for part in parts if part):
        continue
    sys.path.insert(0, extra)
sys.path.insert(0, root)
try:
    module = importlib.import_module(import_name)
except Exception as exc:  # noqa: BLE001 - reported, never raised through
    print(json.dumps({"ok": False, "error": f"import failed: {exc}"}))
    raise SystemExit(0)
if not hasattr(module, "__version__"):
    module_file = os.path.realpath(getattr(module, "__file__", "") or "")
    for extra in extras:
        extra_init = os.path.join(extra, *import_name.split("."), "__init__.py")
        try:
            if (not os.path.isfile(extra_init)) or os.path.realpath(extra_init) == module_file:
                continue
            extra_text = open(extra_init, encoding="utf-8").read()
        except Exception:
            continue
        version_match = re.search("^__version__ *= *(\\S+)", extra_text, re.M)
        if version_match:
            module.__version__ = version_match.group(1).strip().strip(chr(34) + chr(39))
            break

bootstrapped = False
try:
    conf = importlib.import_module(import_name + ".conf")
    settings = getattr(conf, "settings", None)
    if settings is not None and not getattr(settings, "configured", True):
        configure = getattr(settings, "configure", None)
        if callable(configure):
            configure()
            bootstrapped = True
except Exception:
    pass
if bootstrapped:
    try:
        setup = getattr(module, "setup", None)
        if callable(setup):
            setup()
    except Exception:
        pass

EMPTY = inspect.Parameter.empty
candidates = []
seen = set()


def _owner_ok(target):
    owner = getattr(target, "__module__", "") or ""
    func = getattr(target, "__func__", None)
    if func is not None:
        owner = getattr(func, "__module__", owner) or owner
    if not owner:
        return True
    return owner == import_name or owner.startswith(import_name + ".")


def _params_of(target, skip_self=False):
    try:
        signature = inspect.signature(target)
    except Exception:
        return None
    params = []
    for index, param in enumerate(signature.parameters.values()):
        if skip_self and index == 0 and param.name in {"self", "cls"}:
            continue
        annotation = ""
        if param.annotation is not EMPTY:
            raw = param.annotation
            annotation = getattr(raw, "__name__", str(raw)).strip("'\\"")
        params.append(
            {
                "name": param.name,
                "kind": param.kind.name,
                "required": param.default is EMPTY,
                "annotation": annotation,
            }
        )
    returns = ""
    if signature.return_annotation is not EMPTY:
        raw = signature.return_annotation
        returns = getattr(raw, "__name__", str(raw)).strip("'\\"")
    return params, returns


def _consider(name, target, flags, skip_self=False):
    try:
        return _consider_inner(name, target, flags, skip_self=skip_self)
    except Exception:
        return


def _consider_inner(name, target, flags, skip_self=False):
    leaf = str(name or "").split(".")[-1]
    if not leaf or leaf.startswith("_") or name in seen:
        return
    try:
        is_cls = inspect.isclass(target)
        is_callable = callable(target)
    except Exception:
        return
    if is_cls or not is_callable:
        return
    if not (
        inspect.isfunction(target)
        or inspect.ismethod(target)
        or inspect.isbuiltin(target)
        or any(flags.values())
    ):
        return
    if not _owner_ok(target):
        return
    packed = _params_of(target, skip_self=skip_self)
    if packed is None:
        return
    params, returns = packed
    doc = inspect.getdoc(target) or ""
    item = {
        "name": name,
        "params": params,
        "returns": returns,
        "doc": doc.splitlines()[0] if doc else "",
    }
    item.update(flags)
    seen.add(name)
    candidates.append(item)


def _construct_instance(cls):
    try:
        return cls(), False
    except Exception:
        pass
    try:
        return cls({}), True
    except Exception:
        pass
    try:
        return cls(""), True
    except Exception:
        return None, True


def _instance_method_names(cls, instance):
    names = set()
    for klass in inspect.getmro(cls):
        if klass is object:
            continue
        for name, value in klass.__dict__.items():
            if name.startswith("_") or isinstance(value, (staticmethod, classmethod, property)):
                continue
            if inspect.isfunction(value):
                names.add(name)
    if instance is not None:
        try:
            owned = getattr(instance, "__dict__", None) or {}
            items = list(owned.items())
        except Exception:
            items = []
        for name, value in items:
            if name.startswith("_") or inspect.isclass(value) or not callable(value):
                continue
            names.add(name)
    return names


def _static_method_names(cls):
    names = set()
    try:
        mro = inspect.getmro(cls)
    except Exception:
        return names
    for klass in mro:
        if klass is object:
            continue
        try:
            items = list(klass.__dict__.items())
        except Exception:
            continue
        for name, value in items:
            if name.startswith("_"):
                continue
            if isinstance(value, (staticmethod, classmethod)):
                names.add(name)
    return names


def _under_root(path):
    try:
        real = _norm_fs(path)
        base = _norm_fs(root)
        return real == base or real.startswith(base + os.sep)
    except Exception:
        return False


def _file_owned(target):
    paths = []
    try:
        filename = getattr(target, "__file__", None) or ""
        if filename:
            paths.append(filename)
    except Exception:
        pass
    try:
        paths.extend(getattr(target, "__path__", []) or [])
    except Exception:
        pass
    return any(_under_root(path) for path in paths)


def _module_ok(target):
    try:
        owner = getattr(target, "__name__", "") or ""
    except Exception:
        return False
    return (owner == import_name or owner.startswith(import_name + ".")) and _file_owned(target)


def _defined_on(target, prefix, allow_nested_owner=False):
    try:
        owner = getattr(target, "__module__", "") or ""
        func = getattr(target, "__func__", None)
        if func is not None:
            owner = getattr(func, "__module__", owner) or owner
    except Exception:
        return False
    expected = import_name if not prefix else import_name + "." + prefix
    if (not owner) or owner == expected:
        return True
    return bool(allow_nested_owner) and owner.startswith(expected + ".")


def _safe_dir(target):
    try:
        return sorted(dir(target))
    except Exception:
        return []


def _safe_getattr(target, name, default=None):
    try:
        return getattr(target, name, default)
    except Exception:
        return default


def _safe_is_function(target):
    try:
        return inspect.isfunction(target) or inspect.isbuiltin(target)
    except Exception:
        return False


def _safe_is_class(target):
    try:
        return inspect.isclass(target)
    except Exception:
        return False


def _safe_is_module(target):
    try:
        return inspect.ismodule(target)
    except Exception:
        return False


_CLASS_KIND_PREFIXES = (
    "python_class",
    "python_nested_namespace_class",
    "python_deep_nested_namespace_class",
    "python_triple_nested_namespace_class",
    "python_quadruple_nested_namespace_class",
    "python_quintuple_nested_namespace_class",
    "python_sextuple_nested_namespace_class",
    "python_septuple_nested_namespace_class",
    "python_octuple_nested_namespace_class",
    "python_nonuple_nested_namespace_class",
    "python_decuple_nested_namespace_class",
    "python_undecuple_nested_namespace_class",
    "python_duodecuple_nested_namespace_class",
    "python_tredecuple_nested_namespace_class",
    "python_quattuordecuple_nested_namespace_class",
    "python_quindecuple_nested_namespace_class",
    "python_sexdecuple_nested_namespace_class",
    "python_septendecuple_nested_namespace_class",
    "python_octodecuple_nested_namespace_class",
    "python_novemdecuple_nested_namespace_class",
    "python_vigintuple_nested_namespace_class",
    "python_unvigintuple_nested_namespace_class",
    "python_duovigintuple_nested_namespace_class",
    "python_trevigintuple_nested_namespace_class",
    "python_quattuorvigintuple_nested_namespace_class",
    "python_quinvigintuple_nested_namespace_class",
    "python_sexvigintuple_nested_namespace_class",
    "python_septemvigintuple_nested_namespace_class",
    "python_octovigintuple_nested_namespace_class",
    "python_novemvigintuple_nested_namespace_class",
    "python_trigintuple_nested_namespace_class",
    "python_untrigintuple_nested_namespace_class",
    "python_duotrigintuple_nested_namespace_class",
    "python_tretrigintuple_nested_namespace_class",
)


def _consider_class(prefix, target, depth=0):
    try:
        class_name = getattr(target, "__name__", "") or ""
    except Exception:
        class_name = ""
    if class_name.endswith(("AsyncClient", "AsyncIOClient")):
        return
    kind_keys = tuple(item + "_{kind}" for item in _CLASS_KIND_PREFIXES)
    try:
        static_flags = {key.format(kind="static"): (index == depth) for index, key in enumerate(kind_keys)}
        for attr in sorted(_static_method_names(target)):
            fn = _safe_getattr(target, attr, None)
            _consider(f"{prefix}.{attr}", fn, static_flags, skip_self=True)
        instance, requires_args = _construct_instance(target)
        if instance is None:
            return
        flags = {key.format(kind="instance"): (index == depth) for index, key in enumerate(kind_keys)}
        flags["constructor_requires_args"] = bool(requires_args)
        for attr in sorted(_instance_method_names(target, instance)):
            fn = _safe_getattr(instance, attr, None)
            _consider(f"{prefix}.{attr}", fn, flags, skip_self=False)
    except Exception:
        return


_SKIP_SHORT = {
    "test",
    "tests",
    "testing",
    "conftest",
    "transports",
    "pagers",
    "async_client",
    "types",
}
_VERSIONED_CHILD = re.compile(r"^v[0-9][0-9_]*$")


def _load_child(modname):
    try:
        return importlib.import_module(modname)
    except Exception:
        pass
    parent_name, _, short = modname.rpartition(".")
    parent = sys.modules.get(parent_name)
    bases = _owned_paths(parent) if parent is not None else []
    for base in bases:
        child_dir = os.path.join(base, short)
        child_py = child_dir + ".py"
        if os.path.isdir(_fs_path(child_dir)):
            ns = types.ModuleType(modname)
            ns.__path__ = [_fs_path(child_dir)]
            ns.__package__ = modname
            sys.modules[modname] = ns
            return ns
        if os.path.isfile(_fs_path(child_py)):
            spec = importlib.util.spec_from_file_location(modname, _fs_path(child_py))
            if spec is None or spec.loader is None:
                continue
            loaded = importlib.util.module_from_spec(spec)
            sys.modules[modname] = loaded
            try:
                spec.loader.exec_module(loaded)
            except Exception:
                sys.modules.pop(modname, None)
                continue
            return loaded
    return None


def _owned_paths(parent):
    owned = []
    try:
        paths = list(getattr(parent, "__path__", []) or [])
    except Exception:
        return owned
    for base in paths:
        try:
            if _under_root(base):
                owned.append(_fs_path(base))
        except Exception:
            continue
    return owned


def _keep_latest_versioned(names):
    versioned = [name for name in names if _VERSIONED_CHILD.match(name)]
    if len(versioned) < 2:
        return names
    latest = max(versioned, key=lambda name: tuple(int(part) for part in name[1:].split("_") if part.isdigit()))
    drop = set(versioned) - {latest}
    return [name for name in names if name not in drop]


def _limit_named_fanout(names, suffix="_service", keep=8):
    matching = [name for name in names if name.endswith(suffix)]
    if len(matching) <= keep:
        return names
    keep_set = set(matching[:keep])
    return [name for name in names if name not in matching or name in keep_set]


def _child_modules(parent, prefix):
    found = {}
    for name in _safe_dir(parent):
        if name.startswith("_") or name in _SKIP_SHORT:
            continue
        target = _safe_getattr(parent, name, None)
        if _safe_is_module(target) and _module_ok(target):
            found[name] = target
    parent_import = import_name if not prefix else import_name + "." + prefix
    owned = _owned_paths(parent)
    if owned:
        try:
            children = list(pkgutil.iter_modules(owned, parent_import + "."))
        except Exception:
            children = []
        for _finder, modname, _ispkg in children:
            short = modname.rsplit(".", 1)[-1]
            if short.startswith("_") or short in found or short in _SKIP_SHORT:
                continue
            loaded = _load_child(modname)
            if loaded is not None:
                found[short] = loaded
        for base in owned:
            try:
                entries = os.listdir(_fs_path(base))
            except OSError:
                continue
            for short in entries:
                if short.startswith("_") or short in _SKIP_SHORT:
                    continue
                if short.endswith(".py"):
                    name = short[:-3]
                    if name in found or not name.isidentifier():
                        continue
                    loaded = _load_child(parent_import + "." + name)
                    if loaded is not None:
                        found[name] = loaded
                    continue
                if short in found or not short.isidentifier():
                    continue
                child_path = os.path.join(base, short)
                if not os.path.isdir(_fs_path(child_path)):
                    continue
                loaded = _load_child(parent_import + "." + short)
                if loaded is not None:
                    found[short] = loaded
    kept = _limit_named_fanout(_keep_latest_versioned(sorted(found)))
    return {name: found[name] for name in kept}


submodules = {}
for name in _safe_dir(module):
    if name.startswith("_"):
        continue
    target = _safe_getattr(module, name, None)
    if _safe_is_function(target):
        _consider(name, target, {})
        continue
    if _safe_is_module(target) and _module_ok(target):
        submodules[name] = target
        continue
    if not _safe_is_class(target):
        continue
    _consider_class(name, target, depth=0)

try:
    module_has_path = hasattr(module, "__path__")
except Exception:
    module_has_path = False
if module_has_path:
    try:
        top_children = list(pkgutil.iter_modules(_owned_paths(module) or module.__path__, import_name + "."))
    except Exception:
        top_children = []
    for _finder, modname, _ispkg in top_children:
        short = modname.rsplit(".", 1)[-1]
        if short.startswith("_") or short in submodules or short in _SKIP_SHORT:
            continue
        loaded = _load_child(modname)
        if loaded is not None:
            submodules[short] = loaded
for name, target in _child_modules(module, "").items():
    if name not in submodules:
        submodules[name] = target

_FUNC_KEYS = (
    "python_nested_namespace_function",
    "python_deep_nested_namespace_function",
    "python_triple_nested_namespace_function",
    "python_quadruple_nested_namespace_function",
    "python_quintuple_nested_namespace_function",
    "python_sextuple_nested_namespace_function",
    "python_septuple_nested_namespace_function",
    "python_octuple_nested_namespace_function",
    "python_nonuple_nested_namespace_function",
    "python_decuple_nested_namespace_function",
    "python_undecuple_nested_namespace_function",
    "python_duodecuple_nested_namespace_function",
    "python_tredecuple_nested_namespace_function",
    "python_quattuordecuple_nested_namespace_function",
    "python_quindecuple_nested_namespace_function",
    "python_sexdecuple_nested_namespace_function",
    "python_septendecuple_nested_namespace_function",
    "python_octodecuple_nested_namespace_function",
    "python_novemdecuple_nested_namespace_function",
    "python_vigintuple_nested_namespace_function",
    "python_unvigintuple_nested_namespace_function",
    "python_duovigintuple_nested_namespace_function",
    "python_trevigintuple_nested_namespace_function",
    "python_quattuorvigintuple_nested_namespace_function",
    "python_quinvigintuple_nested_namespace_function",
    "python_sexvigintuple_nested_namespace_function",
    "python_septemvigintuple_nested_namespace_function",
    "python_octovigintuple_nested_namespace_function",
    "python_novemvigintuple_nested_namespace_function",
    "python_trigintuple_nested_namespace_function",
    "python_untrigintuple_nested_namespace_function",
    "python_duotrigintuple_nested_namespace_function",
    "python_tretrigintuple_nested_namespace_function",
)
level = submodules
max_depth = len(_CLASS_KIND_PREFIXES) - 1
for depth in range(1, max_depth + 1):
    nxt = {}
    func_flags = {key: (index == depth - 1) for index, key in enumerate(_FUNC_KEYS)}
    need_defined = depth >= 3
    allow_nested = depth >= 6
    for prefix, target in sorted(level.items()):
        for nested_name in _safe_dir(target):
            if nested_name.startswith("_"):
                continue
            nested_target = _safe_getattr(target, nested_name, None)
            if _safe_is_function(nested_target):
                if _defined_on(nested_target, prefix):
                    _consider(f"{prefix}.{nested_name}", nested_target, func_flags)
                continue
            if not _safe_is_class(nested_target):
                continue
            if need_defined and not _defined_on(
                nested_target, prefix, allow_nested_owner=allow_nested
            ):
                continue
            _consider_class(f"{prefix}.{nested_name}", nested_target, depth=depth)
        if depth < max_depth:
            for child_name, child in sorted(_child_modules(target, prefix).items()):
                nxt[f"{prefix}.{child_name}"] = child
    level = nxt

print(json.dumps({"ok": True, "candidates": candidates}))
'''


def introspect_module(
    staged_dir: Path,
    import_name: str,
    path_root: str,
    timeout: int = 300,
    extra_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Reflect one module's public functions in an isolated subprocess."""

    staged_dir = Path(staged_dir).resolve()
    extras = [
        str((staged_dir / item).resolve())
        for item in extra_paths
        if str(item).strip() and not _extra_shadows_stdlib(str(item))
    ]
    with tempfile.TemporaryDirectory(prefix="blackhole-forage-introspect-") as tmp:
        script = Path(tmp) / "introspect.py"
        script.write_text(_INTROSPECT_SCRIPT, encoding="utf-8")
        extras_file = Path(tmp) / "extra.paths"
        extras_file.write_text("\n".join(extras) + ("\n" if extras else ""), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                "-S",
                str(script),
                str((staged_dir / path_root).resolve()),
                import_name,
                str(extras_file),
            ],
            capture_output=True,
            text=True,
            cwd=str(staged_dir),
            timeout=timeout,
            check=False,
        )
    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        return {"ok": False, "error": f"introspection produced no JSON: {completed.stderr.strip()[-200:]}"}
    if not payload.get("ok"):
        return {"ok": False, "error": str(payload.get("error") or "introspection failed")}
    return {"ok": True, "candidates": payload.get("candidates") or []}


def _skip_node_dir(path: Path, root: Path) -> bool:
    return any(part in _NODE_SKIP_DIR_NAMES for part in path.relative_to(root).parts)


def _shallow_fs_files(
    staged_dir: Path,
    *,
    names: frozenset[str] = frozenset(),
    suffix: str = "",
    max_depth: int = 3,
) -> list[Path]:
    """Find files near the staging root without pathlib rglob (Windows MAX_PATH)."""

    found: list[Path] = []
    root_fs = os_fs_path(staged_dir)
    try:
        walker = os.walk(root_fs)
    except OSError:
        return found
    for dirpath, dirnames, filenames in walker:
        rel = os.path.relpath(dirpath, root_fs)
        depth = 0 if rel in {".", os.curdir} else rel.count(os.sep) + 1
        if depth >= max_depth:
            dirnames.clear()
        dirnames[:] = [name for name in dirnames if name not in _NODE_SKIP_DIR_NAMES]
        for filename in filenames:
            if filename in names or (suffix and filename.endswith(suffix)):
                path = Path(dirpath) / filename
                if os.path.isfile(os_fs_path(path)):
                    found.append(path)
    return found


def detect_package_runtime(staged_dir: Path, requested: str = "") -> str:
    """Detect ``python`` or ``node`` from the staged tree, honoring a pin."""

    pinned = str(requested or "").strip().lower()
    if pinned in RUNTIMES:
        return pinned
    package_json = _shallow_fs_files(staged_dir, names=frozenset({"package.json"}))
    mjs_files = _shallow_fs_files(staged_dir, suffix=".mjs")
    python_names: set[str] = set()
    for root in _candidate_roots(staged_dir):
        python_names |= _importable_names(root)
    if (package_json or mjs_files) and not python_names:
        return "node"
    if python_names and not package_json and not mjs_files:
        return "python"
    if package_json or mjs_files:
        return "node"
    return "python"


def _package_json_entry(data: Mapping[str, Any]) -> str:
    exports = data.get("exports")
    if isinstance(exports, str) and exports.strip():
        return exports.lstrip("./")
    if isinstance(exports, Mapping):
        for key in (".", "import", "default", "node"):
            value = exports.get(key)
            if isinstance(value, str) and value.strip():
                return value.lstrip("./")
            if isinstance(value, Mapping):
                for nested in ("import", "default", "node", "require"):
                    inner = value.get(nested)
                    if isinstance(inner, str) and inner.strip():
                        return inner.lstrip("./")
    for field in ("module", "main"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value.lstrip("./")
    return ""


def detect_node_entry(staged_dir: Path, hint: str = "") -> tuple[str, str]:
    """Detect ``(path_root, entry)`` for a Node package from ``package.json`` or index files."""

    normalized_hint = re.sub(r"[^a-z0-9]+", "-", hint.lower()).strip("-")
    discoveries: list[tuple[str, str]] = []
    for package_json in sorted(staged_dir.rglob("package.json")):
        if not package_json.is_file() or _skip_node_dir(package_json.parent, staged_dir):
            continue
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        relative_entry = _package_json_entry(payload)
        if not relative_entry:
            continue
        entry_path = (package_json.parent / relative_entry).resolve()
        try:
            entry_path.relative_to(staged_dir.resolve())
        except ValueError:
            continue
        if not entry_path.is_file():
            continue
        staged_entry = entry_path.relative_to(staged_dir).as_posix()
        package_name = re.sub(r"[^a-z0-9]+", "-", str(payload.get("name") or "").lower()).strip("-")
        if normalized_hint and package_name == normalized_hint:
            return ".", staged_entry
        discoveries.append((staged_entry, package_name))
    unique = {entry for entry, _ in discoveries}
    if len(unique) == 1:
        return ".", next(iter(unique))
    fallback: list[str] = []
    for name in _NODE_ENTRY_NAMES:
        matches = [
            path.relative_to(staged_dir).as_posix()
            for path in staged_dir.rglob(name)
            if path.is_file() and not _skip_node_dir(path.parent, staged_dir)
        ]
        if len(matches) == 1:
            fallback.append(matches[0])
    if len(set(fallback)) == 1:
        return ".", fallback[0]
    raise ValueError(
        f"cannot detect a unique node entry under {staged_dir}: "
        f"hint={normalized_hint!r} entries={sorted(unique)}"
    )


_NODE_INTROSPECT_SCRIPT = """\
import { pathToFileURL } from "node:url";
import path from "node:path";

const entry = process.argv[2];
const includeDefault = process.argv[3] !== "0";
function isIdent(name) {
  return typeof name === "string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(name);
}
function consider(name, target, flags, candidates, seen) {
  const parts = String(name || "").split(".");
  const leaf = parts[parts.length - 1];
  if (
    typeof target !== "function" ||
    !leaf ||
    leaf.startsWith("_") ||
    seen.has(name) ||
    parts.some((part) => !isIdent(part))
  ) {
    return;
  }
  const arity = Number(target.length) || 0;
  if (arity < 1 || arity > 2) {
    return;
  }
  const params = [];
  for (let index = 0; index < arity; index += 1) {
    params.push({
      name: `arg${index}`,
      kind: "POSITIONAL_OR_KEYWORD",
      required: true,
      annotation: "",
    });
  }
  seen.add(name);
  candidates.push({
    name,
    params,
    doc: "",
    default_export: Boolean(flags.defaultExport),
    default_export_object: Boolean(flags.defaultExportObject),
    default_export_class: Boolean(flags.defaultExportClass),
    default_export_class_static: Boolean(flags.defaultExportClassStatic),
    named_export_class_static: Boolean(flags.namedExportClassStatic),
    nested_namespace_class_static: Boolean(flags.nestedNamespaceClassStatic),
    named_export_class: Boolean(flags.namedExportClass),
    nested_namespace_class: Boolean(flags.nestedNamespaceClass),
    constructor_requires_args: Boolean(flags.constructorRequiresArgs),
  });
}
function objectKeys(value) {
  const names = new Set([
    ...Object.keys(value || {}),
    ...Object.getOwnPropertyNames(value || {}),
  ]);
  names.delete("default");
  names.delete("__esModule");
  names.delete("constructor");
  names.delete("prototype");
  names.delete("length");
  names.delete("name");
  names.delete("arguments");
  names.delete("caller");
  return [...names].filter(isIdent).sort();
}
function constructInstance(ctor) {
  if (typeof ctor !== "function") {
    return { ok: false, instance: null, requiresArgs: false };
  }
  try {
    return { ok: true, instance: new ctor(), requiresArgs: false };
  } catch {
    /* constructor rejected zero arguments */
  }
  try {
    return { ok: true, instance: new ctor({}), requiresArgs: true };
  } catch {
    /* constructor rejected empty options */
  }
  try {
    return { ok: true, instance: new ctor(""), requiresArgs: true };
  } catch {
    return { ok: false, instance: null, requiresArgs: true };
  }
}
function considerClassStatics(prefix, ctor, flags, candidates, seen) {
  if (typeof ctor !== "function" || !isIdent(prefix.split(".").pop() || "")) {
    return;
  }
  for (const name of objectKeys(ctor)) {
    consider(`${prefix}.${name}`, ctor[name], flags, candidates, seen);
  }
}
function considerClassInstance(prefix, ctor, flags, candidates, seen) {
  if (typeof ctor !== "function") {
    return;
  }
  const built = constructInstance(ctor);
  const names = new Set(ctor.prototype ? objectKeys(ctor.prototype) : []);
  if (built.instance) {
    for (const name of objectKeys(built.instance)) {
      names.add(name);
    }
  }
  const nextFlags = {
    ...flags,
    constructorRequiresArgs: Boolean(built.ok && built.requiresArgs),
  };
  for (const name of [...names].sort()) {
    const fn =
      (built.instance && typeof built.instance[name] === "function" && built.instance[name]) ||
      (ctor.prototype && ctor.prototype[name]);
    consider(`${prefix}.${name}`, fn, nextFlags, candidates, seen);
  }
}
function considerNestedClassStatics(prefix, namespace, flags, candidates, seen) {
  if (!namespace || typeof namespace !== "object" || Array.isArray(namespace)) {
    return;
  }
  for (const name of objectKeys(namespace)) {
    const nested = namespace[name];
    if (typeof nested !== "function") {
      continue;
    }
    const nestedPrefix = prefix ? `${prefix}.${name}` : name;
    considerClassStatics(nestedPrefix, nested, flags, candidates, seen);
  }
}
function considerNestedClassInstance(prefix, namespace, flags, candidates, seen) {
  if (!namespace || typeof namespace !== "object" || Array.isArray(namespace)) {
    return;
  }
  for (const name of objectKeys(namespace)) {
    const nested = namespace[name];
    if (typeof nested !== "function") {
      continue;
    }
    const nestedPrefix = prefix ? `${prefix}.${name}` : name;
    considerClassInstance(nestedPrefix, nested, flags, candidates, seen);
  }
}
try {
  const mod = await import(pathToFileURL(path.resolve(entry)).href);
  const candidates = [];
  const seen = new Set();
  const def = mod.default;
  if (includeDefault && typeof def === "function") {
    const inferred =
      typeof def.name === "string" && /^[A-Za-z][A-Za-z0-9]{2,}$/.test(def.name)
        ? def.name
        : "default";
    consider(inferred, def, { defaultExport: true }, candidates, seen);
    for (const name of objectKeys(def)) {
      consider(name, def[name], { defaultExport: true, defaultExportClassStatic: true }, candidates, seen);
    }
    const built = constructInstance(def);
    const instanceNames = new Set(def.prototype ? objectKeys(def.prototype) : []);
    if (built.instance) {
      for (const name of objectKeys(built.instance)) {
        instanceNames.add(name);
      }
    }
    for (const name of [...instanceNames].sort()) {
      const fn =
        (built.instance && typeof built.instance[name] === "function" && built.instance[name]) ||
        (def.prototype && def.prototype[name]);
      consider(name, fn, {
        defaultExport: true,
        defaultExportClass: true,
        constructorRequiresArgs: Boolean(built.ok && built.requiresArgs),
      }, candidates, seen);
    }
  }
  if (includeDefault && def && typeof def === "object" && !Array.isArray(def)) {
    for (const name of objectKeys(def)) {
      consider(name, def[name], { defaultExport: true, defaultExportObject: true }, candidates, seen);
    }
  }
  const namedKeys = Object.keys(mod).filter((name) => name !== "default" && isIdent(name)).sort();
  for (const name of namedKeys) {
    consider(name, mod[name], {}, candidates, seen);
    if (typeof mod[name] === "function") {
      considerClassStatics(name, mod[name], { namedExportClassStatic: true }, candidates, seen);
      considerClassInstance(name, mod[name], { namedExportClass: true }, candidates, seen);
    } else {
      considerNestedClassStatics(name, mod[name], { nestedNamespaceClassStatic: true }, candidates, seen);
      considerNestedClassInstance(name, mod[name], { nestedNamespaceClass: true }, candidates, seen);
    }
  }
  if (includeDefault && def && typeof def === "object" && !Array.isArray(def)) {
    considerNestedClassStatics("", def, { defaultExport: true, nestedNamespaceClassStatic: true }, candidates, seen);
  }
  process.stdout.write(JSON.stringify({ ok: true, candidates }));
} catch (err) {
  process.stdout.write(JSON.stringify({ ok: false, error: `import failed: ${err}` }));
}
"""


def _ensure_node_modules(staged_dir: Path) -> None:
    """Copy vendored ``.forage-deps`` packages into ``node_modules`` for ESM resolution."""

    deps = staged_dir / FORAGE_DEPS_DIR
    if not deps.is_dir():
        return
    nm_dir = staged_dir / "node_modules"
    for child in deps.iterdir():
        if not child.is_dir():
            continue
        dest = nm_dir / child.name
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(child, dest)


def introspect_node_module(
    staged_dir: Path,
    entry: str,
    timeout: int = 60,
    *,
    include_default: bool = True,
) -> dict[str, Any]:
    """Reflect one Node module's exported functions in a subprocess."""

    entry_path = staged_dir / entry
    if not entry_path.is_file():
        return {"ok": False, "error": f"node entry module not present: {entry}"}
    _ensure_node_modules(staged_dir)
    with tempfile.TemporaryDirectory(prefix="blackhole-forage-node-introspect-") as tmp:
        script = Path(tmp) / "introspect.mjs"
        script.write_text(_NODE_INTROSPECT_SCRIPT, encoding="utf-8")
        completed = subprocess.run(
            ["node", str(script), str(entry_path.resolve()), "1" if include_default else "0"],
            capture_output=True,
            text=True,
            cwd=staged_dir,
            timeout=timeout,
            check=False,
        )
    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        stderr = (completed.stderr or "").strip()[-200:]
        return {"ok": False, "error": f"introspection produced no JSON: {stderr}"}
    if not payload.get("ok"):
        return {"ok": False, "error": str(payload.get("error") or "introspection failed")}
    return {"ok": True, "candidates": payload.get("candidates") or []}


# ---------------------------------------------------------------------------
# Candidate filtering and probe derivation.
# ---------------------------------------------------------------------------


def _return_root(annotation: str) -> str:
    raw = str(annotation or "").strip().strip("'\"")
    if not raw:
        return ""
    raw = raw.replace("typing.", "").replace("collections.abc.", "")
    base = re.split(r"[\[,]", raw, maxsplit=1)[0].strip()
    return base.rsplit(".", 1)[-1].lower()


def _json_scalar_return(candidate: Mapping[str, Any]) -> bool | None:
    """True when annotated as a JSON scalar, False when a container, else unknown."""

    root = _return_root(str(candidate.get("returns") or ""))
    if not root:
        return None
    if root in {"str", "int", "float", "bool"}:
        return True
    if root in _NON_SCALAR_RETURN_ROOTS:
        return False
    return None


def _required_params(candidate: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """Return the required positional params, or ``None`` when unfit."""

    if _json_scalar_return(candidate) is False:
        return None
    params = candidate.get("params") or []
    required = [
        param
        for param in params
        if param.get("required") and param.get("kind") in {"POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"}
    ]
    for param in params:
        if param.get("required") and param.get("kind") == "KEYWORD_ONLY":
            return None
    if any(param.get("annotation") not in _SCALAR_ANNOTATIONS for param in required):
        return None
    if 1 <= len(required) <= 2:
        return required
    if len(required) == 0 and candidate.get("python_quintuple_nested_namespace_class_static"):
        return required
    return None


def _derive_probes(requires: Sequence[str], domain: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Probe inputs keyed by the derived ``requires`` names, never raw params."""

    samples = list(domain["selection"]) + list(domain["held_out"])
    return [{key: samples[index] for key in requires} for index in range(len(samples))]


def _probe_tree(staged_dir: Path, spec: AcquisitionSpec) -> None:
    (staged_dir / adapter_name_for(spec.runtime)).write_text(
        synthesize_adapter_source(spec), encoding="utf-8"
    )


def _snake_key(value: str) -> str:
    key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return key if key and key[0].isalpha() else "output"


def _provides_key(callable_name: str, requires: Sequence[str]) -> str:
    base = f"{_snake_key(callable_name)}_output"[:64].rstrip("_")
    if not _STATE_KEY_PATTERN.match(base):
        base = "foraged_output"
    occupied = set(requires)
    while base in occupied:
        base = f"{base}_value"[:64].rstrip("_")
    return base


# ---------------------------------------------------------------------------
# Runtime dependency closing: import-unclosed sdists become introspectable.
# ---------------------------------------------------------------------------


def _pep_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()


def _extra_shadows_stdlib(extra: str) -> bool:
    parts = str(extra or "").replace("\\", "/").split("/")
    return any(_pep_name(part) in _STDLIB_SHADOW_REQUIREMENT_NAMES for part in parts if part)


def _requirement_name(line: str) -> str | None:
    raw = str(line or "").strip()
    if not raw or raw.startswith(("#", "-", "[")):
        return None
    lowered = raw.lower()
    if lowered.startswith("requires-dist:"):
        raw = raw.split(":", 1)[1].strip()
        lowered = raw.lower()
    if "extra ==" in lowered.replace('"', "'"):
        return None
    raw = raw.split(";", 1)[0].strip().split("[", 1)[0].strip()
    match = _REQUIREMENT_NAME.match(raw)
    if not match:
        return None
    name = match.group(1)
    pep = _pep_name(name)
    if not name or name[0].isdigit() or pep in _DEV_REQUIREMENT_NAMES or pep in _STDLIB_SHADOW_REQUIREMENT_NAMES:
        return None
    return name


def _add_requirement_names(names: list[str], seen: set[str], candidates: Sequence[str | None]) -> None:
    for candidate in candidates:
        if not candidate:
            continue
        pep = _pep_name(candidate)
        if not pep or pep in seen:
            continue
        seen.add(pep)
        names.append(candidate)


def _parse_requires_txt(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        _add_requirement_names(names, seen, [_requirement_name(stripped)])
    return names


def _parse_requires_dist(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if line.lower().startswith("requires-dist:"):
            _add_requirement_names(names, seen, [_requirement_name(line)])
    return names


def _parse_setup_cfg_requires(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    in_options = False
    in_install = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_options = stripped.lower() == "[options]"
            in_install = False
            continue
        if in_options and stripped.lower().startswith("install_requires"):
            _, _, rest = stripped.partition("=")
            in_install = True
            _add_requirement_names(names, seen, [_requirement_name(rest)])
            continue
        if in_install:
            if not stripped:
                in_install = False
                continue
            if re.match(r"^[A-Za-z_][\w-]*\s*=", stripped):
                in_install = False
                continue
            _add_requirement_names(names, seen, [_requirement_name(stripped)])
    return names


def _parse_pyproject_dependencies(text: str) -> list[str]:
    match = re.search(r"(?ms)^\[project\].*?^dependencies\s*=\s*\[(.*?)\]", text)
    if not match:
        return []
    names: list[str] = []
    seen: set[str] = set()
    _add_requirement_names(names, seen, [_requirement_name(item) for item in _QUOTED_REQUIREMENT.findall(match.group(1))])
    return names


def _parse_setup_py_requires(text: str) -> list[str]:
    match = _INSTALL_REQUIRES_ASSIGN.search(text)
    if not match:
        return []
    names: list[str] = []
    seen: set[str] = set()
    _add_requirement_names(names, seen, [_requirement_name(item) for item in _QUOTED_REQUIREMENT.findall(match.group(1))])
    return names


def _skip_require_dir(name: str) -> bool:
    lowered = str(name or "").lower()
    return (
        name == FORAGE_DEPS_DIR
        or str(name or "").startswith(".")
        or lowered in _SKIP_REQUIRE_DIRS
        or lowered.startswith("test")
    )


def parse_runtime_requires(staged_dir: Path) -> list[str]:
    """Declared install_requires / Requires-Dist, extras skipped."""

    names: list[str] = []
    seen: set[str] = set()
    if not staged_dir.is_dir():
        return names
    for root, dirs, files in os.walk(staged_dir, topdown=True, onerror=lambda _exc: None):
        try:
            rel_root = Path(root).relative_to(staged_dir)
        except ValueError:
            dirs[:] = []
            continue
        depth = 0 if rel_root == Path(".") else len(rel_root.parts)
        dirs[:] = [
            name
            for name in dirs
            if not _skip_require_dir(name)
            and (
                name.endswith((".dist-info", ".egg-info"))
                and depth + 1 <= 3
                or depth + 1 <= 2
            )
        ]
        if depth > 3:
            continue
        found_meta = False
        for filename in files:
            path = Path(root) / filename
            relative = path.relative_to(staged_dir)
            if any(
                part == FORAGE_DEPS_DIR
                or part.startswith(".")
                or part.lower() in _SKIP_REQUIRE_DIRS
                for part in relative.parts
            ):
                continue
            if len(relative.parts) > 3:
                continue
            label = path.name.lower()
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parsed: list[str] = []
            if label == "requires.txt":
                parsed = _parse_requires_txt(text)
            elif label in {"pkg-info", "metadata"}:
                parsed = _parse_requires_dist(text)
            elif label == "setup.cfg":
                parsed = _parse_setup_cfg_requires(text)
            elif label == "pyproject.toml":
                parsed = _parse_pyproject_dependencies(text)
            elif label == "setup.py":
                parsed = _parse_setup_py_requires(text)
            if parsed:
                found_meta = True
            _add_requirement_names(names, seen, parsed)
        if found_meta:
            dirs[:] = []
    return names


def parse_node_runtime_requires(staged_dir: Path) -> list[str]:
    """Declared package.json dependencies, skipping dev/optional extras."""

    names: list[str] = []
    seen: set[str] = set()
    if not staged_dir.is_dir():
        return names
    for path in staged_dir.rglob("package.json"):
        if not path.is_file() or _skip_node_dir(path.parent, staged_dir):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        deps = payload.get("dependencies")
        if not isinstance(deps, Mapping):
            continue
        for raw in deps:
            name = str(raw or "").strip()
            if not name or name.startswith(("node:", ".", "/")):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
    return names


def _archive_matches_project(path: Path, prefix: str) -> bool:
    """True when ``prefix-1.2.3.ext`` is that project, not ``prefix-other-1.2``."""

    name = path.name
    if not name.lower().startswith(prefix.lower() + "-"):
        return False
    rest = name[len(prefix) + 1 :]
    return bool(rest) and rest[0].isdigit()


def _cached_pypi_archive(name: str, dest: Path) -> Path | None:
    prefixes = dict.fromkeys((name, name.replace("_", "-"), name.replace("-", "_")))
    matches: list[Path] = []
    for prefix in prefixes:
        matches.extend(dest.glob(f"{prefix}-*.tar.gz"))
        matches.extend(dest.glob(f"{prefix}-*.zip"))
    files = [path for path in matches if path.is_file() and any(_archive_matches_project(path, prefix) for prefix in prefixes)]
    if not files:
        return None
    files.sort(key=lambda path: path.name)
    return files[-1]


def _cached_pypi_wheel(name: str, dest: Path) -> Path | None:
    prefixes = dict.fromkeys((name, name.replace("_", "-"), name.replace("-", "_")))
    matches: list[Path] = []
    for prefix in prefixes:
        matches.extend(dest.glob(f"{prefix}-*.whl"))
    files = [
        path
        for path in matches
        if path.is_file()
        and _wheel_compatible(path.name)
        and any(_archive_matches_project(path, prefix) for prefix in prefixes)
    ]
    if not files:
        return None
    files.sort(key=lambda path: path.name)
    return files[-1]


def _wheel_compatible(filename: str) -> bool:
    """True when a wheel filename can import on this interpreter."""

    name = filename.lower()
    if not name.endswith(".whl"):
        return False
    impl = f"cp{sys.version_info.major}{sys.version_info.minor}"
    plat = sysconfig.get_platform().replace("-", "_").replace(".", "_").lower()
    if "py3-none-any" in name or "py2.py3-none-any" in name:
        return True
    if plat not in name.replace("-", "_"):
        return False
    if impl in name:
        return True
    if "abi3" not in name:
        return False
    match = re.search(r"cp(\d)(\d+)", name)
    if not match:
        return False
    minimum = (int(match.group(1)), int(match.group(2)))
    return (sys.version_info.major, sys.version_info.minor) >= minimum


def _cached_npm_archive(name: str, dest: Path) -> Path | None:
    basename = name.rsplit("/", 1)[-1]
    files = [path for path in dest.glob(f"{basename}-*.tgz") if path.is_file()]
    if not files:
        return None
    files.sort(key=lambda path: path.name)
    return files[-1]


def _flatten_npm_stage(root: Path) -> None:
    children = [path for path in root.iterdir()]
    if len(children) != 1 or not children[0].is_dir() or children[0].name != "package":
        return
    inner = children[0]
    for item in list(inner.iterdir()):
        dest = root / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))
    shutil.rmtree(inner, ignore_errors=True)


def _archive_version(archive: Path) -> str:
    filename = archive.name
    for suffix in (".tar.gz", ".tgz", ".zip"):
        if filename.endswith(suffix):
            filename = filename[: -len(suffix)]
            break
    return filename.rsplit("-", 1)[-1] if "-" in filename else ""


def _extracted_cache_dir(pep: str, version: str, archive: Path) -> Path:
    """Short extract dir: never embed a ``.whl`` filename (Windows MAX_PATH)."""

    token = re.sub(r"[^a-z0-9._-]+", "-", str(version or archive.stem).lower()).strip("-")
    if not token or token.endswith(".whl") or ".whl" in token:
        token = re.sub(r"[^a-z0-9._-]+", "-", archive.stem.lower()).strip("-")
        token = token.replace(".whl", "").strip("-._")
    return EXTRACT_CACHE_DIR / pep / (token[:40] or "pkg")


def _detach_dep_dest(path: Path) -> None:
    """Remove a staged dep dest without walking a junction into the extract cache."""

    if not os.path.lexists(str(path)):
        return
    if os.path.islink(str(path)):
        path.unlink()
        return
    if path.is_dir():
        try:
            os.rmdir(path)
            return
        except OSError:
            shutil.rmtree(os_fs_path(path), ignore_errors=True)
            return
    path.unlink(missing_ok=True)


def _link_extracted_dep(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _detach_dep_dest(dest)
    src_abs = os.path.abspath(os.fspath(src))
    dest_abs = os.path.abspath(os.fspath(dest))
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", dest_abs, src_abs],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode == 0 and os.path.lexists(dest_abs):
            return
    try:
        os.symlink(src_abs, dest_abs, target_is_directory=True)
        return
    except OSError:
        pass
    shutil.copytree(
        os_fs_path(src),
        os_fs_path(dest),
        ignore=shutil.ignore_patterns(*sorted(_STAGE_SKIP_PARTS)),
    )


def _close_python_runtime_dependencies(
    staged_dir: Path,
    *,
    dest_dir: Path | None = None,
    max_depth: int = 3,
) -> dict[str, Any]:
    download_dir = dest_dir or DEFAULT_DOWNLOAD_DIR
    extra_paths: list[str] = []
    closed: list[dict[str, Any]] = []
    pending = [(name, 0) for name in parse_runtime_requires(staged_dir)]
    seen: set[str] = set()
    errors: list[str] = []
    while pending:
        name, depth = pending.pop(0)
        pep = _pep_name(name)
        if not pep or pep in seen or depth > max(0, int(max_depth)):
            continue
        if pep in _STDLIB_SHADOW_REQUIREMENT_NAMES:
            seen.add(pep)
            continue
        seen.add(pep)
        archive: Path | None = None
        version = ""
        cache_hit = False
        wheel = _cached_pypi_wheel(name, download_dir)
        if wheel is not None:
            archive = wheel
            version = _archive_version(wheel)
            cache_hit = True
        else:
            fetched_wheel = fetch_pypi_wheel(name, dest_dir=download_dir)
            if fetched_wheel.get("ok"):
                archive = Path(str(fetched_wheel["path"]))
                version = str(fetched_wheel.get("version") or "")
        if archive is None:
            cached = _cached_pypi_archive(name, download_dir)
            if cached is not None:
                archive = cached
                version = _archive_version(cached)
                cache_hit = True
            else:
                fetched = fetch_pypi_sdist(name, None, dest_dir=download_dir)
                if fetched.get("ok"):
                    archive = Path(str(fetched["path"]))
                    version = str(fetched.get("version") or "")
                else:
                    errors.append(str(fetched.get("error") or f"fetch failed: {name}"))
                    continue
        dep_root = staged_dir / FORAGE_DEPS_DIR / pep
        cache_root = _extracted_cache_dir(pep, version, archive)
        try:
            if not cache_root.exists():
                cache_root.parent.mkdir(parents=True, exist_ok=True)
                stage_acquisition_source(archive, cache_root)
            _link_extracted_dep(cache_root, dep_root)
        except (ValueError, OSError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        path_root: str | None
        try:
            path_root, _import_name = detect_import_root(dep_root, hint=name)
        except ValueError:
            # Metadata-only metapackages still declare Requires-Dist; recurse
            # so the importable child (apache-airflow-core, etc.) is vendored.
            path_root = None
        if path_root is not None:
            relative = Path(FORAGE_DEPS_DIR) / pep / path_root
            extra = relative.as_posix() if path_root != "." else (Path(FORAGE_DEPS_DIR) / pep).as_posix()
            if pep not in _STDLIB_SHADOW_REQUIREMENT_NAMES and not _extra_shadows_stdlib(extra):
                extra_paths.append(extra)
            closed.append(
                {
                    "name": pep,
                    "requested": name,
                    "version": version,
                    "path_root": extra,
                    "cache_hit": cache_hit,
                }
            )
        if depth < max(0, int(max_depth)):
            pending.extend((child, depth + 1) for child in parse_runtime_requires(dep_root))
    return {
        "ok": not errors,
        "error": "; ".join(errors),
        "requires": [item["name"] for item in closed],
        "closed": closed,
        "extra_paths": extra_paths,
    }


def _close_node_runtime_dependencies(
    staged_dir: Path,
    *,
    dest_dir: Path | None = None,
    max_depth: int = 3,
) -> dict[str, Any]:
    download_dir = dest_dir or DEFAULT_DOWNLOAD_DIR
    extra_paths: list[str] = []
    closed: list[dict[str, Any]] = []
    pending = [(name, 0) for name in parse_node_runtime_requires(staged_dir)]
    seen: set[str] = set()
    errors: list[str] = []
    while pending:
        name, depth = pending.pop(0)
        key = name.strip().lower()
        if not key or key in seen or depth > max(0, int(max_depth)):
            continue
        seen.add(key)
        cached = _cached_npm_archive(name, download_dir)
        archive: Path | None = cached
        version = ""
        cache_hit = cached is not None
        if archive is None:
            fetched = fetch_npm_tarball(name, None, dest_dir=download_dir)
            if not fetched.get("ok"):
                errors.append(str(fetched.get("error") or f"fetch failed: {name}"))
                continue
            archive = Path(str(fetched["path"]))
            version = str(fetched.get("version") or "")
        else:
            version = _archive_version(archive)
        relative = Path(FORAGE_DEPS_DIR, *name.split("/"))
        dep_root = staged_dir / relative
        if dep_root.exists():
            shutil.rmtree(dep_root)
        dep_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            stage_acquisition_source(archive, dep_root)
            _flatten_npm_stage(dep_root)
        except (ValueError, OSError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        extra = relative.as_posix()
        extra_paths.append(extra)
        closed.append(
            {
                "name": key,
                "requested": name,
                "version": version,
                "path_root": extra,
                "cache_hit": cache_hit,
            }
        )
        if depth < max(0, int(max_depth)):
            pending.extend((child, depth + 1) for child in parse_node_runtime_requires(dep_root))
    return {
        "ok": not errors,
        "error": "; ".join(errors),
        "requires": [item["name"] for item in closed],
        "closed": closed,
        "extra_paths": extra_paths,
    }


def close_runtime_dependencies(
    staged_dir: Path,
    *,
    dest_dir: Path | None = None,
    max_depth: int = 3,
    runtime: str = "",
) -> dict[str, Any]:
    """Fetch and vendor declared runtime deps next to an import-unclosed package."""

    detected = str(runtime or "").strip().lower()
    if detected not in RUNTIMES:
        detected = detect_package_runtime(staged_dir)
    if detected == "node":
        return _close_node_runtime_dependencies(
            staged_dir, dest_dir=dest_dir, max_depth=max_depth
        )
    return _close_python_runtime_dependencies(
        staged_dir, dest_dir=dest_dir, max_depth=max_depth
    )


# ---------------------------------------------------------------------------
# Spec inference: the full AcquisitionSpec from introspection alone.
# ---------------------------------------------------------------------------


def _is_class_static_candidate(item: Mapping[str, Any]) -> bool:
    return bool(
        item.get("default_export_class_static")
        or item.get("named_export_class_static")
        or item.get("nested_namespace_class_static")
        or any(item.get(f"{prefix}_static") for prefix in PYTHON_NESTED_CLASS_DEPTH_PREFIXES)
    )


def _is_named_class_instance_candidate(item: Mapping[str, Any]) -> bool:
    return bool(item.get("named_export_class") or item.get("nested_namespace_class"))


def _is_class_method_candidate(item: Mapping[str, Any]) -> bool:
    return (
        bool(item.get("default_export_class"))
        or _is_named_class_instance_candidate(item)
        or _is_class_static_candidate(item)
        or any(item.get(f"{prefix}_instance") for prefix in PYTHON_NESTED_CLASS_DEPTH_PREFIXES)
    )


def _bundle_slug(base: str, callable_name: str) -> str:
    suffix = re.sub(r"[^a-z0-9]+", "-", _snake_key(callable_name)).strip("-")
    slug = f"{base}-{suffix}" if suffix and suffix != base else f"{base}-bundle"
    # ``capability.absorbed-`` is 22 chars; ids must stay within 64.
    return slugify_capability_id(slug, limit=42)


def infer_acquisition_spec(
    *,
    slug: str,
    name: str,
    source: Path,
    staging_root: Path,
    hint: str = "",
    version: str = "",
    origin: Mapping[str, Any] | None = None,
    runtime: str = "",
    bundle: bool | None = None,
    max_bundle: int = 3,
    close_deps: bool = True,
    include_default: bool = True,
) -> dict[str, Any]:
    """Infer complete ``AcquisitionSpec`` values for one uncooperative package.

    Every spec field — runtime, import root or Node entry, entry callable,
    state keys, and probe inputs — is machine-derived. Each winner must pass
    every selection probe of one sample domain and then the held-out probe
    the selector never used. Additional winners become a multi-callable
    bundle. Any total failure refuses the inference honestly.
    """

    source_path = Path(source)
    source_stamp = ""
    source_resolved = str(source_path)
    if source_path.exists():
        source_stat = source_path.stat()
        source_resolved = str(source_path.resolve())
        source_stamp = f"{source_stat.st_mtime_ns}:{source_stat.st_size}"
    cache_key = (
        slug,
        name,
        source_resolved,
        source_stamp,
        hint,
        version,
        runtime,
        bundle,
        int(max_bundle),
        bool(close_deps),
        bool(include_default),
    )
    cached = _INFER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    staged_dir = staging_root / "pkg"
    if staged_dir.exists():
        shutil.rmtree(os_fs_path(staged_dir), ignore_errors=True)
    try:
        stage_acquisition_source(source, staged_dir)
    except (ValueError, OSError) as exc:
        return {"ok": False, "stage": "stage", "slug": slug, "error": str(exc)}
    detected_runtime = detect_package_runtime(staged_dir, runtime)
    collect_bundle = detected_runtime == "node" if bundle is None else bool(bundle)
    winner_limit = max(1, int(max_bundle)) if collect_bundle else 1
    entry = ""
    import_name = ""
    path_root = "."
    extra_paths: tuple[str, ...] = ()
    closed_deps: dict[str, Any] = {"ok": True, "closed": [], "extra_paths": []}
    if close_deps:
        closed_deps = close_runtime_dependencies(staged_dir, runtime=detected_runtime)
        extra_paths = tuple(str(item) for item in closed_deps.get("extra_paths") or [])
    if detected_runtime == "node":
        try:
            path_root, entry = detect_node_entry(staged_dir, hint)
        except ValueError as exc:
            return {"ok": False, "stage": "detect", "slug": slug, "error": str(exc)}
        introspection = introspect_node_module(
            staged_dir, entry, include_default=include_default
        )
    else:
        try:
            path_root, import_name = detect_import_root(staged_dir, hint)
        except ValueError as exc:
            return {"ok": False, "stage": "detect", "slug": slug, "error": str(exc)}
        introspection = introspect_module(
            staged_dir, import_name, path_root, extra_paths=extra_paths
        )
    if not introspection["ok"]:
        return {"ok": False, "stage": "introspect", "slug": slug, "error": introspection["error"]}

    rejected: dict[str, str] = {}
    ordered = sorted(
        introspection["candidates"],
        key=lambda item: (
            *_prefer_deeper_nested_class(item, "static", start=4),
            0
            if item.get("default_export_class_static")
            or item.get("named_export_class_static")
            or item.get("nested_namespace_class_static")
            or item.get("python_class_static")
            else 1,
            0 if item.get("python_triple_nested_namespace_class_static") else 1,
            0 if item.get("python_nested_namespace_class_static") else 1,
            *_prefer_deeper_nested_class(item, "instance", start=5),
            0 if _is_named_class_instance_candidate(item) else 1,
            0 if item.get("python_class_instance") else 1,
            0 if item.get("python_nested_namespace_class_instance") else 1,
            0 if item.get("python_deep_nested_namespace_class_instance") else 1,
            0 if item.get("python_deep_nested_namespace_class_static") else 1,
            0
            if item.get("python_deep_nested_namespace_function")
            else 1
            if item.get("python_nested_namespace_function")
            else 2,
            0
            if 1
            <= len([p for p in item.get("params") or [] if p.get("required")])
            <= 2
            else 1,
            0 if _json_scalar_return(item) else 1,
            len([p for p in item.get("params") or [] if p.get("required")]),
            str(item.get("name")),
        ),
    )
    collected: list[dict[str, Any]] = []
    for candidate in ordered:
        candidate_name = str(candidate.get("name"))
        required = _required_params(candidate)
        if required is None:
            rejected[candidate_name] = "signature is not a 1-2 arg JSON-scalar callable"
            continue
        requires = tuple(_snake_key(str(param["name"])) for param in required)
        if required:
            annotations = [str(param.get("annotation") or "") for param in required]
            domains = probe_domains_for(annotations[0])
            if len(set(annotations)) > 1 or any(probe_domains_for(a) != domains for a in annotations):
                rejected[candidate_name] = "mixed-arity probe domains are not derivable"
                continue
        else:
            domains = _NULLARY_DOMAINS
        winner: dict[str, Any] | None = None
        for domain in domains:
            probes = _derive_probes(requires, domain)
            spec_slug = slug if not collected else _bundle_slug(slug, candidate_name)
            spec = AcquisitionSpec(
                slug=spec_slug,
                name=name if not collected else f"{name} ({candidate_name})",
                source=source,
                import_name=import_name,
                callable_name=candidate_name,
                requires=requires,
                provides=_provides_key(candidate_name, requires),
                path_root=path_root,
                version=version,
                origin=origin or {},
                probes=tuple(probes),
                runtime=detected_runtime,
                entry=entry,
                extra_paths=extra_paths,
            )
            _probe_tree(staged_dir, spec)
            selection_results = [
                _run_probe(staged_dir, spec, probe) for probe in probes[: len(domain["selection"])]
            ]
            if not all(result["ok"] for result in selection_results):
                failed_probe = next(result for result in selection_results if not result.get("ok"))
                rejected[candidate_name] = (
                    f"selection probe failed in domain {domain['domain']!r}: "
                    f"{failed_probe.get('error') or 'unknown error'}"
                )
                continue
            held_out = _run_probe(staged_dir, spec, probes[-1])
            if not held_out["ok"]:
                rejected[candidate_name] = (
                    f"held-out probe failed in domain {domain['domain']!r}: {held_out['error']}"
                )
                break
            if _is_class_method_candidate(candidate):
                fragments = [result.get("fragment") or {} for result in selection_results]
                fragments.append(held_out.get("fragment") or {})
                values = [frag.get(spec.provides) for frag in fragments]
                if any(not isinstance(value, (str, int, float, bool)) for value in values):
                    rejected[candidate_name] = "class method did not return a JSON scalar"
                    continue
                with tempfile.TemporaryDirectory(prefix="blackhole-forage-cwd-") as alt:
                    shifted = _run_probe(staged_dir, spec, probes[-1], cwd=Path(alt))
                if shifted.get("ok") and (shifted.get("fragment") or {}) != (
                    held_out.get("fragment") or {}
                ):
                    rejected[candidate_name] = (
                        "class method did not return a cwd-independent JSON scalar"
                    )
                    continue
            winner = {
                "spec": spec.validate(),
                "domain": str(domain["domain"]),
                "default_export": bool(candidate.get("default_export")),
                "default_export_object": bool(candidate.get("default_export_object")),
                "default_export_class": bool(candidate.get("default_export_class")),
                "default_export_class_static": bool(candidate.get("default_export_class_static")),
                "named_export_class_static": bool(candidate.get("named_export_class_static")),
                "nested_namespace_class_static": bool(candidate.get("nested_namespace_class_static")),
                "named_export_class": bool(candidate.get("named_export_class")),
                "nested_namespace_class": bool(candidate.get("nested_namespace_class")),
                "constructor_requires_args": bool(candidate.get("constructor_requires_args")),
                **python_nested_depth_flags(candidate),
            }
            break
        if winner is not None:
            collected.append(winner)
            if len(collected) >= winner_limit:
                break
            continue
        rejected.setdefault(candidate_name, "no sample domain satisfied every selection probe")
    if not collected:
        failed = {
            "ok": False,
            "stage": "select",
            "slug": slug,
            "error": "no viable candidate generalized to a held-out probe",
            "rejected": rejected,
        }
        _INFER_CACHE[cache_key] = failed
        return failed
    primary = collected[0]["spec"]
    record = {
        "runtime": detected_runtime,
        "import_name": import_name,
        "path_root": path_root,
        "entry": entry,
        "winner": primary.callable_name,
        "domain": collected[0]["domain"],
        "requires": list(primary.requires),
        "provides": primary.provides,
        "probe_count": len(primary.probes),
        "bundle": [item["spec"].callable_name for item in collected],
        "rejected": rejected,
        "runtime_deps": list(closed_deps.get("closed") or []),
        "extra_paths": list(extra_paths),
        "default_export": bool(collected[0].get("default_export")),
        "default_export_object": bool(collected[0].get("default_export_object")),
        "default_export_class": bool(collected[0].get("default_export_class")),
        "default_export_class_static": bool(collected[0].get("default_export_class_static")),
        "named_export_class_static": bool(collected[0].get("named_export_class_static")),
        "nested_namespace_class_static": bool(collected[0].get("nested_namespace_class_static")),
        "named_export_class": bool(collected[0].get("named_export_class")),
        "nested_namespace_class": bool(collected[0].get("nested_namespace_class")),
        "constructor_requires_args": bool(collected[0].get("constructor_requires_args")),
        **python_nested_depth_flags(collected[0]),
    }
    inferred = {
        "ok": True,
        "slug": slug,
        "spec": primary,
        "bundle_specs": [item["spec"] for item in collected[1:]],
        "record": record,
    }
    _INFER_CACHE[cache_key] = inferred
    return inferred


# ---------------------------------------------------------------------------
# Live lane: fetch from the PyPI JSON API with sha256 verification.
# ---------------------------------------------------------------------------


def fetch_pypi_sdist(
    name: str,
    version: str | None = None,
    dest_dir: Path = DEFAULT_DOWNLOAD_DIR,
    timeout: int = 60,
) -> dict[str, Any]:
    """Download one package sdist from PyPI and verify its sha256."""

    api = f"https://pypi.org/pypi/{name}/json" if not version else f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(api, timeout=timeout) as response:
            meta = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "stage": "fetch", "name": name, "error": f"pypi metadata failed: {exc}"}
    resolved = str(meta.get("info", {}).get("version") or "")
    sdist = next((item for item in meta.get("urls") or [] if item.get("packagetype") == "sdist"), None)
    if sdist is None:
        return {"ok": False, "stage": "fetch", "name": name, "error": "registry release ships no sdist"}
    url = str(sdist["url"])
    expected_sha256 = str((sdist.get("digests") or {}).get("sha256") or "")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(url.split("?")[0]).name
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = response.read()
    except OSError as exc:
        return {"ok": False, "stage": "fetch", "name": name, "error": f"sdist download failed: {exc}"}
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and actual_sha256 != expected_sha256:
        return {
            "ok": False,
            "stage": "fetch",
            "name": name,
            "error": f"sha256 mismatch: expected {expected_sha256}, got {actual_sha256}",
        }
    dest.write_bytes(payload)
    return {
        "ok": True,
        "name": name,
        "version": resolved,
        "path": str(dest),
        "sha256": actual_sha256,
        "url": url,
    }


def fetch_pypi_wheel(
    name: str,
    version: str | None = None,
    dest_dir: Path = DEFAULT_DOWNLOAD_DIR,
    timeout: int = 60,
) -> dict[str, Any]:
    """Download one importable wheel for this interpreter from PyPI."""

    api = f"https://pypi.org/pypi/{name}/json" if not version else f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(api, timeout=timeout) as response:
            meta = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "stage": "fetch", "name": name, "error": f"pypi metadata failed: {exc}"}
    resolved = str(meta.get("info", {}).get("version") or "")
    wheels = [
        item
        for item in meta.get("urls") or []
        if item.get("packagetype") == "bdist_wheel"
        and _wheel_compatible(str(Path(str(item.get("url") or "")).name))
    ]
    wheels.sort(
        key=lambda item: (
            0 if "none-any" in str(item.get("filename") or item.get("url") or "").lower() else 1,
            str(item.get("filename") or ""),
        )
    )
    if not wheels:
        return {"ok": False, "stage": "fetch", "name": name, "error": "registry release ships no compatible wheel"}
    chosen = wheels[0]
    url = str(chosen["url"])
    expected_sha256 = str((chosen.get("digests") or {}).get("sha256") or "")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(url.split("?")[0]).name
    if dest.is_file() and dest.stat().st_size > 0:
        return {
            "ok": True,
            "name": name,
            "version": resolved,
            "path": str(dest),
            "sha256": expected_sha256,
            "url": url,
            "cache_hit": True,
        }
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = response.read()
    except OSError as exc:
        return {"ok": False, "stage": "fetch", "name": name, "error": f"wheel download failed: {exc}"}
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and actual_sha256 != expected_sha256:
        return {
            "ok": False,
            "stage": "fetch",
            "name": name,
            "error": f"sha256 mismatch: expected {expected_sha256}, got {actual_sha256}",
        }
    dest.write_bytes(payload)
    return {
        "ok": True,
        "name": name,
        "version": resolved,
        "path": str(dest),
        "sha256": actual_sha256,
        "url": url,
    }


def fetch_npm_tarball(
    name: str,
    version: str | None = None,
    dest_dir: Path = DEFAULT_DOWNLOAD_DIR,
    timeout: int = 60,
) -> dict[str, Any]:
    """Download one package tarball from npm and verify its sha1 when published."""

    encoded = quote(name, safe="@")
    api = (
        f"https://registry.npmjs.org/{encoded}/{version}"
        if version
        else f"https://registry.npmjs.org/{encoded}/latest"
    )
    try:
        with urllib.request.urlopen(api, timeout=timeout) as response:
            meta = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "stage": "fetch", "name": name, "error": f"npm metadata failed: {exc}"}
    resolved = str(meta.get("version") or "")
    dist = meta.get("dist") if isinstance(meta.get("dist"), Mapping) else {}
    url = str(dist.get("tarball") or "")
    expected_shasum = str(dist.get("shasum") or "")
    if not url:
        return {"ok": False, "stage": "fetch", "name": name, "error": "registry release ships no tarball"}
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(url.split("?")[0]).name
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = response.read()
    except OSError as exc:
        return {"ok": False, "stage": "fetch", "name": name, "error": f"tarball download failed: {exc}"}
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_shasum:
        actual_shasum = hashlib.sha1(payload).hexdigest()
        if actual_shasum != expected_shasum:
            return {
                "ok": False,
                "stage": "fetch",
                "name": name,
                "error": f"shasum mismatch: expected {expected_shasum}, got {actual_shasum}",
            }
    dest.write_bytes(payload)
    return {
        "ok": True,
        "name": name,
        "version": resolved,
        "path": str(dest),
        "sha256": actual_sha256,
        "shasum": expected_shasum,
        "url": url,
    }


# ---------------------------------------------------------------------------
# Foraging: fetch (optional), infer, acquire, seal.
# ---------------------------------------------------------------------------


def forage_package(
    request: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Forage one package into proved ledger capabilities, zero human spec."""

    name = str(request["name"])
    slug = str(request.get("slug") or slugify_capability_id(name))
    fetch_record: dict[str, Any] | None = None
    source = request.get("source")
    version = str(request.get("version") or "")
    origin: dict[str, Any] = dict(request.get("origin") or {})
    runtime = str(request.get("runtime") or "")
    registry = str(request.get("registry") or "").strip().lower()

    if registry == "pypi":
        fetch_record = fetch_pypi_sdist(name, version or None)
        if not fetch_record["ok"]:
            return {"ok": False, "slug": slug, "stage": "fetch", "error": fetch_record["error"]}
        source = fetch_record["path"]
        version = fetch_record["version"]
        origin = {
            "kind": "pypi-live",
            "registry": "pypi",
            "name": name,
            "version": version,
            "sha256": fetch_record["sha256"],
            "url": fetch_record["url"],
        }
    elif registry == "npm":
        fetch_record = fetch_npm_tarball(name, version or None)
        if not fetch_record["ok"]:
            return {"ok": False, "slug": slug, "stage": "fetch", "error": fetch_record["error"]}
        source = fetch_record["path"]
        version = fetch_record["version"]
        runtime = runtime or "node"
        origin = {
            "kind": "npm-live",
            "registry": "npm",
            "name": name,
            "version": version,
            "sha256": fetch_record["sha256"],
            "url": fetch_record["url"],
        }
    if source is None or not Path(str(source)).exists():
        return {"ok": False, "slug": slug, "stage": "fetch", "error": f"forage source missing: {source}"}

    with tempfile.TemporaryDirectory(prefix="bh-fg-", ignore_cleanup_errors=True) as tmp:
        inference = infer_acquisition_spec(
            slug=slug,
            name=name,
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or name),
            version=version,
            origin=origin,
            runtime=runtime,
            bundle=request.get("bundle"),
        )
    if not inference["ok"]:
        return {
            "ok": False,
            "slug": slug,
            "stage": inference.get("stage"),
            "error": inference.get("error"),
            "inference": {key: value for key, value in inference.items() if key not in {"ok", "spec", "bundle_specs"}},
        }
    specs = [inference["spec"], *list(inference.get("bundle_specs") or [])]
    acquisitions: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        already = prove_absorbed_capability(spec.slug)
        if already.get("ok"):
            acquisition = {
                "ok": True,
                "stage": "proved",
                "slug": spec.slug,
                "capability_id": capability_id_for_slug(spec.slug),
                "derived_case_count": 0,
                "proof_exit_code": 0,
            }
        else:
            try:
                acquisition = acquire_capability(
                    spec,
                    repo_root=repo_root,
                    output_dir=output_dir,
                    scenario=index == 0,
                )
            except (ValueError, OSError) as exc:
                acquisition = {
                    "ok": False,
                    "stage": "acquire",
                    "error": str(exc),
                    "capability_id": "",
                }
        acquisitions.append(
            {
                "ok": bool(acquisition.get("ok")),
                "slug": spec.slug,
                "callable": spec.callable_name,
                "capability_id": acquisition.get("capability_id"),
                "stage": acquisition.get("stage"),
                "derived_case_count": acquisition.get("derived_case_count"),
                "proof_exit_code": acquisition.get("proof_exit_code"),
                "error": acquisition.get("error"),
            }
        )
        if acquisition.get("ok"):
            continue
        if index == 0:
            return {
                "ok": False,
                "slug": slug,
                "stage": acquisition.get("stage"),
                "error": acquisition.get("error") or f"acquisition failed at {acquisition.get('stage')}",
                "inference": inference["record"],
                "bundle": acquisitions,
            }
    primary = acquisitions[0]
    result: dict[str, Any] = {
        "ok": True,
        "slug": slug,
        "stage": primary.get("stage"),
        "capability_id": primary.get("capability_id"),
        "runtime": inference["record"].get("runtime"),
        "inference": inference["record"],
        "acquisition": {
            key: primary.get(key)
            for key in ("ok", "stage", "derived_case_count", "proof_exit_code")
        },
        "bundle": acquisitions,
    }
    if fetch_record is not None:
        result["fetch"] = {
            key: fetch_record[key]
            for key in ("version", "sha256", "url")
            if key in fetch_record
        }
    return result


def hermetic_forage_requests() -> list[dict[str, Any]]:
    """The offline forage targets exercised by the sealed plane and proof."""

    return [
        {
            "name": "forage-lab (uncooperative fixture package)",
            "slug": "forage-lab",
            "hint": "forage_lab",
            "source": FIXTURE_FORAGE_PACKAGE,
            "origin": {"kind": "fixture", "source": "tests/fixtures/external_packages/forage-lab"},
        },
        {
            "name": "tomli TOML parser (stewardship sdist, inferred spec)",
            "slug": "tomli-foraged",
            "hint": "tomli",
            "source": STEWARDSHIP_ROOT / "tomli-2.4.1" / "tomli-2.4.1.tar.gz",
            "version": "2.4.1",
            "origin": {"kind": "pypi-sdist", "source": "stewardship/tomli-2.4.1/tomli-2.4.1.tar.gz"},
        },
        {
            "name": "Python-Markdown renderer (stewardship sdist, inferred spec)",
            "slug": "markdown-foraged",
            "hint": "markdown",
            "source": STEWARDSHIP_ROOT / "markdown-3.10.3" / "markdown-3.10.3.tar.gz",
            "version": "3.10.3",
            "origin": {
                "kind": "pypi-sdist",
                "source": "stewardship/markdown-3.10.3/markdown-3.10.3.tar.gz",
            },
        },
        {
            "name": "forage-js (uncooperative node fixture package)",
            "slug": "forage-js",
            "hint": "forage-js",
            "runtime": "node",
            "source": FIXTURE_NODE_FORAGE_PACKAGE,
            "origin": {"kind": "fixture", "source": "tests/fixtures/external_packages/forage-js"},
        },
    ]


# ---------------------------------------------------------------------------
# Foraging plane: sealed, verifiable demonstration over the live ledger.
# ---------------------------------------------------------------------------


def _report_digest(report: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}})


def run_foraging_plane(
    output_dir: Path | None = None,
    *,
    live: bool = False,
    live_targets: Sequence[str] = _DEFAULT_LIVE_TARGETS,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Forage every hermetic target (plus live registry targets) and seal it."""

    requests = hermetic_forage_requests()
    if live:
        requests = requests + [
            {"registry": "pypi", "name": target, "slug": slugify_capability_id(target), "hint": target}
            for target in live_targets
        ]
    forages: dict[str, Any] = {}
    for request in requests:
        forages[str(request.get("slug") or slugify_capability_id(str(request["name"])))] = (
            forage_package(request, repo_root=repo_root)
        )
    grade = {
        "forage_count": len(forages),
        "forages_ok": sum(1 for item in forages.values() if item.get("ok")),
        "ok": bool(forages) and all(item.get("ok") for item in forages.values()),
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_foraging_plane",
        "generated_at": utc_now_iso(),
        "live": bool(live),
        "slugs": sorted(forages),
        "forages": forages,
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)

    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": grade["ok"],
        "report_dir": str(target_dir),
        "slugs": sorted(forages),
        "grade": grade,
    }


def verify_foraging_plane(report_dir: Path) -> dict[str, Any]:
    """Re-grade a sealed foraging report; re-prove every foraged capability."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")

    forages = report.get("forages") or {}
    expected_grade = {
        "forage_count": len(forages),
        "forages_ok": sum(1 for item in forages.values() if item.get("ok")),
        "ok": bool(forages) and all(item.get("ok") for item in forages.values()),
    }
    grade_ok = expected_grade == report.get("grade")

    live_proofs = {slug: prove_absorbed_capability(slug) for slug in report.get("slugs") or []}
    live_ok = bool(live_proofs) and all(proof.get("ok") for proof in live_proofs.values())

    ok = digest_ok and grade_ok and live_ok
    return {"ok": ok, "digest_ok": digest_ok, "grade_ok": grade_ok, "live_ok": live_ok}


def builtin_foraging_plane_proof() -> dict[str, Any]:
    """Registered proof: hermetic falsification plus the live sealed plane.

    Hermetic half: inference on the Python fixture recovers a complete spec
    whose winner is ``shout`` while the selection-only decoy ``brittle`` is
    rejected by the held-out probe; the empty fixture is refused before any
    ledger write. Node half: the forage-js fixture is detected as ``node``,
    ``shout`` wins, ``whisper`` joins the multi-callable bundle, and the
    held-out decoy plus the empty Node package are refused. Live half: the
    sealed plane runs all hermetic targets end-to-end and verifies, and a
    hand-tampered report fails verification.
    """

    with tempfile.TemporaryDirectory(prefix="blackhole-foraging-proof-") as tmp:
        root = Path(tmp)
        inference = infer_acquisition_spec(
            slug="forage-lab",
            name="forage-lab (uncooperative fixture package)",
            source=FIXTURE_FORAGE_PACKAGE,
            staging_root=root / "infer",
            hint="forage_lab",
            bundle=True,
        )
        inference_ok = bool(inference["ok"])
        winner_is_shout = inference_ok and inference["record"]["winner"] == "shout"
        brittle_rejected = inference_ok and "held-out probe failed" in inference["record"][
            "rejected"
        ].get("brittle", "")
        python_bundle_has_whisper = inference_ok and "whisper" in inference["record"].get("bundle", [])

        refusal = infer_acquisition_spec(
            slug="forage-empty",
            name="forage-empty (no viable candidate fixture)",
            source=FIXTURE_EMPTY_PACKAGE,
            staging_root=root / "refuse",
            hint="forage_empty",
        )
        empty_refused = (not refusal["ok"]) and refusal.get("stage") == "select"

        node_inference = infer_acquisition_spec(
            slug="forage-js",
            name="forage-js (uncooperative node fixture package)",
            source=FIXTURE_NODE_FORAGE_PACKAGE,
            staging_root=root / "node-infer",
            hint="forage-js",
            runtime="node",
        )
        node_ok = bool(node_inference["ok"])
        node_runtime = node_ok and node_inference["record"].get("runtime") == "node"
        node_winner_is_shout = node_ok and node_inference["record"]["winner"] == "shout"
        node_bundle_has_whisper = node_ok and "whisper" in node_inference["record"].get("bundle", [])
        node_brittle_rejected = node_ok and "held-out probe failed" in node_inference["record"][
            "rejected"
        ].get("brittle", "")

        node_refusal = infer_acquisition_spec(
            slug="forage-js-empty",
            name="forage-js-empty (no viable node candidate fixture)",
            source=FIXTURE_NODE_EMPTY_PACKAGE,
            staging_root=root / "node-refuse",
            hint="forage-js-empty",
            runtime="node",
        )
        node_empty_refused = (not node_refusal["ok"]) and node_refusal.get("stage") == "select"

        report_dir = root / "report"
        plane = run_foraging_plane(report_dir)
        verification = verify_foraging_plane(report_dir) if plane.get("ok") else {"ok": False}
        node_forage = {}
        if plane.get("ok"):
            sealed = json.loads((report_dir / "plane-report.json").read_text(encoding="utf-8"))
            node_forage = dict((sealed.get("forages") or {}).get("forage-js") or {})
        node_forage_ok = bool(node_forage.get("ok")) and node_forage.get("runtime") == "node"
        node_bundle_acquired = node_forage_ok and any(
            item.get("callable") == "whisper" and item.get("ok")
            for item in node_forage.get("bundle") or []
        )

        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["forages_ok"] = 0
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_foraging_plane(report_dir)["ok"]

    verdicts = {
        "inference_ok": inference_ok,
        "winner_is_shout": winner_is_shout,
        "brittle_rejected": brittle_rejected,
        "python_bundle_has_whisper": python_bundle_has_whisper,
        "empty_refused": empty_refused,
        "node_ok": node_ok,
        "node_runtime": node_runtime,
        "node_winner_is_shout": node_winner_is_shout,
        "node_bundle_has_whisper": node_bundle_has_whisper,
        "node_brittle_rejected": node_brittle_rejected,
        "node_empty_refused": node_empty_refused,
        "node_forage_ok": node_forage_ok,
        "node_bundle_acquired": node_bundle_acquired,
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "slugs": plane.get("slugs") or [],
        "action": "foraging_plane",
        "used_skill_route_discovery": False,
    }


def foraging_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_foraging import '
        "builtin_foraging_plane_proof; r=builtin_foraging_plane_proof(); "
        "assert r['ok'] and r.get('action')=='foraging_plane' "
        "and r.get('inference_ok') and r.get('winner_is_shout') "
        "and r.get('brittle_rejected') and r.get('python_bundle_has_whisper') "
        "and r.get('empty_refused') and r.get('node_ok') and r.get('node_runtime') "
        "and r.get('node_winner_is_shout') and r.get('node_bundle_has_whisper') "
        "and r.get('node_brittle_rejected') and r.get('node_empty_refused') "
        "and r.get('node_forage_ok') and r.get('node_bundle_acquired') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_foraging_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the foraging plane in the live ledger."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.application-plane",
            "capability.absorption-plane",
            "capability.acquisition-plane",
            "capability.ablation-proof",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.foraging-plane",
        name="Capability foraging plane",
        description=(
            "Zero-spec autonomous acquisition across Python and Node: a request names "
            "only a package (local source or live PyPI/npm registry entry); runtime, "
            "import root or Node entry, callables, state keys, and probe inputs are "
            "all machine-derived by sandboxed introspection and a fixed, "
            "task-independent probe vocabulary with split-honest held-out "
            "generalization. Every held-out-honest callable is acquired (primary leaf "
            "plus a bounded multi-callable bundle). Packages with no viable candidate "
            "are refused before any ledger write."
        ),
        kind="python",
        entry="blackhole_agent.capability_foraging:demo_foraging_plane",
        proof_command=foraging_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_absorption.py",
            "tests/fixtures/external_packages/forage-lab/",
            "tests/fixtures/external_packages/forage-empty/",
            "tests/fixtures/external_packages/forage-js/",
            "tests/fixtures/external_packages/forage-js-empty/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Uncooperative packages are foraged from a bare name on Python and Node: "
            "runtime and entry are detected from the staged tree, callables are "
            "selected by sandboxed introspection with held-out generalization, every "
            "honest winner is absorbed as a bounded multi-callable bundle, and the "
            "live lane fetches a PyPI sdist or npm tarball through the identical "
            "inference path."
        ),
        tags=("foraging", "plane", "node", "bundle"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    save_ledger(ledger_path, ledger)
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_foraging_plane() -> dict[str, Any]:
    """Entry surface: run the hermetic plane and summarize the foraged capabilities."""

    result = run_foraging_plane()
    return {
        "ok": bool(result["ok"]),
        "foraged": result["slugs"],
        "foraged_count": len(result["slugs"]),
    }


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability foraging plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    plane_parser = sub.add_parser("plane", help="forage every hermetic target (optionally live)")
    plane_parser.add_argument("--live", action="store_true", help="also forage live PyPI targets")
    plane_parser.add_argument("--target", action="append", default=None, help="live PyPI package name")

    sub.add_parser("proof", help="run the registered foraging-plane proof")
    sub.add_parser("register", help="register and prove the plane in the live ledger")

    forage_parser = sub.add_parser("forage", help="forage one live registry package end-to-end")
    source = forage_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pypi", help="PyPI package name")
    source.add_argument("--npm", help="npm package name")
    forage_parser.add_argument("--version", default=None, help="pinned version")

    verify_parser = sub.add_parser("verify", help="verify a sealed foraging report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    args = parser.parse_args(argv)
    if args.command_name == "plane":
        targets = tuple(args.target) if args.target else _DEFAULT_LIVE_TARGETS
        result = run_foraging_plane(live=args.live, live_targets=targets)
    elif args.command_name == "proof":
        result = builtin_foraging_plane_proof()
    elif args.command_name == "register":
        result = register_foraging_plane_capability()
    elif args.command_name == "forage":
        if args.npm:
            result = forage_package(
                {
                    "registry": "npm",
                    "name": args.npm,
                    "version": args.version or "",
                    "hint": args.npm,
                    "runtime": "node",
                }
            )
        else:
            result = forage_package(
                {
                    "registry": "pypi",
                    "name": args.pypi,
                    "version": args.version or "",
                    "hint": args.pypi,
                }
            )
    else:
        result = verify_foraging_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
