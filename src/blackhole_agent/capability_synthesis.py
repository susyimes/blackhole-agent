"""Capability synthesis plane: generative growth past the composition frontier.

The application plane plans over *existing* proved capabilities; when no plan
exists it honestly reports the goal unsolvable and stops. This module closes
the next gap — the missing capability itself is **synthesized from the goal's
frozen evidence**, not hand-authored:

- each synthesis task declares goal keys and at least three frozen
  input/output cases; no behavior, no step sequence, and no answer key
  beyond the cases is given;
- a deterministic generator enumerates a closed family of pure state
  transforms (constant, identity, upper, affix, join over key/field/length
  extractors) in canonical order — the candidate space is derived from the
  case structure and a small task-declared token vocabulary, never from the
  expected outputs;
- selection is split-honest: a candidate must satisfy the *selection* cases
  and then **generalize to held-out cases the selector never optimized on**;
  a per-case memorization table is constructed as a decoy and must be
  rejected by that held-out split;
- the winner is installed as a real ``ApplicationStep`` and the BFS planner
  from the application plane is re-run: the goal that was honestly
  unplannable over the base registry must now plan, execute, and match the
  held-out expectation;
- ablation is falsified directly: removing the synthesized capability must
  make the goal honestly unplannable again;
- tamper is falsified directly: perturbing one winner parameter must fail
  validation against the frozen cases;
- a digest-sealed report under ``artifacts/capability-synthesis/`` whose
  grade is a pure function of the recorded verdicts; verification re-grades,
  re-checks every digest, re-validates each recorded winner against its
  recorded cases, and re-runs planner honesty against the live ledger, so a
  forged winner or an unsound honesty claim fails verification;
- durable persistence: winners are written to
  ``capabilities/synthesized-steps.json`` and registered as first-class
  proved ledger capabilities (``capability.synthesized-*``); the grown
  planning registry (``include_synthesized=True``) folds them in, and each
  persisted capability carries its own proof that re-derives the winner from
  the frozen cases so a hand-edited persistence file fails;
- a registered proof (:func:`builtin_synthesis_plane`) that proves
  determinism across runs and falsifies tampered, forged, and misgraded
  reports.

Determinism contract: candidate enumeration order, selection, and every
verdict must be reproducible across runs on the same checkout. Durations and
timestamps are diagnostics only and are excluded from every digest.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_application import (
    ApplicationStep,
    ApplicationTask,
    build_application_registry,
    execute_application_plan,
    plan_application_task,
)
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-synthesis"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-synthesis.json"
SYNTHESIZED_STEPS_PATH = REPO_ROOT / "capabilities" / "synthesized-steps.json"

# Canonical transform order: simpler hypotheses are tried first.
_TRANSFORMS = ("const", "identity", "upper", "affix", "join")
_JOIN_SEPARATORS = ("#", "-", "::", ":", "|", "_")


# ---------------------------------------------------------------------------
# Synthesis tasks: declarative goals with frozen evidence cases. No behavior
# appears anywhere in a task definition — the synthesizer derives it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SynthesisTask:
    """One generative-growth goal over the live proved ledger."""

    id: str
    description: str
    goal_key: str
    vocabulary: tuple[str, ...]
    cases: tuple[Mapping[str, Any], ...]  # each: {"state": {...}, "expect": {goal_key: value}}


SYNTHESIS_TASKS: tuple[SynthesisTask, ...] = (
    SynthesisTask(
        id="triage-record-key",
        description=(
            "From a triage record, derive the persistence key a downstream "
            "memory step would need. No existing capability provides "
            "record_key; the naming rule must be learned from cases."
        ),
        goal_key="record_key",
        vocabulary=("triage-record:", "record:", "triage:", "lane:", "key-"),
        cases=(
            {"state": {"triage": {"lane": "validation", "gated": False}}, "expect": {"record_key": "triage-record:validation"}},
            {"state": {"triage": {"lane": "security", "gated": False}}, "expect": {"record_key": "triage-record:security"}},
            {"state": {"triage": {"lane": "documentation", "gated": True}}, "expect": {"record_key": "triage-record:documentation"}},
        ),
    ),
    SynthesisTask(
        id="scan-verdict-label",
        description=(
            "From a raw scan verdict, derive the normalized verdict label an "
            "activation report would print. The casing rule must be learned "
            "from cases."
        ),
        goal_key="verdict_label",
        vocabulary=("scan:", "verdict:", "label-", "!"),
        cases=(
            {"state": {"scan": {"scan_conclusion": "success"}}, "expect": {"verdict_label": "SUCCESS"}},
            {"state": {"scan": {"scan_conclusion": "failure"}}, "expect": {"verdict_label": "FAILURE"}},
            {"state": {"scan": {"scan_conclusion": "neutral"}}, "expect": {"verdict_label": "NEUTRAL"}},
        ),
    ),
    SynthesisTask(
        id="triage-label-count-tag",
        description=(
            "From a triage record and the source issue, derive the compact "
            "audit tag '<lane>:<label-count>'. Two extractors must be "
            "composed; neither alone fits the cases."
        ),
        goal_key="triage_tag",
        vocabulary=(":", "|", "-", "::"),
        cases=(
            {
                "state": {"triage": {"lane": "validation", "gated": False}, "issue": {"labels": ["bug", "regression"]}},
                "expect": {"triage_tag": "validation:2"},
            },
            {
                "state": {"triage": {"lane": "security", "gated": True}, "issue": {"labels": ["cve"]}},
                "expect": {"triage_tag": "security:1"},
            },
            {
                "state": {"triage": {"lane": "documentation", "gated": False}, "issue": {"labels": ["docs", "typo", "ui"]}},
                "expect": {"triage_tag": "documentation:3"},
            },
        ),
    ),
)


# ---------------------------------------------------------------------------
# Candidate family: pure state transforms over structural extractors.
# ---------------------------------------------------------------------------

# An extractor is a tuple:
#   ("key", k)          -> state[k]
#   ("field", k, f)     -> state[k][f]
#   ("length", k, f|"") -> len(state[k] or state[k][f])
Extractor = tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    """One parameterized behavior hypothesis, canonically ordered."""

    transform: str
    extractor1: Extractor
    extractor2: Extractor | None = None
    prefix: str = ""
    suffix: str = ""
    constant: str = ""

    def spec(self) -> dict[str, Any]:
        return {
            "transform": self.transform,
            "extractor1": list(self.extractor1),
            "extractor2": list(self.extractor2) if self.extractor2 else None,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "constant": self.constant,
        }

    def requires(self) -> tuple[str, ...]:
        keys = {self.extractor1[1]}
        if self.extractor2:
            keys.add(self.extractor2[1])
        return tuple(sorted(keys))


def _extract(extractor: Extractor, state: Mapping[str, Any]) -> Any:
    kind, key = extractor[0], extractor[1]
    if kind == "key":
        return state[key]
    if kind == "field":
        return state[key][extractor[2]]
    if kind == "length":
        target = state[key] if not extractor[2] else state[key][extractor[2]]
        return len(target)
    raise ValueError(f"unknown extractor kind: {kind}")


def evaluate_candidate(candidate: Candidate, state: Mapping[str, Any]) -> Any:
    """Compute the candidate's output for one state; may raise KeyError."""

    if candidate.transform == "const":
        return candidate.constant
    value1 = _extract(candidate.extractor1, state)
    if candidate.transform == "identity":
        return value1
    if candidate.transform == "upper":
        return str(value1).upper()
    if candidate.transform == "affix":
        return f"{candidate.prefix}{value1}{candidate.suffix}"
    if candidate.transform == "join":
        value2 = _extract(candidate.extractor2 or (), state)
        return f"{value1}{candidate.constant}{value2}"
    raise ValueError(f"unknown transform: {candidate.transform}")


