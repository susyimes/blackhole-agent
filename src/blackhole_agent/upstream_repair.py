"""Upstream repair plane: provable security stewardship of real vendored releases.

The absorption plane makes external tools invocable, but nothing maintains them:
a vendored release with publicly documented defects (XSS, ReDoS) stays
vulnerable forever, and the ledger would still call the capability "proved".
This module closes that gap with a falsifiable repair campaign over real,
pinned upstream artifacts. Every directory under ``stewardship/`` with a
``manifest.json`` is a **target**: a pristine sdist (sha256 pinned to the
published digest), a set of documented upstream defects, one standalone repro
per defect, and one minimal unified-diff patch per defect. The plane
discovers all targets and runs the same campaign over each:

- **provenance** — the pristine sdist's sha256 is verified against the pinned
  published digest before every campaign; a substituted tarball fails closed;
- **reproduction** — every repro exits non-zero while the defect is present
  and zero once repaired; the campaign requires every repro to fail on the
  pristine tree (defect is real, not imagined) before any patch is applied;
- **repair** — patches are applied by a strict, zero-fuzz unified-diff
  applier; after repair every repro must pass and the project's own test
  suite must pass on both the pristine and the repaired tree (so a green
  repaired suite is not a side effect of a broken baseline suite);
- **causal ablation** — per defect, a fresh pristine tree is patched with
  every patch *except* that defect's; its repro must fail again, proving the
  patch — not some other hunk — causes the fix;
- **sealed evidence** — the report under
  ``artifacts/upstream-repair/<target>/`` records sha256 of the sdist, every
  repro, and every patch, plus digest chains over recorded outcomes;
  verification is pure (recomputes digests from recorded outcomes and
  re-hashes the on-disk evidence files) so tampering with the report, a
  repro, or a patch fails verification.

Two proof tiers share this evidence:

- **live campaign** (``run_all_campaigns`` / CLI ``campaign``) — re-executes
  every repro, ablation, and upstream suite and seals a fresh report. This is
  the world-facing evidence producer; it takes minutes and is *not* the
  registered proof.
- **hermetic fleet proof** (``builtin_upstream_repair_proof`` /
  ``run_sealed_fleet_proof``) — the registered ledger proof, bounded to fit
  the integrity batch budget: purely re-verifies each target's latest sealed
  report, falsifies the verifier with a tampered copy in a throwaway
  directory (proofs never dirty the artifacts tree), and re-anchors each
  target to current reality with a bounded live probe — one deterministic
  defect whose repro must still fail on the pristine tree and still pass on
  the fully patched tree. A drifted tool, edited evidence file, forged
  verdict, or missing sealed report fails the proof; the full live campaign
  remains available as an explicit command.

Determinism contract: only exit codes and pass/fail counts enter digests.
Durations (notably ReDoS probe timings) are diagnostics and are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 2

REPO_ROOT = Path(__file__).resolve().parents[2]
STEWARDSHIP_ROOT = REPO_ROOT / "stewardship"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "upstream-repair"

REPRO_TIMEOUT_SECONDS = 90
SUITE_TIMEOUT_SECONDS = 240


# ---------------------------------------------------------------------------
# canonical hashing helpers (same convention as the other evidence planes)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# strict unified-diff application (zero fuzz: context must match exactly)


@dataclass(frozen=True)
class Hunk:
    old_start: int
    lines: tuple[str, ...]  # raw hunk body lines, each prefixed with ' ', '-' or '+'


@dataclass(frozen=True)
class FilePatch:
    path: str
    hunks: tuple[Hunk, ...]


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(text: str) -> list[FilePatch]:
    """Parse a unified diff into per-file patches. Raises on malformed input."""
    lines = text.split("\n")
    patches: list[FilePatch] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("--- "):
            i += 1
            continue
        new_line = lines[i + 1]
        if not new_line.startswith("+++ "):
            raise ValueError(f"malformed diff: expected '+++ ' after {lines[i]!r}")
        path = new_line[4:].split("\t")[0].strip()
        if path.startswith("b/"):
            path = path[2:]
        i += 2
        hunks: list[Hunk] = []
        while i < len(lines) and lines[i].startswith("@@ "):
            m = _HUNK_RE.match(lines[i])
            if not m:
                raise ValueError(f"malformed hunk header: {lines[i]!r}")
            old_start = int(m.group(1))
            old_count = int(m.group(2) or "1")
            new_count = int(m.group(4) or "1")
            i += 1
            # consume exactly the declared body: old_count context/removal lines
            # and new_count context/addition lines (counts bound the body, so a
            # following '--- ' file header is never mistaken for a removal)
            body: list[str] = []
            old_seen = new_seen = 0
            while old_seen < old_count or new_seen < new_count:
                if i >= len(lines) or not lines[i]:
                    raise ValueError(f"truncated hunk body in {path}")
                tag = lines[i][0]
                if tag == "\\":  # '\ No newline at end of file' marker
                    i += 1
                    continue
                if tag == " ":
                    old_seen += 1
                    new_seen += 1
                elif tag == "-":
                    old_seen += 1
                elif tag == "+":
                    new_seen += 1
                else:
                    raise ValueError(f"unexpected hunk line {lines[i]!r} in {path}")
                body.append(lines[i])
                i += 1
            hunks.append(Hunk(old_start=old_start, lines=tuple(body)))
        patches.append(FilePatch(path=path, hunks=tuple(hunks)))
    return patches


def apply_file_patch(file_text: str, patch: FilePatch) -> str:
    """Apply one file's hunks strictly; raise on any context mismatch."""
    lines = file_text.split("\n")
    offset = 0
    for hunk in patch.hunks:
        pos = hunk.old_start - 1 + offset
        out = lines[:pos]
        cursor = pos
        for entry in hunk.lines:
            tag, content = entry[0], entry[1:]
            if tag in (" ", "-"):
                if cursor >= len(lines) or lines[cursor] != content:
                    raise ValueError(
                        f"context mismatch in {patch.path} at line {cursor + 1}: "
                        f"expected {content!r}, found {lines[cursor] if cursor < len(lines) else '<eof>'!r}"
                    )
                cursor += 1
            if tag in (" ", "+"):
                out.append(content)
        out.extend(lines[cursor:])
        offset += sum(1 for e in hunk.lines if e[0] == "+") - sum(1 for e in hunk.lines if e[0] == "-")
        lines = out
    return "\n".join(lines)


