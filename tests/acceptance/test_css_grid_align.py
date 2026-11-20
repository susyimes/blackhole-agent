"""Align a grid item's margin box inside its grid area.

A non-replaced normal item stretches. A replaced normal item keeps its
natural size on the start edge. A definite size stays definite. An automatic
margin absorbs positive free space. An overflowing unsafe center crosses the
start edge, and safe pulls it back. Self-start and physical left follow the
item and the writing mode.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_grid_align import align_grid_item
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, area: object, **kwargs: object) -> dict[str, object]:
        try:
            result = align_grid_item(area, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised alignment is an unmet outcome
            result = {"outcome": "error", "start": None, "size": None, "reason": f"{type(exc).__name__}: {exc}"}
        got = result if isinstance(result, dict) else {"outcome": "error", "start": None, "size": None}
        observed[name] = {
            "outcome": got.get("outcome"),
            "start": got.get("start"),
            "size": got.get("size"),
        }
        return observed[name]

    def expect(name: str, start: object, border: object, area: object, **kwargs: object) -> None:
        got = take(name, area, **kwargs)
        checks.append(got.get("outcome") == "aligned" and got.get("start") == start and got.get("size") == border)

    expect("stretch", 0, 100, 100)
    expect("end", 60, 40, 100, size=40, align="end")
    expect("center", 30, 40, 100, size=40, align="center")
    expect("definite_stretch", 0, 40, 100, size=40, align="stretch")
    expect("replaced", 0, 40, 100, automatic=40, replaced=True)
    expect("auto_margin", 50, 40, 100, automatic=40, margin_start="auto", margin_end=10, align="end")
    expect("unsafe_center", -20, 140, 100, size=140, align="center")
    expect("safe_center", 0, 140, 100, size=140, align="safe center")
    expect("overflow_auto_margin", -20, 140, 100, size=140, margin_start="auto", align="center")
    expect("physical_left", 60, 40, 100, size=40, align="left", container_direction="rtl")
    expect("self_start", 60, 40, 100, size=40, align="self-start", item_direction="rtl")
    expect("orthogonal_self_start", 60, 40, 100, size=40, align="self-start", item_writing_mode="vertical-rl")
    expect("vertical_right", 0, 40, 100, size=40, align="right", container_writing_mode="vertical-rl")
    expect("baseline_fallback", 0, 140, 100, size=140, align="first baseline", item_direction="rtl")
    refused = take("negative_area", -1)
    checks.append(refused.get("outcome") == "invalid" and refused.get("start") is None and refused.get("size") is None)
    return all(checks), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