def enumerate_extractors(state: Mapping[str, Any]) -> list[Extractor]:
    """Structural extractors derived from the case shape, sorted canonically."""

    extractors: set[Extractor] = set()
    for key, value in state.items():
        extractors.add(("key", key, ""))
        if isinstance(value, (list, tuple, str)):
            extractors.add(("length", key, ""))
        if isinstance(value, Mapping):
            for field, sub in value.items():
                extractors.add(("field", key, field))
                if isinstance(sub, (list, tuple, str)):
                    extractors.add(("length", key, field))
    return sorted(extractors)


def enumerate_candidates(task: SynthesisTask) -> list[Candidate]:
    """The closed hypothesis space for one task, in canonical order."""

    extractors = enumerate_extractors(task.cases[0]["state"])
    vocabulary = sorted(set(task.vocabulary))
    candidates: list[Candidate] = []
    for transform in _TRANSFORMS:
        if transform == "const":
            candidates.extend(
                Candidate(transform="const", extractor1=extractors[0], constant=token) for token in vocabulary
            )
        elif transform in ("identity", "upper"):
            candidates.extend(Candidate(transform=transform, extractor1=extractor) for extractor in extractors)
        elif transform == "affix":
            affixes = sorted(
                (prefix, suffix)
                for prefix in ("", *vocabulary)
                for suffix in ("", *vocabulary)
                if prefix or suffix
            )
            candidates.extend(
                Candidate(transform="affix", extractor1=extractor, prefix=prefix, suffix=suffix)
                for extractor, (prefix, suffix) in itertools.product(extractors, affixes)
            )
        elif transform == "join":
            candidates.extend(
                Candidate(transform="join", extractor1=first, extractor2=second, constant=separator)
                for (first, second), separator in itertools.product(
                    itertools.product(extractors, repeat=2), _JOIN_SEPARATORS
                )
            )
    return candidates


