"""Fit a replaced content object inside its content box.

fill stretches. contain and cover keep a ratio, and a missing ratio uses the
box. none keeps a natural size, while a bare ratio is contained. scale-down
picks the smaller of none and contain. left 10px is the other axis. An edge
offset moves inward, and cover may start outside the box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the fitter still exits 0.
"""

from __future__ import annotations

import json


def _geometry(result: object, *, x: object, y: object, width: object, height: object, chosen: str) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "fitted":
        return False
    return (
        result.get("x") == x
        and result.get("y") == y
        and result.get("width") == width
        and result.get("height") == height
        and result.get("chosen") == chosen
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_object_fit import fit_object
    except Exception as exc:  # noqa: BLE001 - baseline without the fitter still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = fit_object(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised fit is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    square = {"content_width": 200, "content_height": 100, "natural_width": 100, "natural_height": 100}
    checks.append(_geometry(keep("contain", fit="contain", **square), x=50, y=0, width=100, height=100, chosen="contain"))
    checks.append(_geometry(keep("cover", fit="cover", **square), x=0, y=-50, width=200, height=200, chosen="cover"))
    checks.append(
        _geometry(keep("scale_equal", fit="scale-down", **square), x=50, y=0, width=100, height=100, chosen="none")
    )
    checks.append(
        _geometry(
            keep("bare_ratio", fit="none", content_width=200, content_height=100, natural_ratio=2),
            x=0,
            y=0,
            width=200,
            height=100,
            chosen="none",
        )
    )
    checks.append(
        _geometry(
            keep(
                "left_length",
                fit="none",
                position="left 10px",
                content_width=200,
                content_height=100,
                natural_width=100,
                natural_height=100,
            ),
            x=0,
            y=10,
            width=100,
            height=100,
            chosen="none",
        )
    )
    checks.append(
        _geometry(
            keep(
                "edge_insets",
                fit="none",
                position="right 10px bottom 20px",
                content_width=200,
                content_height=100,
                natural_width=100,
                natural_height=50,
            ),
            x=90,
            y=30,
            width=100,
            height=50,
            chosen="none",
        )
    )
    flat = {"content_width": 0, "content_height": 100, "natural_ratio": 1}
    cover_flat = keep("cover_flat", fit="cover", **flat)
    contain_flat = keep("contain_flat", fit="contain", **flat)
    checks.append(_geometry(cover_flat, x=-50, y=0, width=100, height=100, chosen="cover"))
    checks.append(_geometry(contain_flat, x=0, y=50, width=0, height=0, chosen="contain"))
    checks.append(
        _geometry(
            keep(
                "scale_down",
                fit="scale-down",
                content_width=100,
                content_height=100,
                natural_width=400,
                natural_height=200,
            ),
            x=0,
            y=25,
            width=100,
            height=50,
            chosen="contain",
        )
    )
    checks.append(
        _geometry(
            keep(
                "scale_none",
                fit="scale-down",
                content_width=100,
                content_height=100,
                natural_width=40,
                natural_height=20,
            ),
            x=30,
            y=40,
            width=40,
            height=20,
            chosen="none",
        )
    )
    top = keep("top_length", content_width=200, content_height=100, position="top 10px")
    negative = keep("negative", content_width=-1, content_height=100)
    checks.append(top.get("outcome") == "invalid" and top.get("width") is None)
    checks.append(
        negative.get("outcome") == "invalid"
        and negative.get("reason") == "content width cannot be negative"
        and negative.get("width") is None
    )
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
