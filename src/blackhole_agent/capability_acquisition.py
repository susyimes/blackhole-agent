"""Capability acquisition plane: uncooperative packages become absorbable tools.

The absorption plane requires an external tool to *ship* an ``absorption.json``
manifest — a cooperative protocol. Real third-party packages ship nothing of
the sort, so the ledger's open-world growth stopped at tools that already
spoke the contract. This module closes that gap — **acquisition**:

- an :class:`AcquisitionSpec` declares only what cannot be machine-derived:
  the package source (directory or sdist/npm tarball), the runtime
  (``python`` or ``node``), the entry point, the state keys, and the probe
  inputs;
- synthesis stages the package source into a scratch tree, writes a generic
  state-threading adapter for the declared runtime (JSON state on stdin, JSON
  fragment on stdout), and **derives** the frozen case expectations by
  executing the probes against the real package — expectations are measured
  from observed behavior, never hand-written;
- the synthesized tree (package source + adapter + ``absorption.json``) is
  validated by the absorption plane's own ``load_manifest`` and preflight,
  then absorbed through :func:`absorb_external_capability` — vendored,
  digest-sealed, registered, and proved like any cooperative tool;
- falsification: a spec naming a missing callable or a probe that raises is
  refused *before* any ledger write; a tampered adapter, case, or vendored
  file fails the absorbed proof; a forged acquisition report fails
  verification;
- a digest-sealed report under ``artifacts/capability-acquisition/`` whose
  grade is a pure function of recorded verdicts; verification re-grades,
  re-checks the digest, and re-proves every acquired capability live.

Determinism contract: staged tree layout, derived case order, and every
verdict must be reproducible on the same checkout. Durations and timestamps
are diagnostics only and are excluded from every digest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import (
    ABSORBED_ROOT,
    SLUG_PATTERN,
    _STATE_KEY_PATTERN,
    absorb_external_capability,
    capability_id_for_slug,
    load_manifest,
    prove_absorbed_capability,
    run_absorption_case,
    run_absorption_scenario,
    tree_digest,
    verify_absorption_plane,
    _digest,
)
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    load_ledger,
    prove_capability,
    register_capability,
    save_ledger,
    utc_now_iso,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-acquisition"
FIXTURE_PACKAGE = REPO_ROOT / "tests" / "fixtures" / "external_packages" / "json-indenter"
FIXTURE_NODE_PACKAGE = REPO_ROOT / "tests" / "fixtures" / "external_packages" / "js-shouter"
STEWARDSHIP_ROOT = REPO_ROOT / "stewardship"

ADAPTER_NAMES = {"python": "acquisition_adapter.py", "node": "acquisition_adapter.mjs"}
RUNTIMES = frozenset(ADAPTER_NAMES)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DOTTED_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")


def adapter_name_for(runtime: str) -> str:
    return ADAPTER_NAMES[runtime]


def adapter_command(spec: "AcquisitionSpec") -> list[str]:
    """The manifest command for one spec: runtime executable + adapter file."""

    executable = "python" if spec.runtime == "python" else "node"
    return [executable, adapter_name_for(spec.runtime)]


# ---------------------------------------------------------------------------
# Acquisition specification: the irreducible declarative kernel.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcquisitionSpec:
    """What cannot be machine-derived about one uncooperative package."""

    slug: str
    name: str
    source: Path
    import_name: str
    callable_name: str
    requires: tuple[str, ...]
    provides: str
    probes: tuple[dict[str, Any], ...]
    runtime: str = "python"
    entry: str = ""
    path_root: str = "."
    version: str = ""
    origin: Mapping[str, Any] = field(default_factory=dict)
    extra_paths: tuple[str, ...] = ()

    def validate(self) -> "AcquisitionSpec":
        if not SLUG_PATTERN.match(self.slug):
            raise ValueError(f"invalid acquisition slug: {self.slug!r}")
        if not str(self.name).strip():
            raise ValueError("acquisition spec requires a name")
        if not self.source.exists():
            raise ValueError(f"acquisition source not found: {self.source}")
        if self.runtime not in RUNTIMES:
            raise ValueError(f"unsupported acquisition runtime: {self.runtime!r}")
        if self.runtime == "python":
            if not _DOTTED_IDENTIFIER.match(self.import_name):
                raise ValueError(f"invalid import name: {self.import_name!r}")
        else:
            # Node adapters import one explicit module file; no import name.
            if not self.entry or Path(self.entry).is_absolute() or ".." in Path(self.entry).parts:
                raise ValueError(f"node acquisition entry must stay inside the staged tree: {self.entry!r}")
        if not _DOTTED_IDENTIFIER.match(self.callable_name):
            raise ValueError(f"invalid callable name: {self.callable_name!r}")
        if (
            not self.requires
            or not all(_STATE_KEY_PATTERN.match(key) for key in self.requires)
            or len(set(self.requires)) != len(self.requires)
        ):
            raise ValueError("acquisition requires must be unique snake_case state keys")
        if not _STATE_KEY_PATTERN.match(self.provides):
            raise ValueError(f"invalid provides key: {self.provides!r}")
        if self.provides in set(self.requires):
            raise ValueError("acquisition provides key must not shadow a requires key")
        if len(self.probes) < 2:
            raise ValueError("acquisition requires at least two probe inputs")
        for index, probe in enumerate(self.probes):
            if not isinstance(probe, dict):
                raise ValueError(f"probe {index} must be an object")
            missing = [key for key in self.requires if key not in probe]
            if missing:
                raise ValueError(f"probe {index} input is missing required keys: {missing}")
        if Path(self.path_root).is_absolute() or ".." in Path(self.path_root).parts:
            raise ValueError(f"path_root must stay inside the staged tree: {self.path_root!r}")
        for extra in self.extra_paths:
            extra_path = Path(str(extra))
            if extra_path.is_absolute() or ".." in extra_path.parts:
                raise ValueError(f"extra_paths must stay inside the staged tree: {extra!r}")
        return self


# ---------------------------------------------------------------------------
# Generic state-threading adapter, synthesized per spec.
# ---------------------------------------------------------------------------

_ADAPTER_TEMPLATE = '''"""Synthesized acquisition adapter: JSON state in, JSON fragment out.