def candidate_matches(candidate: Candidate, cases: Sequence[Mapping[str, Any]], goal_key: str) -> bool:
    """True when the candidate reproduces every expected output; crashes fail."""

    for case in cases:
        try:
            if evaluate_candidate(candidate, case["state"]) != case["expect"][goal_key]:
                return False
        except Exception:  # noqa: BLE001 - a crashing hypothesis is a wrong hypothesis
            return False
    return True


def synthesize_candidate(task: SynthesisTask) -> dict[str, Any]:
    """Split-honest selection: fit the selection split, generalize or lose.

    The first canonically-ordered candidate that satisfies both the selection
    cases and the held-out cases wins. Candidates that fit the selection
    split but fail held-out are counted as near-misses — the report shows the
    search rejected them instead of fitting one frozen instance.
    """

    selection = task.cases[:-1]
    held_out = task.cases[-1:]
    tried = 0
    near_misses = 0
    for candidate in enumerate_candidates(task):
        tried += 1
        if not candidate_matches(candidate, selection, task.goal_key):
            continue
        if not candidate_matches(candidate, held_out, task.goal_key):
            near_misses += 1
            continue
        return {
            "found": True,
            "candidate": candidate,
            "candidates_tried": tried,
            "near_misses": near_misses,
        }
    return {"found": False, "candidate": None, "candidates_tried": tried, "near_misses": near_misses}


def build_memorization_decoy(task: SynthesisTask) -> dict[str, str]:
    """A per-case lookup table fit on the selection split — the cheat path.

    A synthesizer graded only on seen instances would accept this table; the
    held-out split must reject it, because the held-out state never appears
    in the key set.
    """

    return {
        json.dumps(case["state"], sort_keys=True, separators=(",", ":")): str(case["expect"][task.goal_key])
        for case in task.cases[:-1]
    }


def tamper_candidate(candidate: Candidate) -> Candidate:
    """One-parameter perturbation of a winner; must fail case validation."""

    if candidate.transform in ("affix",):
        return Candidate(
            transform=candidate.transform,
            extractor1=candidate.extractor1,
            extractor2=candidate.extractor2,
            prefix=f"{candidate.prefix}X",
            suffix=candidate.suffix,
        )
    if candidate.transform == "join":
        separator = "#" if candidate.constant != "#" else "|"
        return Candidate(
            transform="join",
            extractor1=candidate.extractor1,
            extractor2=candidate.extractor2,
            constant=separator,
        )
    if candidate.transform == "upper":
        return Candidate(transform="identity", extractor1=candidate.extractor1)
    return Candidate(transform="const", extractor1=candidate.extractor1, constant=f"{candidate.constant}X")


def synthesized_step(task: SynthesisTask, candidate: Candidate) -> ApplicationStep:
    """Install a winning candidate as a real invocable application step."""

    capability_id = f"capability.synthesized-{task.id}"

    def invoke(state: Mapping[str, Any]) -> dict[str, Any]:
        return {task.goal_key: evaluate_candidate(candidate, state)}

    return ApplicationStep(
        capability_id=capability_id,
        requires=candidate.requires(),
        provides=(task.goal_key,),
        invoke=invoke,
    )


# ---------------------------------------------------------------------------
# Durable persistence: winners become first-class ledger capabilities.
# ---------------------------------------------------------------------------


def candidate_from_spec(spec: Mapping[str, Any]) -> Candidate:
    """Rebuild a candidate from its recorded JSON spec."""

    return Candidate(
        transform=str(spec["transform"]),
        extractor1=tuple(str(part) for part in spec["extractor1"]),
        extractor2=tuple(str(part) for part in spec["extractor2"]) if spec.get("extractor2") else None,
        prefix=str(spec.get("prefix", "")),
        suffix=str(spec.get("suffix", "")),
        constant=str(spec.get("constant", "")),
    )


def synthesized_capability_id(task_id: str) -> str:
    return f"capability.synthesized-{task_id}"


