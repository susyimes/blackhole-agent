"""Capability foraging plane: zero-spec autonomous acquisition.

The acquisition plane still needs a human to write the declarative kernel of
each ``AcquisitionSpec``: import name, entry callable, state keys, and probe
inputs. This module removes that last human input — **foraging**:

- a forage request names only a package: a local source (directory or
  sdist tarball) or a live PyPI registry name plus an optional version;
- the import root and import name are detected from the staged tree layout
  (flat, src-layout, or nested), never declared;
- candidate callables are enumerated by sandboxed introspection — a
  subprocess imports the package and reflects its module-level functions —
  filtered to JSON-scalar signatures, and ordered deterministically;
- probe inputs are derived from a fixed, task-independent sample vocabulary
  (plain text, TOML, JSON, and markdown string domains; fixed scalar
  samples for int/float/bool), split into selection and held-out probes; no
  expected output is ever written or consulted;
- candidate selection is split-honest: a candidate must satisfy every
  selection probe of one sample domain and then generalize to that domain's
  held-out probe the selector never used; rejected candidates are recorded
  with their reason;
- the winner becomes a complete ``AcquisitionSpec`` and flows through the
  acquisition plane unchanged: expectations are measured from the real
  package's behavior, the tree is absorbed, vendored, digest-sealed,
  registered, and proved;
- the live lane fetches a package from the PyPI JSON API, verifies its
  sha256, and forages it through the identical inference path;
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

from blackhole_agent.capability_absorption import (
    _STATE_KEY_PATTERN,
    _digest,
    prove_absorbed_capability,
)
from blackhole_agent.capability_acquisition import (
    STEWARDSHIP_ROOT,
    AcquisitionSpec,
    _run_probe,
    acquire_capability,
    stage_acquisition_source,
    synthesize_adapter_source,
    adapter_name_for,
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
    for child in sorted(entry for entry in staged_dir.iterdir() if entry.is_dir()):
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


def introspect_module(staged_dir: Path, import_name: str, path_root: str, timeout: int = 60) -> dict[str, Any]:
    """Reflect one module's public functions in a subprocess."""

    with tempfile.TemporaryDirectory(prefix="blackhole-forage-introspect-") as tmp:
        script = Path(tmp) / "introspect.py"
        script.write_text(_INTROSPECT_SCRIPT, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(script), str(staged_dir / path_root), import_name],
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
# Spec inference: the full AcquisitionSpec from introspection alone.
# ---------------------------------------------------------------------------


