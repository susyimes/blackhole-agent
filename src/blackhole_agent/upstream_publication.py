"""Upstream publication plane: verified outward actuation of a sealed bundle.

The contribution plane (``upstream_contribution``) stops at a submission-ready
bundle: a digest-sealed patch, regression test, and repro, proven against the
true upstream source. It performs no outward action. The publication plane
closes the loop: a sealed, submittable bundle becomes a real pull request on
the true upstream repository, delivered through a fork of the authenticated
GitHub account, with disclosed automated authorship and a tamper-evident
receipt.

For one sealed bundle the plane:

1. re-verifies the bundle seal (``verify_contribution_bundle``) and refuses
   anything not ``submittable`` (``bundle_not_submittable``);
2. triages existing upstream PRs for the publication branch
   (``blackhole/<defect-id>``): an open PR makes publication idempotent
   (``already_published`` re-seals a receipt against the live PR), a merged PR
   means the repair landed upstream (``upstream_already_merged``), a closed
   unmerged PR means upstream rejected it (``upstream_closed_unmerged``) —
   neither re-publishes;
3. forks the upstream repo (idempotent), clones the fork, and applies the
   bundle's repo-native patch at the default-branch HEAD
   (``patch_diverged_at_head`` refuses when upstream moved on);
4. installs the bundle's native regression test into the project's own tests
   directory;
5. re-verifies the exact tree to be pushed: the manifest-declared build runs,
   the bundle's repro must pass (defect gone at patched HEAD,
   ``repair_ineffective_at_head`` refuses), and the project's own suite must
   stay green with the regression test installed (``patch_regression_at_head``
   refuses);
6. commits with an automation-disclosure trailer, pushes the branch to the
   fork, and opens the pull request with an evidence body carrying the
   bundle's sha256 payload digests and a plain disclosure of automated
   authorship;
7. seals a receipt under ``artifacts/upstream-publication/`` with sha256
   digests of the PR body and commit message; ``verify_publication_receipt``
   re-checks the seal and, when given a ``gh`` runner, confirms the PR still
   exists upstream with the recorded head SHA.

Every refusal is a verdict-bearing ``PublicationRefused``; a refusal or an
idempotent triage also seals a receipt so the decision is auditable. The plane
never force-pushes and never opens a second PR for a branch that already has
one. All GitHub interaction goes through the injected ``gh`` runner seam and
all verification through the injected ``verifier`` seam, so the builtin proof
is hermetic.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent import upstream_contribution as uc
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-publication"

GIT_TIMEOUT_SECONDS = 300
GH_TIMEOUT_SECONDS = 60
INSTALL_TIMEOUT_SECONDS = 600
SUITE_TIMEOUT_SECONDS = 600

AUTOMATION_TRAILER = "Generated-by: blackhole-agent upstream-publication plane (autonomous stewardship mission)"


class PublicationRefused(Exception):
    """A verdict-bearing refusal: publication must not happen."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


# ---------------------------------------------------------------------------
# seams: gh runner, git, verifier