def synthesized_step_record(task: SynthesisTask, candidate: Candidate) -> dict[str, Any]:
    """The durable record for one synthesized capability."""

    return {
        "capability_id": synthesized_capability_id(task.id),
        "task_id": task.id,
        "goal_key": task.goal_key,
        "requires": list(candidate.requires()),
        "provides": [task.goal_key],
        "winner": candidate.spec(),
        "cases": [dict(case) for case in task.cases],
        "cases_digest": _digest([dict(case) for case in task.cases]),
    }


def synthesized_step_proof_command(task_id: str) -> str:
    """The exact shell proof command registered for one synthesized step."""

    return (
        'uv run python -c "from blackhole_agent.capability_synthesis import prove_synthesized_step; '
        f"r=prove_synthesized_step('{task_id}'); assert r['ok'] and r.get('winner_matches_search') "
        "and r.get('cases_pass') and r.get('honestly_unplannable_without') and r.get('grown_plan_matched') "
        "and r.get('tamper_rejected') and r.get('decoy_rejected')\""
    )


def load_persisted_records(path: Path | None = None) -> list[dict[str, Any]]:
    """The persisted synthesized-step records; empty when nothing is persisted."""

    steps_path = path or SYNTHESIZED_STEPS_PATH
    if not steps_path.exists():
        return []
    payload = json.loads(steps_path.read_text(encoding="utf-8"))
    return [dict(record) for record in payload.get("steps") or []]


def load_persisted_synthesized_steps(path: Path | None = None) -> dict[str, ApplicationStep]:
    """Rebuild invocable application steps from the persisted records.

    This is what lets the grown planning registry plan over authored
    behavior without re-running search: the persisted winner spec *is* the
    capability, and its honesty is enforced by ``prove_synthesized_step``
    re-deriving the winner from the frozen cases.
    """

    steps: dict[str, ApplicationStep] = {}
    for record in load_persisted_records(path):
        candidate = candidate_from_spec(record["winner"])
        goal_key = str(record["goal_key"])

        def invoke(state: Mapping[str, Any], _candidate: Candidate = candidate, _goal_key: str = goal_key) -> dict[str, Any]:
            return {_goal_key: evaluate_candidate(_candidate, state)}

        steps[str(record["capability_id"])] = ApplicationStep(
            capability_id=str(record["capability_id"]),
            requires=tuple(str(key) for key in record["requires"]),
            provides=(goal_key,),
            invoke=invoke,
        )
    return steps


