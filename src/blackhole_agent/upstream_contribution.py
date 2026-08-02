"""Upstream contribution plane: close the stewardship loop back upstream.

The repair plane (``upstream_repair``) stops at a *local* repair: a patch
against the vendored sdist tree, proven against a suite overlay. Nothing
checks the repair against the project it would actually be offered to. The
contribution plane closes that gap: a stewarded defect becomes a
submission-ready contribution bundle verified against the true upstream
repository, not the vendored copy.

For one defect entry in a stewardship manifest the plane:

1. fetches the upstream repository archive at the pinned release tag and
   re-confirms the synthesized repro still triggers the defect on the true
   upstream source (``defect_absent_at_tag`` rejects a stale claim);
2. runs the project's *own* test suite from the repo checkout as a pristine
   baseline (``suite_baseline_broken`` rejects an unhealthy target);
3. triages upstream HEAD: if the repro no longer triggers on the default
   branch, the defect is already fixed upstream — the bundle is sealed as
   triage-only with ``submittable: false`` and no patch is offered;
4. rebases the stewardship patch onto the repo layout, applies it, and
   requires the repro to pass on the patched checkout
   (``repair_ineffective`` rejects a repair that only works on the sdist);
5. installs a regression test into the repo's own tests directory — either
   a defect-declared native test (``defects[].regression_test``, written in
   the upstream project's own test conventions) or a synthesized wrapper
   that runs the minimized repro against the patched source;
6. re-runs the project's own suite including the regression test on the
   patched checkout (``patch_regression`` rejects a repair that breaks the
   upstream suite);
7. seals the bundle under ``artifacts/upstream-contribution/`` with sha256
   digests of every payload; ``verify_contribution_bundle`` re-checks the
   seal and detects tampering.

Falsification is part of the contract: a defect already fixed at HEAD never
produces a submittable bundle, and a patch that breaks the upstream suite is
rejected, never sealed. The plane performs no outward action — the bundle is
submission-ready evidence, not a submission.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-contribution"

DOWNLOAD_TIMEOUT_SECONDS = 60
SUITE_TIMEOUT_SECONDS = 300


class ContributionRejected(Exception):
    """A verdict-bearing rejection: the defect/patch failed a gate."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


# ---------------------------------------------------------------------------
# fetching and extraction


def _http_get(url: str, timeout: int = DOWNLOAD_TIMEOUT_SECONDS) -> bytes:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "blackhole-agent-contribution"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def github_archive_url(repo_url: str, ref: str) -> str:
    """Codeload tarball URL for a tag or branch ref of a GitHub repo."""
    slug = repo_url.rstrip("/").removesuffix(".git")
    slug = slug.split("github.com/", 1)[-1]
    return f"https://codeload.github.com/{slug}/tar.gz/{ref}"


def fetch_repo_archive(repo_url: str, ref: str, *, fetcher: Any = None) -> bytes:
    get = fetcher or _http_get
    return get(github_archive_url(repo_url, ref))


def _extract_archive(data: bytes, dest: Path) -> Path:
    """Extract a repo archive; return the single top-level checkout dir."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(dest, filter="data")
    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise ContributionRejected("archive_shape", f"expected one top-level dir, found {len(roots)}")
    return roots[0]


# ---------------------------------------------------------------------------
# repro, patch, suite primitives


def run_repro(repro_path: Path, src_dir: Path) -> bool:
    """True while the defect reproduces (repro exits nonzero)."""
    proc = subprocess.run(
        [sys.executable, str(repro_path), str(src_dir)],
        capture_output=True,
        text=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    return proc.returncode != 0


def rebase_patch_paths(patch_text: str, top_dir: str) -> str:
    """Rewrite ``a/<top_dir>/...``/``b/<top_dir>/...`` headers to repo-root paths.

    Stewardship patches are authored against the sdist layout whose top
    directory is ``<name>-<version>``; the upstream repo checkout at the same
    tag already *is* that top directory, so the prefix is stripped.
    """
    rebased = patch_text.replace(f"a/{top_dir}/", "a/").replace(f"b/{top_dir}/", "b/")
    if rebased == patch_text:
        raise ContributionRejected("patch_rebase", f"no header carried the expected {top_dir}/ prefix")
    return rebased


def apply_patch(checkout: Path, patch_text: str) -> None:
    # Bytes, not text mode: on Windows subprocess text mode rewrites \n to
    # CRLF and git apply then rejects the patch as corrupt.
    proc = subprocess.run(
        ["git", "apply", "-p1", "-"],
        input=patch_text.encode("utf-8"),
        cwd=checkout,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise ContributionRejected("patch_apply", detail[:400] or "git apply failed")


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


def run_suite(checkout: Path, tests_rel: str, src_abs: Path) -> dict[str, Any]:
    """Run the project's own test suite against ``src_abs`` via PYTHONPATH."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_abs) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [*_pytest_prefix(), tests_rel, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT_SECONDS,
    )
    output = proc.stdout + proc.stderr
    passed = re.search(r"(\d+) passed", output)
    failed = re.search(r"(\d+) failed", output)
    return {
        "exit_code": proc.returncode,
        "passed": int(passed.group(1)) if passed else 0,
        "failed": int(failed.group(1)) if failed else 0,
        "tail": output.strip().splitlines()[-1][:300] if output.strip() else "",
        "ok": proc.returncode == 0,
    }


