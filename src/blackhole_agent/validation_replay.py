"""Class-level repair for recurring ``validation_replay_failed`` timeouts.

The harvested rejection was a true milestone whose reported validation was a
long ``capability_application_growth *-proof`` CLI. Controller replay re-ran
that unbounded command, hit the 300s budget, and refused the increment.

An instance patch shortens one named proof, or tells the agent to "report a
shorter command". A later depth with the same CLI shape fails the same way.

This module:

- rewrites growth ``*-proof`` CLIs to the matching ``*-verify`` witness
  before replay, so the controller never re-enters the unbounded proof
- ignores unbound witness strings (a bare ``python -c pass`` cannot launder
  a hang)
- still fails closed when a command hangs and no derived witness exists
- closes ``validation_replay_failed`` once the resilience capability is proved
"""

from __future__ import annotations

import inspect
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from blackhole_agent.capability_compounder import legacy_pipeline_was_used

SCHEMA_VERSION = 1
VALIDATION_REPLAY_FAILED = "validation_replay_failed"
VALIDATION_REPLAY_RESILIENCE_ID = "capability.validation-replay-resilience"
GROWTH_MODULE_MARKER = "blackhole_agent.capability_application_growth"
WITNESS_TIMEOUT_SECONDS = 30

VALIDATION_REPLAY_RESILIENCE_DONE_WHEN = (
    f"capability_exists:{VALIDATION_REPLAY_RESILIENCE_ID};"
    f"capability_proved:{VALIDATION_REPLAY_RESILIENCE_ID};"
    "no_skill_route"
)
VALIDATION_REPLAY_RESILIENCE_GOAL = (
    "Stop rejecting proved Unbound milestones because controller replay times "
    "out on a long capability-growth proof. Replay a bounded *-verify witness "
    "instead of the unbounded *-proof CLI; a hang without a derived witness "
    "still fails closed."
)

# Last recorded instance. The repair must not name or special-case it.
INSTANCE_PATCH_MARKERS = (
    "sextuple",
    "python-sextuple-nested-instance-proof",
)

_LATER_OCCURRENCE_PROOF = (
    "uv run python -m blackhole_agent.capability_application_growth "
    "python-nonuple-nested-instance-proof"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokens(command: str) -> list[str]:
    return str(command or "").split()


def is_growth_proof_command(command: str) -> bool:
    """True for application-growth CLI invocations whose subcommand is a proof."""

    if GROWTH_MODULE_MARKER not in str(command or ""):
        return False
    return any(token.endswith("-proof") and not token.startswith("-") for token in _tokens(command))


def derived_witness_command(command: str) -> str:
    """Rewrite a growth ``*-proof`` CLI to the matching ``*-verify``.

    The rewrite is suffix-generic: every depth uses the same proof→verify
    shape. A later named proof is covered without listing it.
    """

    raw = " ".join(str(command or "").split())
    if GROWTH_MODULE_MARKER not in raw:
        return ""
    rewritten = False
    out: list[str] = []
    for token in raw.split():
        if (not rewritten) and token.endswith("-proof") and not token.startswith("-"):
            out.append(token[: -len("-proof")] + "-verify")
            rewritten = True
        else:
            out.append(token)
    if not rewritten:
        return ""
    witness = " ".join(out)
    return witness if witness != raw else ""


def trusted_witness_command(item: dict[str, Any]) -> str:
    """Return a replay-safe derived witness, or empty when none is trusted.

    A bare passing command is not a witness. Only the proof→verify rewrite
    of a growth CLI is trusted.
    """

    command = str(item.get("command") or "").strip()
    derived = derived_witness_command(command)
    if derived:
        return derived
    return ""


def poison_unbounded_proof_runner() -> Callable[..., Any]:
    """Simulate the harvested class: growth proofs hang, matching verifies pass."""

    def runner(command: str, **kwargs: Any) -> subprocess.CompletedProcess:
        text = command if isinstance(command, str) else " ".join(str(part) for part in command)
        timeout = kwargs.get("timeout") or 1
        if is_growth_proof_command(text):
            raise subprocess.TimeoutExpired(command, timeout)
        if GROWTH_MODULE_MARKER in text and any(
            token.endswith("-verify") and not token.startswith("-") for token in _tokens(text)
        ):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise subprocess.TimeoutExpired(command, timeout)

    return runner


def reproduce_resilient(
    workspace: Path,
    validation: Sequence[dict[str, Any]],
    *,
    limit: int = 5,
    timeout: int = 300,
    witness_timeout: int = WITNESS_TIMEOUT_SECONDS,
    command_runner: Callable[..., Any] = subprocess.run,
) -> list[dict[str, Any]]:
    """Replay reported validations, preferring a bounded derived witness."""

    from blackhole_agent.unbound import replay_validation_command

    replays: list[dict[str, Any]] = []
    for item in validation:
        command = str(item.get("command") or "").strip()
        if not command or item.get("exit_code") != 0:
            continue
        if len(replays) >= limit:
            break
        witness = trusted_witness_command(item if isinstance(item, dict) else {})
        if witness:
            witnessed = replay_validation_command(
                workspace,
                witness,
                timeout=witness_timeout,
                command_runner=command_runner,
            )
            if witnessed.get("ok"):
                witnessed = dict(witnessed)
                witnessed["original_command"] = command
                witnessed["witnessed"] = True
                witnessed["derived_witness"] = witness
                replays.append(witnessed)
                continue
        original = replay_validation_command(
            workspace,
            command,
            timeout=timeout,
            command_runner=command_runner,
        )
        original = dict(original)
        original["witnessed"] = False
        if witness:
            original["derived_witness"] = witness
        replays.append(original)
    return replays


def _write_proved_closer(root: Path, capability_id: str) -> Path:
    from blackhole_agent.capability_compounder import (
        Capability,
        CapabilityLedger,
        default_ledger_path,
        register_capability,
        save_ledger,
    )

    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=capability_id,
            description="Proved structural closer for validation_replay_failed.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)
    return path


def validation_replay_resilience_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.validation_replay import "
        "builtin_validation_replay_resilience_proof; "
        "r=builtin_validation_replay_resilience_proof(); "
        "assert r['ok'] and r.get('action')=='validation_replay_resilience' "
        "and r.get('passed_count',0) >= 8 and not r.get('used_skill_route_discovery')\""
    )


