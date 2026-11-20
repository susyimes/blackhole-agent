"""Select a CSS font face by width, style, weight, and unicode-range.

A weight from 400 through 500 searches upward before it looks below. Style
beats a closer weight. A composite face tries its later unicode-range first,
and a miss falls through to the next family. An unavailable @font-face family
hides an installed face of the same name. A private-use character skips
generic families. Caseless names match; a combining ring does not match a
precomposed letter.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the matcher still exits 0.
"""

from __future__ import annotations

import json


def _take(result: object) -> dict[str, object]:
    if not isinstance(result, dict):
        return {"outcome": "error"}
    return result


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_font_match import first_available_font, select_font_face
    except Exception as exc:  # noqa: BLE001 - baseline without the matcher still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def pick(name: str, families: object, faces: object, character: object, **kwargs: object) -> dict[str, object]:
        try:
            result = select_font_face(families, faces, character, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised match is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        result = _take(result)
        observed[name] = {
            "outcome": result.get("outcome"),
            "id": result.get("id"),
            "weight": result.get("weight"),
            "style": result.get("style"),
            "angle": result.get("angle"),
            "requested_weight": result.get("requested_weight"),
            "rendered": result.get("rendered"),
            "variation_ignored": result.get("variation_ignored"),
            "reason": result.get("reason"),
        }
        return result

    def expect(name: str, result: dict[str, object], face: str, **fields: object) -> None:
        ok = result.get("outcome") == "matched" and result.get("id") == face
        for key, value in fields.items():
            ok = ok and result.get(key) == value
        checks.append(ok)

    between = [
        {"id": "light", "family": "pair", "weight": 300},
        {"id": "medium", "family": "pair", "weight": 500},
    ]
    expect("weight_400_up_through_500", pick("weight_400_up_through_500", ["pair"], between, "A", weight=400), "medium")
    outside = [
        {"id": "light", "family": "pair", "weight": 300},
        {"id": "heavy", "family": "pair", "weight": 600},
    ]
    expect("weight_400_below_gap", pick("weight_400_below_gap", ["pair"], outside, "A", weight=400), "light")
    upward = [
        {"id": "book", "family": "pair", "weight": 500},
        {"id": "black", "family": "pair", "weight": 900},
    ]
    expect("weight_600_upward", pick("weight_600_upward", ["pair"], upward, "A", weight=600), "black")

    simple = [
        {"id": "normal", "family": "simple", "weight": "normal"},
        {"id": "bold", "family": "simple", "weight": "bold"},
    ]
    for value in (100, 400, 499, 500):
        expect(
            f"wpt_{value}",
            pick(f"wpt_{value}", ["simple"], simple, "A", weight=value),
            "normal",
        )
    for value in (501, 600, 700, 900):
        expect(
            f"wpt_{value}",
            pick(f"wpt_{value}", ["simple"], simple, "A", weight=value),
            "bold",
        )

    widths = [
        {"id": "narrow", "family": "box", "width": "ultra-condensed", "weight": 400},
        {"id": "regular", "family": "box", "width": "normal", "weight": 700},
    ]
    expect(
        "width_before_weight",
        pick("width_before_weight", ["box"], widths, "A", weight=400, width="normal"),
        "regular",
        weight=700,
    )
    stretched = [
        {"id": "normal", "family": "box", "width": "100%", "weight": 400},
        {"id": "expanded", "family": "box", "width": "150%", "weight": 400},
    ]
    expect(
        "width_above_normal",
        pick("width_above_normal", ["box"], stretched, "A", width="125%"),
        "expanded",
    )

    styled = [
        {"id": "ita", "family": "style", "style": "italic", "weight": 400},
        {"id": "obl", "family": "style", "style": "oblique 14deg", "weight": 700},
    ]
    expect("italic_before_oblique", pick("italic_before_oblique", ["style"], styled, "A", style="italic"), "ita")
    expect(
        "oblique_40",
        pick("oblique_40", ["style"], styled, "A", style="oblique 40deg"),
        "obl",
        angle=14,
        style="oblique",
    )
    expect(
        "normal_prefers_oblique",
        pick("normal_prefers_oblique", ["style"], styled, "A", style="normal"),
        "obl",
        angle=14,
    )
    upright = [{"id": "upright", "family": "plain", "style": "normal"}]
    expect(
        "italic_falls_back_to_normal",
        pick("italic_falls_back_to_normal", ["plain"], upright, "A", style="italic"),
        "upright",
        style="normal",
    )

    ranged = [
        {
            "id": "pos",
            "family": "axes",
            "style": "oblique 45deg 67.5deg",
            "weight": "200 300",
            "width": "100%",
        },
        {
            "id": "neg",
            "family": "axes",
            "style": "oblique -67.5deg -45deg",
            "weight": "700 800",
            "width": "100%",
        },
    ]
    expect(
        "style_before_weight_range",
        pick("style_before_weight_range", ["axes"], ranged, "A", style="normal", weight=400),
        "pos",
        weight=300,
        angle=45,
        style="oblique",
    )
    negative = [
        {"id": "near", "family": "slant", "style": "oblique -10deg"},
        {"id": "far", "family": "slant", "style": "oblique -30deg"},
    ]
    expect(
        "negative_oblique",
        pick("negative_oblique", ["slant"], negative, "A", style="oblique -20deg"),
        "far",
        angle=-30,
    )

    composite = [
        {"id": "early", "family": "demo", "weight": 400, "unicode_range": "U+41-5A"},
        {"id": "late", "family": "demo", "weight": 400, "unicode_range": "U+41"},
        {"id": "boldb", "family": "demo", "weight": 700, "unicode_range": "U+62"},
        {"id": "other", "family": "other", "weight": 400},
    ]
    expect("composite_later_range", pick("composite_later_range", ["demo", "other"], composite, "A"), "late")
    expect("composite_earlier_range", pick("composite_earlier_range", ["demo", "other"], composite, "B"), "early")
    expect(
        "range_miss_next_family",
        pick("range_miss_next_family", ["demo", "other"], composite, "b", weight=400),
        "other",
    )

    hidden = [
        {"id": "ghost", "family": "Demo", "source": "font-face", "available": False},
        {"id": "platform", "family": "Demo", "source": "installed"},
        {"id": "next", "family": "Other", "source": "installed"},
    ]
    expect(
        "unavailable_hides_installed",
        pick("unavailable_hides_installed", ["Demo", "Other"], hidden, "A"),
        "next",
    )

    private = [
        {"id": "generic", "family": "DejaVu", "characters": "\ue000A"},
        {"id": "named", "family": "Private", "characters": "\ue000"},
    ]
    generics = {"sans-serif": "DejaVu"}
    expect(
        "generic_family_resolves",
        pick("generic_family_resolves", ["sans-serif"], private, "A", generics=generics),
        "generic",
    )
    expect(
        "pua_skips_generic",
        pick("pua_skips_generic", ["sans-serif", "Private"], private, 0xE000, generics=generics),
        "named",
    )
    pua_only = pick("pua_only_generic", ["sans-serif"], private, 0xE000, generics=generics)
    checks.append(pua_only.get("outcome") == "unmatched" and pua_only.get("id") is None)

    expect("caseless_family", pick("caseless_family", ["ARIAL"], [{"id": "arial", "family": "Arial"}], "A"), "arial")
    ring = pick("combining_ring_distinct", ["a\u030a"], [{"id": "aring", "family": "\u00e5"}], "A")
    checks.append(ring.get("outcome") == "unmatched")

    relatives = [
        {"id": "normal", "family": "rel", "weight": 400},
        {"id": "bold", "family": "rel", "weight": 700},
    ]
    expect(
        "bolder_from_400",
        pick("bolder_from_400", ["rel"], relatives, "A", weight="bolder", inherited_weight=400),
        "bold",
        requested_weight=700,
        weight=700,
    )
    expect(
        "lighter_from_400",
        pick("lighter_from_400", ["rel"], relatives, "A", weight="lighter", inherited_weight=400),
        "normal",
        requested_weight=100,
        weight=400,
    )

    clusters = [
        {"id": "decomp", "family": "a", "characters": "e\u0301"},
        {"id": "pre", "family": "b", "characters": "\u00e9"},
    ]
    expect(
        "cluster_sequence",
        pick("cluster_sequence", ["a", "b"], clusters, "e\u0301"),
        "decomp",
        rendered="e\u0301",
    )
    expect(
        "cluster_canonical",
        pick("cluster_canonical", ["b"], clusters, "e\u0301"),
        "pre",
        rendered="\u00e9",
    )
    selectors = [
        {"id": "base", "family": "a", "characters": "a"},
        {"id": "both", "family": "v", "characters": "a\ufe0e"},
    ]
    expect(
        "variation_ignored",
        pick("variation_ignored", ["a"], selectors, "a\ufe0e"),
        "base",
        variation_ignored=True,
    )
    expect(
        "variation_kept",
        pick("variation_kept", ["v"], selectors, "a\ufe0e"),
        "both",
        variation_ignored=False,
    )

    contained = [
        {"id": "var", "family": "span", "weight": "200 900"},
        {"id": "static", "family": "span", "weight": 700},
    ]
    expect("range_contains_weight", pick("range_contains_weight", ["span"], contained, "A", weight=450), "var", weight=450)
    reversed_range = [{"id": "wide", "family": "rev", "weight": "900 100"}]
    expect("reversed_weight_range", pick("reversed_weight_range", ["rev"], reversed_range, "A", weight=400), "wide", weight=400)

    invalid = pick("weight_zero", ["simple"], simple, "A", weight=0)
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("id") is None)

    try:
        available = first_available_font(
            ["cjk", "latin"],
            [
                {"id": "cjk400", "family": "cjk", "weight": 400, "unicode_range": "U+4E00-9FFF"},
                {"id": "cjk700", "family": "cjk", "weight": 700, "unicode_range": "U+0-7F"},
                {"id": "latin", "family": "latin", "weight": 400},
            ],
            weight=400,
        )
    except Exception as exc:  # noqa: BLE001 - a raised match is an unmet outcome
        available = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
    available = _take(available)
    observed["first_available"] = {
        "outcome": available.get("outcome"),
        "id": available.get("id"),
        "reason": available.get("reason"),
    }
    checks.append(available.get("outcome") == "matched" and available.get("id") == "latin")

    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
