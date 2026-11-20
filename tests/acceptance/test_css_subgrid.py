"""Place stretched CSS subgrid items on the parent tracks they share.

The 300px CSS Grid example uses tracks 100 and 150 with a 50px parent gutter.
Gap 0 pulls the items together, gap 75 pushes them apart, and gap normal
leaves the parent tracks. A 100px start edge insets only the first item.
A one-track subgrid clamps line 2 / span 3 onto that track.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json


def _items(*rows: tuple[str, int, int]) -> list[dict[str, object]]:
    return [{"id": ident, "start": start, "span": span} for ident, start, span in rows]


def _box(ident: str, start: object, size: object) -> dict[str, object]:
    return {"id": ident, "start": start, "size": size}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_subgrid import place_subgrid_items
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []
    pair = _items(("left", 1, 1), ("right", 2, 1))

    def take(name: str, tracks: list[int], rows: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
        try:
            result = place_subgrid_items(tracks, rows, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised placement is an unmet outcome
            result = {"outcome": "error", "items": None, "reason": f"{type(exc).__name__}: {exc}"}
        placed = result if isinstance(result, dict) else {"outcome": "error", "items": None}
        boxes = placed.get("items")
        compact = None
        if isinstance(boxes, list):
            compact = [
                {"id": item.get("id"), "start": item.get("start"), "size": item.get("size")}
                for item in boxes
                if isinstance(item, dict)
            ]
        observed[name] = {
            "outcome": placed.get("outcome"),
            "items": compact,
            "reason": placed.get("reason"),
        }
        return observed[name]

    def expect(
        name: str,
        boxes: list[dict[str, object]],
        tracks: list[int],
        rows: list[dict[str, object]],
        **kwargs: object,
    ) -> None:
        got = take(name, tracks, rows, **kwargs)
        checks.append(got.get("outcome") == "placed" and got.get("items") == boxes)

    expect("gap_zero", [_box("left", 0, 125), _box("right", 125, 175)], [100, 150], pair, gap=50, subgrid_gap=0)
    expect(
        "gap_normal",
        [_box("left", 0, 100), _box("right", 150, 150)],
        [100, 150],
        pair,
        gap=50,
        subgrid_gap="normal",
    )
    expect(
        "gap_75",
        [_box("left", 0, 87.5), _box("right", 162.5, 137.5)],
        [100, 150],
        pair,
        gap=50,
        subgrid_gap=75,
    )
    expect(
        "gap_25",
        [_box("left", 0, 112.5), _box("right", 137.5, 162.5)],
        [100, 150],
        pair,
        gap=50,
        subgrid_gap=25,
    )
    expect(
        "edge",
        [_box("left", 100, 200), _box("right", 300, 100)],
        [300, 100],
        pair,
        gap=0,
        edge_start=100,
    )
    expect("clamped", [_box("only", 0, 40)], [40], _items(("only", 2, 3)))
    expect(
        "span_gutter",
        [_box("both", 0, 300)],
        [100, 150],
        _items(("both", 1, 2)),
        gap=50,
        subgrid_gap=0,
    )
    invalid = take("negative_gap", [100, 150], pair, gap=-50)
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("items") is None and bool(invalid.get("reason")))
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