def apply_patch_text(tree_root: Path, patch_text: str) -> list[str]:
    """Apply a unified diff to an extracted tree; returns touched paths.

    A ``+++ b/path`` whose old header is ``--- /dev/null`` creates the file.
    """
    touched: list[str] = []
    for file_patch in parse_unified_diff(patch_text):
        target = tree_root / file_patch.path
        if target.is_file():
            original = target.read_text(encoding="utf-8", newline="")
            patched = apply_file_patch(original, file_patch)
        else:
            # new file (--- /dev/null): body is additions only
            added = [
                entry[1:]
                for hunk in file_patch.hunks
                for entry in hunk.lines
                if entry[0] in ("+", " ")
            ]
            patched = "\n".join(added)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patched, encoding="utf-8", newline="")
        touched.append(file_patch.path)
    return touched


# ---------------------------------------------------------------------------
# target discovery and loading


@dataclass(frozen=True)
class Defect:
    id: str
    title: str
    kind: str
    upstream_ref: str
    repro: Path
    patch: Path


@dataclass(frozen=True)
class Target:
    manifest: Mapping[str, Any]
    root: Path
    sdist: Path
    defects: tuple[Defect, ...]

    @property
    def slug(self) -> str:
        return f"{self.manifest['name']}-{self.manifest['version']}"


def discover_targets(stewardship_root: Path = STEWARDSHIP_ROOT) -> list[Path]:
    """Every stewardship/<target>/ with a manifest.json, sorted by name."""
    if not stewardship_root.is_dir():
        return []
    return sorted(
        (child for child in stewardship_root.iterdir() if (child / "manifest.json").is_file()),
        key=lambda p: p.name,
    )


def load_target(target_root: Path) -> Target:
    manifest = json.loads((target_root / "manifest.json").read_text(encoding="utf-8"))
    defects_list: list[Defect] = []
    for d in manifest.get("defects") or []:
        # Admission may record discoveries before a patch exists. Repair only
        # operates on defects that already carry an on-disk patch.
        if d.get("pending_patch") or not d.get("patch"):
            continue
        patch_path = target_root / d["patch"]
        if not patch_path.is_file():
            continue
        defects_list.append(
            Defect(
                id=d["id"],
                title=d["title"],
                kind=d["kind"],
                upstream_ref=d.get("upstream_ref") or "",
                repro=target_root / d["repro"],
                patch=patch_path,
            )
        )
    defects = tuple(defects_list)
    return Target(manifest=manifest, root=target_root, sdist=target_root / manifest["sdist"], defects=defects)


