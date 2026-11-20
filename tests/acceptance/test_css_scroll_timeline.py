"""Drive a CSS animation from scroll progress and view progress.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the timeline still exits 0.
"""

from __future__ import annotations

import json


def _sheet(decls: dict[str, str], frames: str = "from { width: 0px; } to { width: 100px; }") -> str:
    body = "\n".join(f"  {name}: {value};" for name, value in decls.items())
    return f"@keyframes slide {{\n{frames}\n}}\n.el {{\n  animation-name: slide;\n{body}\n}}\n"


def _near(found: object, expected: float) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) < 1e-9


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_scroll_timeline import (
            sample_scroll_driven_animation,
            scroll_timeline_progress,
            view_timeline_progress,
        )
    except Exception as exc:  # noqa: BLE001 - baseline without the timeline still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def timeline(name: str, result: object) -> dict[str, object]:
        payload = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = payload
        return payload

    def active(name: str, result: object, progress: float, start: float, end: float) -> None:
        row = timeline(name, result)
        checks.append(
            row.get("outcome") == "active"
            and _near(row.get("progress"), progress)
            and _near(row.get("start"), start)
            and _near(row.get("end"), end)
            and row.get("reason") == ""
        )

    def quiet(name: str, result: object, start: float, end: float) -> None:
        row = timeline(name, result)
        checks.append(
            row.get("outcome") == "inactive"
            and row.get("progress") is None
            and _near(row.get("start"), start)
            and _near(row.get("end"), end)
            and row.get("reason") == "range"
        )

    def rejected(name: str, result: object, reason: str) -> None:
        row = timeline(name, result)
        checks.append(
            row.get("outcome") == "invalid"
            and row.get("progress") is None
            and row.get("start") is None
            and row.get("end") is None
            and row.get("reason") == reason
        )

    active("scroll_start", scroll_timeline_progress(0, 300, 100), 0, 0, 200)
    active("scroll_mid", scroll_timeline_progress(100, 300, 100), 0.5, 0, 200)
    active("scroll_end", scroll_timeline_progress(200, 300, 100), 1, 0, 200)
    active("scroll_before", scroll_timeline_progress(-50, 300, 100), -0.25, 0, 200)
    quiet("scroll_zero", scroll_timeline_progress(0, 100, 100), 0, 0)
    rejected("scroll_short", scroll_timeline_progress(0, 80, 100), "overflow")
    rejected("scroll_bool", scroll_timeline_progress(True, 300, 100), "offset")

    active("cover_0", view_timeline_progress(100, 200, 40, 100), 0, 100, 240)
    active("cover_mid", view_timeline_progress(170, 200, 40, 100), 0.5, 100, 240)
    active("cover_100", view_timeline_progress(240, 200, 40, 100), 1, 100, 240)
    active("contain_mid", view_timeline_progress(170, 200, 40, 100, range_name="contain"), 0.5, 140, 200)
    active("entry_mid", view_timeline_progress(120, 200, 40, 100, range_name="entry"), 0.5, 100, 140)
    active("exit_mid", view_timeline_progress(220, 200, 40, 100, range_name="exit"), 0.5, 200, 240)
    active("cover_point", view_timeline_progress(150, 200, 0, 100), 0.5, 100, 200)
    quiet("entry_point", view_timeline_progress(150, 200, 0, 100, range_name="entry"), 100, 100)
    active(
        "entry_crossing",
        view_timeline_progress(175, 200, 150, 100, range_name="entry-crossing"),
        0.5,
        100,
        250,
    )
    active(
        "exit_crossing",
        view_timeline_progress(275, 200, 150, 100, range_name="exit-crossing"),
        0.5,
        200,
        350,
    )
    active(
        "inset_cover",
        view_timeline_progress(175, 200, 40, 100, inset_start="10%", inset_end="20px"),
        0.5,
        120,
        230,
    )
    active(
        "view_scroll",
        view_timeline_progress(100, 200, 40, 100, range_name="scroll", overflow=300),
        0.5,
        0,
        200,
    )
    rejected("range_name", view_timeline_progress(0, 200, 40, 100, range_name="sideways"), "range")
    rejected("inset_closed", view_timeline_progress(0, 200, 40, 100, inset_start=60, inset_end=50), "inset")

    linear = {"animation-duration": "1000ms", "animation-timing-function": "linear", "width": "7px"}

    def sample(name: str, progress: object, decls: dict[str, str] | None = None) -> dict[str, object]:
        try:
            result = sample_scroll_driven_animation(_sheet(decls or linear), progress)
        except Exception as exc:  # noqa: BLE001 - a raised sample is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        payload = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = payload
        return payload

    def sampled(name: str, progress: object, value: float, decls: dict[str, str] | None = None) -> None:
        row = sample(name, progress, decls)
        checks.append(
            row.get("outcome") == "sampled"
            and row.get("applying") is True
            and _near(row.get("value"), value)
            and row.get("unit") == "px"
        )

    def idle(name: str, progress: object, value: float, reason: str, decls: dict[str, str] | None = None) -> None:
        row = sample(name, progress, decls)
        checks.append(
            row.get("outcome") == "idle"
            and row.get("applying") is False
            and _near(row.get("value"), value)
            and row.get("reason") == reason
        )

    sampled("play_0", 0, 0)
    sampled("play_mid", 0.5, 50)
    idle("play_end", 1, 7, "")
    sampled("play_hold", 1, 100, {**linear, "animation-fill-mode": "forwards"})
    inactive = sample("play_inactive", None)
    checks.append(
        inactive.get("outcome") == "inactive"
        and inactive.get("applying") is False
        and _near(inactive.get("value"), 7)
        and inactive.get("progress") is None
        and inactive.get("reason") == "timeline"
    )
    eased = sample("play_ease", 0.5, {**linear, "animation-timing-function": "ease"})
    checks.append(
        eased.get("outcome") == "sampled"
        and eased.get("applying") is True
        and _near(eased.get("value"), 80.24033875848569)
        and not _near(eased.get("value"), 50)
    )
    twice = {**linear, "animation-iteration-count": "2"}
    sampled("twice_quarter", 0.25, 50, twice)
    sampled("twice_boundary", 0.5, 100, twice)
    sampled("twice_three", 0.75, 50, twice)
    sampled("alternate_late", 0.875, 25, {**twice, "animation-direction": "alternate"})
    delayed = {**linear, "animation-delay": "250ms", "animation-duration": "750ms"}
    idle("delay_before", 0, 7, "", delayed)
    sampled("delay_open", 0.25, 0, delayed)
    sampled("delay_mid", 0.625, 50, delayed)
    early = {**linear, "animation-delay": "-200ms"}
    sampled("early_open", 0, 20, early)
    sampled("early_mid", 0.5, 60, early)
    idle("infinite", 0.5, 7, "infinite", {**linear, "animation-iteration-count": "infinite"})

    cover = view_timeline_progress(120, 200, 40, 100)
    entry = view_timeline_progress(120, 200, 40, 100, range_name="entry")
    sampled("entry_at_120", entry.get("progress"), 50)
    cover_value = sample("cover_at_120", cover.get("progress"))
    checks.append(cover_value.get("outcome") == "sampled" and _near(cover_value.get("value"), 100 / 7))
    later_cover = view_timeline_progress(170, 200, 40, 100)
    later_entry = view_timeline_progress(170, 200, 40, 100, range_name="entry")
    sampled("cover_at_170", later_cover.get("progress"), 50)
    idle("entry_at_170", later_entry.get("progress"), 7, "")

    passed = all(checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in zip(observed, checks) if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