Generated by blackhole_agent.capability_acquisition for spec slug {slug!r}.
Do not hand-edit: the vendored tree digest seals this file.
"""

import importlib
import json
import sys
from pathlib import Path

CONFIG = {config}

_ROOT = Path(__file__).resolve().parent
for _extra in CONFIG.get("extra_paths") or []:
    sys.path.insert(0, str(_ROOT / _extra))
sys.path.insert(0, str(_ROOT / CONFIG["path_root"]))


def main() -> int:
    state = json.load(sys.stdin)
    module = importlib.import_module(CONFIG["import_name"])
    target = module
    for part in CONFIG["callable_name"].split("."):
        target = getattr(target, part)
    args = [state[key] for key in CONFIG["requires"]]
    result = target(*args)
    json.dump({{CONFIG["provides"]: result}}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

_NODE_ADAPTER_TEMPLATE = '''// Synthesized acquisition adapter: JSON state in, JSON fragment out.
//
// Generated by blackhole_agent.capability_acquisition for spec slug {slug!r}.
// Do not hand-edit: the vendored tree digest seals this file.

import fs from "node:fs";
import path from "node:path";
import {{ fileURLToPath, pathToFileURL }} from "node:url";

const CONFIG = {config};

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const extras = CONFIG.extra_paths || [];
const nmDir = path.join(ROOT, "node_modules");
const created = [];
const nmExisted = fs.existsSync(nmDir);
function destFor(extra) {{
  const parts = String(extra).split(/[\\\\/]/).filter(Boolean);
  const idx = parts.indexOf(".forage-deps");
  const rest = idx >= 0 ? parts.slice(idx + 1) : parts.slice(-1);
  return path.join(nmDir, ...rest);
}}
try {{
  for (const extra of extras) {{
    const src = path.join(ROOT, extra);
    const dest = destFor(extra);
    if (!fs.existsSync(src) || fs.existsSync(dest)) {{
      continue;
    }}
    fs.mkdirSync(path.dirname(dest), {{ recursive: true }});
    fs.cpSync(src, dest, {{ recursive: true }});
    created.push(dest);
  }}
  function resolvePath(root, dotted) {{
    let current = root;
    for (const part of String(dotted || "").split(".")) {{
      if (current == null) {{
        return undefined;
      }}
      current = current[part];
    }}
    return current;
  }}
  function constructInstance(ctor) {{
    if (typeof ctor !== "function") {{
      return null;
    }}
    try {{
      return new ctor();
    }} catch {{
      /* constructor rejected zero arguments */
    }}
    try {{
      return new ctor({{}});
    }} catch {{
      /* constructor rejected empty options */
    }}
    try {{
      return new ctor("");
    }} catch {{
      return null;
    }}
  }}
  function instanceMethod(ctor, leaf) {{
    const instance = constructInstance(ctor);
    if (instance && typeof instance[leaf] === "function") {{
      return instance[leaf];
    }}
    if (ctor && ctor.prototype && typeof ctor.prototype[leaf] === "function") {{
      return ctor.prototype[leaf];
    }}
    return null;
  }}
  const moduleUrl = pathToFileURL(path.join(ROOT, CONFIG.entry));
  const mod = await import(moduleUrl);
  const dotted = String(CONFIG.callable_name).includes(".");
  let target = resolvePath(mod, CONFIG.callable_name);
  if (typeof target !== "function" && dotted) {{
    target = resolvePath(mod.default, CONFIG.callable_name);
  }}
  let instanceCtor = null;
  if (typeof target !== "function" && dotted) {{
    const parts = String(CONFIG.callable_name).split(".");
    const leaf = parts[parts.length - 1];
    const parentName = parts.slice(0, -1).join(".");
    const ctor = resolvePath(mod, parentName) ?? resolvePath(mod.default, parentName);
    const method = instanceMethod(ctor, leaf);
    if (typeof method === "function") {{
      target = method;
      instanceCtor = ctor;
    }}
  }}
  if (typeof target === "function" && dotted) {{
    const method = target;
    if (instanceCtor) {{
      const leaf = String(CONFIG.callable_name).split(".").pop();
      target = (...args) => {{
        const instance = constructInstance(instanceCtor);
        const fn = instance && typeof instance[leaf] === "function" ? instance[leaf] : method;
        return fn.apply(instance, args);
      }};
    }} else {{
      const parentName = String(CONFIG.callable_name).split(".").slice(0, -1).join(".");
      const receiver = resolvePath(mod, parentName) ?? resolvePath(mod.default, parentName);
      target = (...args) => method.apply(receiver, args);
    }}
  }}
  if (typeof target !== "function") {{
    const fallback = mod.default;
    if (
      typeof fallback === "function" &&
      (CONFIG.callable_name === "default" || fallback.name === CONFIG.callable_name)
    ) {{
      target = fallback;
    }} else if (
      typeof fallback === "function" &&
      Object.prototype.hasOwnProperty.call(fallback, CONFIG.callable_name) &&
      typeof fallback[CONFIG.callable_name] === "function"
    ) {{
      const method = fallback[CONFIG.callable_name];
      target = (...args) => method.apply(fallback, args);
    }} else if (typeof fallback === "function") {{
      const method = instanceMethod(fallback, CONFIG.callable_name);
      if (typeof method === "function") {{
        target = (...args) => {{
          const instance = constructInstance(fallback);
          const fn =
            instance && typeof instance[CONFIG.callable_name] === "function"
              ? instance[CONFIG.callable_name]
              : method;
          return fn.apply(instance, args);
        }};
      }}
    }}
    if (typeof target !== "function" && fallback && typeof fallback === "object") {{
      const nested = fallback[CONFIG.callable_name];
      if (typeof nested === "function") {{
        target = nested;
      }}
    }}
  }}
  if (typeof target !== "function") {{
    console.error(`acquisition callable not found: ${{CONFIG.callable_name}}`);
    process.exitCode = 1;
  }} else {{
    const state = JSON.parse(fs.readFileSync(0, "utf8"));
    const args = CONFIG.requires.map((key) => state[key]);
    const result = await target(...args);
    process.stdout.write(JSON.stringify({{ [CONFIG.provides]: result }}));
  }}
}} finally {{
  for (const dest of created.reverse()) {{
    try {{
      fs.rmSync(dest, {{ recursive: true, force: true }});
    }} catch {{
      /* ignore */
    }}
  }}
  if (!nmExisted && fs.existsSync(nmDir)) {{
    try {{
      fs.rmSync(nmDir, {{ recursive: true, force: true }});
    }} catch {{
      /* ignore */
    }}
  }}
}}
'''


def synthesize_adapter_source(spec: AcquisitionSpec) -> str:
    """Render the state-threading adapter for one spec."""

    config = {
        "slug": spec.slug,
        "import_name": spec.import_name,
        "callable_name": spec.callable_name,
        "requires": list(spec.requires),
        "provides": spec.provides,
        "path_root": spec.path_root,
        "entry": spec.entry,
    }
    if spec.extra_paths:
        config["extra_paths"] = list(spec.extra_paths)
    template = _ADAPTER_TEMPLATE if spec.runtime == "python" else _NODE_ADAPTER_TEMPLATE
    return template.format(slug=spec.slug, config=json.dumps(config, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Staging: package source (directory or sdist tarball) into a scratch tree.
# ---------------------------------------------------------------------------


def stage_acquisition_source(source: Path, staging_dir: Path) -> None:
    """Materialize the package source into ``staging_dir`` (no manifest needed)."""

    staging_dir.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for entry in sorted(source.iterdir()):
            target = staging_dir / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
        return
    name = source.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(source) as archive:
            archive.extractall(staging_dir, filter="data")
        return
    raise ValueError(f"unsupported acquisition source (directory or .tar.gz/.tgz): {source}")


# ---------------------------------------------------------------------------
# Synthesis: probes derive the frozen expectations from real behavior.
# ---------------------------------------------------------------------------


def _run_probe(staged_dir: Path, spec: AcquisitionSpec, probe: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the synthesized adapter on one probe; return its JSON fragment."""

    command = adapter_command(spec)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        input=json.dumps(dict(probe)),
        capture_output=True,
        text=True,
        cwd=staged_dir,
        timeout=60,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip().splitlines()
        return {
            "ok": False,
            "error": f"adapter exited {completed.returncode}: {stderr[-1] if stderr else 'no stderr'}",
        }
    try:
        fragment = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"adapter stdout is not a JSON fragment: {exc}"}
    if not isinstance(fragment, dict) or set(fragment) != {spec.provides}:
        return {"ok": False, "error": f"adapter fragment must provide exactly {spec.provides!r}"}
    return {"ok": True, "fragment": fragment}


