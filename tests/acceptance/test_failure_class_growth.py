"""Unclassified failures become one confirmable class.

Three failures that share a stack fingerprint and match no hand-written
pattern class must form one candidate card. Confirming it registers the
class so the required pattern mission names it and a later copy increments
the open count. A single failure, a dissimilar failure, and a validation
replay rejection must not join that card.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


FOO_SAMPLES = (
    r"FooError: widget sprocket missing at C:\tmp\run-1\widget.py line 12",
    r"FooError: widget sprocket missing at C:\tmp\run-2\widget.py line 48",
    r"FooError: widget sprocket missing at D:\other\run-9\widget.py line 3",
)
FOO_LATER = r"FooError: widget sprocket missing at C:\tmp\run-4\widget.py line 7"
BAR_SAMPLE = (
    "BarError: quota token rejected for session "
    "11111111-2222-3333-4444-555555555555"
)
REPLAY_TURN = {
    "iteration": 1,
    "milestone_gate": {
        "requested": True,
        "accepted": False,
        "reasons": [
            "validation replay failed: reported exit 0 but controller replay got exit 1"
        ],
    },
}


def _baseline(samples: tuple[str, ...]) -> tuple[bool, dict]:
    from blackhole_agent.pattern_register import classify_unbound_turn

    classes = []
    for sample in samples:
        events = classify_unbound_turn(
            {"effective_status": "error", "error": sample, "iteration": 1}
        )
        classes.append(str(events[0].get("class_id") or "") if events else "")
    observed = {
        "card": None,
        "classes": classes,
        "generic_only": bool(classes) and set(classes) == {"kernel_turn_failed"},
        "growth": False,
    }
    return False, observed


def _write_cluster_repo(root: Path) -> None:
    missions = root / ".blackhole-agent" / "unbound" / "missions"
    for index, sample in enumerate(FOO_SAMPLES, start=1):
        mission = missions / f"fixture-{index}"
        mission.mkdir(parents=True)
        payload = {
            "mission_id": f"fixture-{index}",
            "status": "complete",
            "last_error": sample,
            "iteration": 1,
            "recent_turns": [],
        }
        (mission / "state.json").write_text(json.dumps(payload), encoding="utf-8")


def _candidate() -> tuple[bool, dict]:
    from blackhole_agent.failure_class_growth import (
        cluster_unclassified_failures,
        confirm_failure_candidate,
        record_matching_failure,
        render_unclassified_growth_for_genesis,
    )
    from blackhole_agent.pattern_register import classify_unbound_turn

    replay_class = ""
    for event in classify_unbound_turn(REPLAY_TURN):
        replay_class = str(event.get("class_id") or "")
        if replay_class:
            break
    failures = [*FOO_SAMPLES, BAR_SAMPLE, {"text": "validation replay", "turn": REPLAY_TURN}]
    first = cluster_unclassified_failures(failures)
    second = cluster_unclassified_failures(failures)
    alone = cluster_unclassified_failures(FOO_SAMPLES[:1])
    with tempfile.TemporaryDirectory(prefix="bh-failure-class-") as directory:
        root = Path(directory)
        card = first[0]
        _write_cluster_repo(root)
        rendered = render_unclassified_growth_for_genesis(root)
        confirmed = confirm_failure_candidate(root, card)
        opened = record_matching_failure(root, card["class_id"], FOO_LATER)
    observed = {
        "growth": True,
        "card_count": len(first),
        "class_id": "" if not first else first[0]["class_id"],
        "sample_count": 0 if not first else first[0]["sample_count"],
        "stable_id": bool(first and second and first[0]["class_id"] == second[0]["class_id"]),
        "alone_cards": len(alone),
        "bar_outside": bool(first) and all("BarError" not in card["signature"] for card in first),
        "replay_class": replay_class,
        "replay_absent": bool(first) and all(card["class_id"] != replay_class for card in first),
        "mission_class_id": confirmed["mission_class_id"],
        "open_count_after_confirm": confirmed["open_count"],
        "open_count_after_later": opened,
        "rendered": card["class_id"] in rendered and "samples=3" in rendered,
    }
    passed = (
        observed["card_count"] == 1
        and observed["sample_count"] == 3
        and observed["stable_id"] is True
        and observed["class_id"].startswith("grown-")
        and observed["alone_cards"] == 0
        and observed["bar_outside"] is True
        and observed["replay_class"] == "validation_replay_failed"
        and observed["replay_absent"] is True
        and observed["mission_class_id"] == observed["class_id"]
        and observed["open_count_after_confirm"] == 3
        and observed["open_count_after_later"] == 4
        and observed["rendered"] is True
    )
    return passed, observed


def observe() -> tuple[bool, dict]:
    try:
        from blackhole_agent import failure_class_growth  # noqa: F401
    except ImportError:
        return _baseline(FOO_SAMPLES)
    return _candidate()


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:500]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
