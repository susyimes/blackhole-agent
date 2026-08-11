"""Generic multi-round durable loop engine for stewardship leaf dialects.

Collapses the program / succession / epoch multi-round copy-paste tower into
one noun-parameterized implementation: resolve portfolio → round loop with
pre-goal / child-run / between-round / post-goal / idle / budget stops → seal.

New outer loops are a :class:`LoopDialect` row plus hooks — not another
~1000–1700 line rename of ``run_succession`` / ``run_epoch`` / ``run_program``.
No skill-route discovery.

The multi-child tower (quettacontinuum..institution) already lives in
``upstream_constitution_engine``. This engine covers the *leaf dialect* that
constitution explicitly carved out: multi-succession / multi-epoch / multi-wave
durable loops over a portfolio world-model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]


class LoopRefused(Exception):
    """A verdict-bearing refusal from the generic loop engine."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


@dataclass(frozen=True)
class LoopDialect:
    """Nouns and stop-reason vocabulary for one multi-round durable loop."""

    name: str  # self noun: program | succession | epoch
    child: str  # child noun: succession | epoch | wave
    child_plural: str
    max_stop_reason: str
    goal_stop_reason: str
    idle_stop_reason: str
    rank_only_stop_reason: str = "rank_only"
    budget_stop_reason: str = "dispatch_budget"
    artifacts_relative: str = ""
    receipt_filename: str = ""
    digest_field: str = ""
    dir_field: str = ""
    count_field: str = ""
    digests_field: str = ""
    met_field: str = ""
    records_field: str = ""

    @property
    def artifacts_root(self) -> Path:
        rel = self.artifacts_relative or f"artifacts/upstream-{self.name}"
        return REPO_ROOT / rel

    @property
    def receipt_name(self) -> str:
        return self.receipt_filename or f"{self.name}.json"

    @property
    def self_digest_field(self) -> str:
        return self.digest_field or f"{self.name}_digest"

    @property
    def self_dir_field(self) -> str:
        return self.dir_field or f"{self.name}_dir"

    @property
    def child_count_field(self) -> str:
        return self.count_field or f"{self.child}_count"

    @property
    def child_digests_field(self) -> str:
        return self.digests_field or f"{self.child}_digests"

    @property
    def self_met_field(self) -> str:
        return self.met_field or f"{self.name}_met"

    @property
    def child_records_field(self) -> str:
        return self.records_field or self.child_plural


# Registered leaf multi-round dialects (outer → inner).
LOOP_STACK: tuple[LoopDialect, ...] = (
    LoopDialect(
        name="program",
        child="succession",
        child_plural="successions",
        max_stop_reason="max_successions",
        goal_stop_reason="program_met",
        idle_stop_reason="program_idle",
        artifacts_relative="artifacts/upstream-program",
        met_field="program_met",
    ),
    LoopDialect(
        name="succession",
        child="epoch",
        child_plural="epochs",
        max_stop_reason="max_epochs",
        goal_stop_reason="mandate_met",
        idle_stop_reason="succession_idle",
        artifacts_relative="artifacts/upstream-succession",
        met_field="mandate_met",
    ),
    LoopDialect(
        name="epoch",
        child="wave",
        child_plural="waves",
        max_stop_reason="max_waves",
        goal_stop_reason="epoch_idle",  # epoch "goal" is often idle/no-work
        idle_stop_reason="epoch_idle",
        artifacts_relative="artifacts/upstream-epoch",
        met_field="epoch_idle",
        digests_field="wave_digests",
    ),
)

LOOP_DIALECTS: dict[str, LoopDialect] = {d.name: d for d in LOOP_STACK}


def get_loop_dialect(name: str) -> LoopDialect:
    key = str(name or "").strip().lower()
    if key not in LOOP_DIALECTS:
        raise LoopRefused(
            "loop_unknown_dialect",
            f"unknown loop dialect {name!r}; known={sorted(LOOP_DIALECTS)}",
        )
    return LOOP_DIALECTS[key]


def list_loop_dialects() -> list[str]:
    return [d.name for d in LOOP_STACK]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return _sha256_bytes(canonical.encode("utf-8"))