_SYNTH_TEST_TEMPLATE = '''"""Regression test synthesized by blackhole_agent.upstream_contribution.

Runs the minimized standalone repro for defect {defect_id} against the
patched source tree; the repro exits 0 only once the defect is repaired.
"""

import subprocess
import sys
from pathlib import Path

REPRO = Path(__file__).resolve().parent / {repro_name!r}
SRC = Path(__file__).resolve().parents[{depth}] / {src_rel!r}


def test_{test_name}_regression() -> None:
    proc = subprocess.run([sys.executable, str(REPRO), str(SRC)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]
'''


def synthesize_regression_test(defect_id: str, repro_name: str, tests_rel: str, src_rel: str) -> str:
    depth = len([p for p in tests_rel.split("/") if p])
    test_name = re.sub(r"[^a-z0-9]+", "_", defect_id.lower()).strip("_")
    return _SYNTH_TEST_TEMPLATE.format(
        defect_id=defect_id,
        repro_name=repro_name,
        depth=depth,
        src_rel=src_rel,
        test_name=test_name,
    )


# ---------------------------------------------------------------------------
# bundle build / verify


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _rel(manifest_path_value: str) -> str:
    """Strip the sdist top-dir component from a manifest path value."""
    parts = [p for p in manifest_path_value.split("/") if p]
    return "/".join(parts[1:]) if len(parts) > 1 else parts[0]