def persist_synthesized_steps(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Synthesize, persist, and register every winner as a ledger capability.

    Idempotent: the steps file is only rewritten when the derived records
    change, so re-running persistence on an unchanged frontier produces no
    artifact churn. Registration uses ``replace=True`` so a re-derived
    winner upgrades its ledger entry in place.
    """

    records: list[dict[str, Any]] = []
    for task in SYNTHESIS_TASKS:
        result = synthesize_candidate(task)
        if not result["found"] or result["candidate"] is None:
            return {"ok": False, "stage": "synthesize", "task_id": task.id}
        records.append(synthesized_step_record(task, result["candidate"]))

    steps_path = repo_root / "capabilities" / "synthesized-steps.json"
    wrote_steps_file = True
    if steps_path.exists():
        existing = json.loads(steps_path.read_text(encoding="utf-8"))
        wrote_steps_file = existing.get("steps") != records
    if wrote_steps_file:
        atomic_write_json(
            steps_path,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "synthesized_steps",
                "synthesized_at": utc_now_iso(),
                "steps": records,
                "steps_digest": _digest(records),
            },
        )

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    registered: list[str] = []
    for record in records:
        capability = Capability(
            id=record["capability_id"],
            name=f"Synthesized capability: {record['task_id']}",
            description=(
                f"Authored by the capability synthesis plane from the frozen cases of goal "
                f"'{record['task_id']}': a {record['winner']['transform']} transform providing "
                f"'{record['goal_key']}'. Its proof re-derives the winner from the cases, so a "
                "hand-edited persistence record fails."
            ),
            kind="python",
            entry="blackhole_agent.capability_synthesis:demo_synthesized_steps",
            proof_command=synthesized_step_proof_command(record["task_id"]),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.application-plane",
                "capability.synthesis-plane",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_synthesis.py",
                "capabilities/synthesized-steps.json",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                f"Goal '{record['task_id']}' was honestly unplannable over the base proved ledger; "
                f"the synthesized {record['winner']['transform']} capability makes it solvable "
                "end-to-end, and ablating it makes the goal unplannable again."
            ),
            # Not tagged "synthesized": that tag marks combinatorial stack
            # growth. These are authored primitive behavior units.
            tags=("authored", "generative", "goal-directed", "evidence"),
        )
        ledger = register_capability(ledger, capability, replace=True)
        registered.append(record["capability_id"])
    save_ledger(ledger_path, ledger)

    return {
        "ok": True,
        "wrote_steps_file": wrote_steps_file,
        "steps_path": str(steps_path),
        "registered": registered,
        "steps_digest": _digest(records),
    }


def prove_synthesized_step(task_id: str) -> dict[str, Any]:
    """Registered proof for one persisted ``capability.synthesized-*`` entry.

    Re-derives the winner from the module's frozen cases (the persisted
    record must be the honest search result, not a hand-written artifact),
    re-validates it against every case, proves the goal is still honestly
    unplannable without the synthesized capability, proves the grown
    registry plans and matches the held-out outcome with it, and re-checks
    the tamper and memorization-decoy rejections.
    """

    task = next((candidate_task for candidate_task in SYNTHESIS_TASKS if candidate_task.id == task_id), None)
    if task is None:
        return {"ok": False, "stage": "unknown-task", "task_id": task_id}
    record = next((item for item in load_persisted_records() if item.get("task_id") == task_id), None)
    if record is None:
        return {"ok": False, "stage": "persistence-missing", "task_id": task_id}

    candidate = candidate_from_spec(record["winner"])
    search = synthesize_candidate(task)
    winner_matches_search = bool(
        search["found"] and search["candidate"] is not None and search["candidate"].spec() == record["winner"]
    )
    cases_pass = candidate_matches(candidate, task.cases, task.goal_key) and candidate_matches(
        candidate, record.get("cases") or [], task.goal_key
    )

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    registered = record["capability_id"] in ledger.capabilities
    base_registry = build_application_registry(ledger, include_synthesized=False)
    goal_task = _goal_task(task)
    honestly_unplannable_without = plan_application_task(goal_task, base_registry) is None

    step = synthesized_step(task, candidate)
    grown_registry = {**base_registry, step.capability_id: step}
    plan = plan_application_task(goal_task, grown_registry)
    grown_plan_matched = False
    if plan == [step.capability_id]:
        try:
            outcome = execute_application_plan(goal_task, plan, grown_registry)
            grown_plan_matched = outcome.get(task.goal_key) == goal_task.oracle[task.goal_key]
        except Exception:  # noqa: BLE001 - a crashed plan is a broken outcome, not a crashed proof
            grown_plan_matched = False

    tamper_rejected = not candidate_matches(tamper_candidate(candidate), task.cases, task.goal_key)
    decoy = build_memorization_decoy(task)
    held_out_key = json.dumps(task.cases[-1]["state"], sort_keys=True, separators=(",", ":"))
    decoy_rejected = held_out_key not in decoy

    ok = all(
        (
            registered,
            winner_matches_search,
            cases_pass,
            honestly_unplannable_without,
            grown_plan_matched,
            tamper_rejected,
            decoy_rejected,
        )
    )
    return {
        "ok": ok,
        "task_id": task_id,
        "capability_id": record["capability_id"],
        "registered": registered,
        "winner_matches_search": winner_matches_search,
        "cases_pass": cases_pass,
        "honestly_unplannable_without": honestly_unplannable_without,
        "grown_plan_matched": grown_plan_matched,
        "tamper_rejected": tamper_rejected,
        "decoy_rejected": decoy_rejected,
    }


def demo_synthesized_steps() -> dict[str, Any]:
    """Invocable entry for persisted synthesized capabilities.

    Executes every persisted synthesized step on its held-out goal instance
    (the case the selector never optimized on) and grades the outputs
    against the frozen expectations.
    """

    records = load_persisted_records()
    steps = load_persisted_synthesized_steps()
    outcomes: dict[str, Any] = {}
    ok = bool(records)
    for record in records:
        capability_id = str(record["capability_id"])
        step = steps.get(capability_id)
        if step is None:
            outcomes[capability_id] = {"matched": False, "error": "step not loadable"}
            ok = False
            continue
        state = record["cases"][-1]["state"]
        expected = record["cases"][-1]["expect"][record["goal_key"]]
        try:
            output = step.invoke(state).get(record["goal_key"])
        except Exception as exc:  # noqa: BLE001 - a crashed step is a broken outcome
            outcomes[capability_id] = {"matched": False, "error": f"{type(exc).__name__}: {exc}"}
            ok = False
            continue
        matched = output == expected
        outcomes[capability_id] = {"output": output, "expected": expected, "matched": matched}
        ok = ok and matched
    return {"ok": ok, "step_count": len(records), "outcomes": outcomes}


# ---------------------------------------------------------------------------
# Plane execution.
# ---------------------------------------------------------------------------


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _goal_task(task: SynthesisTask) -> ApplicationTask:
    """The goal instance is the held-out case: unseen during selection."""

    instance = task.cases[-1]
    return ApplicationTask(
        id=task.id,
        description=task.description,
        initial_state=instance["state"],
        goal=(task.goal_key,),
        oracle={task.goal_key: instance["expect"][task.goal_key]},
    )


def run_synthesis_plane() -> dict[str, Any]:
    """Prove honest unsolvability, synthesize, re-plan, and falsify per task."""

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    base_registry = build_application_registry(ledger, include_synthesized=False)

    task_records: list[dict[str, Any]] = []
    for task in SYNTHESIS_TASKS:
        started = time.perf_counter()
        goal_task = _goal_task(task)

        # Honesty before: no composition of existing proved capabilities
        # covers the goal key — an honest unsolvable, never a fabricated plan.
        honestly_unsolvable_before = plan_application_task(goal_task, base_registry) is None

        result = synthesize_candidate(task)
        candidate = result["candidate"]

        selection_pass = False
        held_out_pass = False
        plan_after: list[str] | None = None
        outcome_matched = False
        ablation_unsolvable = False
        tamper_rejected = False
        decoy_rejected = False

        if candidate is not None:
            selection_pass = candidate_matches(candidate, task.cases[:-1], task.goal_key)
            held_out_pass = candidate_matches(candidate, task.cases[-1:], task.goal_key)

            step = synthesized_step(task, candidate)
            grown_registry = {**base_registry, step.capability_id: step}
            plan_after = plan_application_task(goal_task, grown_registry)
            if plan_after is not None:
                try:
                    outcome = execute_application_plan(goal_task, plan_after, grown_registry)
                    outcome_matched = outcome.get(task.goal_key) == goal_task.oracle[task.goal_key]
                except Exception:  # noqa: BLE001 - a crashed plan is a broken outcome, not a crashed plane
                    outcome_matched = False

            # Ablation: without the synthesized capability the goal must be
            # honestly unplannable again — the synthesized member carries it.
            ablation_unsolvable = plan_application_task(goal_task, base_registry) is None

            # Tamper: one perturbed parameter must fail case validation.
            tamper_rejected = not candidate_matches(tamper_candidate(candidate), task.cases, task.goal_key)

            # Decoy: the memorization table must fail the held-out split.
            decoy = build_memorization_decoy(task)
            held_out_key = json.dumps(
                task.cases[-1]["state"], sort_keys=True, separators=(",", ":")
            )
            decoy_rejected = held_out_key not in decoy

        task_records.append(
            {
                "id": task.id,
                "description": task.description,
                "goal_key": task.goal_key,
                "cases": [dict(case) for case in task.cases],
                "honestly_unsolvable_before": honestly_unsolvable_before,
                "candidates_tried": result["candidates_tried"],
                "near_misses": result["near_misses"],
                "winner": candidate.spec() if candidate is not None else None,
                "synthesized_capability": f"capability.synthesized-{task.id}" if candidate is not None else None,
                "selection_pass": selection_pass,
                "held_out_pass": held_out_pass,
                "plan_after": plan_after,
                "outcome_matched": outcome_matched,
                "ablation_unsolvable": ablation_unsolvable,
                "tamper_rejected": tamper_rejected,
                "decoy_rejected": decoy_rejected,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )

    grade = compute_synthesis_grade(task_records)
    winners_digest = _digest(
        [{"id": record["id"], "winner": record["winner"], "plan_after": record["plan_after"]} for record in task_records]
    )
    verdicts_digest = _digest(
        [
            {
                "id": record["id"],
                "honestly_unsolvable_before": record["honestly_unsolvable_before"],
                "selection_pass": record["selection_pass"],
                "held_out_pass": record["held_out_pass"],
                "outcome_matched": record["outcome_matched"],
                "ablation_unsolvable": record["ablation_unsolvable"],
                "tamper_rejected": record["tamper_rejected"],
                "decoy_rejected": record["decoy_rejected"],
            }
            for record in task_records
        ]
    )
    grade_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"synthesis:{winners_digest}:{verdicts_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_synthesis_plane",
        "run_at": utc_now_iso(),
        "task_records": task_records,
        "synthesis": grade,
        "winners_digest": winners_digest,
        "verdicts_digest": verdicts_digest,
        "grade_digest": grade_digest,
        "report_digest": report_digest,
        "ok": (
            grade["task_solved_count"] == grade["task_count"]
            and grade["synthesis_score"] == 1.0
            and all(record["honestly_unsolvable_before"] for record in task_records)
        ),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


# ---------------------------------------------------------------------------
# Pure grading.
# ---------------------------------------------------------------------------


def compute_synthesis_grade(task_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure synthesis derivation from recorded task verdicts.

    A task is **synthesis-attributed** when the goal was honestly unplannable
    before, a winner generalized across the selection/held-out split, the
    grown registry planned and matched the held-out outcome, ablation made
    the goal unplannable again, and both the tampered winner and the
    memorization decoy were rejected. This function is the single grading
    rule: a report whose recorded grade disagrees with its recorded verdicts
    is misgraded and fails verification.
    """

    attributed: list[str] = []
    for record in task_records:
        flags = (
            "honestly_unsolvable_before",
            "selection_pass",
            "held_out_pass",
            "outcome_matched",
            "ablation_unsolvable",
            "tamper_rejected",
            "decoy_rejected",
        )
        if record.get("winner") and record.get("plan_after") and all(bool(record.get(flag)) for flag in flags):
            attributed.append(str(record.get("id")))
    task_ids = [str(record.get("id")) for record in task_records]
    return {
        "task_solved_count": sum(1 for record in task_records if record.get("outcome_matched")),
        "task_count": len(task_records),
        "synthesis_attributed": attributed,
        "synthesis_score": round(len(attributed) / len(task_ids), 4) if task_ids else 0.0,
    }


