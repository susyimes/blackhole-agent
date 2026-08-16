"""Spine family catalog: leftover name lists derive from one spec walk.

Post-consensus apply order lives here as :data:`SPINE_FAMILY_CHAIN`. Surface
exports, public flags, resume planes, continuity-guard, resume-config, and
want-effects slices are derived from that chain plus the log/pair spec
registries and a compact quirk overlay. A new family is a chain row (and,
when it should be imported, a spec row) — not another copied name tuple.

Historical quirks stay data:

* execution stays off the surface catalog (source-probe wrappers)
* continuity-guard and resume-config stop at resolution
* want-effects stops at capital
* resume prepends finality; config order is reverse(through resolution)
  with finality immediately before execution

A probe extra chain row appears in every derived view its quirks allow.
No skill-route discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# Apply-order catalog. Source variants are historical residue:
# consensus (execution), pred (actuation/settlement), self_pred
# (clearing through margin), self (collateral through supervision).
SPINE_FAMILY_CHAIN: tuple[tuple[str, str, str, str], ...] = (
    ("execution", "finality", "execute", "consensus"),
    ("actuation", "execution", "actuate", "pred"),
    ("settlement", "actuation", "settle", "pred"),
    ("clearing", "settlement", "clear", "self_pred"),
    ("delivery", "clearing", "deliver", "self_pred"),
    ("custody", "delivery", "custody", "self_pred"),
    ("margin", "custody", "margin", "self_pred"),
    ("collateral", "margin", "collateral", "self"),
    ("liquidity", "collateral", "liquidity", "self"),
    ("funding", "liquidity", "funding", "self"),
    ("capital", "funding", "capital", "self"),
    ("solvency", "capital", "solvency", "self"),
    ("risk", "solvency", "risk", "self"),
    ("stress", "risk", "stress", "self"),
    ("recovery", "stress", "recovery", "self"),
    ("resolution", "recovery", "resolution", "self"),
    ("restructuring", "resolution", "restructuring", "self"),
    ("emergence", "restructuring", "emerge", "self"),
    ("reorganization", "emergence", "reorganize", "self"),
    ("rehabilitation", "reorganization", "rehabilitate", "self"),
    ("ratification", "rehabilitation", "ratify", "self"),
    ("supervision", "ratification", "supervise", "self"),
)


@dataclass(frozen=True)
class SpineFamilyQuirks:
    """Historical leftover slices that are data, not another name list."""

    surface_skip: frozenset[str] = frozenset({"execution"})
    continuity_guard_through: str = "resolution"
    want_effects_through: str = "capital"
    config_omit: frozenset[str] = frozenset(
        {
            "emergence",
            "reorganization",
            "rehabilitation",
            "ratification",
            "supervision",
        }
    )
    resume_prepend: tuple[str, ...] = ("finality",)


SPINE_FAMILY_QUIRKS = SpineFamilyQuirks()
SPINE_FAMILY_CATALOG_IMPL = True


def _prefix_through(names: Sequence[str], through: str) -> tuple[str, ...]:
    items = list(names)
    return tuple(items[: items.index(through) + 1])


def derive_spine_family_views(
    *,
    chain: Sequence[tuple[str, str, str, str]] | None = None,
    extra_chain: Sequence[tuple[str, str, str, str]] = (),
    extra_surface_pair: Sequence[str] = (),
    extra_surface_log: Sequence[str] = (),
    quirks: SpineFamilyQuirks | None = None,
    log_families: Sequence[str] | None = None,
    pair_families: Sequence[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Derive every leftover family name list from the catalog + quirks.

    ``extra_chain`` / ``extra_surface_*`` are the probe surface: a new family
    is appended and appears in every derived view its kind and quirks allow.
    """

    quirks = quirks or SPINE_FAMILY_QUIRKS
    rows = tuple(chain or SPINE_FAMILY_CHAIN) + tuple(extra_chain)
    post = tuple(row[0] for row in rows)
    if log_families is None or pair_families is None:
        from blackhole_agent.upstream_total_spine_effects import PAIR_EFFECT_SPECS
        from blackhole_agent.upstream_total_spine_logs import LOG_FAMILY_SPECS

        if log_families is None:
            log_families = tuple(LOG_FAMILY_SPECS)
        if pair_families is None:
            pair_families = tuple(PAIR_EFFECT_SPECS)
    surface_log = tuple(
        name for name in log_families if name not in quirks.surface_skip
    ) + tuple(extra_surface_log)
    surface_pair = tuple(pair_families) + tuple(extra_surface_pair)
    resume = tuple(quirks.resume_prepend) + post
    through_guard = _prefix_through(post, quirks.continuity_guard_through)
    through_effects = _prefix_through(post, quirks.want_effects_through)
    continuity_guard = tuple(quirks.resume_prepend) + through_guard
    want_effects = tuple(quirks.resume_prepend) + through_effects
    config_core = [
        name for name in reversed(through_guard) if name not in quirks.config_omit
    ]
    if config_core and config_core[-1] == "execution":
        config_order = tuple(config_core[:-1] + ["finality", "execution"])
    else:
        config_order = tuple(config_core)
    return {
        "post_consensus": post,
        "public_flags": post,
        "resume_planes": resume,
        "surface_log": surface_log,
        "surface_pair": surface_pair,
        "surface_families": surface_log + surface_pair,
        "continuity_guard": continuity_guard,
        "want_effects": want_effects,
        "config_order": config_order,
    }