def verify_sdist(target: Target) -> dict[str, Any]:
    actual = _sha256_file(target.sdist)
    expected = target.manifest["sdist_sha256"]
    return {"path": str(target.sdist), "expected": expected, "actual": actual, "ok": actual == expected}


def tree_digest(root: Path) -> str:
    """Deterministic digest over a directory tree's relative paths and bytes."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def verify_suite_overlay(target: Target) -> dict[str, Any] | None:
    """Verify the vendored upstream suite overlay against its pinned digest.

    Returns ``None`` when the manifest declares no overlay (nothing pinned).
    """
    overlay = target.manifest.get("suite_overlay")
    if not overlay:
        return None
    root = target.root / overlay
    actual = tree_digest(root) if root.is_dir() else None
    expected = target.manifest.get("suite_overlay_sha256")
    return {
        "path": str(root),
        "source_url": target.manifest.get("suite_source_url"),
        "expected": expected,
        "actual": actual,
        "ok": actual is not None and actual == expected,
    }


def stage_suite_overlay(tree_root: Path, target: Target) -> None:
    """Overlay the vendored upstream suite into an extracted tree.

    Frontier targets whose sdist ships no test suite vendor upstream's own
    suite (digest-pinned) in the target dir; it is copied to
    ``tests_subdir`` so campaigns exercise upstream's real tests.
    """
    overlay = target.manifest.get("suite_overlay")
    if not overlay:
        return
    src = target.root / overlay
    dest = tree_root / target.manifest["tests_subdir"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def extract_sdist(target: Target, dest: Path) -> Path:
    """Extract the pristine sdist into dest (recreated). Returns the tree root."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tarfile.open(target.sdist, "r:gz") as tar:
        tar.extractall(dest, filter="data")
    return dest


# ---------------------------------------------------------------------------
# subprocess runners


def _tree_env(tree_root: Path, manifest: Mapping[str, Any]) -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(tree_root / manifest["src_subdir"])
    env["PYTHONUTF8"] = "1"  # hermetic decoding of upstream fixtures on any host
    env.pop("PYTHONHOME", None)
    return env