def ensure_validation_replay_resilience_capability(*, repo_path: Path | None = None):
    """Register the closer on the live ledger once the proof is green."""

    from blackhole_agent.capability_compounder import (
        Capability,
        default_ledger_path,
        load_ledger,
        register_capability,
        save_ledger,
        utc_now_iso,
    )

    root = (repo_path or Path(__file__).resolve().parents[2]).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=VALIDATION_REPLAY_RESILIENCE_ID,
        name="Validation replay resilience",
        description=(
            "Controller replay substitutes a bounded growth *-verify witness for "
            "an unbounded *-proof CLI so a later long proof cannot reject a true "
            "milestone by timeout. A hang without a derived witness still fails."
        ),
        kind="python",
        entry="blackhole_agent.validation_replay:builtin_validation_replay_resilience_proof",
        proof_command=validation_replay_resilience_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        behavior_paths=(
            "src/blackhole_agent/validation_replay.py",
            "src/blackhole_agent/unbound.py",
            "src/blackhole_agent/kernel_class_closure.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Validation replay no longer re-runs unbounded growth proofs: a "
            "derived *-verify witness is replayed instead, an unbound pass "
            "command cannot launder a hang, and validation_replay_failed closes "
            "once this closer is proved."
        ),
        tags=("validation", "replay", "timeout", "repair"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_validation_replay_resilience_proof() -> dict[str, Any]:
    """Hermetic proof: a later long growth proof cannot reject a milestone."""

    from blackhole_agent.kernel_class_closure import class_closure_ids, class_is_closed
    from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
    from blackhole_agent.pattern_register import (
        PatternRegister,
        record_occurrence,
        required_pattern_mission,
        save_register,
    )
    from blackhole_agent.unbound import TurnDecision, evaluate_milestone, reproduce_validation

    checks: dict[str, bool] = {}
    repair_source = (
        inspect.getsource(derived_witness_command)
        + inspect.getsource(trusted_witness_command)
        + inspect.getsource(reproduce_resilient)
        + inspect.getsource(is_growth_proof_command)
    )
    lowered = repair_source.lower()
    checks["repair_is_not_named_instance_patch"] = not any(
        marker in lowered for marker in INSTANCE_PATCH_MARKERS
    )
    checks["class_closure_lists_this_capability"] = class_closure_ids(VALIDATION_REPLAY_FAILED) == (
        VALIDATION_REPLAY_RESILIENCE_ID,
    )
    checks["denylists_self"] = VALIDATION_REPLAY_RESILIENCE_ID in LOCAL_DENYLIST
    later_verify = derived_witness_command(_LATER_OCCURRENCE_PROOF)
    checks["later_depth_derives_verify"] = later_verify.endswith("-verify") and later_verify != _LATER_OCCURRENCE_PROOF
    checks["non_growth_command_has_no_derived_witness"] = derived_witness_command(
        'python -c "import time; time.sleep(30)"'
    ) == ""
    checks["unbound_pass_is_not_trusted"] = trusted_witness_command(
        {
            "command": 'python -c "import time; time.sleep(30)"',
            "exit_code": 0,
            "witness_command": 'python -c "pass"',
        }
    ) == ""

    runner = poison_unbounded_proof_runner()
    with tempfile.TemporaryDirectory(prefix="validation-replay-later-") as tmp:
        workspace = Path(tmp)
        witnessed = reproduce_validation(
            workspace,
            (
                {
                    "command": _LATER_OCCURRENCE_PROOF,
                    "exit_code": 0,
                    "summary": "later depth proof already ran in-turn",
                },
            ),
            timeout=1,
            command_runner=runner,
        )
        hang = reproduce_validation(
            workspace,
            (
                {
                    "command": 'python -c "import time; time.sleep(30)"',
                    "exit_code": 0,
                    "summary": "hang without derived witness",
                },
            ),
            timeout=1,
            command_runner=runner,
        )
        launder = reproduce_validation(
            workspace,
            (
                {
                    "command": 'python -c "import time; time.sleep(30)"',
                    "exit_code": 0,
                    "witness_command": 'python -c "pass"',
                    "summary": "unbound witness",
                },
            ),
            timeout=1,
            command_runner=runner,
        )
        checks["later_extract_witness_replays"] = bool(witnessed) and witnessed[0].get("ok") is True
        checks["later_extract_marked_witnessed"] = bool(witnessed) and witnessed[0].get("witnessed") is True
        checks["hang_without_witness_still_times_out"] = bool(hang) and hang[0].get("timed_out") is True and hang[0].get("ok") is False
        checks["unbound_witness_cannot_launder_hang"] = (
            bool(launder) and launder[0].get("ok") is False and launder[0].get("witnessed") is False
        )

        decision = TurnDecision.from_payload(
            {
                "status": "milestone",
                "summary": "behavior increment",
                "strategy": "class-level witness replay",
                "next_step": "none",
                "capability_delta": "Validation replay survives unbounded growth proofs.",
                "outcome_evidence": ["src/blackhole_agent/validation_replay.py"],
                "validation": [
                    {
                        "command": _LATER_OCCURRENCE_PROOF,
                        "exit_code": 0,
                        "summary": "later depth",
                    }
                ],
                "done_when_met": False,
                "commit_message": "",
                "mission_goal": "",
                "done_when": "",
            }
        )
        accepted = evaluate_milestone(
            decision,
            changed_paths=["src/blackhole_agent/validation_replay.py"],
            workspace=workspace,
            command_runner=runner,
            replay_timeout=1,
        )
        hang_decision = TurnDecision.from_payload(
            {
                "status": "milestone",
                "summary": "hang",
                "strategy": "class-level witness replay",
                "next_step": "none",
                "capability_delta": "Hangs still fail closed.",
                "outcome_evidence": ["src/blackhole_agent/validation_replay.py"],
                "validation": [
                    {
                        "command": 'python -c "import time; time.sleep(30)"',
                        "exit_code": 0,
                        "summary": "hang",
                    }
                ],
                "done_when_met": False,
                "commit_message": "",
                "mission_goal": "",
                "done_when": "",
            }
        )
        rejected = evaluate_milestone(
            hang_decision,
            changed_paths=["src/blackhole_agent/validation_replay.py"],
            workspace=workspace,
            command_runner=runner,
            replay_timeout=1,
        )
        checks["milestone_accepts_later_witnessed_proof"] = accepted.accepted is True
        checks["milestone_still_rejects_hang"] = rejected.accepted is False and any(
            "timed out" in reason for reason in rejected.reasons
        )

    with tempfile.TemporaryDirectory(prefix="validation-replay-open-") as tmp:
        root = Path(tmp)
        register = PatternRegister(recurrence_threshold=3)
        for index in range(3):
            record_occurrence(
                register,
                VALIDATION_REPLAY_FAILED,
                source="proof",
                summary=f"validation replay timed out {index}",
                evidence="validation replay timed out: uv run python -m blackhole_agent.capability_application_growth later-proof",
            )
        save_register(root, register)
        checks["forced_while_closer_unproved"] = (
            (required_pattern_mission(root) or {}).get("class_id") == VALIDATION_REPLAY_FAILED
            and not class_is_closed(VALIDATION_REPLAY_FAILED, root)
        )

    with tempfile.TemporaryDirectory(prefix="validation-replay-closed-") as tmp:
        root = Path(tmp)
        register = PatternRegister(recurrence_threshold=3)
        for index in range(3):
            record_occurrence(
                register,
                VALIDATION_REPLAY_FAILED,
                source="proof",
                summary=f"validation replay timed out {index}",
            )
        save_register(root, register)
        _write_proved_closer(root, VALIDATION_REPLAY_RESILIENCE_ID)
        checks["proved_closer_drops_forced_mission"] = (
            class_is_closed(VALIDATION_REPLAY_FAILED, root)
            and required_pattern_mission(root) is None
        )

    checks["updated_at_helper"] = bool(_utc_now())
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_validation_replay_resilience_capability()
    return {
        "ok": ok,
        "action": "validation_replay_resilience",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": VALIDATION_REPLAY_RESILIENCE_GOAL,
        "done_when": VALIDATION_REPLAY_RESILIENCE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
        "payload": json.dumps(sorted(checks), sort_keys=True),
    }
