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
  exported functions, including a Node default export when that is the
  only callable — filtered to JSON-scalar signatures, and ordered
  deterministically;
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
  bundle, each flowing through the acquisition plane unchanged;
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
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from blackhole_agent.capability_absorption import (
    _STATE_KEY_PATTERN,
    _digest,
    prove_absorbed_capability,
)
from blackhole_agent.capability_acquisition import (
    STEWARDSHIP_ROOT,
    AcquisitionSpec,
    RUNTIMES,
    _run_probe,
    acquire_capability,
    adapter_name_for,
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

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-foraging"
DEFAULT_DOWNLOAD_DIR = DEFAULT_ARTIFACT_DIR / "downloads"
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
_REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_INSTALL_REQUIRES_ASSIGN = re.compile(r"install_requires\s*=\s*\[(.*?)\]", re.DOTALL)
_QUOTED_REQUIREMENT = re.compile(r"""['"]([^'"]+)['"]""")

_SKIP_MODULE_NAMES = frozenset({"setup", "conftest", "test", "tests", "__init__"})
_SCALAR_ANNOTATIONS = frozenset({"", "str", "int", "float", "bool"})
_DEFAULT_LIVE_TARGETS = ("inflection",)


# ---------------------------------------------------------------------------
# Fixed, task-independent probe vocabulary. No expected outputs anywhere.
# ---------------------------------------------------------------------------

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


def _importable_names(root: Path) -> set[str]:
    names = {
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "__init__.py").is_file()
    }
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
import inspect
import json
import sys

root, import_name = sys.argv[1], sys.argv[2]
for extra in sys.argv[3:]:
    sys.path.insert(0, extra)
sys.path.insert(0, root)
try:
    module = importlib.import_module(import_name)
except Exception as exc:  # noqa: BLE001 - reported, never raised through
    print(json.dumps({"ok": False, "error": f"import failed: {exc}"}))
    raise SystemExit(0)