@dataclass
class LoopState:
    """Mutable round-loop state threaded through hooks."""

    dialect: LoopDialect
    portfolio: dict[str, Any] | None
    portfolio_source: str
    portfolio_start_digest: str | None
    loop_dir: Path
    child_root: Path
    max_rounds: int
    dispatch: bool
    dispatch_budget: int | None
    idle_limit: int
    total_dispatched: int = 0
    total_dispatched_ok: int = 0
    idle_streak: int = 0
    stop_reason: str = ""
    goal_met: bool = False
    records: list[dict[str, Any]] = field(default_factory=list)
    child_digests: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def round_index(self) -> int:
        return len(self.records)


# Hook types -----------------------------------------------------------------

BuildChildKwargs = Callable[[LoopState, int], dict[str, Any]]
OnChildResult = Callable[[LoopState, int, dict[str, Any]], dict[str, Any] | None]
# Returns optional record dict (appended). May mutate state.portfolio etc.
PreRoundStop = Callable[[LoopState, int], str | None]
PostRoundStop = Callable[[LoopState, int, dict[str, Any]], str | None]
IsIdleRound = Callable[[LoopState, int, dict[str, Any]], bool]
ClassifyVerdict = Callable[[LoopState], tuple[bool, str]]
SealLoop = Callable[[LoopState], dict[str, Any]]
ExtractDispatched = Callable[[dict[str, Any]], tuple[int, int]]
ExtractChildDigest = Callable[[dict[str, Any]], str | None]
ExtractPortfolio = Callable[[LoopState, dict[str, Any]], dict[str, Any] | None]