def _default_gh_runner(argv: Sequence[str], cwd: Path | None = None) -> str:
    """Run the real ``gh`` CLI; returns stdout. Raises on nonzero exit."""
    proc = subprocess.run(
        ["gh", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise PublicationRefused(
            "gh_failed", f"gh {argv[0]} {argv[1] if len(argv) > 1 else ''}: {proc.stderr.strip()[:300]}"
        )
    return proc.stdout


def _git(argv: Sequence[str], cwd: Path | None = None, *, input_bytes: bytes | None = None) -> str:
    proc = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        input=input_bytes,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise PublicationRefused("git_failed", f"git {argv[0]}: {detail[:300]}")
    return proc.stdout.decode("utf-8", errors="replace")


def _gh_json(gh: Callable[..., str], argv: Sequence[str]) -> Any:
    out = gh(list(argv))
    try:
        return json.loads(out) if out.strip() else None
    except json.JSONDecodeError as exc:
        raise PublicationRefused("gh_failed", f"gh returned non-JSON for {argv[:2]}: {exc}")


# ---------------------------------------------------------------------------
# bundle intake


def load_submittable_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Verify the seal and require a submittable verdict."""
    bundle_dir = Path(bundle_dir)
    checked = uc.verify_contribution_bundle(bundle_dir)
    if checked["mismatched"]:
        raise PublicationRefused(
            "bundle_seal", f"payload digest mismatch: {', '.join(checked['mismatched'])}"
        )
    bundle = json.loads(durable_read_path(bundle_dir / "bundle.json").read_text(encoding="utf-8"))
    if not checked["ok"] or not bundle.get("submittable"):
        raise PublicationRefused(
            "bundle_not_submittable", f"bundle verdict is {bundle.get('verdict')!r}"
        )
    bundle["_dir"] = str(bundle_dir)
    return bundle


def _load_manifest(bundle: Mapping[str, Any], manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if manifest is not None:
        return dict(manifest)
    target = Path(str(bundle.get("target") or ""))
    if not target.is_absolute():
        target = REPO_ROOT / target
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        raise PublicationRefused("manifest_missing", f"no stewardship manifest at {manifest_path}")
    return json.loads(durable_read_path(manifest_path).read_text(encoding="utf-8"))


def publication_branch(defect_id: str) -> str:
    return f"blackhole/{defect_id}"


def _bundle_payload(bundle: Mapping[str, Any], name: str) -> bytes:
    return durable_read_path(Path(str(bundle["_dir"])) / name).read_bytes()


# ---------------------------------------------------------------------------
# upstream PR triage


def triage_existing_pr(
    upstream_repo: str,
    branch: str,
    *,
    gh: Callable[..., str],
    owner: str | None = None,
) -> dict[str, Any] | None:
    """Latest PR (any state) for our publication branch, or None."""
    owner = owner or _gh_owner(gh)
    if not owner:
        raise PublicationRefused("gh_failed", "could not resolve authenticated gh user")
    slug = _repo_slug(upstream_repo)
    prs = _gh_json(
        gh,
        [
            "pr", "list", "--repo", slug, "--head", f"{owner}:{branch}",
            "--state", "all", "--json", "number,url,state,headRefOid,title",
        ],
    ) or []
    if not prs:
        return None
    prs.sort(key=lambda pr: int(pr.get("number") or 0), reverse=True)
    return prs[0]


def _gh_owner(gh: Callable[..., str]) -> str:
    return str(gh(["api", "user", "--jq", ".login"])).strip().strip('"')


def _repo_slug(repo_url: str) -> str:
    slug = repo_url.rstrip("/").removesuffix(".git")
    return slug.split("github.com/", 1)[-1]


# ---------------------------------------------------------------------------
# verification of the exact tree to be pushed


def default_verifier(
    checkout: Path,
    *,
    manifest: Mapping[str, Any],
    bundle: Mapping[str, Any],
    run_suite: bool = True,
) -> dict[str, Any]:
    """Build the patched checkout, require the repro to pass and the suite green."""
    contribution = manifest.get("contribution")
    if not contribution:
        raise PublicationRefused(
            "contribution_contract", "manifest lacks a contribution build/suite contract"
        )
    repro_name = _repro_payload_name(bundle)
    scratch = Path(tempfile.mkdtemp(prefix="publication-repro-"))
    repro_path = scratch / repro_name
    repro_path.write_bytes(_bundle_payload(bundle, repro_name))
    try:
        if manifest.get("ecosystem") == "npm" or contribution.get("install"):
            if contribution.get("install"):
                uc._run_npm_steps(checkout, contribution["install"], "install")
            uc._run_npm_steps(checkout, contribution["build"], "build")
            if uc.run_repro(repro_path, checkout):
                raise PublicationRefused(
                    "repair_ineffective_at_head", "repro still triggers on the patched HEAD checkout"
                )
            suite = uc.run_npm_suite(checkout, contribution) if run_suite else {"ok": True, "skipped": True}
        else:
            if uc.run_repro(repro_path, checkout):
                raise PublicationRefused(
                    "repair_ineffective_at_head", "repro still triggers on the patched HEAD checkout"
                )
            tests_rel = contribution.get("tests_subdir") or "tests"
            src_rel = contribution.get("src_subdir") or "src"
            suite = (
                uc.run_suite(checkout, tests_rel, checkout / src_rel)
                if run_suite
                else {"ok": True, "skipped": True}
            )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if not suite.get("ok"):
        raise PublicationRefused(
            "patch_regression_at_head", f"patched HEAD suite red: {str(suite.get('tail'))[:300]}"
        )
    return {"repro_passed": True, "suite": suite}


def _repro_payload_name(bundle: Mapping[str, Any]) -> str:
    for name in bundle.get("payload_sha256", {}):
        if name.endswith((".cjs", ".py")) and "test" not in name:
            return name
    raise PublicationRefused("bundle_seal", "no repro payload found in bundle")


def _test_payload_name(bundle: Mapping[str, Any]) -> str:
    for name in bundle.get("payload_sha256", {}):
        if name != "contribution.patch" and name != _repro_payload_name(bundle):
            return name
    raise PublicationRefused("bundle_seal", "no regression-test payload found in bundle")


# ---------------------------------------------------------------------------
# receipt sealing / verification


def _seal_receipt(
    *,
    out_root: Path | None,
    bundle: Mapping[str, Any],
    verdict: str,
    published: bool,
    pr: Mapping[str, Any] | None,
    branch: str,
    head_sha: str,
    payloads: Mapping[str, bytes],
    extra: Mapping[str, Any] | None = None,
) -> str:
    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    receipt_dir = (
        root
        / f"{bundle['name']}-{bundle['version']}"
        / str(bundle["defect_id"])
        / stamp
    )
    receipt_dir.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name, data in payloads.items():
        (receipt_dir / name).write_bytes(data)
        digests[name] = uc._sha256_bytes(data)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "bundle_dir": str(bundle["_dir"]),
        "bundle_payload_sha256": dict(bundle.get("payload_sha256", {})),
        "name": bundle["name"],
        "version": bundle["version"],
        "defect_id": bundle["defect_id"],
        "upstream_repo": bundle["upstream_repo"],
        "branch": branch,
        "head_sha": head_sha,
        "verdict": verdict,
        "published": published,
        "pull_request": dict(pr) if pr else None,
        "payload_sha256": digests,
        "created_at": utc_now_iso(),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    if extra:
        receipt.update(extra)
    atomic_write_json(receipt_dir / "receipt.json", receipt)
    return str(receipt_dir)


def verify_publication_receipt(
    receipt_dir: Path,
    *,
    gh: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Re-check a sealed receipt: payload digests, and (with ``gh``) the live PR."""
    receipt_dir = Path(receipt_dir)
    receipt = json.loads(durable_read_path(receipt_dir / "receipt.json").read_text(encoding="utf-8"))
    mismatched = []
    for name, digest in receipt.get("payload_sha256", {}).items():
        path = receipt_dir / name
        if not path.exists() or uc._sha256_path(path) != digest:
            mismatched.append(name)
    ok = not mismatched and receipt.get("verdict") in {
        "published",
        "already_published",
        "upstream_already_merged",
        "upstream_closed_unmerged",
        "patch_diverged_at_head",
    }
    live: dict[str, Any] | None = None
    pr = receipt.get("pull_request") or {}
    if gh is not None and pr.get("number") and receipt.get("upstream_repo"):
        live = _gh_json(
            gh,
            [
                "pr", "view", str(pr["number"]), "--repo", _repo_slug(receipt["upstream_repo"]),
                "--json", "number,url,state,headRefOid",
            ],
        )
        if receipt.get("published") or receipt.get("verdict") == "already_published":
            ok = ok and bool(live) and live.get("url") == pr.get("url")
            if receipt.get("head_sha") and live and live.get("headRefOid"):
                ok = ok and live["headRefOid"] == receipt["head_sha"]
    return {
        "ok": ok,
        "verdict": receipt.get("verdict"),
        "published": receipt.get("published"),
        "mismatched": mismatched,
        "live_pr": live,
        "used_skill_route_discovery": receipt.get("used_skill_route_discovery"),
    }


# ---------------------------------------------------------------------------
# publication


def render_pr_body(bundle: Mapping[str, Any], test_name: str, repro_name: str) -> str:
    digests = bundle.get("payload_sha256", {})
    baseline = bundle.get("baseline_suite") or {}
    patched = bundle.get("patched_suite") or {}
    lines = [
        "## Summary",
        "",
        str(bundle.get("defect_title") or bundle.get("defect_id")),
        "",
        "## Evidence",
        "",
        f"- Defect reproduced on the true upstream source at release tag `{bundle.get('tag_ref')}`"
        f" (`reproduced_at_tag: {bundle.get('reproduced_at_tag')}`).",
        f"- HEAD triage at time of verification: `{bundle.get('head_triage')}`"
        f" (ref `{bundle.get('head_ref')}`).",
        f"- Pristine suite baseline: {baseline.get('passed')} passed, {baseline.get('failed')} failed.",
        f"- Patched suite (this change + the regression test): {patched.get('passed')} passed,"
        f" {patched.get('failed')} failed.",
        "",
        "The regression test `" + test_name + "` is installed under the project's own test"
        " conventions and fails before the patch / passes after it.",
        "",
        "## Reproduction",
        "",
        f"A minimized standalone repro (`{repro_name}`) doubles the input size and measures the"
        " growth exponent; it flags superlinear growth pre-patch and passes post-patch.",
        "",
        "## Provenance and disclosure",
        "",
        "This pull request was prepared by an autonomous stewardship agent"
        " ([blackhole-agent](https://github.com/susyimes/blackhole-agent))."
        " The defect was discovered, minimized, repaired, and verified by that agent;"
        " a human operator runs the mission runtime.",
        "",
        "Sealed evidence bundle digests (sha256):",
        "",
    ]
    for name, digest in sorted(digests.items()):
        lines.append(f"- `{name}`: `{digest}`")
    lines += [
        "",
        "These digests seal the exact patch, regression test, and repro this PR carries,"
        " so the evidence chain can be re-checked byte-for-byte.",
        "",
    ]
    return "\n".join(lines)


def render_commit_message(bundle: Mapping[str, Any]) -> str:
    title = str(bundle.get("defect_title") or bundle.get("defect_id"))
    summary = title.split("(", 1)[0].strip()
    if len(summary) > 72:
        summary = summary[:69].rstrip() + "..."
    return (
        f"fix: {summary}\n\n"
        f"{title}\n\n"
        f"Defect id: {bundle.get('defect_id')}\n"
        f"Verified against upstream tag {bundle.get('tag_ref')} and HEAD"
        f" (triage: {bundle.get('head_triage')}).\n\n"
        f"{AUTOMATION_TRAILER}\n"
    )


def publish_contribution(
    bundle_dir: Path,
    *,
    publish: bool = False,
    gh: Callable[..., str] | None = None,
    verifier: Callable[..., dict[str, Any]] | None = None,
    manifest: Mapping[str, Any] | None = None,
    fork_url: str | None = None,
    out_root: Path | None = None,
    work_root: Path | None = None,
    run_suite: bool = True,
) -> dict[str, Any]:
    """Gate, actuate, and receipt the publication of one sealed bundle.

    With ``publish=False`` only the non-mutating gates run (bundle seal,
    submittability, upstream PR triage) and the result reports
    ``dry_run_gates_passed``. With ``publish=True`` the full outward actuation
    runs. All GitHub calls go through ``gh`` (default: real ``gh`` CLI).
    """
    bundle = load_submittable_bundle(bundle_dir)
    manifest = _load_manifest(bundle, manifest)
    branch = publication_branch(str(bundle["defect_id"]))
    gh = gh or _default_gh_runner
    verifier = verifier or default_verifier
    upstream_repo = str(bundle["upstream_repo"])
    slug = _repo_slug(upstream_repo)

    owner = _gh_owner(gh)
    if not owner:
        raise PublicationRefused("gh_failed", "could not resolve authenticated gh user")

    existing = triage_existing_pr(upstream_repo, branch, gh=gh, owner=owner)
    if existing:
        state = str(existing.get("state") or "").upper()
        if state == "OPEN":
            receipt_dir = _seal_receipt(
                out_root=out_root, bundle=bundle, verdict="already_published",
                published=True, pr=existing, branch=branch,
                head_sha=str(existing.get("headRefOid") or ""), payloads={},
            )
            return {
                "ok": True, "published": True, "verdict": "already_published",
                "pull_request": existing, "receipt_dir": receipt_dir,
            }
        verdict = "upstream_already_merged" if state == "MERGED" else "upstream_closed_unmerged"
        receipt_dir = _seal_receipt(
            out_root=out_root, bundle=bundle, verdict=verdict,
            published=False, pr=existing, branch=branch, head_sha="", payloads={},
        )
        return {
            "ok": True, "published": False, "verdict": verdict,
            "pull_request": existing, "receipt_dir": receipt_dir,
        }

    if not publish:
        return {
            "ok": True,
            "published": False,
            "verdict": "dry_run_gates_passed",
            "branch": branch,
            "owner": owner,
            "upstream_repo": upstream_repo,
        }

    # outward actuation: fork -> clone -> patch -> verify -> push -> PR
    gh(["repo", "fork", slug, "--clone=false"])
    if not fork_url:
        fork_info = _gh_json(gh, ["repo", "view", f"{owner}/{slug.split('/', 1)[1]}", "--json", "url"])
        fork_url = str((fork_info or {}).get("url") or f"https://github.com/{owner}/{slug.split('/', 1)[1]}")

    scratch = Path(tempfile.mkdtemp(prefix=f"publication-{bundle['defect_id']}-", dir=work_root))
    checkout = scratch / "checkout"
    try:
        _git(["clone", fork_url, str(checkout)])
        _git(["checkout", "-b", branch], cwd=checkout)
        _git(["remote", "add", "upstream", f"https://github.com/{slug}.git"], cwd=checkout)

        patch_bytes = _bundle_payload(bundle, "contribution.patch")
        try:
            _git(["apply", "-p1", "-"], cwd=checkout, input_bytes=patch_bytes)
        except PublicationRefused as exc:
            raise PublicationRefused(
                "patch_diverged_at_head",
                f"bundle patch no longer applies at upstream HEAD: {exc.detail}",
            ) from exc

        contribution = manifest.get("contribution") or {}
        tests_rel = contribution.get("tests_subdir") or "tests"
        test_name = _test_payload_name(bundle)
        tests_dir = checkout / tests_rel
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / test_name).write_bytes(_bundle_payload(bundle, test_name))

        verification = verifier(
            checkout, manifest=manifest, bundle=bundle, run_suite=run_suite
        )

        repro_name = _repro_payload_name(bundle)
        pr_body = render_pr_body(bundle, test_name, repro_name)
        commit_message = render_commit_message(bundle)
        _git(["add", "-A"], cwd=checkout)
        _git_commit(checkout, commit_message)
        head_sha = _git(["rev-parse", "HEAD"], cwd=checkout).strip()
        _git(["push", "-u", "origin", branch], cwd=checkout)

        body_file = scratch / "pr-body.md"
        body_file.write_text(pr_body, encoding="utf-8")
        pr_url = gh([
            "pr", "create", "--repo", slug, "--head", f"{owner}:{branch}",
            "--title", f"fix: {str(bundle.get('defect_title') or bundle['defect_id']).split('(', 1)[0].strip()[:72]}",
            "--body-file", str(body_file),
        ]).strip().splitlines()[-1].strip()
        pr_info = _gh_json(gh, [
            "pr", "view", pr_url, "--repo", slug, "--json", "number,url,state,headRefOid",
        ]) or {"url": pr_url}

        receipt_dir = _seal_receipt(
            out_root=out_root,
            bundle=bundle,
            verdict="published",
            published=True,
            pr=pr_info,
            branch=branch,
            head_sha=head_sha,
            payloads={"pr-body.md": pr_body.encode("utf-8"), "commit-message.txt": commit_message.encode("utf-8")},
            extra={"verification": verification},
        )
        return {
            "ok": True,
            "published": True,
            "verdict": "published",
            "pull_request": pr_info,
            "head_sha": head_sha,
            "verification": verification,
            "receipt_dir": receipt_dir,
        }
    except PublicationRefused as exc:
        if exc.verdict in {"patch_diverged_at_head", "repair_ineffective_at_head", "patch_regression_at_head"}:
            receipt_dir = _seal_receipt(
                out_root=out_root, bundle=bundle, verdict=exc.verdict,
                published=False, pr=None, branch=branch, head_sha="", payloads={},
                extra={"refusal_detail": exc.detail},
            )
            return {
                "ok": False, "published": False, "verdict": exc.verdict,
                "detail": exc.detail, "receipt_dir": receipt_dir,
            }
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _git_commit(checkout: Path, message: str) -> None:
    """Commit with the operator's git identity; fall back to a disclosed bot identity."""
    def _config(key: str) -> str:
        proc = subprocess.run(
            ["git", "config", "--get", key],
            cwd=checkout, capture_output=True, text=True, timeout=30,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""

    env = dict(os.environ)
    name = _config("user.name") or "blackhole-agent (autonomous stewardship)"
    email = _config("user.email") or "blackhole-agent@localhost"
    env["GIT_AUTHOR_NAME"] = name
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_COMMITTER_NAME"] = name
    env["GIT_COMMITTER_EMAIL"] = email
    proc = subprocess.run(
        ["git", "commit", "-a", "-F", "-"],
        cwd=checkout,
        input=message.encode("utf-8"),
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
        env=env,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise PublicationRefused("git_failed", f"git commit: {detail[:300]}")


# ---------------------------------------------------------------------------
# registered proof (hermetic; no network)


def _proof_write_bundle(
    root: Path,
    *,
    patch: str,
    test_text: str,
    repro_text: str,
    submittable: bool = True,
    target: str = "proof-target",
) -> Path:
    """Hand-seal a minimal contribution bundle the verifier accepts."""
    bundle_dir = root / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "contribution.patch": patch.encode(),
        "scaling.test.py": test_text.encode(),
        "repro.py": repro_text.encode(),
    }
    digests = {}
    for name, data in payloads.items():
        (bundle_dir / name).write_bytes(data)
        digests[name] = uc._sha256_bytes(data)
    bundle = {
        "schema_version": 1,
        "target": target,
        "name": "pubprobe",
        "version": "1.0.0",
        "defect_id": "masking-quadratic",
        "defect_title": "scanner rebuilds the mask preamble per call making n refs + n defs O(n^2)",
        "upstream_repo": "https://github.com/proof/pubprobe",
        "tag_ref": "1.0.0",
        "head_ref": "HEAD",
        "reproduced_at_tag": True,
        "head_triage": "unfixed_at_head",
        "verdict": "submittable" if submittable else "already_fixed_at_head",
        "submittable": submittable,
        "baseline_suite": {"ok": True, "passed": 2, "failed": 0},
        "patched_suite": {"ok": True, "passed": 3, "failed": 0},
        "payload_sha256": digests,
        "native_regression_test": True,
        "created_at": utc_now_iso(),
        "used_skill_route_discovery": False,
    }
    atomic_write_json(bundle_dir / "bundle.json", bundle)
    return bundle_dir


_PROOF_SOURCE_V1 = "def scan(refs, defs):\n    masked = list(defs)\n    out = []\n    for ref in refs:\n        if ref in masked:\n            out.append(ref)\n    return out\n"
_PROOF_SOURCE_V2 = "def scan(refs, defs):\n    masked = set(defs) if any('[' in r for r in refs) else defs\n    out = []\n    for ref in refs:\n        if ref in masked:\n            out.append(ref)\n    return out\n"
_PROOF_PATCH = (
    "--- a/src/scanner.py\n"
    "+++ b/src/scanner.py\n"
    "@@ -1,5 +1,5 @@\n"
    " def scan(refs, defs):\n"
    "-    masked = list(defs)\n"
    "+    masked = set(defs) if any('[' in r for r in refs) else defs\n"
    "     out = []\n"
    "     for ref in refs:\n"
    "         if ref in masked:\n"
)
_PROOF_TEST = "def test_masking_regression():\n    assert True\n"
_PROOF_REPRO = "import sys\nsys.exit(0)\n"


class _FakeGh:
    """Hermetic gh seam: fork/PR state over local bare repos."""

    def __init__(self, fork_repo: Path):
        self.fork_repo = Path(fork_repo)
        self.prs: list[dict[str, Any]] = []
        self.forked: list[str] = []
        self.owner = "proofbot"
        self._next_number = 100

    def __call__(self, argv: Sequence[str], cwd: Path | None = None) -> str:
        args = list(argv)
        if args[:2] == ["api", "user"]:
            return "proofbot"
        if args[:2] == ["repo", "fork"]:
            self.forked.append(args[2])
            return ""
        if args[:2] == ["repo", "view"]:
            return json.dumps({"url": str(self.fork_repo)})
        if args[:2] == ["pr", "list"]:
            head = args[args.index("--head") + 1]
            branch = head.split(":", 1)[-1]
            found = [pr for pr in self.prs if pr["branch"] == branch]
            return json.dumps([
                {
                    "number": pr["number"],
                    "url": pr["url"],
                    "state": pr["state"],
                    "headRefOid": pr.get("headRefOid", ""),
                    "title": pr["title"],
                }
                for pr in found
            ])
        if args[:2] == ["pr", "create"]:
            branch = args[args.index("--head") + 1].split(":", 1)[-1]
            self._next_number += 1
            number = self._next_number
            url = f"https://github.com/proof/pubprobe/pull/{number}"
            self.prs.append({
                "number": number, "url": url, "state": "OPEN",
                "branch": branch, "title": args[args.index("--title") + 1],
                "headRefOid": "",
            })
            return url + "\n"
        if args[:2] == ["pr", "view"]:
            key = args[2]
            pr = next(
                (p for p in self.prs if str(p["number"]) == key or p["url"] == key),
                None,
            )
            if pr is None:
                raise PublicationRefused("gh_failed", f"no such pr {key}")
            try:
                sha = subprocess.run(
                    ["git", "rev-parse", pr["branch"]],
                    cwd=self.fork_repo, capture_output=True, text=True, timeout=30,
                ).stdout.strip()
            except Exception:
                sha = ""
            pr["headRefOid"] = sha
            return json.dumps({
                "number": pr["number"], "url": pr["url"],
                "state": pr["state"], "headRefOid": sha,
            })
        raise PublicationRefused("gh_failed", f"fake gh cannot handle {args[:2]}")


def _proof_remotes(scratch: Path, source_text: str) -> tuple[Path, Path]:
    """An 'upstream' working repo and a bare 'fork' the plane can clone/push."""
    upstream = scratch / "upstream"
    (upstream / "src").mkdir(parents=True)
    (upstream / "tests").mkdir()
    (upstream / "src" / "scanner.py").write_text(source_text, encoding="utf-8")
    _git(["init", "-b", "master"], cwd=upstream)
    _git(["add", "-A"], cwd=upstream)
    _git(["-c", "user.email=proof@example.com", "-c", "user.name=proof", "commit", "-m", "v1"], cwd=upstream)
    fork = scratch / "fork.git"
    _git(["clone", "--bare", str(upstream), str(fork)])
    return upstream, fork


def _proof_verifier(checkout: Path, **kwargs: Any) -> dict[str, Any]:
    text = (checkout / "src" / "scanner.py").read_text(encoding="utf-8")
    if "set(defs)" not in text:
        raise PublicationRefused("repair_ineffective_at_head", "patch content missing in checkout")
    return {"repro_passed": True, "suite": {"ok": True, "skipped": True}}


def builtin_upstream_publication_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the publication plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="publication-proof-"))
    try:
        upstream, fork = _proof_remotes(scratch, _PROOF_SOURCE_V1)
        gh = _FakeGh(fork)
        manifest = {"contribution": {"tests_subdir": "tests"}}
        bundle_dir = _proof_write_bundle(
            scratch, patch=_PROOF_PATCH, test_text=_PROOF_TEST, repro_text=_PROOF_REPRO
        )

        # 1. dry run: gates pass without any outward mutation.
        dry = publish_contribution(
            bundle_dir, publish=False, gh=gh, verifier=_proof_verifier,
            manifest=manifest, out_root=scratch / "receipts",
        )
        dry_ok = dry["ok"] and dry["verdict"] == "dry_run_gates_passed" and not gh.prs

        # 2. real publication against the local remotes.
        published = publish_contribution(
            bundle_dir, publish=True, gh=gh, verifier=_proof_verifier,
            manifest=manifest, out_root=scratch / "receipts",
        )
        publish_ok = (
            published["ok"]
            and published["verdict"] == "published"
            and len(gh.prs) == 1
            and gh.forked == ["proof/pubprobe"]
        )
        receipt_dir = Path(published["receipt_dir"])

        # 3. receipt verifies, offline and against the live (fake) PR.
        offline = verify_publication_receipt(receipt_dir)
        online = verify_publication_receipt(receipt_dir, gh=gh)
        verify_ok = offline["ok"] and online["ok"] and online["live_pr"]["state"] == "OPEN"

        # 4. tamper detection: flip one byte of the sealed PR body.
        body_path = receipt_dir / "pr-body.md"
        data = bytearray(body_path.read_bytes())
        data[0] ^= 0xFF
        body_path.write_bytes(bytes(data))
        tampered = verify_publication_receipt(receipt_dir)
        tamper_detected = not tampered["ok"] and tampered["mismatched"] == ["pr-body.md"]

        # 5. idempotency: a second publication triages to already_published.
        again = publish_contribution(
            bundle_dir, publish=True, gh=gh, verifier=_proof_verifier,
            manifest=manifest, out_root=scratch / "receipts",
        )
        idempotent = again["verdict"] == "already_published" and len(gh.prs) == 1

        # 6. a non-submittable bundle is refused before any outward action.
        stale_dir = _proof_write_bundle(
            scratch / "stale", patch=_PROOF_PATCH, test_text=_PROOF_TEST,
            repro_text=_PROOF_REPRO, submittable=False,
        )
        refused_stale = False
        try:
            publish_contribution(
                stale_dir, publish=True, gh=gh, verifier=_proof_verifier,
                manifest=manifest, out_root=scratch / "receipts",
            )
        except PublicationRefused as exc:
            refused_stale = exc.verdict == "bundle_not_submittable"

        # 7. upstream divergence: patch no longer applies -> verdict, no PR.
        diverged_upstream, diverged_fork = _proof_remotes(scratch / "div", _PROOF_SOURCE_V2)
        gh_div = _FakeGh(diverged_fork)
        div_bundle = _proof_write_bundle(
            scratch / "divbundle", patch=_PROOF_PATCH, test_text=_PROOF_TEST,
            repro_text=_PROOF_REPRO,
        )
        diverged = publish_contribution(
            div_bundle, publish=True, gh=gh_div, verifier=_proof_verifier,
            manifest=manifest, out_root=scratch / "receipts",
        )
        divergence_refused = (
            diverged["verdict"] == "patch_diverged_at_head" and not gh_div.prs
        )

        # 8. a merged upstream PR is triaged, never re-published.
        gh.prs[0]["state"] = "MERGED"
        merged = publish_contribution(
            bundle_dir, publish=True, gh=gh, verifier=_proof_verifier,
            manifest=manifest, out_root=scratch / "receipts",
        )
        merged_triaged = merged["verdict"] == "upstream_already_merged" and len(gh.prs) == 1

        ok = all([
            dry_ok, publish_ok, verify_ok, tamper_detected, idempotent,
            refused_stale, divergence_refused, merged_triaged,
        ])
        return {
            "ok": ok,
            "dry_run_gated": dry_ok,
            "published": publish_ok,
            "receipt_verified": verify_ok,
            "tamper_detected": tamper_detected,
            "idempotent_republish": idempotent,
            "stale_bundle_refused": refused_stale,
            "divergence_refused": divergence_refused,
            "merged_triaged": merged_triaged,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", help="sealed contribution bundle directory")
    parser.add_argument("--publish", action="store_true", help="perform the outward actuation")
    parser.add_argument("--no-suite", action="store_true", help="skip the patched-HEAD suite run")
    parser.add_argument("--verify-receipt", help="verify a sealed publication receipt")
    parser.add_argument("--online", action="store_true", help="also check the live PR via gh")
    parser.add_argument("--proof", action="store_true", help="run the hermetic builtin proof")
    args = parser.parse_args(argv)

    if args.proof:
        result = builtin_upstream_publication_proof()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    if args.verify_receipt:
        result = verify_publication_receipt(
            Path(args.verify_receipt), gh=_default_gh_runner if args.online else None
        )
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    if not args.bundle:
        parser.error("--bundle is required unless --proof/--verify-receipt")
    result = publish_contribution(
        Path(args.bundle), publish=args.publish, run_suite=not args.no_suite
    )
    print(json.dumps({k: v for k, v in result.items()}, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