def build_contribution(
    target_dir: Path,
    defect_id: str,
    *,
    out_root: Path | None = None,
    fetcher: Any = None,
    head_refs: Sequence[str] = ("HEAD",),
) -> dict[str, Any]:
    """Build (or triage-reject) a contribution bundle for one stewarded defect."""
    target_dir = Path(target_dir)
    manifest = json.loads(durable_read_path(target_dir / "manifest.json").read_text(encoding="utf-8"))
    defect = next((d for d in manifest.get("defects", []) if d.get("id") == defect_id), None)
    if defect is None:
        raise ContributionRejected("defect_unknown", f"no defect {defect_id} in {target_dir}")
    repo_url = manifest.get("upstream_repo")
    if not repo_url:
        raise ContributionRejected("repo_unknown", "manifest has no upstream_repo")
    version = manifest["version"]
    top_dir = manifest["src_subdir"].split("/")[0]
    src_rel = _rel(manifest["src_subdir"])
    tests_rel = _rel(manifest["tests_subdir"]) if manifest.get("tests_subdir") else "tests"
    repro_path = target_dir / defect["repro"]
    patch_text = durable_read_path(target_dir / defect["patch"]).read_text(encoding="utf-8")

    scratch = Path(tempfile.mkdtemp(prefix=f"contribution-{defect_id}-"))
    try:
        # 1. true upstream source at the pinned tag; defect must reproduce.
        tag_archive = fetch_repo_archive(repo_url, version, fetcher=fetcher)
        tag_checkout = _extract_archive(tag_archive, scratch / "tag")
        tag_src = tag_checkout / src_rel
        if not run_repro(repro_path, tag_src):
            raise ContributionRejected(
                "defect_absent_at_tag", f"repro does not trigger on upstream {version} source"
            )

        # 2. pristine baseline: the project's own suite must be green.
        tests_dir = tag_checkout / tests_rel
        if not tests_dir.is_dir():
            raise ContributionRejected("suite_missing", f"no tests dir at {tests_rel} in repo archive")
        baseline = run_suite(tag_checkout, tests_rel, tag_src)
        if not baseline["ok"]:
            raise ContributionRejected(
                "suite_baseline_broken", f"pristine suite red: {baseline['tail']}"
            )

        # 3. HEAD triage: already fixed upstream means triage-only bundle.
        head_verdict = "unfixed_at_head"
        head_src_rel: str | None = None
        for head_ref in head_refs:
            try:
                head_archive = fetch_repo_archive(repo_url, head_ref, fetcher=fetcher)
            except Exception:
                continue
            head_checkout = _extract_archive(head_archive, scratch / f"head-{head_ref}")
            candidate = head_checkout / src_rel
            if candidate.is_dir():
                head_src_rel = src_rel
                if not run_repro(repro_path, candidate):
                    head_verdict = "already_fixed_at_head"
                break
        if head_verdict == "already_fixed_at_head":
            bundle = _seal_bundle(
                out_root=out_root,
                target_dir=target_dir,
                manifest=manifest,
                defect=defect,
                verdict=head_verdict,
                submittable=False,
                payloads={},
                baseline=baseline,
                patched=None,
                head_ref=head_refs[0],
                head_triage=head_verdict,
            )
            return {"ok": True, "submittable": False, "verdict": head_verdict, "bundle_dir": bundle}

        # 4. rebase + apply the stewardship patch on the true upstream tree.
        rebased = rebase_patch_paths(patch_text, top_dir)
        apply_patch(tag_checkout, rebased)
        if run_repro(repro_path, tag_src):
            raise ContributionRejected(
                "repair_ineffective", "repro still triggers on the patched repo checkout"
            )

        # 5. regression test: defect-declared native test, else synthesized.
        repro_name = Path(defect["repro"]).name
        native = defect.get("regression_test")
        if native:
            test_text = durable_read_path(target_dir / native).read_text(encoding="utf-8")
            test_name = Path(native).name
        else:
            test_text = synthesize_regression_test(defect_id, repro_name, tests_rel, src_rel)
            test_name = f"test_contribution_{re.sub(r'[^a-z0-9]+', '_', defect_id.lower()).strip('_')}.py"
        (tests_dir / test_name).write_text(test_text, encoding="utf-8")
        if not native:
            shutil.copy2(repro_path, tests_dir / repro_name)

        # 6. patched suite must stay green, regression test included.
        patched = run_suite(tag_checkout, tests_rel, tag_src)
        if not patched["ok"]:
            raise ContributionRejected(
                "patch_regression", f"patched suite red: {patched['tail']}"
            )

        # 7. seal.
        payloads = {
            "contribution.patch": rebased,
            test_name: test_text,
            repro_name: durable_read_path(repro_path).read_text(encoding="utf-8"),
        }
        bundle = _seal_bundle(
            out_root=out_root,
            target_dir=target_dir,
            manifest=manifest,
            defect=defect,
            verdict="submittable",
            submittable=True,
            payloads=payloads,
            baseline=baseline,
            patched=patched,
            head_ref=head_refs[0],
            head_triage=head_verdict,
        )
        return {
            "ok": True,
            "submittable": True,
            "verdict": "submittable",
            "bundle_dir": bundle,
            "baseline": baseline,
            "patched": patched,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _seal_bundle(
    *,
    out_root: Path | None,
    target_dir: Path,
    manifest: dict[str, Any],
    defect: dict[str, Any],
    verdict: str,
    submittable: bool,
    payloads: dict[str, str],
    baseline: dict[str, Any],
    patched: dict[str, Any] | None,
    head_ref: str,
    head_triage: str,
) -> str:
    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    bundle_dir = root / f"{manifest['name']}-{manifest['version']}" / defect["id"] / stamp
    bundle_dir.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name, text in payloads.items():
        # Bytes, not text mode: the digest seals the exact payload bytes, and
        # Windows text-mode writes would rewrite \n to CRLF under them.
        data = text.encode("utf-8")
        (bundle_dir / name).write_bytes(data)
        digests[name] = _sha256_bytes(data)
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "target": str(target_dir),
        "name": manifest["name"],
        "version": manifest["version"],
        "defect_id": defect["id"],
        "defect_title": defect.get("title", ""),
        "upstream_repo": manifest["upstream_repo"],
        "tag_ref": manifest["version"],
        "head_ref": head_ref,
        "reproduced_at_tag": True,
        "head_triage": head_triage,
        "verdict": verdict,
        "submittable": submittable,
        "baseline_suite": baseline,
        "patched_suite": patched,
        "payload_sha256": digests,
        "native_regression_test": bool(defect.get("regression_test")),
        "created_at": utc_now_iso(),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    atomic_write_json(bundle_dir / "bundle.json", bundle)
    return str(bundle_dir)


def verify_contribution_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Re-check a sealed bundle: every payload digest must match."""
    bundle_dir = Path(bundle_dir)
    bundle = json.loads(durable_read_path(bundle_dir / "bundle.json").read_text(encoding="utf-8"))
    mismatched = []
    for name, digest in bundle.get("payload_sha256", {}).items():
        path = bundle_dir / name
        if not path.exists() or _sha256_path(path) != digest:
            mismatched.append(name)
    ok = not mismatched and bundle.get("verdict") in {"submittable", "already_fixed_at_head"}
    return {
        "ok": ok,
        "verdict": bundle.get("verdict"),
        "submittable": bundle.get("submittable"),
        "mismatched": mismatched,
        "used_skill_route_discovery": bundle.get("used_skill_route_discovery"),
    }


# ---------------------------------------------------------------------------
# registered proof (hermetic; no network)


_PROOF_PKG = "contribprobe"
_PROOF_VERSION = "1.0.0"

_PROOF_INIT_BUGGY = (
    "class ParseError(Exception):\n"
    "    pass\n"
    "\n"
    "\n"
    "def parse(text):\n"
    "    if text == 'boom':\n"
    "        raise ValueError('boom escapes the API contract')\n"
    "    if not text.startswith('ok'):\n"
    "        raise ParseError('bad input')\n"
    "    return text\n"
)

_PROOF_INIT_FIXED = _PROOF_INIT_BUGGY.replace(
    "raise ValueError('boom escapes the API contract')",
    "raise ParseError('boom escapes the API contract')",
)

_PROOF_REPRO = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import contribprobe\n"
    "try:\n"
    "    contribprobe.parse('boom')\n"
    "except contribprobe.ParseError:\n"
    "    sys.exit(0)\n"
    "except ValueError:\n"
    "    sys.exit(1)\n"
    "sys.exit(2)\n"
)

_PROOF_TEST_BASIC = (
    "import pytest\n"
    "\n"
    "import contribprobe\n"
    "\n"
    "\n"
    "def test_ok_roundtrip():\n"
    "    assert contribprobe.parse('ok fine') == 'ok fine'\n"
    "\n"
    "\n"
    "def test_bad_input_rejected():\n"
    "    with pytest.raises(contribprobe.ParseError):\n"
    "        contribprobe.parse('nope')\n"
)

_PROOF_PATCH = (
    f"--- a/{_PROOF_PKG}-{_PROOF_VERSION}/src/{_PROOF_PKG}/__init__.py\n"
    f"+++ b/{_PROOF_PKG}-{_PROOF_VERSION}/src/{_PROOF_PKG}/__init__.py\n"
    "@@ -5,6 +5,6 @@\n"
    " def parse(text):\n"
    "     if text == 'boom':\n"
    "-        raise ValueError('boom escapes the API contract')\n"
    "+        raise ParseError('boom escapes the API contract')\n"
    "     if not text.startswith('ok'):\n"
    "         raise ParseError('bad input')\n"
    "     return text\n"
)

# A patch that keeps the defect fix but breaks the pristine suite.
_PROOF_BREAKING_PATCH = _PROOF_PATCH.replace(
    "@@ -5,6 +5,6 @@\n",
    "@@ -5,6 +5,7 @@\n",
).replace(
    "+        raise ParseError('boom escapes the API contract')\n",
    "+        raise ParseError('boom escapes the API contract')\n+    return None\n",
)


def _proof_archive(init_src: str, *, top: str | None = None) -> bytes:
    top = top or f"{_PROOF_PKG}-{_PROOF_VERSION}"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in (
            (f"{top}/src/{_PROOF_PKG}/__init__.py", init_src),
            (f"{top}/tests/test_basic.py", _PROOF_TEST_BASIC),
        ):
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _proof_target(root: Path) -> Path:
    """Fabricate a stewardship target carrying one repaired defect."""
    target = root / f"{_PROOF_PKG}-{_PROOF_VERSION}"
    (target / "repros").mkdir(parents=True)
    (target / "patches").mkdir()
    (target / "repros" / "boom.py").write_text(_PROOF_REPRO, encoding="utf-8")
    (target / "patches" / "boom.patch").write_text(_PROOF_PATCH, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "name": _PROOF_PKG,
        "version": _PROOF_VERSION,
        "kind": "pypi-sdist",
        "frontier": True,
        "src_subdir": f"{_PROOF_PKG}-{_PROOF_VERSION}/src",
        "tests_subdir": f"{_PROOF_PKG}-{_PROOF_VERSION}/tests",
        "upstream_repo": "https://github.com/proof/contribprobe",
        "defects": [
            {
                "id": "boom-valueerror",
                "kind": "crash",
                "patch": "patches/boom.patch",
                "repro": "repros/boom.py",
                "title": "uncaught ValueError escapes parse() instead of ParseError",
            }
        ],
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


def builtin_upstream_contribution_proof() -> dict[str, Any]:
    """Prove the contribution plane hermetically with fabricated archives.

    Scenario A (unfixed at HEAD): the full pipeline seals a submittable
    bundle; the seal verifies and a tampered payload digest is detected.
    Scenario B (fixed at HEAD): the same defect is triaged already-fixed and
    no submittable bundle is produced. Scenario C (suite-breaking patch):
    the patch is rejected with ``patch_regression`` and nothing is sealed.
    """
    repo_url = "https://github.com/proof/contribprobe"
    tag_url = github_archive_url(repo_url, _PROOF_VERSION)
    head_url = github_archive_url(repo_url, "HEAD")
    tag_archive = _proof_archive(_PROOF_INIT_BUGGY)

    scratch = Path(tempfile.mkdtemp(prefix="contribution-proof-"))
    try:
        target = _proof_target(scratch / "stewardship")
        out_root = scratch / "artifacts"

        def fetcher_unfixed(url: str) -> bytes:
            if url == head_url:
                return _proof_archive(_PROOF_INIT_BUGGY, top=f"{_PROOF_PKG}-HEAD")
            return tag_archive

        built = build_contribution(target, "boom-valueerror", out_root=out_root, fetcher=fetcher_unfixed)
        verified = verify_contribution_bundle(Path(built["bundle_dir"]))

        bundle_dir = Path(built["bundle_dir"])
        tampered = json.loads((bundle_dir / "bundle.json").read_text(encoding="utf-8"))
        tampered["payload_sha256"]["contribution.patch"] = "0" * 64
        (bundle_dir / "bundle.json").write_text(json.dumps(tampered), encoding="utf-8")
        tamper = verify_contribution_bundle(bundle_dir)

        def fetcher_fixed(url: str) -> bytes:
            if url == head_url:
                return _proof_archive(_PROOF_INIT_FIXED, top=f"{_PROOF_PKG}-HEAD")
            return tag_archive

        triaged = build_contribution(
            target, "boom-valueerror", out_root=scratch / "artifacts-fixed", fetcher=fetcher_fixed
        )

        breaking_target = _proof_target(scratch / "stewardship-breaking")
        (breaking_target / "patches" / "boom.patch").write_text(_PROOF_BREAKING_PATCH, encoding="utf-8")
        rejected: dict[str, Any] | None = None
        try:
            build_contribution(
                breaking_target, "boom-valueerror", out_root=scratch / "artifacts-breaking", fetcher=fetcher_unfixed
            )
        except ContributionRejected as exc:
            rejected = {"verdict": exc.verdict}

        ok = bool(
            built["ok"]
            and built["submittable"]
            and built["patched"]["passed"] >= 3  # 2 pristine + 1 synthesized regression
            and verified["ok"]
            and not tamper["ok"]
            and "contribution.patch" in tamper["mismatched"]
            and triaged["ok"]
            and not triaged["submittable"]
            and triaged["verdict"] == "already_fixed_at_head"
            and rejected is not None
            and rejected["verdict"] == "patch_regression"
        )
        return {
            "ok": ok,
            "submittable_sealed": bool(built["submittable"]),
            "seal_verified": bool(verified["ok"]),
            "tamper_detected": not tamper["ok"],
            "already_fixed_triaged": triaged["verdict"] == "already_fixed_at_head" and not triaged["submittable"],
            "breaking_patch_rejected": rejected == {"verdict": "patch_regression"},
            "baseline_passed": built["baseline"]["passed"],
            "patched_passed": built["patched"]["passed"],
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="upstream contribution plane")
    sub = parser.add_subparsers(dest="command", required=True)
    build_p = sub.add_parser("build", help="build a contribution bundle for a stewarded defect")
    build_p.add_argument("--target", required=True, help="stewardship target dir")
    build_p.add_argument("--defect", required=True, help="defect id in the target manifest")
    verify_p = sub.add_parser("verify", help="verify a sealed contribution bundle")
    verify_p.add_argument("bundle_dir")
    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            result = build_contribution(Path(args.target), args.defect)
        except ContributionRejected as exc:
            print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
            return 1
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.command == "verify":
        result = verify_contribution_bundle(Path(args.bundle_dir))
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