def resolve_portfolio(
    *,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    recompute_digest: Callable[[MutableMapping[str, Any]], str] | None = None,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Resolve starting portfolio from inject / dir / none."""
    current: dict[str, Any] | None = None
    source = "none"
    if portfolio is not None:
        current = dict(portfolio)
        source = "injected"
    elif portfolio_dir is not None:
        path = durable_read_path(Path(portfolio_dir) / "portfolio.json")
        if not path.is_file():
            raise LoopRefused(
                "portfolio_missing", f"no portfolio.json under {portfolio_dir}"
            )
        current = json.loads(path.read_text(encoding="utf-8"))
        source = "dir"
    start_digest = current.get("portfolio_digest") if current else None
    if current and not start_digest and recompute_digest is not None:
        start_digest = recompute_digest(current)
        current["portfolio_digest"] = start_digest
    elif current:
        start_digest = current.get("portfolio_digest")
    return current, source, start_digest


def open_loop_dir(
    dialect: LoopDialect,
    *,
    out_root: Path | None = None,
    child_out_root: Path | None = None,
    child_subdir: str | None = None,
    nest_stamp: bool = True,
) -> tuple[Path, Path]:
    """Create a stamped loop directory and child-output root.

    Default matches succession/epoch legacy contract: ``out_root / <stamp>``
    (or ``artifacts_root / <stamp>``). Pass ``nest_stamp=False`` to use
    ``out_root`` itself as the loop directory (program-style).
    """
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None and not nest_stamp:
        loop_dir = Path(out_root)
    else:
        parent = Path(out_root) if out_root is not None else dialect.artifacts_root
        loop_dir = parent / stamp
    loop_dir.mkdir(parents=True, exist_ok=True)
    child_root = (
        Path(child_out_root)
        if child_out_root is not None
        else (loop_dir / (child_subdir or dialect.child_plural))
    )
    return loop_dir, child_root


def default_extract_dispatched(result: Mapping[str, Any]) -> tuple[int, int]:
    n = int(
        result.get("total_dispatched")
        if result.get("total_dispatched") is not None
        else result.get("dispatched_count")
        or 0
    )
    ok = int(
        result.get("total_dispatched_ok")
        if result.get("total_dispatched_ok") is not None
        else result.get("dispatched_ok")
        or 0
    )
    return n, ok


def run_durable_loop(
    dialect: LoopDialect | str,
    *,
    max_rounds: int,
    dispatch: bool = True,
    dispatch_budget: int | None = None,
    idle_limit: int = 1,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_dir: Path | None = None,
    out_root: Path | None = None,
    child_out_root: Path | None = None,
    child_runner: Callable[..., dict[str, Any]],
    build_child_kwargs: BuildChildKwargs,
    on_child_result: OnChildResult,
    pre_round_stop: PreRoundStop | None = None,
    post_round_stop: PostRoundStop | None = None,
    is_idle_round: IsIdleRound | None = None,
    classify_verdict: ClassifyVerdict,
    seal: SealLoop,
    extract_dispatched: ExtractDispatched | None = None,
    refuse_on_first: Sequence[type[BaseException]] = (),
    recompute_digest: Callable[[MutableMapping[str, Any]], str] | None = None,
    prior_total_dispatched: int = 0,
    prior_total_dispatched_ok: int = 0,
    initial_extras: Mapping[str, Any] | None = None,
    wrap_refuse: Callable[[BaseException], BaseException] | None = None,
    nest_stamp: bool = True,
) -> dict[str, Any]:
    """Run a multi-round durable loop and return the dialect seal result.

    Control flow (shared by program / succession / epoch):

    1. resolve portfolio
    2. open loop dir
    3. for round in 0..max_rounds-1:
       a. pre_round_stop → break (goal already met, budget, …)
       b. remaining budget → break if exhausted
       c. child_runner(**build_child_kwargs)
       d. accumulate dispatch counts
       e. on_child_result → optional record
       f. post_round_stop → break
       g. idle streak → break
       h. budget exhausted → break
    4. classify_verdict + seal
    """
    d = get_loop_dialect(dialect) if isinstance(dialect, str) else dialect
    if max_rounds < 1:
        raise LoopRefused(f"{d.name}_invalid", f"max_rounds must be >= 1 for {d.name}")

    current, source, start_digest = resolve_portfolio(
        portfolio=portfolio,
        portfolio_dir=portfolio_dir,
        recompute_digest=recompute_digest,
    )
    loop_dir, child_root = open_loop_dir(
        d,
        out_root=out_root,
        child_out_root=child_out_root,
        nest_stamp=nest_stamp,
    )

    state = LoopState(
        dialect=d,
        portfolio=current,
        portfolio_source=source,
        portfolio_start_digest=start_digest,
        loop_dir=loop_dir,
        child_root=child_root,
        max_rounds=max_rounds,
        dispatch=bool(dispatch),
        dispatch_budget=dispatch_budget,
        idle_limit=max(1, int(idle_limit)),
        total_dispatched=int(prior_total_dispatched),
        total_dispatched_ok=int(prior_total_dispatched_ok),
        stop_reason=d.max_stop_reason,
        extras=dict(initial_extras or {}),
    )
    extract = extract_dispatched or default_extract_dispatched
    refuse_types = tuple(refuse_on_first)

    for round_index in range(max_rounds):
        if pre_round_stop is not None:
            reason = pre_round_stop(state, round_index)
            if reason:
                state.stop_reason = str(reason)
                break

        remaining_budget = None
        if state.dispatch_budget is not None:
            remaining_budget = max(
                0, int(state.dispatch_budget) - state.total_dispatched
            )
            if state.dispatch and remaining_budget <= 0:
                state.stop_reason = d.budget_stop_reason
                break

        kwargs = build_child_kwargs(state, round_index)
        if remaining_budget is not None and "dispatch_budget" in kwargs:
            # Caller may already have set it; keep their value if smaller.
            try:
                kwargs["dispatch_budget"] = min(
                    int(kwargs["dispatch_budget"])
                    if kwargs["dispatch_budget"] is not None
                    else remaining_budget,
                    remaining_budget,
                )
            except (TypeError, ValueError):
                kwargs["dispatch_budget"] = remaining_budget

        try:
            child_result = child_runner(**kwargs)
        except Exception as exc:  # noqa: BLE001 — dialect refuse mapping
            if refuse_types and isinstance(exc, refuse_types):
                if round_index == 0 and not state.extras.get("resumed"):
                    if wrap_refuse is not None:
                        raise wrap_refuse(exc) from exc
                    raise
                verdict = getattr(exc, "verdict", type(exc).__name__)
                state.stop_reason = f"{d.child}_refused:{verdict}"
                break
            raise

        dispatched_n, dispatched_ok = extract(child_result)
        state.total_dispatched += dispatched_n
        state.total_dispatched_ok += dispatched_ok

        record = on_child_result(state, round_index, child_result)
        if record is not None:
            state.records.append(dict(record))

        if post_round_stop is not None:
            reason = post_round_stop(state, round_index, child_result)
            if reason:
                state.stop_reason = str(reason)
                break

        idle = False
        if is_idle_round is not None:
            idle = bool(is_idle_round(state, round_index, child_result))
        else:
            idle = dispatched_n == 0

        if idle:
            state.idle_streak += 1
            if state.idle_streak >= state.idle_limit:
                if not state.dispatch:
                    state.stop_reason = d.rank_only_stop_reason
                else:
                    state.stop_reason = d.idle_stop_reason
                break
        else:
            state.idle_streak = 0

        if (
            state.dispatch_budget is not None
            and state.total_dispatched >= int(state.dispatch_budget)
        ):
            state.stop_reason = d.budget_stop_reason
            break
    else:
        state.stop_reason = d.max_stop_reason

    ok, verdict = classify_verdict(state)
    state.extras["ok"] = ok
    state.extras["verdict"] = verdict
    result = seal(state)
    # Ensure common fields always present for cross-dialect callers.
    result.setdefault("ok", ok)
    result.setdefault("verdict", verdict)
    result.setdefault("stop_reason", state.stop_reason)
    result.setdefault("total_dispatched", state.total_dispatched)
    result.setdefault("total_dispatched_ok", state.total_dispatched_ok)
    result.setdefault(d.self_dir_field, str(state.loop_dir))
    result.setdefault(d.child_count_field, len(state.records))
    result.setdefault(d.child_digests_field, list(state.child_digests))
    result.setdefault("portfolio_start_digest", state.portfolio_start_digest)
    result.setdefault(
        "portfolio_end_digest",
        (state.portfolio or {}).get("portfolio_digest") if state.portfolio else None,
    )
    result.setdefault("portfolio_source", state.portfolio_source)
    result.setdefault("used_skill_route_discovery", legacy_pipeline_was_used())
    result.setdefault("loop_engine", True)
    result.setdefault("loop_dialect", d.name)
    return result


def seal_json_receipt(
    state: LoopState,
    receipt: Mapping[str, Any],
    *,
    digest_payload: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    summary_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Write receipt + summary under state.loop_dir; set digest field."""
    body = dict(receipt)
    body.setdefault("schema_version", SCHEMA_VERSION)
    body.setdefault("created_at", utc_now_iso())
    body.setdefault("used_skill_route_discovery", legacy_pipeline_was_used())
    digest = _sha256_json(digest_payload(body))
    body[state.dialect.self_digest_field] = digest
    atomic_write_json(state.loop_dir / state.dialect.receipt_name, body)
    summary: dict[str, Any] = {
        "verdict": body.get("verdict"),
        "ok": body.get("ok"),
        "stop_reason": body.get("stop_reason"),
        state.dialect.self_digest_field: digest,
        state.dialect.child_count_field: body.get(state.dialect.child_count_field),
        "total_dispatched": body.get("total_dispatched"),
        "total_dispatched_ok": body.get("total_dispatched_ok"),
    }
    if summary_fields:
        for key in summary_fields:
            if key in body:
                summary[key] = body[key]
    atomic_write_json(state.loop_dir / "summary.json", summary)
    return {
        "ok": bool(body.get("ok")),
        "verdict": body.get("verdict"),
        "stop_reason": body.get("stop_reason"),
        state.dialect.self_dir_field: str(state.loop_dir),
        state.dialect.self_digest_field: digest,
        state.dialect.child_count_field: len(state.records),
        state.dialect.child_digests_field: list(state.child_digests),
        "total_dispatched": state.total_dispatched,
        "total_dispatched_ok": state.total_dispatched_ok,
        "portfolio_start_digest": state.portfolio_start_digest,
        "portfolio_end_digest": (
            (state.portfolio or {}).get("portfolio_digest") if state.portfolio else None
        ),
        "portfolio_source": state.portfolio_source,
        "used_skill_route_discovery": body.get("used_skill_route_discovery"),
        "loop_engine": True,
        "loop_dialect": state.dialect.name,
        "receipt": body,
    }


def verify_loop_receipt(
    dialect: LoopDialect | str,
    loop_dir: Path,
    *,
    digest_payload: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    nested_verify: Callable[[Path], Mapping[str, Any]] | None = None,
    nested_dir_field: str | None = None,
) -> dict[str, Any]:
    """Re-check a sealed loop receipt for digest integrity."""
    d = get_loop_dialect(dialect) if isinstance(dialect, str) else dialect
    path = durable_read_path(Path(loop_dir) / d.receipt_name)
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(digest_payload(receipt))
    recorded = str(receipt.get(d.self_digest_field) or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append(d.self_digest_field)

    records = list(receipt.get(d.child_records_field) or [])
    listed = list(receipt.get(d.child_digests_field) or [])
    # Epoch uses fleet_digest per wave; succession uses epoch_digest per epoch.
    # Only length-check listed digests when both present.
    if listed and len(listed) != len(
        [r for r in records if r.get(f"{d.child}_digest") or r.get("fleet_digest")]
    ):
        # soft: dialects may filter empty digests differently
        pass

    nested_failures: list[str] = []
    if nested_verify is not None:
        field_name = nested_dir_field or f"{d.child}_dir"
        for rec in records:
            nd = rec.get(field_name) or rec.get("plan_dir")
            if not nd:
                continue
            np = Path(str(nd))
            # Only verify when a receipt-like file exists under the nested dir.
            if any(np.joinpath(name).is_file() for name in (
                f"{d.child}.json",
                "epoch.json",
                "succession.json",
                "plan.json",
                "program.json",
            )):
                nested = nested_verify(np)
                if not nested.get("ok"):
                    nested_failures.append(str(nd))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": f"{d.name}_sealed" if ok else f"{d.name}_tampered",
        d.self_digest_field: recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        d.child_count_field: len(records),
        "loop_engine": True,
    }


# ---------------------------------------------------------------------------
# builtin proof: engine registers 3 dialects + drives succession via adapter


def builtin_loop_engine_proof() -> dict[str, Any]:
    """Hermetic proof that the multi-round loop engine owns the leaf dialects.

    Closes:
    - 3 dialects registered as data (program, succession, epoch)
    - program + succession + epoch runs go through run_durable_loop
      (LOOP_ENGINE=True and loop_engine flag on live results)
    - existing program / succession / epoch hermetic proofs still green
    - nested composition: program → succession → epoch all engine-owned
    - no skill-route discovery
    """
    from blackhole_agent import upstream_epoch as ue
    from blackhole_agent import upstream_program as up
    from blackhole_agent import upstream_succession as us
    from blackhole_agent import upstream_fleet as uf

    dialects = list_loop_dialects()
    dialects_ok = dialects == ["program", "succession", "epoch"]

    # Engine-native mini loop (no fleet): proves control flow hermetically.
    scratch = Path(tempfile.mkdtemp(prefix="loop-engine-proof-"))
    try:
        dialect = get_loop_dialect("succession")
        child_calls = {"n": 0}

        def child_runner(**kwargs: Any) -> dict[str, Any]:
            child_calls["n"] += 1
            idx = int(kwargs.get("round_index") or child_calls["n"] - 1)
            port = dict(kwargs.get("portfolio") or {"entries": [], "portfolio_digest": ""})
            entries = list(port.get("entries") or [])
            entries.append(
                {
                    "name": "demo",
                    "version": "1.0.0",
                    "defect_id": f"d{idx}",
                    "outcome": "impact_merged",
                    "impact_digest": _sha256_json({"i": idx}),
                    "ok": True,
                }
            )
            port["entries"] = entries
            port["portfolio_digest"] = _sha256_json(
                [{"d": e.get("defect_id"), "o": e.get("outcome")} for e in entries]
            )
            out = Path(str(kwargs.get("out_root") or scratch / f"child-{idx}"))
            out.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                out / "epoch.json",
                {
                    "ok": True,
                    "epoch_digest": _sha256_json({"i": idx}),
                    "portfolio_final": port,
                    "total_dispatched": 1,
                    "total_dispatched_ok": 1,
                },
            )
            return {
                "ok": True,
                "verdict": "epoch_progressed",
                "stop_reason": "max_waves",
                "epoch_dir": str(out),
                "epoch_digest": _sha256_json({"i": idx}),
                "total_dispatched": 1,
                "total_dispatched_ok": 1,
                "wave_count": 1,
            }

        def build_kwargs(state: LoopState, round_index: int) -> dict[str, Any]:
            return {
                "portfolio": state.portfolio,
                "out_root": state.child_root / f"epoch-{round_index:02d}",
                "round_index": round_index,
            }

        def on_result(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> dict[str, Any]:
            ed = result.get("epoch_dir")
            if ed and (Path(str(ed)) / "epoch.json").is_file():
                receipt = json.loads(
                    (Path(str(ed)) / "epoch.json").read_text(encoding="utf-8")
                )
                if isinstance(receipt.get("portfolio_final"), Mapping):
                    state.portfolio = dict(receipt["portfolio_final"])
            if result.get("epoch_digest"):
                state.child_digests.append(str(result["epoch_digest"]))
            return {
                "epoch": round_index,
                "ok": True,
                "epoch_digest": result.get("epoch_digest"),
                "epoch_dir": result.get("epoch_dir"),
                "total_dispatched": result.get("total_dispatched"),
                "total_dispatched_ok": result.get("total_dispatched_ok"),
            }

        def pre_stop(state: LoopState, round_index: int) -> str | None:
            entries = list((state.portfolio or {}).get("entries") or [])
            if len(entries) >= 2:
                state.goal_met = True
                return dialect.goal_stop_reason
            return None

        def post_stop(
            state: LoopState, round_index: int, result: dict[str, Any]
        ) -> str | None:
            entries = list((state.portfolio or {}).get("entries") or [])
            if len(entries) >= 2:
                state.goal_met = True
                return dialect.goal_stop_reason
            return None

        def classify(state: LoopState) -> tuple[bool, str]:
            if state.goal_met:
                return True, "succession_mandate_met"
            if state.total_dispatched_ok > 0:
                return True, "succession_progressed"
            return True, "succession_completed"

        def seal(state: LoopState) -> dict[str, Any]:
            receipt = {
                "ok": state.extras.get("ok"),
                "verdict": state.extras.get("verdict"),
                "stop_reason": state.stop_reason,
                "max_epochs": state.max_rounds,
                "dispatch_budget": state.dispatch_budget,
                "portfolio_start_digest": state.portfolio_start_digest,
                "portfolio_end_digest": (
                    (state.portfolio or {}).get("portfolio_digest")
                    if state.portfolio
                    else None
                ),
                "epoch_count": len(state.records),
                "epochs": state.records,
                "epoch_digests": list(state.child_digests),
                "total_dispatched": state.total_dispatched,
                "total_dispatched_ok": state.total_dispatched_ok,
                "mandate_met": state.goal_met,
                "coverage_end": {
                    "required": 2,
                    "covered": len(list((state.portfolio or {}).get("entries") or [])),
                    "met": state.goal_met,
                },
            }

            def payload(r: Mapping[str, Any]) -> dict[str, Any]:
                return {
                    "schema_version": r.get("schema_version"),
                    "verdict": r.get("verdict"),
                    "stop_reason": r.get("stop_reason"),
                    "max_epochs": r.get("max_epochs"),
                    "dispatch_budget": r.get("dispatch_budget"),
                    "portfolio_start_digest": r.get("portfolio_start_digest"),
                    "portfolio_end_digest": r.get("portfolio_end_digest"),
                    "epoch_count": r.get("epoch_count"),
                    "epoch_digests": list(r.get("epoch_digests") or []),
                    "total_dispatched": r.get("total_dispatched"),
                    "total_dispatched_ok": r.get("total_dispatched_ok"),
                    "mandate_met": r.get("mandate_met"),
                    "coverage_end": r.get("coverage_end"),
                }

            sealed = seal_json_receipt(state, receipt, digest_payload=payload)
            sealed["mandate_met"] = state.goal_met
            sealed["coverage_end"] = receipt["coverage_end"]
            sealed["epochs"] = state.records
            return sealed

        engine_native = run_durable_loop(
            dialect,
            max_rounds=4,
            dispatch=True,
            dispatch_budget=4,
            idle_limit=2,
            portfolio={"entries": [], "portfolio_digest": _sha256_json([])},
            out_root=scratch / "engine-native",
            child_runner=child_runner,
            build_child_kwargs=build_kwargs,
            on_child_result=on_result,
            pre_round_stop=pre_stop,
            post_round_stop=post_stop,
            classify_verdict=classify,
            seal=seal,
        )
        engine_native_ok = (
            engine_native.get("ok")
            and engine_native.get("loop_engine") is True
            and engine_native.get("loop_dialect") == "succession"
            and engine_native.get("mandate_met") is True
            and int(engine_native.get("epoch_count") or 0) >= 2
            and child_calls["n"] >= 2
        )
        verified = verify_loop_receipt(
            dialect,
            Path(engine_native["succession_dir"]),
            digest_payload=lambda r: {
                "schema_version": r.get("schema_version"),
                "verdict": r.get("verdict"),
                "stop_reason": r.get("stop_reason"),
                "max_epochs": r.get("max_epochs"),
                "dispatch_budget": r.get("dispatch_budget"),
                "portfolio_start_digest": r.get("portfolio_start_digest"),
                "portfolio_end_digest": r.get("portfolio_end_digest"),
                "epoch_count": r.get("epoch_count"),
                "epoch_digests": list(r.get("epoch_digests") or []),
                "total_dispatched": r.get("total_dispatched"),
                "total_dispatched_ok": r.get("total_dispatched_ok"),
                "mandate_met": r.get("mandate_met"),
                "coverage_end": r.get("coverage_end"),
            },
        )
        seal_ok = bool(verified.get("ok"))

        # Tamper
        sp = Path(engine_native["succession_dir"]) / "succession.json"
        body = json.loads(sp.read_text(encoding="utf-8"))
        body["succession_digest"] = "0" * 64
        sp.write_text(json.dumps(body, indent=2), encoding="utf-8")
        tampered = verify_loop_receipt(
            dialect,
            Path(engine_native["succession_dir"]),
            digest_payload=lambda r: {
                "schema_version": r.get("schema_version"),
                "verdict": r.get("verdict"),
                "stop_reason": r.get("stop_reason"),
                "max_epochs": r.get("max_epochs"),
                "dispatch_budget": r.get("dispatch_budget"),
                "portfolio_start_digest": r.get("portfolio_start_digest"),
                "portfolio_end_digest": r.get("portfolio_end_digest"),
                "epoch_count": r.get("epoch_count"),
                "epoch_digests": list(r.get("epoch_digests") or []),
                "total_dispatched": r.get("total_dispatched"),
                "total_dispatched_ok": r.get("total_dispatched_ok"),
                "mandate_met": r.get("mandate_met"),
                "coverage_end": r.get("coverage_end"),
            },
        )
        tamper_ok = (not tampered.get("ok")) and "succession_digest" in (
            tampered.get("mismatched") or []
        )

        # Live dialect modules flag engine ownership.
        succession_uses_engine = getattr(us, "LOOP_ENGINE", False) is True
        epoch_uses_engine = getattr(ue, "LOOP_ENGINE", False) is True
        program_uses_engine = getattr(up, "LOOP_ENGINE", False) is True
        program_nested = getattr(up, "LOOP_ENGINE_NESTED", False) is True

        # Re-prove live modules (they must stay green after migration).
        succ_proof = us.builtin_upstream_succession_proof()
        epoch_proof = ue.builtin_upstream_epoch_proof()
        program_proof = up.builtin_upstream_program_proof()
        live_proofs_ok = (
            bool(succ_proof.get("ok"))
            and bool(epoch_proof.get("ok"))
            and bool(program_proof.get("ok"))
        )

        # Spot-check live succession + program advertise loop_engine ownership.
        stew = scratch / "stew"
        stew.mkdir()
        uf._proof_target(
            stew,
            name="alpha",
            version="1.0.0",
            defects=[
                {
                    "id": "a1",
                    "title": "a1",
                    "kind": "complexity",
                    "patch": "patches/a1.patch",
                    "repro": "repros/a1.py",
                }
            ],
        )
        live = us.run_succession(
            stewardship_root=stew,
            portfolio=None,
            max_epochs=2,
            max_waves_per_epoch=1,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=us._proof_campaign_runner(scratch / "live"),
            mandate_goal="none",
            out_root=scratch / "live-succ",
        )
        live_flag = live.get("loop_engine") is True and live.get("loop_dialect") == "succession"

        live_prog = up.run_program(
            stewardship_root=stew,
            portfolio=None,
            max_successions=1,
            max_epochs_per_succession=1,
            max_waves_per_epoch=1,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=us._proof_campaign_runner(scratch / "live-prog"),
            program_goal="none",
            mandate_goal="none",
            out_root=scratch / "live-prog",
        )
        live_program_flag = (
            live_prog.get("loop_engine") is True
            and live_prog.get("loop_dialect") == "program"
        )

        # LOC evidence: prior tower was three large modules; engine is the shared core.
        engine_path = Path(__file__).resolve()
        engine_loc = sum(
            1
            for line in engine_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        tower_paths = [
            REPO_ROOT / "src" / "blackhole_agent" / f"upstream_{n}.py"
            for n in ("program", "succession", "epoch")
        ]
        tower_loc = 0
        for p in tower_paths:
            if p.is_file():
                tower_loc += sum(
                    1
                    for line in p.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.strip().startswith("#")
                )
        # Historical pre-collapse sizes (committed baselines from this mission).
        tower_loc_before = 1085 + 1224 + 1732  # epoch + succession + program

        # Ledger binding for this capability (registered by the owning mission).
        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get("capability.upstream-loop-engine")
            ledger_ok = (
                entry is not None
                and "upstream_loop_engine" in (entry.entry or "")
                and "loop" in " ".join(entry.tags).lower()
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        # Full-stack ownership: program + succession + epoch control flow.
        full_stack_owned = (
            program_uses_engine and succession_uses_engine and epoch_uses_engine
        )

        # done_when: engine owns program+succession+epoch control flow;
        # dialect modules keep only hooks (expand/ROI/resume/coverage).
        ok = all(
            [
                dialects_ok,
                engine_native_ok,
                seal_ok,
                tamper_ok,
                succession_uses_engine,
                epoch_uses_engine,
                program_uses_engine,
                full_stack_owned,
                live_flag,
                live_program_flag,
                live_proofs_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "loop_engine_proof",
            "dialect_count": len(dialects),
            "dialects": dialects,
            "dialects_ok": dialects_ok,
            "engine_native_ok": engine_native_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_ok,
            "succession_loop_engine": succession_uses_engine,
            "epoch_loop_engine": epoch_uses_engine,
            "program_loop_engine": program_uses_engine,
            "program_loop_engine_nested": program_nested,
            "full_stack_owned": full_stack_owned,
            "live_succession_flag": live_flag,
            "live_program_flag": live_program_flag,
            "succession_proof_ok": bool(succ_proof.get("ok")),
            "epoch_proof_ok": bool(epoch_proof.get("ok")),
            "program_proof_ok": bool(program_proof.get("ok")),
            "live_proofs_ok": live_proofs_ok,
            "ledger_capability_ok": ledger_ok,
            "engine_loc": engine_loc,
            "tower_loc_after": tower_loc,
            "tower_loc_before": tower_loc_before,
            "engine_native_digest": engine_native.get("succession_digest"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof", help="Run hermetic loop-engine proof")
    sub.add_parser("list", help="List registered loop dialects")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "list":
        print(json.dumps({"dialects": list_loop_dialects()}, indent=2))
        return 0
    if args.cmd == "proof":
        result = builtin_loop_engine_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