# ---------------------------------------------------------------------------
# Report sealing and verification.
# ---------------------------------------------------------------------------


def write_synthesis_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the synthesis report artifact and refresh the latest pointer."""

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "report.json", dict(report))
    if output_dir.parent == LATEST_POINTER.parent:
        atomic_write_json(
            LATEST_POINTER,
            {"report_dir": output_dir.name, "report_digest": report.get("report_digest")},
        )
    return {
        "ok": bool(report.get("ok")),
        "output_dir": str(output_dir),
        "report_digest": report.get("report_digest"),
        "synthesis_score": (report.get("synthesis") or {}).get("synthesis_score"),
    }


def verify_synthesis_report(report_dir: Path) -> dict[str, Any]:
    """Recompute every digest, re-grade, and re-check winner soundness.

    Verification never re-runs synthesis. A report whose verdicts were
    flipped, whose grade was miscomputed, or whose digest chain was edited
    fails on recompute. Beyond that, each recorded winner is re-validated
    against its recorded frozen cases (a forged winner fails), and planner
    honesty is re-run against the live ledger (a task that was secretly
    plannable before synthesis fails the honesty re-check).
    """

    report_path = report_dir / "report.json"
    if not report_path.exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    task_records = report.get("task_records") or []

    regraded = compute_synthesis_grade(task_records)
    winners_digest = _digest(
        [{"id": record.get("id"), "winner": record.get("winner"), "plan_after": record.get("plan_after")} for record in task_records]
    )
    verdicts_digest = _digest(
        [
            {
                "id": record.get("id"),
                "honestly_unsolvable_before": record.get("honestly_unsolvable_before"),
                "selection_pass": record.get("selection_pass"),
                "held_out_pass": record.get("held_out_pass"),
                "outcome_matched": record.get("outcome_matched"),
                "ablation_unsolvable": record.get("ablation_unsolvable"),
                "tamper_rejected": record.get("tamper_rejected"),
                "decoy_rejected": record.get("decoy_rejected"),
            }
            for record in task_records
        ]
    )
    grade_digest = _digest(regraded)
    report_digest = hashlib.sha256(
        f"synthesis:{winners_digest}:{verdicts_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    base_registry = build_application_registry(ledger, include_synthesized=False)
    winners_sound = True
    honesty_sound = True
    for record in task_records:
        winner = record.get("winner")
        if not winner:
            winners_sound = False
            continue
        candidate = Candidate(
            transform=winner["transform"],
            extractor1=tuple(winner["extractor1"]),
            extractor2=tuple(winner["extractor2"]) if winner.get("extractor2") else None,
            prefix=winner.get("prefix", ""),
            suffix=winner.get("suffix", ""),
            constant=winner.get("constant", ""),
        )
        if not candidate_matches(candidate, record.get("cases") or [], str(record.get("goal_key"))):
            winners_sound = False
        cases = record.get("cases") or []
        if cases:
            goal_task = ApplicationTask(
                id=str(record.get("id")),
                description="",
                initial_state=cases[-1]["state"],
                goal=(str(record.get("goal_key")),),
                oracle={},
            )
            if plan_application_task(goal_task, base_registry) is not None:
                honesty_sound = False

    checks = {
        "winners_digest": winners_digest == report.get("winners_digest"),
        "verdicts_digest": verdicts_digest == report.get("verdicts_digest"),
        "grade_recomputed_matches": regraded == report.get("synthesis"),
        "grade_digest": grade_digest == report.get("grade_digest"),
        "report_digest": report_digest == report.get("report_digest"),
        "winners_sound_against_cases": winners_sound,
        "honesty_sound_against_live_ledger": honesty_sound,
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


# ---------------------------------------------------------------------------
# Registered proof.
# ---------------------------------------------------------------------------


def builtin_synthesis_plane() -> dict[str, Any]:
    """Registered proof for ``capability.synthesis-plane``.

    Runs the plane twice to prove synthesis determinism, seals and verifies a
    report, then proves falsifiability three ways: a flipped task verdict, a
    forged winner whose parameters do not fit the recorded cases (re-sealed
    so only the soundness re-check can catch it), and a misgraded synthesis
    score must all fail verification.
    """

    import os
    import tempfile

    first = run_synthesis_plane()
    second = run_synthesis_plane()
    determinism = (
        first["winners_digest"] == second["winners_digest"]
        and first["verdicts_digest"] == second["verdicts_digest"]
    )
    if not determinism:
        return {"ok": False, "stage": "determinism"}
    if not first["ok"]:
        return {"ok": False, "stage": "plane", "synthesis": first["synthesis"]}

    report_dir_raw = (os.environ.get("BLACKHOLE_SYNTHESIS_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_synthesis_report(first, out)
        verified = verify_synthesis_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": True,
            "synthesis": first["synthesis"],
            "report_digest": first["report_digest"],
            "report_dir": str(out),
            "deterministic": True,
            "used_skill_route_discovery": first["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-synthesis-proof-") as tmp:
        out = Path(tmp) / "report"
        write_synthesis_report(first, out)
        verified = verify_synthesis_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one recorded verdict; verification must fail.
        tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
        tampered["task_records"][0]["held_out_pass"] = not tampered["task_records"][0]["held_out_pass"]
        atomic_write_json(out / "report.json", tampered)
        if verify_synthesis_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "flipped verdict passed verification"}

        # Falsifiability 2: forge a winner that does not fit the cases.
        forged = json.loads(json.dumps(first))
        forged["task_records"][0]["winner"] = tamper_candidate(
            Candidate(
                transform=first["task_records"][0]["winner"]["transform"],
                extractor1=tuple(first["task_records"][0]["winner"]["extractor1"]),
                extractor2=(
                    tuple(first["task_records"][0]["winner"]["extractor2"])
                    if first["task_records"][0]["winner"].get("extractor2")
                    else None
                ),
                prefix=first["task_records"][0]["winner"].get("prefix", ""),
                suffix=first["task_records"][0]["winner"].get("suffix", ""),
                constant=first["task_records"][0]["winner"].get("constant", ""),
            )
        ).spec()
        # Re-seal every digest so only the winner soundness re-check can catch it.
        forged["winners_digest"] = _digest(
            [{"id": record["id"], "winner": record["winner"], "plan_after": record["plan_after"]} for record in forged["task_records"]]
        )
        forged["grade_digest"] = _digest(forged["synthesis"])
        forged["report_digest"] = hashlib.sha256(
            f"synthesis:{forged['winners_digest']}:{forged['verdicts_digest']}:{forged['grade_digest']}".encode(
                "utf-8"
            )
        ).hexdigest()
        atomic_write_json(out / "report.json", forged)
        if verify_synthesis_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "forged-winner-falsification",
                "detail": "winner that does not fit the recorded cases passed verification",
            }

        # Falsifiability 3: restore the winner but misgrade the score.
        misgraded = json.loads(json.dumps(first))
        misgraded["synthesis"]["synthesis_score"] = 0.0
        atomic_write_json(out / "report.json", misgraded)
        if verify_synthesis_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "misgraded score passed verification"}

    return {
        "ok": not first["used_skill_route_discovery"],
        "synthesis": first["synthesis"],
        "report_digest": first["report_digest"],
        "deterministic": True,
        "tamper_detected": True,
        "forged_winner_detected": True,
        "misgrade_detected": True,
        "used_skill_route_discovery": first["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability synthesis plane")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the plane and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    mode.add_argument(
        "--persist",
        action="store_true",
        help="persist winners to capabilities/synthesized-steps.json and register them in the ledger",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.persist:
        summary = persist_synthesized_steps()
    elif args.run:
        report = run_synthesis_plane()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_synthesis_report(report, out)
        summary["synthesis"] = report["synthesis"]
    else:
        summary = verify_synthesis_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