def infer_acquisition_spec(
    *,
    slug: str,
    name: str,
    source: Path,
    staging_root: Path,
    hint: str = "",
    version: str = "",
    origin: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer a complete ``AcquisitionSpec`` for one uncooperative package.

    Every spec field — import root, import name, entry callable, state keys,
    and probe inputs — is machine-derived. The winner must pass every
    selection probe of one sample domain and then the held-out probe the
    selector never used. Any failure refuses the inference honestly.
    """

    staged_dir = staging_root / slug
    if staged_dir.exists():
        shutil.rmtree(staged_dir)
    try:
        stage_acquisition_source(source, staged_dir)
    except (ValueError, OSError) as exc:
        return {"ok": False, "stage": "stage", "slug": slug, "error": str(exc)}
    try:
        path_root, import_name = detect_import_root(staged_dir, hint)
    except ValueError as exc:
        return {"ok": False, "stage": "detect", "slug": slug, "error": str(exc)}

    introspection = introspect_module(staged_dir, import_name, path_root)
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
            spec = AcquisitionSpec(
                slug=slug,
                name=name,
                source=source,
                import_name=import_name,
                callable_name=candidate_name,
                requires=requires,
                provides=_provides_key(candidate_name, requires),
                path_root=path_root,
                version=version,
                origin=origin or {},
                probes=tuple(probes),
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
            winner = {"spec": spec, "domain": str(domain["domain"])}
            break
        if winner is not None:
            spec = winner["spec"].validate()
            record = {
                "import_name": import_name,
                "path_root": path_root,
                "winner": candidate_name,
                "domain": winner["domain"],
                "requires": list(spec.requires),
                "provides": spec.provides,
                "probe_count": len(spec.probes),
                "rejected": rejected,
            }
            return {"ok": True, "slug": slug, "spec": spec, "record": record}
        rejected.setdefault(candidate_name, "no sample domain satisfied every selection probe")
    return {
        "ok": False,
        "stage": "select",
        "slug": slug,
        "error": "no viable candidate generalized to a held-out probe",
        "rejected": rejected,
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


# ---------------------------------------------------------------------------
# Foraging: fetch (optional), infer, acquire, seal.
# ---------------------------------------------------------------------------


def forage_package(
    request: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Forage one package into a proved ledger capability, zero human spec."""

    name = str(request["name"])
    slug = str(request.get("slug") or slugify_capability_id(name))
    fetch_record: dict[str, Any] | None = None
    source = request.get("source")
    version = str(request.get("version") or "")
    origin: dict[str, Any] = dict(request.get("origin") or {})

    if request.get("registry") == "pypi":
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
        )
    if not inference["ok"]:
        return {
            "ok": False,
            "slug": slug,
            "stage": inference.get("stage"),
            "error": inference.get("error"),
            "inference": {key: value for key, value in inference.items() if key not in {"ok", "spec"}},
        }
    acquisition = acquire_capability(inference["spec"], repo_root=repo_root, output_dir=output_dir)
    result: dict[str, Any] = {
        "ok": bool(acquisition.get("ok")),
        "slug": slug,
        "stage": acquisition.get("stage"),
        "capability_id": acquisition.get("capability_id"),
        "inference": inference["record"],
        "acquisition": {
            key: value
            for key, value in acquisition.items()
            if key in {"ok", "stage", "derived_case_count", "proof_exit_code"}
        },
    }
    if not acquisition.get("ok"):
        result["error"] = acquisition.get("error") or f"acquisition failed at {acquisition.get('stage')}"
    if fetch_record is not None:
        result["fetch"] = {key: fetch_record[key] for key in ("version", "sha256", "url")}
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

    Hermetic half: inference on the fixture recovers a complete spec whose
    winner is ``shout`` while the selection-only decoy ``brittle`` is
    rejected by the held-out probe; the empty fixture (no viable candidate)
    is refused at the selection stage before any ledger write. Live half:
    the sealed plane runs all hermetic targets end-to-end and verifies, and
    a hand-tampered report fails verification.
    """

    with tempfile.TemporaryDirectory(prefix="blackhole-foraging-proof-") as tmp:
        inference = infer_acquisition_spec(
            slug="forage-lab",
            name="forage-lab (uncooperative fixture package)",
            source=FIXTURE_FORAGE_PACKAGE,
            staging_root=Path(tmp) / "infer",
            hint="forage_lab",
        )
        inference_ok = bool(inference["ok"])
        winner_is_shout = inference_ok and inference["record"]["winner"] == "shout"
        brittle_rejected = inference_ok and "held-out probe failed" in inference["record"][
            "rejected"
        ].get("brittle", "")

        refusal = infer_acquisition_spec(
            slug="forage-empty",
            name="forage-empty (no viable candidate fixture)",
            source=FIXTURE_EMPTY_PACKAGE,
            staging_root=Path(tmp) / "refuse",
            hint="forage_empty",
        )
        empty_refused = (not refusal["ok"]) and refusal.get("stage") == "select"

        report_dir = Path(tmp) / "report"
        plane = run_foraging_plane(report_dir)
        verification = verify_foraging_plane(report_dir) if plane.get("ok") else {"ok": False}

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
        "empty_refused": empty_refused,
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
    }
    return {"ok": all(verdicts.values()), **verdicts, "slugs": plane.get("slugs") or []}


def foraging_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_foraging import '
        "builtin_foraging_plane_proof; r=builtin_foraging_plane_proof(); "
        "assert r['ok'] and r.get('inference_ok') and r.get('winner_is_shout') "
        "and r.get('brittle_rejected') and r.get('empty_refused') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected')\""
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
            "Zero-spec autonomous acquisition: a request names only a package (local "
            "source or live PyPI registry entry); import root, import name, entry "
            "callable, state keys, and probe inputs are all machine-derived by "
            "sandboxed introspection and a fixed, task-independent probe vocabulary "
            "with split-honest held-out generalization. The inferred spec flows "
            "through the acquisition and absorption planes unchanged, ending as a "
            "proved, vendored, digest-sealed ledger capability. Packages with no "
            "viable candidate are refused before any ledger write."
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
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "The last human-authored input to acquisition is gone: packages are "
            "foraged from a bare name — import root detected from the tree layout, "
            "entry callable selected by sandboxed introspection with held-out "
            "generalization, probes derived from a fixed task-independent "
            "vocabulary, and the result absorbed and proved through the existing "
            "planes. The live lane fetches a real PyPI sdist, verifies its sha256, "
            "and forages it through the identical inference path."
        ),
        tags=("foraging", "plane"),
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

    forage_parser = sub.add_parser("forage", help="forage one live PyPI package end-to-end")
    forage_parser.add_argument("--pypi", required=True, help="PyPI package name")
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
        result = forage_package(
            {"registry": "pypi", "name": args.pypi, "version": args.version or "", "hint": args.pypi}
        )
    else:
        result = verify_foraging_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
