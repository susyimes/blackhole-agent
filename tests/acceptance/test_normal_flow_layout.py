"""Place normal-flow boxes from a stylesheet instead of pre-solved lengths.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without document placement still exits 0.
"""

from __future__ import annotations

import json

_MARKUP = """
<div id="page">
  <div id="a"></div>
  <div id="gone"></div>
  <div id="b"></div>
</div>
"""

_STYLESHEET = """
html { --page: 160px; }
#page {
  width: var(--page);
  margin-top: 30px;
  margin-left: auto;
  margin-right: auto;
  padding-left: 20px;
}
#a {
  width: 50%;
  margin-top: 10px;
  margin-bottom: 24px;
  height: 20px;
}
#gone {
  display: none;
  margin-top: 100px;
  height: 50px;
}
#b {
  width: 40px;
  margin-top: 8px;
  margin-left: auto;
  margin-right: auto;
  height: 12px;
}
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(box: dict[str, object] | None, **expected: int) -> bool:
    if box is None:
        return False
    return all(box.get(key) == value for key, value in expected.items())


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        placed = layout_normal_flow(_MARKUP, _STYLESHEET, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        placed = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        rejected = layout_normal_flow('<div id="bad"></div>', "#bad { padding-top: -1px; }", viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised rejection is an unmet outcome
        rejected = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}

    boxes = placed.get("boxes") if isinstance(placed, dict) else None
    page = _box(boxes, "page")
    first = _box(boxes, "a")
    second = _box(boxes, "b")
    hidden = _box(boxes, "gone")
    observed: dict[str, object] = {
        "outcome": placed.get("outcome") if isinstance(placed, dict) else None,
        "reason": placed.get("reason") if isinstance(placed, dict) else None,
        "page": page,
        "a": first,
        "b": second,
        "gone": hidden,
        "ids": [item.get("id") for item in boxes] if isinstance(boxes, list) else None,
        "rejected_outcome": rejected.get("outcome") if isinstance(rejected, dict) else None,
        "rejected_reason": rejected.get("reason") if isinstance(rejected, dict) else None,
    }
    checks = {
        "placed": placed.get("outcome") == "placed" if isinstance(placed, dict) else False,
        "page": _near(page, x=10, y=30, content_width=160, content_height=56, border_width=180, margin_left=10),
        "a": _near(first, x=30, y=30, content_width=80, content_height=20, border_height=20, margin_left=0),
        "b": _near(second, x=90, y=74, content_width=40, content_height=12, border_height=12, margin_left=60),
        "gone_absent": hidden is None,
        "negative_padding": (
            isinstance(rejected, dict)
            and rejected.get("outcome") == "invalid"
            and rejected.get("boxes") is None
            and isinstance(rejected.get("reason"), str)
            and "padding" in str(rejected.get("reason"))
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
