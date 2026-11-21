"""Resolve overlapping CSS border-radius curves to used corner ellipses.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without used border radii still exits 0.
"""

from __future__ import annotations

import json


def _near(found: object, expected: float, tol: float = 1e-6) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) <= tol


def _corner(row: object, name: str, key: str) -> object:
    if not isinstance(row, dict):
        return None
    corners = row.get("corners")
    if not isinstance(corners, dict):
        return None
    item = corners.get(name)
    if not isinstance(item, dict):
        return None
    return item.get(key)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_border_radius import used_border_radii
    except Exception as exc:  # noqa: BLE001 - baseline without the curves still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[tuple[str, bool]] = []

    def call(name: str, **kwargs: object) -> dict[str, object]:
        try:
            row = used_border_radii(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            row = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        payload = row if isinstance(row, dict) else {"outcome": "error"}
        observed[name] = payload
        return payload

    def resolved(name: str, row: dict[str, object]) -> None:
        checks.append((name, row.get("outcome") == "resolved" and row.get("reason") is None and row.get("applied") is True))

    def invalid(name: str, row: dict[str, object], reason: str) -> None:
        checks.append(
            (
                name,
                row.get("outcome") == "invalid"
                and row.get("reason") == reason
                and row.get("corners") is None
                and row.get("applied") is False
                and row.get("scale") is None,
            )
        )

    spec = call("spec_overlap", width=600, height=200, radius="50px 200px 50px 200px")
    resolved("spec_overlap", spec)
    checks.append(("spec_scale", _near(spec.get("scale"), 0.8)))
    for name, outer in (
        ("top-left", 40),
        ("top-right", 160),
        ("bottom-right", 40),
        ("bottom-left", 160),
    ):
        checks.append((f"spec_{name}_x", _near(_corner(spec, name, "outer_x"), outer)))
        checks.append((f"spec_{name}_y", _near(_corner(spec, name, "outer_y"), outer)))

    inset = call("uniform_inset", width=100, height=50, radius="40px", border="10px")
    resolved("uniform_inset", inset)
    checks.append(("uniform_scale", _near(inset.get("scale"), 0.625)))
    checks.append(("uniform_outer", _near(_corner(inset, "top-left", "outer_x"), 25)))
    checks.append(("uniform_inner", _near(_corner(inset, "bottom-right", "inner_y"), 15)))

    elliptical = call("elliptical_partial", width=100, height=100, radius="60px 60px 0 0 / 10px 10px 0 0")
    resolved("elliptical_partial", elliptical)
    checks.append(("elliptical_scale", _near(elliptical.get("scale"), 100 / 120)))
    checks.append(("elliptical_x", _near(_corner(elliptical, "top-left", "outer_x"), 50)))
    checks.append(("elliptical_y", _near(_corner(elliptical, "top-right", "outer_y"), 25 / 3)))
    checks.append(("elliptical_square", _corner(elliptical, "bottom-left", "outer_x") == 0))

    percent = call("percent_unscaled", width=200, height=80, radius="50% 10px / 25% 20px")
    resolved("percent_unscaled", percent)
    checks.append(("percent_scale", percent.get("scale") == 1))
    checks.append(("percent_tl_x", _near(_corner(percent, "top-left", "outer_x"), 100)))
    checks.append(("percent_tl_y", _near(_corner(percent, "top-left", "outer_y"), 20)))
    checks.append(("percent_tr_x", _near(_corner(percent, "top-right", "outer_x"), 10)))
    checks.append(("percent_br_x", _near(_corner(percent, "bottom-right", "outer_x"), 100)))
    checks.append(("percent_bl_x", _near(_corner(percent, "bottom-left", "outer_x"), 10)))

    content = call("content_edge", width=100, height=100, radius="30px", border="10px", padding="8px")
    resolved("content_edge", content)
    checks.append(("content_outer", _near(_corner(content, "top-left", "outer_x"), 30)))
    checks.append(("content_inner", _near(_corner(content, "top-left", "inner_x"), 20)))
    checks.append(("content_radius", _near(_corner(content, "top-right", "content_y"), 12)))

    asymmetric = call("asymmetric_border", width=100, height=50, radius="40px", border="5px 30px")
    resolved("asymmetric_border", asymmetric)
    checks.append(("asymmetric_inner_x", _corner(asymmetric, "top-left", "inner_x") == 0))
    checks.append(("asymmetric_inner_y", _near(_corner(asymmetric, "top-left", "inner_y"), 20)))

    math_radius = call("calc_overlap", width=100, height=100, radius="calc(80px) calc(80px) 0 0")
    resolved("calc_overlap", math_radius)
    checks.append(("calc_scale", _near(math_radius.get("scale"), 0.625)))
    checks.append(("calc_outer", _near(_corner(math_radius, "top-left", "outer_x"), 50)))
    checks.append(("calc_square", _corner(math_radius, "bottom-right", "outer_y") == 0))

    divided = call("calc_slash", width=100, height=100, radius="calc(20px / 2)/8px")
    resolved("calc_slash", divided)
    checks.append(("calc_slash_x", _near(_corner(divided, "bottom-left", "outer_x"), 10)))
    checks.append(("calc_slash_y", _near(_corner(divided, "bottom-left", "outer_y"), 8)))

    absolute = call("absolute_inch", width=200, height=200, radius="1in")
    resolved("absolute_inch", absolute)
    checks.append(("inch", _near(_corner(absolute, "top-right", "outer_x"), 96)))

    three = call("three_values", width=400, height=400, radius="10px 20px 30px")
    resolved("three_values", three)
    checks.append(("three_tl", _near(_corner(three, "top-left", "outer_x"), 10)))
    checks.append(("three_tr", _near(_corner(three, "top-right", "outer_x"), 20)))
    checks.append(("three_br", _near(_corner(three, "bottom-right", "outer_x"), 30)))
    checks.append(("three_bl", _near(_corner(three, "bottom-left", "outer_x"), 20)))

    zero_height = call("zero_height", width=100, height=0, radius="10px")
    resolved("zero_height", zero_height)
    checks.append(("zero_scale", zero_height.get("scale") == 0))
    checks.append(("zero_outer", _corner(zero_height, "top-left", "outer_y") == 0))

    folded = call("case_fold", width=200, height=200, radius="40PX /* kept */ 0")
    resolved("case_fold", folded)
    checks.append(("case_tl", _near(_corner(folded, "top-left", "outer_x"), 40)))
    checks.append(("case_tr", _corner(folded, "top-right", "outer_x") == 0))

    collapsed = call("collapsed", width=100, height=100, radius="40px", border_collapse="Collapse")
    checks.append(
        (
            "collapsed",
            collapsed.get("outcome") == "resolved"
            and collapsed.get("applied") is False
            and collapsed.get("scale") is None
            and _corner(collapsed, "top-left", "outer_x") == 0
            and _corner(collapsed, "bottom-right", "inner_y") == 0,
        )
    )

    invalid("negative", call("negative", width=100, height=100, radius="-1px"), "radius is invalid")
    invalid("fifth", call("fifth", width=100, height=100, radius="1px 2px 3px 4px 5px"), "radius is invalid")
    invalid("two_slashes", call("two_slashes", width=100, height=100, radius="1px / 2px / 3px"), "radius is invalid")
    invalid("length_ratio", call("length_ratio", width=100, height=100, radius="calc(10px / 2px)"), "radius is invalid")
    invalid("em", call("em", width=100, height=100, radius="1em"), "radius is invalid")
    invalid("percent_border", call("percent_border", width=100, height=100, radius="10px", border="10%"), "border is invalid")
    invalid("negative_box", call("negative_box", width=-1, height=100, radius="10px"), "box is invalid")
    invalid("bool_box", call("bool_box", width=True, height=100, radius="0"), "box is invalid")

    passed = all(ok for _, ok in checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in checks if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
