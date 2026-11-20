"""Rest a CSS scroll container on the snap positions its areas define.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the snap reader still exits 0.
"""

from __future__ import annotations

import json


def _port(**overrides: object) -> dict[str, object]:
    container: dict[str, object] = {
        "port_x": 200,
        "port_y": 100,
        "max_x": 5000,
        "max_y": 5000,
        "intended_x": 0,
        "intended_y": 0,
        "intent": "absolute",
        "snap_type": "x mandatory",
        "writing_mode": "horizontal-tb",
        "direction": "ltr",
    }
    container.update(overrides)
    return container


def _area(area_id: str, x: float, y: float, width: float, height: float, **overrides: object) -> dict[str, object]:
    area: dict[str, object] = {
        "id": area_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "align_block": "none",
        "align_inline": "start",
    }
    area.update(overrides)
    return area


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_scroll_snap import resolve_scroll_snap
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def snap(name: str, container: dict[str, object], areas: list[dict[str, object]]) -> dict[str, object]:
        try:
            result = resolve_scroll_snap(container, areas)
        except Exception as exc:  # noqa: BLE001 - a raised snap is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error"}
        observed[name] = {
            "outcome": result.get("outcome"),
            "x": result.get("x"),
            "y": result.get("y"),
            "snapped_inline": result.get("snapped_inline"),
            "snapped_block": result.get("snapped_block"),
            "reason": result.get("reason"),
        }
        return result

    def expect(name: str, result: dict[str, object], **fields: object) -> None:
        ok = True
        for key, value in fields.items():
            ok = ok and result.get(key) == value
        checks.append(ok)

    expect(
        "padding_start",
        snap(
            "padding_start",
            _port(padding_left=20),
            [_area("padded", 100, 0, 40, 20)],
        ),
        outcome="snapped",
        x=80,
        y=0,
    )
    expect(
        "end_padding",
        snap(
            "end_padding",
            _port(padding_right=10),
            [_area("ended", 500, 0, 40, 20, align_inline="end")],
        ),
        outcome="snapped",
        x=350,
        y=0,
    )
    expect(
        "center",
        snap(
            "center",
            _port(),
            [_area("centered", 500, 0, 100, 20, align_inline="center")],
        ),
        outcome="snapped",
        x=450,
        y=0,
    )
    expect(
        "margin_start",
        snap(
            "margin_start",
            _port(),
            [_area("margined", 100, 0, 40, 20, margin_left=15)],
        ),
        outcome="snapped",
        x=85,
        y=0,
    )
    tall = [_area("chapter", 0, 0, 20, 400, align_block="start", align_inline="none")]
    expect(
        "cover_inside",
        snap("cover_inside", _port(snap_type="y mandatory", intended_y=150), tall),
        outcome="snapped",
        x=0,
        y=150,
    )
    expect(
        "cover_edge",
        snap("cover_edge", _port(snap_type="y mandatory", intended_y=350), tall),
        outcome="snapped",
        x=0,
        y=300,
    )
    expect(
        "tie_toward_end",
        snap(
            "tie_toward_end",
            _port(snap_type="y mandatory", intended_y=20),
            [
                _area("low", 0, 0, 20, 20, align_block="start", align_inline="none"),
                _area("high", 0, 40, 20, 20, align_block="start", align_inline="none"),
            ],
        ),
        outcome="snapped",
        y=40,
    )
    expect(
        "offscreen",
        snap(
            "offscreen",
            _port(intended_x=10),
            [_area("gone", -500, 0, 40, 20)],
        ),
        outcome="unsnapped",
        x=10,
        y=0,
    )
    expect(
        "clamped_visible",
        snap(
            "clamped_visible",
            _port(max_x=1000),
            [_area("far", 1050, 0, 40, 20)],
        ),
        outcome="snapped",
        x=1000,
    )
    expect(
        "relative_escape",
        snap(
            "relative_escape",
            _port(intent="relative", current_x=0, intended_x=250),
            [_area("here", 0, 0, 20, 20), _area("far", 800, 0, 20, 20)],
        ),
        outcome="unsnapped",
        x=250,
    )
    expect(
        "always_stop",
        snap(
            "always_stop",
            _port(intent="relative", current_x=0, intended_x=250),
            [
                _area("here", 0, 0, 20, 20),
                _area("trap", 80, 0, 20, 20, snap_stop="always"),
                _area("closer", 200, 0, 20, 20),
            ],
        ),
        outcome="snapped",
        x=80,
    )
    expect(
        "proximity",
        snap(
            "proximity",
            _port(snap_type="x proximity", intended_x=400),
            [_area("origin", 0, 0, 20, 20)],
        ),
        outcome="unsnapped",
        x=400,
    )
    expect(
        "mandatory_far",
        snap(
            "mandatory_far",
            _port(intended_x=400),
            [_area("origin", 0, 0, 20, 20)],
        ),
        outcome="snapped",
        x=0,
    )
    shared = [
        _area("inline-only", 0, 0, 20, 20, align_inline="start", align_block="none"),
        _area("block-only", 0, 0, 100, 20, align_inline="none", align_block="start"),
        _area("both-axes", 200, 200, 20, 20, align_inline="start", align_block="start"),
    ]
    square = _port(port_x=100, port_y=100, intended_x=40, intended_y=30)
    expect(
        "both_axes",
        snap("both_axes", {**square, "snap_type": "both mandatory"}, shared),
        outcome="snapped",
        x=0,
        y=0,
    )
    expect(
        "pair_axes",
        snap("pair_axes", {**square, "snap_type": "pair mandatory"}, shared),
        outcome="snapped",
        x=200,
        y=200,
    )
    expect(
        "rtl_large",
        snap(
            "rtl_large",
            _port(port_x=100, intended_x=290),
            [
                _area("rtl-page", 0, 0, 400, 20, direction="rtl"),
                _area("a", 0, 0, 20, 20),
                _area("b", 100, 0, 20, 20),
                _area("c", 200, 0, 20, 20),
            ],
        ),
        outcome="snapped",
        x=300,
    )
    expect(
        "vertical_rl",
        snap(
            "vertical_rl",
            _port(writing_mode="vertical-rl", snap_type="block mandatory"),
            [_area("column", 300, 0, 40, 20, align_block="start", align_inline="none")],
        ),
        outcome="snapped",
        x=140,
        y=0,
    )
    expect(
        "targeted",
        snap(
            "targeted",
            _port(intended_x=10),
            [
                _area("plain", 0, 0, 20, 20),
                _area("marked", 500, 0, 20, 20, targeted=True),
            ],
        ),
        outcome="snapped",
        x=500,
        snapped_inline="marked",
    )
    expect(
        "child_wins",
        snap(
            "child_wins",
            _port(intended_x=30),
            [
                _area("section", 0, 0, 20, 20),
                _area("title", 0, 0, 20, 20, parent="section"),
            ],
        ),
        outcome="snapped",
        x=0,
        snapped_inline="title",
    )
    invalid = snap("negative_padding", _port(padding_left=-1), [])
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("x") is None)

    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