def run_repro(defect: Defect, tree_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    if defect.repro.suffix == ".cjs":
        # node-runtime target: the repro expects the extracted package root
        # (require(TARGET_DIR) resolves its package.json), not the tree root.
        node = shutil.which("node")
        if node is None:
            return {
                "defect_id": defect.id,
                "exit_code": -1,
                "duration_seconds": 0.0,
                "stderr_tail": "node runtime not found on PATH",
            }
        cmd = [node, str(defect.repro), str(tree_root / manifest["src_subdir"])]
    else:
        cmd = [sys.executable, str(defect.repro), str(tree_root)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=REPRO_TIMEOUT_SECONDS,
        env=_tree_env(tree_root, manifest),
    )
    return {
        "defect_id": defect.id,
        "exit_code": proc.returncode,
        "duration_seconds": round(time.monotonic() - start, 3),
        "stderr_tail": (proc.stderr or "")[-400:],
    }


_PYTEST_PROBE: list[str] | None = None


def _pytest_prefix() -> list[str]:
    """Interpreter prefix that can run pytest.

    Proofs may execute under ``uv run`` (portable ledger proof commands),
    whose synced project env carries only main dependencies. When the ambient
    interpreter lacks pytest, fall back to ``uv run --extra dev`` so the
    pinned dev extra from uv.lock provides it.
    """
    global _PYTEST_PROBE
    if _PYTEST_PROBE is None:
        probe = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if probe.returncode == 0:
            _PYTEST_PROBE = [sys.executable, "-m", "pytest"]
        else:
            _PYTEST_PROBE = [
                "uv", "run", "--project", str(REPO_ROOT), "--extra", "dev",
                "python", "-m", "pytest",
            ]
    return list(_PYTEST_PROBE)


def run_upstream_suite(tree_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Run the target's own test suite.

    The runner is manifest-selectable via ``suite_runner``: ``pytest``
    (default) or ``unittest`` — upstream projects that support
    ``python -m unittest discover`` (and whose pytest collection requires
    optional tooling) are exercised through their own supported runner.
    """
    tests_subdir = manifest["tests_subdir"]
    if tests_subdir is None:
        # Target ships no runnable suite (and none is overlaid): the suite
        # gate is vacuous for this target, recorded honestly as skipped.
        return {
            "exit_code": 0,
            "passed": 0,
            "summary": "skipped: no upstream test suite available",
            "stderr_tail": "",
            "duration_seconds": 0.0,
        }
    tests_dir = tree_root / tests_subdir
    runner = manifest.get("suite_runner", "pytest")
    start = time.monotonic()
    if runner == "unittest":
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(tests_dir), "-t", "."],
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_SECONDS,
            cwd=str(tree_root / manifest["src_subdir"].split("/")[0]),
            env=_tree_env(tree_root, manifest),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        tail = output.strip().splitlines()
        summary = tail[-1] if tail else ""
        m = re.search(r"Ran (\d+) tests", output)
        return {
            "exit_code": proc.returncode,
            "passed": int(m.group(1)) if (m and proc.returncode == 0) else 0,
            "summary": summary[-300:],
            "stderr_tail": (proc.stderr or "")[-300:],
            "duration_seconds": round(time.monotonic() - start, 3),
        }
    proc = subprocess.run(
        [*_pytest_prefix(), str(tests_dir), "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT_SECONDS,
        cwd=str(tree_root / manifest["src_subdir"].split("/")[0]),
        env=_tree_env(tree_root, manifest),
    )
    tail = (proc.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else ""
    m = re.search(r"(\d+) passed", proc.stdout or "")
    return {
        "exit_code": proc.returncode,
        "passed": int(m.group(1)) if m else 0,
        "summary": summary[-300:],
        "stderr_tail": (proc.stderr or "")[-300:],
        "duration_seconds": round(time.monotonic() - start, 3),
    }


# ---------------------------------------------------------------------------
# campaign (per target)


def _target_artifact_dir(target: Target, artifact_dir: Path) -> Path:
    return artifact_dir / target.slug


def run_repair_campaign(
    target_root: Path,
    artifact_dir: Path = ARTIFACT_DIR,
) -> dict[str, Any]:
    """Run the full reproduce -> repair -> ablate campaign and seal a report."""
    target = load_target(target_root)
    if not target.defects:
        # Discovery-staging target: onboarded for autonomous discovery but no
        # defect admitted to the manifest yet. There is nothing to repair.
        return {
            "ok": False,
            "error": "no curated defects: discovery-staging target",
            "defect_count": 0,
            "repaired_count": 0,
            "repair_score": 0.0,
        }
    provenance = verify_sdist(target)
    if not provenance["ok"]:
        return {"ok": False, "error": "sdist provenance mismatch", "provenance": provenance}
    suite_overlay = verify_suite_overlay(target)
    if suite_overlay is not None and not suite_overlay["ok"]:
        return {"ok": False, "error": "suite overlay digest mismatch", "suite_overlay": suite_overlay}

    target_dir = _target_artifact_dir(target, artifact_dir)
    # Scratch trees extract to a short temp dir: artifact paths under a deep
    # workspace plus long upstream fixture names overflow Windows MAX_PATH.
    work_root = Path(tempfile.mkdtemp(prefix="upstream-repair-"))

    # evidence file hashes: any post-hoc edit of a repro or patch breaks verification
    evidence_files = {
        "sdist": provenance["actual"],
        "repros": {d.id: _sha256_file(d.repro) for d in target.defects},
        "patches": {d.id: _sha256_file(d.patch) for d in target.defects},
    }

    # 1. reproduce every defect on the pristine tree
    pristine = extract_sdist(target, work_root / "pristine")
    stage_suite_overlay(pristine, target)
    baseline_outcomes = [run_repro(d, pristine, target.manifest) for d in target.defects]
    baseline_suite = run_upstream_suite(pristine, target.manifest)

    # 2. apply all patches and re-run every repro
    repaired = extract_sdist(target, work_root / "repaired")
    stage_suite_overlay(repaired, target)
    patched_files: dict[str, list[str]] = {}
    for d in target.defects:
        patched_files[d.id] = apply_patch_text(repaired, d.patch.read_text(encoding="utf-8"))
    repaired_outcomes = [run_repro(d, repaired, target.manifest) for d in target.defects]
    repaired_suite = run_upstream_suite(repaired, target.manifest)

    # 3. per-defect causal ablation: all patches except this one must re-open the defect
    ablation_outcomes: list[dict[str, Any]] = []
    for d in target.defects:
        ablated = extract_sdist(target, work_root / f"ablation-{d.id}")
        for other in target.defects:
            if other.id != d.id:
                apply_patch_text(ablated, other.patch.read_text(encoding="utf-8"))
        outcome = run_repro(d, ablated, target.manifest)
        ablation_outcomes.append(outcome)

    defect_results = []
    for d, base, fixed, abl in zip(target.defects, baseline_outcomes, repaired_outcomes, ablation_outcomes):
        defect_results.append(
            {
                "id": d.id,
                "kind": d.kind,
                "title": d.title,
                "upstream_ref": d.upstream_ref,
                "reproduced_on_pristine": base["exit_code"] != 0,
                "repaired": fixed["exit_code"] == 0,
                "ablation_reopens": abl["exit_code"] != 0,
                "baseline_exit": base["exit_code"],
                "repaired_exit": fixed["exit_code"],
                "ablation_exit": abl["exit_code"],
                "patched_files": patched_files[d.id],
            }
        )

    repaired_count = sum(
        1 for r in defect_results if r["reproduced_on_pristine"] and r["repaired"] and r["ablation_reopens"]
    )
    repair_score = repaired_count / len(defect_results) if defect_results else 0.0

    outcomes_digest = _digest(
        [
            {k: r[k] for k in ("id", "baseline_exit", "repaired_exit", "ablation_exit")}
            for r in defect_results
        ]
    )
    suite_record = {
        "pristine": {"exit_code": baseline_suite["exit_code"], "passed": baseline_suite["passed"]},
        "repaired": {"exit_code": repaired_suite["exit_code"], "passed": repaired_suite["passed"]},
    }
    suite_digest = _digest(suite_record)
    report_digest = _digest(
        {
            "schema_version": SCHEMA_VERSION,
            "target": target.manifest["name"] + "==" + target.manifest["version"],
            "evidence_files": evidence_files,
            "outcomes_digest": outcomes_digest,
            "suite_digest": suite_digest,
        }
    )

    ok = (
        repair_score == 1.0
        and baseline_suite["exit_code"] == 0
        and repaired_suite["exit_code"] == 0
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "target": {
            "name": target.manifest["name"],
            "version": target.manifest["version"],
            "fixed_in": target.manifest["fixed_in"],
            "upstream_repo": target.manifest["upstream_repo"],
            "upstream_changelog": target.manifest["upstream_changelog"],
            "source_url": target.manifest["source_url"],
        },
        "provenance": provenance,
        "suite_overlay": suite_overlay,
        "evidence_files": evidence_files,
        "defects": defect_results,
        "suites": {
            "pristine": baseline_suite,
            "repaired": repaired_suite,
        },
        "repair_score": repair_score,
        "repaired_count": repaired_count,
        "defect_count": len(defect_results),
        "outcomes_digest": outcomes_digest,
        "suite_digest": suite_digest,
        "report_digest": report_digest,
        "ok": ok,
    }

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    report_dir = target_dir / f"report-{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_dir / "report.json", report)
    atomic_write_json(target_dir / "latest-report.json", {"report_dir": str(report_dir), "report_digest": report_digest})
    shutil.rmtree(work_root, ignore_errors=True)
    report["report_dir"] = str(report_dir)
    return report


# ---------------------------------------------------------------------------
# verification (pure: digests recomputed from recorded outcomes + on-disk evidence)


def verify_repair_report(report_dir: Path, target_root: Path) -> dict[str, Any]:
    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    problems: list[str] = []

    target = load_target(target_root)

    # on-disk evidence must match the recorded hashes
    ev = report.get("evidence_files", {})
    if _sha256_file(target.sdist) != ev.get("sdist"):
        problems.append("sdist hash mismatch")
    for d in target.defects:
        if _sha256_file(d.repro) != ev.get("repros", {}).get(d.id):
            problems.append(f"repro hash mismatch: {d.id}")
        if _sha256_file(d.patch) != ev.get("patches", {}).get(d.id):
            problems.append(f"patch hash mismatch: {d.id}")

    defects = report.get("defects", [])
    outcomes_digest = _digest(
        [
            {k: r[k] for k in ("id", "baseline_exit", "repaired_exit", "ablation_exit")}
            for r in defects
        ]
    )
    if outcomes_digest != report.get("outcomes_digest"):
        problems.append("outcomes digest mismatch")

    suites = report.get("suites", {})
    suite_record = {
        "pristine": {"exit_code": suites.get("pristine", {}).get("exit_code"), "passed": suites.get("pristine", {}).get("passed")},
        "repaired": {"exit_code": suites.get("repaired", {}).get("exit_code"), "passed": suites.get("repaired", {}).get("passed")},
    }
    if _digest(suite_record) != report.get("suite_digest"):
        problems.append("suite digest mismatch")

    report_digest = _digest(
        {
            "schema_version": report.get("schema_version"),
            "target": f"{report.get('target', {}).get('name')}=={report.get('target', {}).get('version')}",
            "evidence_files": ev,
            "outcomes_digest": report.get("outcomes_digest"),
            "suite_digest": report.get("suite_digest"),
        }
    )
    if report_digest != report.get("report_digest"):
        problems.append("report digest mismatch")

    # semantic consistency: every defect must show the full causal chain
    for r in defects:
        if not (r.get("reproduced_on_pristine") and r.get("repaired") and r.get("ablation_reopens")):
            problems.append(f"incomplete causal chain: {r.get('id')}")
    repaired_count = sum(
        1 for r in defects if r.get("reproduced_on_pristine") and r.get("repaired") and r.get("ablation_reopens")
    )
    score = repaired_count / len(defects) if defects else 0.0
    if score != report.get("repair_score"):
        problems.append("repair score mismatch")
    if suites.get("pristine", {}).get("exit_code") != 0 or suites.get("repaired", {}).get("exit_code") != 0:
        problems.append("upstream suite not green on both trees")

    return {
        "ok": not problems and bool(defects) and score == 1.0,
        "problems": problems,
        "defect_count": len(defects),
        "repair_score": score,
    }


def load_latest_report_dir(target_dir: Path) -> Path | None:
    pointer_path = durable_read_path(target_dir / "latest-report.json")
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    report_dir = Path(pointer["report_dir"])
    return report_dir if durable_read_path(report_dir / "report.json").is_file() else None


# ---------------------------------------------------------------------------
# multi-target campaign + registered proof


def run_all_campaigns(
    stewardship_root: Path = STEWARDSHIP_ROOT,
    artifact_dir: Path = ARTIFACT_DIR,
) -> dict[str, Any]:
    """Run the live repair campaign over every discovered stewardship target.

    This is the evidence-refresh tier: it re-executes every repro, ablation,
    and upstream suite and seals fresh reports (minutes of wall-clock). The
    registered ledger proof is the hermetic tier — see
    ``run_sealed_fleet_proof``.

    Each target gets its own sealed report; every report is then verified
    purely, and the verifier is falsified per target by flipping one recorded
    outcome (tamper must be detected everywhere).
    """
    target_roots = discover_targets(stewardship_root)
    targets: list[dict[str, Any]] = []
    all_verified = True
    all_tamper_detected = True
    for target_root in target_roots:
        if not load_target(target_root).defects:
            # Discovery-staging target (no curated defects yet): the repair
            # plane does not score it, but it must not fail the fleet either.
            targets.append(
                {
                    "target_root": str(target_root),
                    "ok": True,
                    "skipped": "no curated defects: discovery-staging target",
                    "repair_score": None,
                    "defect_count": 0,
                    "repaired_count": 0,
                }
            )
            continue
        report = run_repair_campaign(target_root, artifact_dir)
        entry: dict[str, Any] = {
            "target_root": str(target_root),
            "ok": bool(report.get("ok")),
            "repair_score": report.get("repair_score"),
            "defect_count": report.get("defect_count"),
            "repaired_count": report.get("repaired_count"),
            "report_dir": report.get("report_dir"),
        }
        if not report.get("ok"):
            entry["error"] = report.get("error", "campaign failed")
            all_verified = False
            all_tamper_detected = False
            targets.append(entry)
            continue

        report_dir = Path(report["report_dir"])
        verification = verify_repair_report(report_dir, target_root)
        entry["verified"] = verification["ok"]
        entry["verify_problems"] = verification.get("problems", [])
        all_verified = all_verified and verification["ok"]

        # falsify the verifier: one flipped outcome must be detected
        tampered = json.loads(durable_read_path(report_dir / "report.json").read_text(encoding="utf-8"))
        tampered["defects"][0]["repaired_exit"] = 1 if tampered["defects"][0]["repaired_exit"] == 0 else 0
        tamper_dir = report_dir.parent / "tamper-probe"
        tamper_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(tamper_dir / "report.json", tampered)
        tamper_verdict = verify_repair_report(tamper_dir, target_root)
        entry["tamper_detected"] = not tamper_verdict["ok"]
        all_tamper_detected = all_tamper_detected and entry["tamper_detected"]
        targets.append(entry)

    defect_count = sum(t.get("defect_count") or 0 for t in targets)
    repaired_count = sum(t.get("repaired_count") or 0 for t in targets)
    scores = [t["repair_score"] for t in targets if t.get("repair_score") is not None]
    suite_green = all(
        t.get("ok") for t in targets
    ) and bool(targets)
    ok = (
        bool(targets)
        and all(t["ok"] for t in targets)
        and all_verified
        and all_tamper_detected
        and repaired_count == defect_count
        and all(score == 1.0 for score in scores)
    )
    return {
        "ok": ok,
        "target_count": len(targets),
        "targets": targets,
        "defect_count": defect_count,
        "repaired_count": repaired_count,
        "repair_score": min(scores) if scores else 0.0,
        "verified": all_verified,
        "tamper_detected": all_tamper_detected,
        "suite_green": suite_green,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def run_live_probe(target_root: Path, *, defect_id: str | None = None) -> dict[str, Any]:
    """Bounded live anchor for one target: one defect, one tree, two repro runs.

    Re-executes the actual vendored code (no upstream suite) so the hermetic
    fleet proof is anchored in current reality rather than only in recorded
    verdicts: the probe defect's repro must still fail on the pristine tree
    and still pass after every patch is applied. The probe defect defaults to
    the first defect by sorted id so the choice is deterministic across runs.
    Cost is one sdist extraction plus two repro executions per target.
    """
    target = load_target(target_root)
    if not target.defects:
        return {"ok": False, "error": "no curated defects: discovery-staging target"}
    if defect_id is None:
        defect = sorted(target.defects, key=lambda d: d.id)[0]
    else:
        defect = next((d for d in target.defects if d.id == defect_id), None)
        if defect is None:
            return {"ok": False, "error": f"unknown probe defect: {defect_id}"}
    provenance = verify_sdist(target)
    if not provenance["ok"]:
        return {"ok": False, "error": "sdist provenance mismatch", "defect_id": defect.id}
    start = time.monotonic()
    work_root = Path(tempfile.mkdtemp(prefix="upstream-repair-probe-"))
    try:
        tree = extract_sdist(target, work_root / "tree")
        baseline = run_repro(defect, tree, target.manifest)
        if baseline["exit_code"] != 0:
            for d in target.defects:
                apply_patch_text(tree, d.patch.read_text(encoding="utf-8"))
            repaired = run_repro(defect, tree, target.manifest)
        else:
            # Defect did not reproduce on the pristine tree: the probe has
            # already failed, so the patched run would prove nothing.
            repaired = {"exit_code": None, "stderr_tail": "skipped: baseline did not fail"}
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    ok = baseline["exit_code"] != 0 and repaired["exit_code"] == 0
    return {
        "ok": ok,
        "defect_id": defect.id,
        "baseline_exit": baseline["exit_code"],
        "repaired_exit": repaired["exit_code"],
        "stderr_tail": "" if ok else (baseline.get("stderr_tail") or repaired.get("stderr_tail") or ""),
        "duration_seconds": round(time.monotonic() - start, 3),
    }


def run_sealed_fleet_proof(
    stewardship_root: Path = STEWARDSHIP_ROOT,
    artifact_dir: Path = ARTIFACT_DIR,
) -> dict[str, Any]:
    """Hermetic, bounded proof of the repair plane across every target.

    Per curated target: purely re-verify the latest sealed campaign report,
    prove the verifier honest with a tampered report copy in a throwaway
    directory, and re-anchor with a bounded live probe. Result keys mirror
    ``run_all_campaigns`` so the registered ledger proof command is unchanged.
    """
    start = time.monotonic()
    target_roots = discover_targets(stewardship_root)
    targets: list[dict[str, Any]] = []
    all_verified = True
    all_tamper_detected = True
    all_probes_ok = True
    for target_root in target_roots:
        target = load_target(target_root)
        if not target.defects:
            targets.append(
                {
                    "target_root": str(target_root),
                    "ok": True,
                    "skipped": "no curated defects: discovery-staging target",
                    "repair_score": None,
                    "defect_count": 0,
                    "repaired_count": 0,
                }
            )
            continue
        entry: dict[str, Any] = {"target_root": str(target_root)}
        report_dir = load_latest_report_dir(_target_artifact_dir(target, artifact_dir))
        if report_dir is None:
            entry.update(
                {
                    "ok": False,
                    "error": "no sealed campaign report: run the live campaign to seal one",
                    "verified": False,
                    "tamper_detected": False,
                    "live_probe": {"ok": False, "error": "not run: no sealed report"},
                }
            )
            all_verified = False
            all_tamper_detected = False
            all_probes_ok = False
            targets.append(entry)
            continue

        verification = verify_repair_report(report_dir, target_root)
        entry["verified"] = verification["ok"]
        entry["verify_problems"] = verification.get("problems", [])
        all_verified = all_verified and verification["ok"]

        # Verifier honesty: one flipped recorded outcome in a throwaway copy
        # must be detected. Proofs never write into the artifacts tree.
        report = json.loads(durable_read_path(report_dir / "report.json").read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        first = tampered["defects"][0]
        first["repaired_exit"] = 1 if first["repaired_exit"] == 0 else 0
        with tempfile.TemporaryDirectory(prefix="upstream-repair-tamper-") as tmp:
            tamper_dir = Path(tmp) / "tampered"
            tamper_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(tamper_dir / "report.json", tampered)
            tamper_verdict = verify_repair_report(tamper_dir, target_root)
        entry["tamper_detected"] = not tamper_verdict["ok"]
        all_tamper_detected = all_tamper_detected and entry["tamper_detected"]

        probe = run_live_probe(target_root)
        entry["live_probe"] = probe
        all_probes_ok = all_probes_ok and probe["ok"]

        entry["report_dir"] = str(report_dir)
        entry["report_digest"] = report.get("report_digest")
        entry["repair_score"] = report.get("repair_score")
        entry["defect_count"] = report.get("defect_count")
        entry["repaired_count"] = report.get("repaired_count")
        entry["ok"] = bool(entry["verified"] and entry["tamper_detected"] and probe["ok"])
        targets.append(entry)

    scored = [t for t in targets if t.get("repair_score") is not None]
    defect_count = sum(t.get("defect_count") or 0 for t in targets)
    repaired_count = sum(t.get("repaired_count") or 0 for t in targets)
    scores = [t["repair_score"] for t in scored]
    suite_green = all(t.get("ok") for t in targets) and bool(targets)
    ok = (
        bool(scored)
        and all(t["ok"] for t in targets)
        and all_verified
        and all_tamper_detected
        and all_probes_ok
        and repaired_count == defect_count
        and all(score == 1.0 for score in scores)
    )
    return {
        "ok": ok,
        "proof_mode": "hermetic-sealed-verification+live-probe",
        "target_count": len(targets),
        "targets": targets,
        "defect_count": defect_count,
        "repaired_count": repaired_count,
        "repair_score": min(scores) if scores else 0.0,
        "verified": all_verified,
        "tamper_detected": all_tamper_detected,
        "live_probes_ok": all_probes_ok,
        "suite_green": suite_green,
        "wall_clock_seconds": round(time.monotonic() - start, 3),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_upstream_repair_proof() -> dict[str, Any]:
    """Prove the upstream repair plane across every stewardship target.

    Registered ledger proof: hermetic sealed-report re-verification plus a
    bounded live probe per target, so the proof fits the integrity batch
    budget. The full live campaign (``run_all_campaigns``) remains available
    as the explicit evidence-refresh path.
    """
    return run_sealed_fleet_proof()


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="upstream repair plane")
    sub = parser.add_subparsers(dest="command", required=True)
    campaign_p = sub.add_parser("campaign", help="run repair campaign(s) and seal report(s)")
    campaign_p.add_argument("target", nargs="?", default=None, help="stewardship target dir (default: all)")
    verify_p = sub.add_parser("verify", help="purely verify a sealed report")
    verify_p.add_argument("report_dir", nargs="?", default=None)
    verify_p.add_argument("--target", default=None, help="stewardship target dir of the report")
    sub.add_parser("proof", help="run the registered hermetic proof (sealed verification + live probe)")
    args = parser.parse_args(argv)

    if args.command == "campaign":
        if args.target:
            report = run_repair_campaign(Path(args.target))
            print(json.dumps({k: report[k] for k in ("ok", "repair_score", "repaired_count", "defect_count", "report_dir")}, indent=2))
            return 0 if report.get("ok") else 1
        result = run_all_campaigns()
        print(json.dumps({k: v for k, v in result.items() if k != "targets"}, indent=2))
        return 0 if result.get("ok") else 1
    if args.command == "verify":
        if args.report_dir:
            report_dir = Path(args.report_dir)
        else:
            target_dir = ARTIFACT_DIR / (Path(args.target).name if args.target else "")
            found = load_latest_report_dir(target_dir) if args.target else None
            report_dir = found if found else None  # type: ignore[assignment]
        if report_dir is None or args.target is None:
            print("usage: verify <report_dir> --target <stewardship-target-dir>")
            return 1
        verdict = verify_repair_report(report_dir, Path(args.target))
        print(json.dumps(verdict, indent=2))
        return 0 if verdict["ok"] else 1
    result = builtin_upstream_repair_proof()
    print(json.dumps({k: v for k, v in result.items() if k != "targets"}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