def synthesize_acquisition(spec: AcquisitionSpec, staging_root: Path) -> dict[str, Any]:
    """Synthesize a cooperative tool tree from an uncooperative package.

    Stages the source, writes the generic adapter, executes every probe to
    derive the frozen expectations, writes ``absorption.json``, and validates
    the result through the absorption plane's own ``load_manifest`` plus a
    full case preflight. Any probe failure refuses the acquisition before a
    manifest exists — nothing reaches the ledger.
    """

    spec.validate()
    staged_dir = staging_root / spec.slug
    if staged_dir.exists():
        shutil.rmtree(staged_dir)
    try:
        stage_acquisition_source(spec.source, staged_dir)
    except (ValueError, tarfile.TarError, OSError) as exc:
        return {"ok": False, "stage": "stage", "slug": spec.slug, "error": str(exc)}
    if spec.extra_paths:
        from blackhole_agent.capability_foraging import close_runtime_dependencies

        closed = close_runtime_dependencies(staged_dir, runtime=spec.runtime)
        missing = [path for path in spec.extra_paths if not (staged_dir / path).exists()]
        if missing or not closed.get("ok"):
            return {
                "ok": False,
                "stage": "deps",
                "slug": spec.slug,
                "error": str(closed.get("error") or f"runtime extra_paths missing: {missing}"),
            }
    if not (staged_dir / spec.path_root).exists():
        return {
            "ok": False,
            "stage": "stage",
            "slug": spec.slug,
            "error": f"path_root not present in staged source: {spec.path_root!r}",
        }
    if spec.runtime == "node" and not (staged_dir / spec.entry).is_file():
        return {
            "ok": False,
            "stage": "stage",
            "slug": spec.slug,
            "error": f"node entry module not present in staged source: {spec.entry!r}",
        }
    (staged_dir / adapter_name_for(spec.runtime)).write_text(
        synthesize_adapter_source(spec), encoding="utf-8"
    )

    cases: list[dict[str, Any]] = []
    for index, probe in enumerate(spec.probes):
        result = _run_probe(staged_dir, spec, probe)
        if not result["ok"]:
            shutil.rmtree(staged_dir, ignore_errors=True)
            return {
                "ok": False,
                "stage": "probe",
                "slug": spec.slug,
                "probe_index": index,
                "error": result["error"],
            }
        cases.append({"input": dict(probe), "expect": result["fragment"]})

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "slug": spec.slug,
        "name": spec.name,
        "version": spec.version,
        "origin": dict(spec.origin),
        "command": adapter_command(spec),
        "requires": list(spec.requires),
        "provides": [spec.provides],
        "cases": cases,
    }
    (staged_dir / "absorption.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        validated = load_manifest(staged_dir)
    except ValueError as exc:
        return {"ok": False, "stage": "validate", "slug": spec.slug, "error": str(exc)}

    preflight = run_absorption_case(
        staged_dir, validated["command"], validated["cases"][0]
    )
    if not preflight["ok"]:
        return {"ok": False, "stage": "preflight", "slug": spec.slug, "error": preflight["error"]}
    return {
        "ok": True,
        "slug": spec.slug,
        "staged_dir": str(staged_dir),
        "manifest": validated,
        "case_count": len(cases),
    }


# ---------------------------------------------------------------------------
# Acquisition: synthesize, absorb, and seal the honesty scenario.
# ---------------------------------------------------------------------------


def acquire_capability(
    spec: AcquisitionSpec,
    *,
    repo_root: Path = REPO_ROOT,
    scenario: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Acquire one uncooperative package as a proved ledger capability."""

    with tempfile.TemporaryDirectory(prefix=f"blackhole-acquire-{spec.slug}-") as tmp:
        synthesis = synthesize_acquisition(spec, Path(tmp))
        if not synthesis["ok"]:
            return synthesis
        absorption = absorb_external_capability(
            Path(synthesis["staged_dir"]), repo_root=repo_root, origin=spec.origin or None
        )
    if not absorption["ok"]:
        return {"ok": False, "stage": "absorb", "slug": spec.slug, "absorption": absorption}

    result: dict[str, Any] = {
        "ok": True,
        "stage": absorption["stage"],
        "slug": spec.slug,
        "capability_id": absorption["capability_id"],
        "derived_case_count": synthesis["case_count"],
        "proof_exit_code": absorption["proof_exit_code"],
    }
    if scenario:
        honesty = run_absorption_scenario(spec.slug, output_dir)
        result["honesty"] = honesty
        result["ok"] = result["ok"] and bool(honesty.get("ok"))
    return result


# ---------------------------------------------------------------------------
# Catalogued stewardship acquisitions: staged packages with no manifest.
# ---------------------------------------------------------------------------


def stewardship_acquisition_specs() -> list[AcquisitionSpec]:
    """The stewardship-staged packages this plane acquires on demand."""

    return [
        AcquisitionSpec(
            slug="tomli-parser",
            name="tomli TOML parser (stewardship-staged pypi sdist)",
            source=STEWARDSHIP_ROOT / "tomli-2.4.1" / "tomli-2.4.1.tar.gz",
            import_name="tomli",
            callable_name="loads",
            requires=("toml_source",),
            provides="parsed_toml",
            path_root="tomli-2.4.1/src",
            version="2.4.1",
            origin={"kind": "pypi-sdist", "source": "stewardship/tomli-2.4.1/tomli-2.4.1.tar.gz"},
            probes=(
                {"toml_source": 'title = "blackhole"\n'},
                {"toml_source": "[tool.unbound]\nenabled = true\n"},
                {"toml_source": "values = [1, 2, 3]\n"},
            ),
        ),
        AcquisitionSpec(
            slug="python-markdown",
            name="Python-Markdown renderer (stewardship-staged pypi sdist)",
            source=STEWARDSHIP_ROOT / "markdown-3.10.3" / "markdown-3.10.3.tar.gz",
            import_name="markdown",
            callable_name="markdown",
            requires=("markdown_source",),
            provides="rendered_markdown",
            path_root="markdown-3.10.3",
            version="3.10.3",
            origin={
                "kind": "pypi-sdist",
                "source": "stewardship/markdown-3.10.3/markdown-3.10.3.tar.gz",
            },
            probes=(
                {"markdown_source": "# Blackhole\n"},
                {"markdown_source": "**unbound** growth\n"},
                {"markdown_source": "1. absorb\n2. prove\n"},
            ),
        ),
        AcquisitionSpec(
            slug="marked-renderer",
            name="marked markdown parser (stewardship-staged npm tarball)",
            source=STEWARDSHIP_ROOT / "marked-18.0.7" / "marked-18.0.7.tgz",
            import_name="",
            callable_name="parse",
            requires=("markdown_source",),
            provides="marked_html",
            runtime="node",
            entry="package/lib/marked.esm.js",
            version="18.0.7",
            origin={"kind": "npm-tarball", "source": "stewardship/marked-18.0.7/marked-18.0.7.tgz"},
            probes=(
                {"markdown_source": "# Blackhole\n"},
                {"markdown_source": "**unbound** growth\n"},
                {"markdown_source": "- absorb\n- prove\n"},
            ),
        ),
    ]


def fixture_node_acquisition_spec() -> AcquisitionSpec:
    """The hermetic node-runtime fixture spec used by the proof and tests."""

    return AcquisitionSpec(
        slug="js-shouter",
        name="JS shouter (uncooperative node fixture package)",
        source=FIXTURE_NODE_PACKAGE,
        import_name="",
        callable_name="shout",
        requires=("quiet_text",),
        provides="shouted_text",
        runtime="node",
        entry="index.mjs",
        origin={"kind": "fixture", "source": "tests/fixtures/external_packages/js-shouter"},
        probes=(
            {"quiet_text": "hello unbound"},
            {"quiet_text": "acquire everything"},
        ),
    )


def fixture_acquisition_spec() -> AcquisitionSpec:
    """The hermetic fixture spec used by the registered proof and tests."""

    return AcquisitionSpec(
        slug="json-indenter",
        name="JSON indenter (uncooperative fixture package)",
        source=FIXTURE_PACKAGE,
        import_name="json_indenter",
        callable_name="indent",
        requires=("raw_json",),
        provides="indented_json",
        origin={"kind": "fixture", "source": "tests/fixtures/external_packages/json-indenter"},
        probes=(
            {"raw_json": '{"b": 1, "a": 2}'},
            {"raw_json": '{"z": [3, 1]}'},
        ),
    )


# ---------------------------------------------------------------------------
# Acquisition plane: sealed, verifiable demonstration over the live ledger.
# ---------------------------------------------------------------------------


def _report_digest(report: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}})


def run_acquisition_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Acquire every catalogued stewardship package and seal the evidence."""

    acquisitions: dict[str, Any] = {}
    for spec in stewardship_acquisition_specs():
        acquisitions[spec.slug] = acquire_capability(spec, output_dir=None)
    grade = {
        "acquisition_count": len(acquisitions),
        "acquisitions_ok": sum(1 for item in acquisitions.values() if item.get("ok")),
        "ok": bool(acquisitions) and all(item.get("ok") for item in acquisitions.values()),
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_acquisition_plane",
        "generated_at": utc_now_iso(),
        "slugs": sorted(acquisitions),
        "acquisitions": acquisitions,
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)

    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": grade["ok"],
        "report_dir": str(target_dir),
        "slugs": sorted(acquisitions),
        "grade": grade,
    }


def verify_acquisition_plane(report_dir: Path) -> dict[str, Any]:
    """Re-grade a sealed acquisition report; re-prove every acquired capability."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")

    acquisitions = report.get("acquisitions") or {}
    expected_grade = {
        "acquisition_count": len(acquisitions),
        "acquisitions_ok": sum(1 for item in acquisitions.values() if item.get("ok")),
        "ok": bool(acquisitions) and all(item.get("ok") for item in acquisitions.values()),
    }
    grade_ok = expected_grade == report.get("grade")

    live_proofs = {
        slug: prove_absorbed_capability(slug) for slug in report.get("slugs") or []
    }
    live_ok = bool(live_proofs) and all(proof.get("ok") for proof in live_proofs.values())

    ok = digest_ok and grade_ok and live_ok
    return {"ok": ok, "digest_ok": digest_ok, "grade_ok": grade_ok, "live_ok": live_ok}


def builtin_acquisition_plane_proof() -> dict[str, Any]:
    """Registered proof: hermetic falsification plus the live sealed plane.

    Hermetic half (scratch dirs only, no ledger writes): the fixture package
    — which ships no manifest — synthesizes into a passing cooperative tool;
    a spec naming a missing callable is refused at the probe stage; a probe
    that raises inside the real package is refused; a hand-tampered derived
    expectation fails re-execution; the node-runtime fixture synthesizes the
    same way and refuses a missing JS callable. Live half: the stewardship
    acquisitions run end-to-end (unplannable before, solved after, ablation
    breaks) and the sealed report verifies.
    """

    spec = fixture_acquisition_spec()
    node_spec = fixture_node_acquisition_spec()
    with tempfile.TemporaryDirectory(prefix="blackhole-acquisition-proof-") as tmp:
        staging_root = Path(tmp) / "staging"
        synthesis = synthesize_acquisition(spec, staging_root / "good")
        synthesis_ok = bool(synthesis["ok"])

        tampered_case_rejected = False
        if synthesis_ok:
            staged_dir = Path(str(synthesis["staged_dir"]))
            manifest_path = staged_dir / "absorption.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["cases"][0]["expect"] = {spec.provides: "hand-edited expectation"}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            tampered = run_absorption_case(staged_dir, manifest["command"], manifest["cases"][0])
            tampered_case_rejected = not tampered["ok"]

        bad_callable = synthesize_acquisition(
            AcquisitionSpec(
                slug=spec.slug,
                name=spec.name,
                source=spec.source,
                import_name=spec.import_name,
                callable_name="missing_function",
                requires=spec.requires,
                provides=spec.provides,
                probes=spec.probes,
            ),
            staging_root / "bad-callable",
        )
        bad_callable_refused = (not bad_callable["ok"]) and bad_callable.get("stage") == "probe"

        failing_probe = synthesize_acquisition(
            AcquisitionSpec(
                slug=spec.slug,
                name=spec.name,
                source=spec.source,
                import_name=spec.import_name,
                callable_name=spec.callable_name,
                requires=spec.requires,
                provides=spec.provides,
                probes=({"raw_json": '{"broken"'}, *spec.probes),
            ),
            staging_root / "failing-probe",
        )
        failing_probe_refused = (not failing_probe["ok"]) and failing_probe.get("stage") == "probe"

        node_synthesis = synthesize_acquisition(node_spec, staging_root / "node-good")
        node_synthesis_ok = bool(node_synthesis["ok"])

        node_bad_callable = synthesize_acquisition(
            AcquisitionSpec(
                slug=node_spec.slug,
                name=node_spec.name,
                source=node_spec.source,
                import_name=node_spec.import_name,
                callable_name="missing_function",
                requires=node_spec.requires,
                provides=node_spec.provides,
                runtime="node",
                entry=node_spec.entry,
                probes=node_spec.probes,
            ),
            staging_root / "node-bad-callable",
        )
        node_bad_callable_refused = (not node_bad_callable["ok"]) and node_bad_callable.get("stage") == "probe"

        report_dir = Path(tmp) / "report"
        plane = run_acquisition_plane(report_dir)
        verification = verify_acquisition_plane(report_dir) if plane.get("ok") else {"ok": False}

    verdicts = {
        "synthesis_ok": synthesis_ok,
        "bad_callable_refused": bad_callable_refused,
        "failing_probe_refused": failing_probe_refused,
        "tampered_case_rejected": tampered_case_rejected,
        "node_synthesis_ok": node_synthesis_ok,
        "node_bad_callable_refused": node_bad_callable_refused,
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
    }
    return {"ok": all(verdicts.values()), **verdicts, "slugs": plane.get("slugs") or []}


def acquisition_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_acquisition import '
        "builtin_acquisition_plane_proof; r=builtin_acquisition_plane_proof(); "
        "assert r['ok'] and r.get('synthesis_ok') and r.get('bad_callable_refused') "
        "and r.get('failing_probe_refused') and r.get('tampered_case_rejected') "
        "and r.get('node_synthesis_ok') and r.get('node_bad_callable_refused') "
        "and r.get('plane_ok') and r.get('verify_ok')\""
    )


def register_acquisition_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the acquisition plane in the live ledger."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.application-plane",
            "capability.absorption-plane",
            "capability.ablation-proof",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.acquisition-plane",
        name="Capability acquisition plane",
        description=(
            "Uncooperative third-party packages become proved ledger capabilities: a "
            "declarative spec is staged, wrapped in a synthesized state-threading adapter "
            "for its runtime (python or node), frozen expectations are derived by executing "
            "the real package, and the result passes through the absorption plane's "
            "vendoring, digest sealing, and honesty scenario. Specs whose probes fail are "
            "refused before any ledger write."
        ),
        kind="python",
        entry="blackhole_agent.capability_acquisition:demo_acquisition_plane",
        proof_command=acquisition_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_absorption.py",
            "tests/fixtures/external_packages/json-indenter/",
            "tests/fixtures/external_packages/js-shouter/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "External packages that ship no absorption contract are now acquirable across "
            "runtimes: stewardship-staged sdists (tomli, Python-Markdown) and the npm "
            "tarball (marked, ESM-only, via a synthesized node adapter) become proved, "
            "invocable, application-plane-composable capabilities with machine-derived "
            "frozen cases."
        ),
        tags=("acquisition", "plane"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    save_ledger(ledger_path, ledger)
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_acquisition_plane() -> dict[str, Any]:
    """Entry surface: run the plane and summarize the acquired capabilities."""

    result = run_acquisition_plane()
    return {
        "ok": bool(result["ok"]),
        "acquired": result["slugs"],
        "acquired_count": len(result["slugs"]),
    }


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability acquisition plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    sub.add_parser("plane", help="acquire every catalogued stewardship package")
    sub.add_parser("proof", help="run the registered acquisition-plane proof")
    sub.add_parser("register", help="register and prove the plane in the live ledger")

    verify_parser = sub.add_parser("verify", help="verify a sealed acquisition report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    args = parser.parse_args(argv)
    if args.command_name == "plane":
        result = run_acquisition_plane()
    elif args.command_name == "proof":
        result = builtin_acquisition_plane_proof()
    elif args.command_name == "register":
        result = register_acquisition_plane_capability()
    else:
        result = verify_acquisition_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