candidates = []
for name in sorted(dir(module)):
    if name.startswith("_"):
        continue
    target = getattr(module, name, None)
    if not (inspect.isfunction(target) or inspect.isbuiltin(target)):
        continue
    owner = getattr(target, "__module__", "") or ""
    if owner != import_name and not owner.startswith(import_name + "."):
        continue
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        continue
    params = []
    for param in signature.parameters.values():
        annotation = ""
        if param.annotation is not inspect.Parameter.empty:
            raw = param.annotation
            annotation = getattr(raw, "__name__", str(raw)).strip("'\\"")
        params.append(
            {
                "name": param.name,
                "kind": param.kind.name,
                "required": param.default is inspect.Parameter.empty,
                "annotation": annotation,
            }
        )
    doc = inspect.getdoc(target) or ""
    candidates.append({"name": name, "params": params, "doc": doc.splitlines()[0] if doc else ""})
print(json.dumps({"ok": True, "candidates": candidates}))
'''


def introspect_module(
    staged_dir: Path,
    import_name: str,
    path_root: str,
    timeout: int = 60,
    extra_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Reflect one module's public functions in an isolated subprocess."""

    extras = [str(staged_dir / item) for item in extra_paths if str(item).strip()]
    with tempfile.TemporaryDirectory(prefix="blackhole-forage-introspect-") as tmp:
        script = Path(tmp) / "introspect.py"
        script.write_text(_INTROSPECT_SCRIPT, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "-S", str(script), str(staged_dir / path_root), import_name, *extras],
            capture_output=True,
            text=True,
            cwd=staged_dir,
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


def detect_package_runtime(staged_dir: Path, requested: str = "") -> str:
    """Detect ``python`` or ``node`` from the staged tree, honoring a pin."""

    pinned = str(requested or "").strip().lower()
    if pinned in RUNTIMES:
        return pinned
    package_json = [
        path
        for path in staged_dir.rglob("package.json")
        if path.is_file() and not _skip_node_dir(path.parent, staged_dir)
    ]
    mjs_files = [
        path
        for path in staged_dir.rglob("*.mjs")
        if path.is_file() and not _skip_node_dir(path.parent, staged_dir)
    ]
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
function consider(name, target, isDefault, candidates, seen) {
  if (typeof target !== "function" || !name || name.startsWith("_") || seen.has(name)) {
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
  candidates.push({ name, params, doc: "", default_export: Boolean(isDefault) });
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
    consider(inferred, def, true, candidates, seen);
  }
  for (const name of Object.keys(mod).sort()) {
    if (name === "default") {
      continue;
    }
    consider(name, mod[name], false, candidates, seen);
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


def _required_params(candidate: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """Return the required positional params, or ``None`` when unfit."""

    params = candidate.get("params") or []
    required = [
        param
        for param in params
        if param.get("required") and param.get("kind") in {"POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"}
    ]
    if not 1 <= len(required) <= 2:
        return None
    for param in params:
        if param.get("required") and param.get("kind") == "KEYWORD_ONLY":
            return None
    if any(param.get("annotation") not in _SCALAR_ANNOTATIONS for param in required):
        return None
    return required


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
    base = f"{_snake_key(callable_name)}_output"
    if not _STATE_KEY_PATTERN.match(base):
        base = "foraged_output"
    while base in set(requires):
        base = f"{base}_value"
    return base[:64]


# ---------------------------------------------------------------------------
# Runtime dependency closing: import-unclosed sdists become introspectable.
# ---------------------------------------------------------------------------


def _pep_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()


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
    if _pep_name(name) in _DEV_REQUIREMENT_NAMES:
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


def parse_runtime_requires(staged_dir: Path) -> list[str]:
    """Declared install_requires / Requires-Dist, extras skipped."""

    names: list[str] = []
    seen: set[str] = set()
    if not staged_dir.is_dir():
        return names
    for path in staged_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(staged_dir)
        if any(part == FORAGE_DEPS_DIR or part.startswith(".") for part in relative.parts):
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
        _add_requirement_names(names, seen, parsed)
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


def _cached_pypi_archive(name: str, dest: Path) -> Path | None:
    prefixes = dict.fromkeys((name, name.replace("_", "-"), name.replace("-", "_")))
    matches: list[Path] = []
    for prefix in prefixes:
        matches.extend(dest.glob(f"{prefix}-*.tar.gz"))
        matches.extend(dest.glob(f"{prefix}-*.tgz"))
    files = [path for path in matches if path.is_file()]
    if not files:
        return None
    files.sort(key=lambda path: path.name)
    return files[-1]


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
        seen.add(pep)
        cached = _cached_pypi_archive(name, download_dir)
        archive: Path | None = cached
        version = ""
        cache_hit = cached is not None
        if archive is None:
            fetched = fetch_pypi_sdist(name, None, dest_dir=download_dir)
            if not fetched.get("ok"):
                errors.append(str(fetched.get("error") or f"fetch failed: {name}"))
                continue
            archive = Path(str(fetched["path"]))
            version = str(fetched.get("version") or "")
        else:
            version = _archive_version(archive)
        dep_root = staged_dir / FORAGE_DEPS_DIR / pep
        if dep_root.exists():
            shutil.rmtree(dep_root)
        try:
            stage_acquisition_source(archive, dep_root)
            path_root, _import_name = detect_import_root(dep_root, hint=name)
        except (ValueError, OSError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        relative = Path(FORAGE_DEPS_DIR) / pep / path_root
        extra = relative.as_posix() if path_root != "." else (Path(FORAGE_DEPS_DIR) / pep).as_posix()
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


def _bundle_slug(base: str, callable_name: str) -> str:
    suffix = re.sub(r"[^a-z0-9]+", "-", _snake_key(callable_name)).strip("-")
    slug = f"{base}-{suffix}" if suffix and suffix != base else f"{base}-bundle"
    return slugify_capability_id(slug)


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

    staged_dir = staging_root / slug
    if staged_dir.exists():
        shutil.rmtree(staged_dir)
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
        annotations = [str(param.get("annotation") or "") for param in required]
        domains = probe_domains_for(annotations[0])
        if len(set(annotations)) > 1 or any(probe_domains_for(a) != domains for a in annotations):
            rejected[candidate_name] = "mixed-arity probe domains are not derivable"
            continue
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
                continue
            held_out = _run_probe(staged_dir, spec, probes[-1])
            if not held_out["ok"]:
                rejected[candidate_name] = (
                    f"held-out probe failed in domain {domain['domain']!r}: {held_out['error']}"
                )
                break
            winner = {
                "spec": spec.validate(),
                "domain": str(domain["domain"]),
                "default_export": bool(candidate.get("default_export")),
            }
            break
        if winner is not None:
            collected.append(winner)
            if len(collected) >= winner_limit:
                break
            continue
        rejected.setdefault(candidate_name, "no sample domain satisfied every selection probe")
    if not collected:
        return {
            "ok": False,
            "stage": "select",
            "slug": slug,
            "error": "no viable candidate generalized to a held-out probe",
            "rejected": rejected,
        }
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
    }
    return {
        "ok": True,
        "slug": slug,
        "spec": primary,
        "bundle_specs": [item["spec"] for item in collected[1:]],
        "record": record,
    }


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

    with tempfile.TemporaryDirectory(prefix=f"blackhole-forage-{slug}-") as tmp:
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
    for spec in specs:
        acquisition = acquire_capability(spec, repo_root=repo_root, output_dir=output_dir)
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
        if not acquisition.get("ok"):
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
