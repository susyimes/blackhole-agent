"""Consume shipped leftovers so genesis cannot reopen closed 402 follow-on work.

The harvested leftover from 20260817T120603Z-e58518e3 still says a bounded
mission-plane should run after cheap-anchor rotation. That follow-on, plus
succession, resume, and local contract finality, already exists and is
proved. Experience fuel nevertheless re-injects the original next_step into
every later genesis because leftover harvest never checks whether later
missions or the ledger already closed the claim.

This module:

- treats a leftover as satisfied when a later complete mission overlaps it,
  a proved ledger capability matches a leftover marker, or a durable claim
  was consumed
- consults the origin/lineage-tip ledger, not only a lagging checkout, so a
  shipped leftover whose closer already landed on origin cannot re-enter
  genesis fuel
- keeps unsatisfied leftovers in genesis fuel
- binds remaining leftovers to a campaign-relative ``program_passes``
  contract so 402-local ticks can complete them
- consumes a leftover-bound campaign after local finality so the next
  genesis cannot reopen it, including leftover-prefixed goals bound from
  ``state.goal`` rather than the leftover class
- stamps a durable leftover-claim when a proved ledger marker already
  closes the leftover, so 402-local campaigns do not re-bind it
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
)

SCHEMA_VERSION = 1
CLAIMS_RELATIVE = Path(".blackhole-agent") / "unbound" / "leftover-claims.json"
PHRASE_OVERLAP_MIN = 2
MISSION_SCAN_LIMIT = 32
LEFTOVER_CLASS = "mission_leftover"
LEFTOVER_GOAL_PREFIX = f"Close operational class `{LEFTOVER_CLASS}`: "

KERNEL_LEFTOVER_DONE_WHEN = (
    "capability_exists:capability.kernel-leftover;"
    "capability_proved:capability.kernel-leftover;"
    "no_skill_route"
)
KERNEL_LEFTOVER_GOAL = (
    "When a leftover next_step has already been completed by a later mission "
    "or a proved ledger capability, do not re-inject it as genesis fuel. "
    "Remaining leftovers bind a campaign-relative contract so a 402-local "
    "campaign can complete and consume them instead of reopening shipped work."
)

HARVESTED_MISSION_PLANE_LEFTOVER = (
    "Sovereign local kernel is live. Optional follow-on is a bounded "
    "mission-plane program on local ticks once cheap-anchor rotation is exhausted."
)

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "to",
        "of",
        "on",
        "in",
        "for",
        "and",
        "or",
        "once",
        "after",
        "before",
        "from",
        "with",
        "without",
        "that",
        "this",
        "its",
        "as",
        "at",
        "by",
        "it",
        "via",
        "than",
        "then",
        "when",
        "while",
        "into",
        "over",
        "under",
        "not",
        "no",
        "nor",
        "so",
        "if",
        "but",
        "out",
        "up",
        "down",
        "off",
        "can",
        "must",
        "may",
        "does",
        "did",
        "optional",
    }
)
_CAP_ID = re.compile(r"capability\.[a-z0-9][a-z0-9.-]*", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MARKERS = (
    ("mission-worktree reclamation of stale", "capability.worktree-gc-resilience"),
    ("no longer a git working tree", "capability.worktree-gc-resilience"),
    ("last_worktree_gc_error sticky", "capability.worktree-gc-resilience"),
    ("is not a working tree still fails", "capability.worktree-gc-resilience"),
    ("leftover harvest isolation", "capability.leftover-lineage-plane"),
    ("lagging checkout leftover", "capability.leftover-lineage-plane"),
    ("shipped leftover still enters genesis fuel", "capability.leftover-lineage-plane"),
    ("origin leftover closer", "capability.leftover-lineage-plane"),
    ("only reads the lagging checkout ledger", "capability.leftover-lineage-plane"),
    ("mission-plane", "capability.kernel-mission-plane"),
    ("mission plane", "capability.kernel-mission-plane"),
    ("campaign handoff", "capability.kernel-resume"),
    ("resume from the local campaign", "capability.kernel-resume"),
    ("machine-checkable campaign contract", "capability.kernel-finality"),
    ("without a first-class", "capability.kernel-unscoped-resume"),
    ("class_closed left genesis", "capability.kernel-unscoped-resume"),
    ("unscoped genesis", "capability.kernel-unscoped-resume"),
    ("consumed local campaign", "capability.kernel-genesis-bind"),
    ("gate-passing successor", "capability.kernel-genesis-bind"),
    ("blocked selection", "capability.kernel-genesis-bind"),
    ("saturated forage cannot stall", "capability.kernel-genesis-bind"),
    ("cheap inventory ticks", "capability.kernel-consumed-growth"),
    ("new ledger leaf in-process", "capability.kernel-consumed-growth"),
    ("recovered kernels compound capability", "capability.kernel-consumed-growth"),
    ("stalled growth", "capability.kernel-consumed-growth"),
    ("absorbed leaves from consumed", "capability.kernel-compound-loop"),
    ("stalled compounding", "capability.kernel-compound-loop"),
    ("novelty-ranked growth loop", "capability.kernel-compound-loop"),
    ("expanding primitive coverage", "capability.kernel-compound-loop"),
    ("novelty-ranked in-process primitive leaves", "capability.kernel-primitive-compose"),
    ("stalled composition", "capability.kernel-primitive-compose"),
    ("ready multi-primitive composition", "capability.kernel-primitive-compose"),
    ("keep compounding programs", "capability.kernel-primitive-compose"),
    ("in-process multi-primitive compositions", "capability.kernel-composed-program"),
    ("stalled program compounding", "capability.kernel-composed-program"),
    ("ready composed program", "capability.kernel-composed-program"),
    ("keep stacking programs", "capability.kernel-composed-program"),
    ("in-process composed programs", "capability.kernel-program-stack"),
    ("stalled program stacking", "capability.kernel-program-stack"),
    ("ready stacked program", "capability.kernel-program-stack"),
    ("keep compounding towers", "capability.kernel-program-stack"),
    ("stalled lattice compounding", "capability.kernel-program-tower"),
    ("ready program tower", "capability.kernel-program-tower"),
    ("keep compounding lattices", "capability.kernel-program-tower"),
    ("unique stacked-program coverage", "capability.kernel-program-tower"),
    ("stalled fabric compounding", "capability.kernel-program-lattice"),
    ("ready program lattice", "capability.kernel-program-lattice"),
    ("keep compounding fabrics", "capability.kernel-program-lattice"),
    ("unique program-tower coverage", "capability.kernel-program-lattice"),
    ("stalled weave compounding", "capability.kernel-program-fabric"),
    ("ready program fabric", "capability.kernel-program-fabric"),
    ("keep compounding weaves", "capability.kernel-program-fabric"),
    ("unique program-lattice coverage", "capability.kernel-program-fabric"),
    ("stalled tapestry compounding", "capability.kernel-program-weave"),
    ("ready program weave", "capability.kernel-program-weave"),
    ("keep compounding tapestries", "capability.kernel-program-weave"),
    ("program fabrics fill unique coverage", "capability.kernel-program-weave"),
    ("empty successor", "capability.kernel-genesis-diversify"),
    ("diversity-ranked mission", "capability.kernel-genesis-diversify"),
    ("catalog successor fails controller selection", "capability.kernel-genesis-diversify"),
    ("leave genesis unbound", "capability.kernel-genesis-diversify"),
    ("mission-memory recall", "capability.kernel-mission-memory"),
    ("replayed from durable memory", "capability.kernel-mission-memory"),
    ("re-invented instead of replayed", "capability.kernel-mission-memory"),
    ("kernel health persistence", "capability.kernel-half-open-persist"),
    ("half-open probe", "capability.kernel-half-open-persist"),
    ("cooldown has elapsed still records state=open", "capability.kernel-half-open-persist"),
    ("mcp client handshake isolation", "capability.mcp-handshake-isolation"),
    ("initialize response never arrives", "capability.mcp-handshake-isolation"),
    ("dead handshake", "capability.mcp-handshake-isolation"),
    ("mcp tool-call isolation", "capability.mcp-call-isolation"),
    ("tools/call never returns", "capability.mcp-call-isolation"),
    ("hung actuation", "capability.mcp-call-isolation"),
    ("blocks sibling plugins on the same plane", "capability.mcp-call-isolation"),
    ("tools/list never returned", "capability.mcp-call-isolation"),
    ("red producer fails the mixed absorbed stack grade", "capability.absorbed-stack-health-plane"),
    ("folding absorbed composition pipelines into goal-stack health", "capability.absorbed-stack-health-plane"),
    ("absorbed composition pipelines into goal-stack health", "capability.absorbed-stack-health-plane"),
    ("mixed absorbed stack grade", "capability.absorbed-stack-health-plane"),
    ("healable producer restores mixed absorbed stack health", "capability.absorbed-stack-repair-plane"),
    ("restores mixed absorbed stack health", "capability.absorbed-stack-repair-plane"),
    ("mixed absorbed stack repair so a healable producer", "capability.absorbed-stack-repair-plane"),
    ("mixed absorbed stack repair", "capability.absorbed-stack-repair-plane"),
    ("healable hop restores mixed stack health", "capability.mcp-stack-repair-plane"),
    ("restore mixed stack health", "capability.mcp-stack-repair-plane"),
    ("mixed stack repair so a healable hop", "capability.mcp-stack-repair-plane"),
    ("mixed stack repair", "capability.mcp-stack-repair-plane"),
    ("red hop fails the stack grade", "capability.mcp-stack-health-plane"),
    ("folding mixed python-to-mcp pipelines into goal-stack health", "capability.mcp-stack-health-plane"),
    ("mixed python-to-mcp pipelines into goal-stack health", "capability.mcp-stack-health-plane"),
    ("mcp hop spof is counted", "capability.mcp-fragility-plane"),
    ("mcp hop spof", "capability.mcp-fragility-plane"),
    ("counted in blast radius", "capability.mcp-fragility-plane"),
    ("mixed mcp+absorbed goals on the fragility plane", "capability.mcp-fragility-plane"),
    ("scoring mixed mcp+absorbed", "capability.mcp-fragility-plane"),
    ("red mcp hop is healed", "capability.mcp-recovery-plane"),
    ("red mcp hop", "capability.mcp-recovery-plane"),
    ("mixed mcp+absorbed goals in the recovery plane", "capability.mcp-recovery-plane"),
    ("hidden mcp hop", "capability.mcp-reliability-plane"),
    ("mcp hop is named drift", "capability.mcp-reliability-plane"),
    ("mixed mcp+absorbed goals in the reliability plane", "capability.mcp-reliability-plane"),
    ("planner isolation of live mcp", "capability.mcp-application-bridge"),
    ("live mcp tool as an application step", "capability.mcp-application-bridge"),
    ("mixed mcp+absorbed goal is planner-derived", "capability.mcp-application-bridge"),
    ("mixed mcp and absorbed", "capability.mcp-application-bridge"),
    ("python→mcp", "capability.mcp-application-bridge"),
    ("python->mcp", "capability.mcp-application-bridge"),
    ("broken typed key-bridge ships as a healthy stack", "capability.absorbed-reliability-plane"),
    ("absorbed composition goals are invisible", "capability.absorbed-reliability-plane"),
    ("named drift when the bridge is hidden", "capability.absorbed-reliability-plane"),
    ("validation replay timed out", "capability.validation-replay-resilience"),
    ("validation_replay_failed", "capability.validation-replay-resilience"),
    ("controller replay times out", "capability.validation-replay-resilience"),
    ("bounded sealed witness", "capability.validation-replay-resilience"),
    ("red absorbed producer", "capability.absorbed-recovery-plane"),
    ("typed composition pipeline unplannable", "capability.absorbed-recovery-plane"),
    ("recovery loop never heals", "capability.absorbed-recovery-plane"),
    ("lagging controller checkout", "capability.local-mission-sovereignty"),
    ("already-proved harvested contract", "capability.local-mission-sovereignty"),
    ("lineage-tip ledger", "capability.kernel-class-closure"),
    ("node runtime", "capability.foraging-plane"),
    ("multi-callable bundle", "capability.foraging-plane"),
    ("bundle foraging", "capability.foraging-plane"),
    ("trend-driven automatic forage-target", "capability.forage-target-plane"),
    ("trend-driven automatic target selection", "capability.forage-target-plane"),
    ("forage-target selection", "capability.forage-target-plane"),
    ("goal-driven forage match", "capability.forage-growth-plane"),
    ("forage matching that ignores", "capability.forage-growth-plane"),
    ("pre-declared catalog provides", "capability.forage-growth-plane"),
    ("unplannable application goal", "capability.application-growth-plane"),
    ("without a separate plane invocation", "capability.application-growth-plane"),
    ("forage matching without a separate", "capability.application-growth-plane"),
    ("live-registry catalog refresh", "capability.application-live-growth-plane"),
    ("live npm/pypi search", "capability.application-live-growth-plane"),
    ("instead of a frozen catalog", "capability.application-live-growth-plane"),
    ("no replay_source", "capability.application-registry-growth-plane"),
    ("without a fixture overlay", "capability.application-registry-growth-plane"),
    ("covering registry package", "capability.application-registry-growth-plane"),
    ("live-fetch probing", "capability.application-live-fetch-growth-plane"),
    ("no on-disk archive", "capability.application-live-fetch-growth-plane"),
    ("stewardship tree has never seen", "capability.application-live-fetch-growth-plane"),
    ("transitive runtime dependencies", "capability.application-runtime-deps-growth-plane"),
    ("import-unclosed sdists", "capability.application-runtime-deps-growth-plane"),
    ("runtime dependencies of a fetched", "capability.application-runtime-deps-growth-plane"),
    ("package.json dependencies", "capability.application-node-runtime-deps-growth-plane"),
    ("import-unclosed npm", "capability.application-node-runtime-deps-growth-plane"),
    ("node package.json", "capability.application-node-runtime-deps-growth-plane"),
    ("live-fetched tarball", "capability.application-node-runtime-deps-growth-plane"),
    ("default-export-only", "capability.application-node-default-export-growth-plane"),
    ("default exports", "capability.application-node-default-export-growth-plane"),
    ("node default export", "capability.application-node-default-export-growth-plane"),
    ("reflecting node default exports", "capability.application-node-default-export-growth-plane"),
    ("default-exported objects", "capability.application-node-default-export-object-growth-plane"),
    ("namespace of functions", "capability.application-node-default-export-object-growth-plane"),
    ("default export is a namespace", "capability.application-node-default-export-object-growth-plane"),
    ("default-exported classes", "capability.application-node-default-export-class-growth-plane"),
    ("constructable API", "capability.application-node-default-export-class-growth-plane"),
    ("default export is a constructable", "capability.application-node-default-export-class-growth-plane"),
    ("node class static methods", "capability.application-node-class-static-growth-plane"),
    ("class.method rather than new", "capability.application-node-class-static-growth-plane"),
    ("new class().method", "capability.application-node-class-static-growth-plane"),
    ("static methods on named class exports", "capability.application-node-named-class-static-growth-plane"),
    ("nested namespace classes", "capability.application-node-named-class-static-growth-plane"),
    ("base64.encode", "capability.application-node-named-class-static-growth-plane"),
    ("buffer.buffer.bytelength", "capability.application-node-named-class-static-growth-plane"),
    ("constructor requires arguments", "capability.application-node-named-class-construct-growth-plane"),
    ("parser(options).parse", "capability.application-node-named-class-construct-growth-plane"),
    ("new parser(options)", "capability.application-node-named-class-construct-growth-plane"),
    ("python class instance methods", "capability.application-python-class-instance-growth-plane"),
    ("parser(opts).loads rather than a module-level", "capability.application-python-class-instance-growth-plane"),
    ("python class static methods", "capability.application-python-class-static-growth-plane"),
    ("class.method rather than parser", "capability.application-python-class-static-growth-plane"),
    ("python nested-namespace class statics six submodule", "capability.application-python-sext-nested-static-growth-plane"),
    ("six-level nested class.method static", "capability.application-python-sext-nested-static-growth-plane"),
    ("rather than a five-level nested class.method static", "capability.application-python-sext-nested-static-growth-plane"),
    ("python nested-namespace class statics five submodule", "capability.application-python-quint-nested-static-growth-plane"),
    ("cwd-independent json scalar", "capability.application-python-quint-nested-static-growth-plane"),
    ("rather than an inherited path validator", "capability.application-python-quint-nested-static-growth-plane"),
    ("python nested-namespace class instance methods one hundred sixty submodule", "capability.application-python-sexaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-nine submodule", "capability.application-python-novemquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-eight submodule", "capability.application-python-octoquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-seven submodule", "capability.application-python-septemquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-six submodule", "capability.application-python-sexquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-five submodule", "capability.application-python-quinquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-four submodule", "capability.application-python-quattuorquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-three submodule", "capability.application-python-trequinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-two submodule", "capability.application-python-duoquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty-one submodule", "capability.application-python-unquinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifty submodule", "capability.application-python-quinquaginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-nine submodule", "capability.application-python-novemquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-eight submodule", "capability.application-python-octoquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-seven submodule", "capability.application-python-septemquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-six submodule", "capability.application-python-sexquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-five submodule", "capability.application-python-quinquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-four submodule", "capability.application-python-quattuorquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-three submodule", "capability.application-python-trequadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-two submodule", "capability.application-python-duoquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty-one submodule", "capability.application-python-unquadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred forty submodule", "capability.application-python-quadraginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-nine submodule", "capability.application-python-novemtriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-eight submodule", "capability.application-python-octotriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-seven submodule", "capability.application-python-septemtriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-six submodule", "capability.application-python-sextriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-five submodule", "capability.application-python-quintriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-four submodule", "capability.application-python-quattuortriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-three submodule", "capability.application-python-tretriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-two submodule", "capability.application-python-duotriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty-one submodule", "capability.application-python-untriginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirty submodule", "capability.application-python-triginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-nine submodule", "capability.application-python-novemviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-eight submodule", "capability.application-python-octoviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-seven submodule", "capability.application-python-septemviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-six submodule", "capability.application-python-sexviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-five submodule", "capability.application-python-quinviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-four submodule", "capability.application-python-quattuorviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-three submodule", "capability.application-python-treviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-two submodule", "capability.application-python-duoviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty-one submodule", "capability.application-python-unviginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twenty submodule", "capability.application-python-viginticent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred nineteen submodule", "capability.application-python-novemdecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred eighteen submodule", "capability.application-python-octodecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred seventeen submodule", "capability.application-python-septendecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred sixteen submodule", "capability.application-python-sexdecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fifteen submodule", "capability.application-python-quindecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred fourteen submodule", "capability.application-python-quattuordecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred thirteen submodule", "capability.application-python-tredecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred twelve submodule", "capability.application-python-duodecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred eleven submodule", "capability.application-python-undecicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred ten submodule", "capability.application-python-decicent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred nine submodule", "capability.application-python-novemcent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred eight submodule", "capability.application-python-octocent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred seven submodule", "capability.application-python-septencent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred six submodule", "capability.application-python-sexcent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred five submodule", "capability.application-python-quincent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred four submodule", "capability.application-python-quattuorcent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred three submodule", "capability.application-python-trecent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred two submodule", "capability.application-python-duocent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred one submodule", "capability.application-python-uncent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods one hundred submodule", "capability.application-python-cent-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-nine submodule", "capability.application-python-novnonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-eight submodule", "capability.application-python-octnonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-seven submodule", "capability.application-python-septnonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-six submodule", "capability.application-python-sexnonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-five submodule", "capability.application-python-quinnonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-four submodule", "capability.application-python-quattuornonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-three submodule", "capability.application-python-trenonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-two submodule", "capability.application-python-duononagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety-one submodule", "capability.application-python-unnonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ninety submodule", "capability.application-python-nonagint-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-nine submodule", "capability.application-python-novoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-eight submodule", "capability.application-python-octoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-seven submodule", "capability.application-python-septoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-six submodule", "capability.application-python-sexoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-five submodule", "capability.application-python-quinoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-four submodule", "capability.application-python-quatoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-three submodule", "capability.application-python-treoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-two submodule", "capability.application-python-duoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty-one submodule", "capability.application-python-unoctog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighty submodule", "capability.application-python-octog-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-nine submodule", "capability.application-python-novseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-eight submodule", "capability.application-python-octseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-seven submodule", "capability.application-python-septseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-six submodule", "capability.application-python-sexseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-five submodule", "capability.application-python-quinseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-four submodule", "capability.application-python-quatseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-three submodule", "capability.application-python-treseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-two submodule", "capability.application-python-duoseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy-one submodule", "capability.application-python-unseptuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventy submodule", "capability.application-python-septuag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-nine submodule", "capability.application-python-novsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-eight submodule", "capability.application-python-octsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-seven submodule", "capability.application-python-septsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-six submodule", "capability.application-python-sexsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-five submodule", "capability.application-python-quinsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-four submodule", "capability.application-python-quatsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-three submodule", "capability.application-python-tresex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-two submodule", "capability.application-python-duosex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty-one submodule", "capability.application-python-unsex-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixty submodule", "capability.application-python-sexag-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-nine submodule", "capability.application-python-novqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-eight submodule", "capability.application-python-octqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-seven submodule", "capability.application-python-septqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-six submodule", "capability.application-python-sexqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-five submodule", "capability.application-python-qiqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-four submodule", "capability.application-python-quatqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-three submodule", "capability.application-python-treqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-two submodule", "capability.application-python-duoqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty-one submodule", "capability.application-python-unqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifty submodule", "capability.application-python-quinqi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-nine submodule", "capability.application-python-novqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-eight submodule", "capability.application-python-octqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-seven submodule", "capability.application-python-septqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-six submodule", "capability.application-python-sexqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-five submodule", "capability.application-python-quinqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-four submodule", "capability.application-python-quatqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-three submodule", "capability.application-python-trequa-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-two submodule", "capability.application-python-duoqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty-one submodule", "capability.application-python-unqua-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods forty submodule", "capability.application-python-quadra-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-nine submodule", "capability.application-python-novtr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-eight submodule", "capability.application-python-octtr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-seven submodule", "capability.application-python-septr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-six submodule", "capability.application-python-sextr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-five submodule", "capability.application-python-quintr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-four submodule", "capability.application-python-quattr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-three submodule", "capability.application-python-tretr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-two submodule", "capability.application-python-duotr-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty-one submodule", "capability.application-python-untri-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirty submodule", "capability.application-python-trigi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-nine submodule", "capability.application-python-novvi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-eight submodule", "capability.application-python-octov-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-seven submodule", "capability.application-python-septv-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-six submodule", "capability.application-python-sexvi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-five submodule", "capability.application-python-quinv-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-four submodule", "capability.application-python-quatv-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-three submodule", "capability.application-python-trevi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-two submodule", "capability.application-python-duovi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty-one submodule", "capability.application-python-unvig-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twenty submodule", "capability.application-python-vigi-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods nineteen submodule", "capability.application-python-novem-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eighteen submodule", "capability.application-python-octod-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seventeen submodule", "capability.application-python-septd-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods sixteen submodule", "capability.application-python-sexde-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fifteen submodule", "capability.application-python-quind-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods fourteen submodule", "capability.application-python-quatt-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods thirteen submodule", "capability.application-python-trede-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods twelve submodule", "capability.application-python-dodec-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eleven submodule", "capability.application-python-undec-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods ten submodule", "capability.application-python-deca-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods nine submodule", "capability.application-python-nona-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods eight submodule", "capability.application-python-oct-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods seven submodule", "capability.application-python-sept-nested-instance-growth-plane"),
    ("rather than a six-level nested class().method instance", "capability.application-python-sept-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods six submodule", "capability.application-python-sext-nested-instance-growth-plane"),
    ("covering api is a six-level nested class().method instance", "capability.application-python-sext-nested-instance-growth-plane"),
    ("rather than a five-level nested class().method instance", "capability.application-python-sext-nested-instance-growth-plane"),
    ("python nested-namespace class instance methods five submodule", "capability.application-python-quint-nested-instance-growth-plane"),
    ("package.subpackage.subpackage.subpackage.subpackage.submodule.class().method", "capability.application-python-quint-nested-instance-growth-plane"),
    ("rather than a four-level nested class.method static", "capability.application-python-quint-nested-instance-growth-plane"),
    ("python nested-namespace class statics four submodule", "capability.application-python-quad-nested-static-growth-plane"),
    ("package.subpackage.subpackage.subpackage.submodule.class.method", "capability.application-python-quad-nested-static-growth-plane"),
    ("rather than a three-level package.subpackage.subpackage.submodule.class.method", "capability.application-python-quad-nested-static-growth-plane"),
    ("python nested-namespace class statics three submodule", "capability.application-python-triple-nested-static-growth-plane"),
    ("package.subpackage.subpackage.submodule.class.method rather than a two-level", "capability.application-python-triple-nested-static-growth-plane"),
    ("rather than a two-level package.subpackage.submodule.class.method", "capability.application-python-triple-nested-static-growth-plane"),
    ("python nested-namespace class statics two submodule", "capability.application-python-deep-nested-static-growth-plane"),
    ("package.subpackage.submodule.class.method rather than a two-level module function", "capability.application-python-deep-nested-static-growth-plane"),
    ("python nested-namespace class statics so", "capability.application-python-nested-class-static-growth-plane"),
    ("rather than a top-level class.method", "capability.application-python-nested-class-static-growth-plane"),
    ("python nested-namespace class instance methods so", "capability.application-python-nested-class-instance-growth-plane"),
    ("api is package.submodule.class(opts).method", "capability.application-python-nested-class-instance-growth-plane"),
    ("rather than package.submodule.class.method", "capability.application-python-nested-class-instance-growth-plane"),
    ("python nested-namespace class instance methods two submodule", "capability.application-python-deep-nested-instance-growth-plane"),
    ("two submodule levels down so sdists whose api is package.subpackage.submodule.class(opts).method", "capability.application-python-deep-nested-instance-growth-plane"),
    ("package.subpackage.submodule.class(opts).method", "capability.application-python-deep-nested-instance-growth-plane"),
    ("rather than package.submodule.class(opts).method", "capability.application-python-deep-nested-instance-growth-plane"),
    ("functions exported only on nested submodules", "capability.application-python-nested-function-growth-plane"),
    ("package.subpackage.submodule.func rather than a class method", "capability.application-python-nested-function-growth-plane"),
    ("package.submodule.func rather than a class method", "capability.application-python-nested-function-growth-plane"),
    ("functions exported two submodule levels down", "capability.application-python-deep-nested-function-growth-plane"),
    ("package.subpackage.submodule.func rather than package.submodule.func", "capability.application-python-deep-nested-function-growth-plane"),
    ("instance methods on named class exports", "capability.application-node-named-class-instance-growth-plane"),
    ("named class instance", "capability.application-node-named-class-instance-growth-plane"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leftover_claim_id(text: str) -> str:
    normalized = " ".join(str(text or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def leftover_tokens(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(str(text or "").lower()) if token not in _STOP and len(token) >= 3]


def leftover_phrases(text: str) -> set[str]:
    tokens = leftover_tokens(text)
    return {f"{tokens[index]} {tokens[index + 1]}" for index in range(len(tokens) - 1)}


def leftover_phrase_overlap(left: str, right: str) -> int:
    return len(leftover_phrases(left) & leftover_phrases(right))


def leftover_marker_ids(text: str) -> tuple[str, ...]:
    lowered = str(text or "").lower()
    found: list[str] = []
    for marker, capability_id in _MARKERS:
        if marker in lowered and capability_id not in found:
            found.append(capability_id)
    for match in _CAP_ID.findall(lowered):
        if match not in found:
            found.append(match)
    return tuple(found)


def claims_path(root: Path) -> Path:
    return Path(root) / CLAIMS_RELATIVE


def load_leftover_claims(root: Path) -> dict[str, Any]:
    path = claims_path(root)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "claims": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "claims": {}}
    if not isinstance(payload, Mapping):
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "claims": {}}
    raw = payload.get("claims") if isinstance(payload.get("claims"), Mapping) else {}
    return {
        "schema_version": int(payload.get("schema_version") or SCHEMA_VERSION),
        "updated_at": str(payload.get("updated_at") or ""),
        "claims": {str(key): dict(value) for key, value in raw.items() if isinstance(value, Mapping)},
    }


def save_leftover_claims(root: Path, payload: Mapping[str, Any]) -> Path:
    path = claims_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": int(payload.get("schema_version") or SCHEMA_VERSION),
        "updated_at": _utc_now(),
        "claims": dict(payload.get("claims") or {}),
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def leftover_claim_consumed(root: Path, text: str) -> bool:
    claim = (load_leftover_claims(root).get("claims") or {}).get(leftover_claim_id(text)) or {}
    return bool(str(claim.get("consumed_at") or "").strip())


def consume_leftover(
    root: Path,
    text: str,
    *,
    satisfied_by: str,
    source_mission_id: str = "",
) -> str:
    payload = load_leftover_claims(root)
    claims = dict(payload.get("claims") or {})
    claim_id = leftover_claim_id(text)
    claims[claim_id] = {
        "consumed_at": _utc_now(),
        "satisfied_by": str(satisfied_by or "")[:200],
        "source_mission_id": str(source_mission_id or ""),
        "summary": str(text or "")[:400],
    }
    payload["claims"] = claims
    save_leftover_claims(root, payload)
    return claim_id


def leftover_summary_from_goal(goal: str) -> str:
    text = str(goal or "").strip()
    if text.startswith(LEFTOVER_GOAL_PREFIX):
        return text[len(LEFTOVER_GOAL_PREFIX) :].strip()
    return text


def campaign_binds_leftover(campaign: Any) -> bool:
    """True when a local campaign is leftover-bound by source or leftover-prefixed goal.

    Cheap 402-local ticks often bind from ``state.goal+state.done_when`` after
    genesis already copied a leftover into the mission goal. Those campaigns
    still close the leftover class and must consume the claim.
    """

    bound = str(getattr(campaign, "bound_from", "") or "")
    goal = str(getattr(campaign, "goal", "") or "")
    return LEFTOVER_CLASS in bound or goal.startswith(LEFTOVER_GOAL_PREFIX)


def _load_checkout_ledger(root: Path) -> CapabilityLedger | None:
    path = default_ledger_path(Path(root))
    if not path.exists():
        return None
    try:
        return load_ledger(path)
    except Exception:  # noqa: BLE001 - leftover harvest must still return fuel
        return None


def _load_repo_ledger(root: Path, *, lineage_ref: str = "") -> CapabilityLedger | None:
    """Working-tree ledger plus proved leftover closers from the origin tip.

    Leftover harvest runs against the controller checkout, which can lag the
    published lineage. Marker satisfaction must still see closers that exist
    only on ``lineage_ref``.
    """

    try:
        from blackhole_agent.kernel_class_closure import load_effective_ledger

        merged = load_effective_ledger(Path(root), lineage_ref=lineage_ref)
        if merged is not None:
            return merged
    except Exception:  # noqa: BLE001 - leftover harvest must still consult the checkout
        pass
    return _load_checkout_ledger(root)


def _ledger_proves(ledger: CapabilityLedger | None, capability_id: str) -> bool:
    if ledger is None:
        return False
    capability = ledger.capabilities.get(capability_id)
    return bool(capability is not None and capability.last_proof_exit_code == 0)


def _mission_states(root: Path, *, limit: int = MISSION_SCAN_LIMIT) -> list[dict[str, Any]]:
    missions_dir = Path(root) / ".blackhole-agent" / "unbound" / "missions"
    if not missions_dir.is_dir():
        return []
    files = sorted(
        (path for path in missions_dir.glob("*/state.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    states: list[dict[str, Any]] = []
    for path in files[: max(1, int(limit))]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping):
            states.append(dict(payload))
    return states


def _complete_mission_text(state: Mapping[str, Any]) -> str:
    parts = [
        str(state.get("goal") or ""),
        str(state.get("last_summary") or ""),
        str(state.get("done_when") or ""),
    ]
    for milestone in list(state.get("milestones") or []):
        if isinstance(milestone, Mapping):
            parts.append(str(milestone.get("capability_delta") or ""))
    for turn in list(state.get("recent_turns") or []):
        if isinstance(turn, Mapping):
            parts.extend(
                [
                    str(turn.get("capability_delta") or ""),
                    str(turn.get("summary") or ""),
                    str(turn.get("mission_goal") or ""),
                ]
            )
    return " ".join(part for part in parts if part.strip())


def leftover_satisfied_by(
    text: str,
    root: Path,
    *,
    source_mission_id: str = "",
    ledger: CapabilityLedger | None = None,
    lineage_ref: str = "",
) -> str:
    """Return a short reason when leftover work is already closed, else empty.

    ``ledger`` pins satisfaction to an explicit snapshot (used to prove a
    lagging checkout still sees the leftover). When omitted, the origin
    lineage ledger is merged so a closer that already landed on the
    published tip consumes the leftover.
    """

    leftover = " ".join(str(text or "").split())
    if not leftover:
        return "empty"
    if leftover_claim_consumed(root, leftover):
        claim = (load_leftover_claims(root).get("claims") or {}).get(leftover_claim_id(leftover)) or {}
        return str(claim.get("satisfied_by") or "claim_consumed")
    live_ledger = (
        ledger if ledger is not None else _load_repo_ledger(root, lineage_ref=lineage_ref)
    )
    markers = leftover_marker_ids(leftover)
    for capability_id in markers:
        if _ledger_proves(live_ledger, capability_id):
            reason = f"ledger:{capability_id}"
            consume_leftover(
                root,
                leftover,
                satisfied_by=reason,
                source_mission_id=source_mission_id,
            )
            return reason
    if markers:
        return ""
    skip = str(source_mission_id or "").strip()
    source_created = ""
    if skip:
        for state in _mission_states(root):
            if str(state.get("mission_id") or "") == skip:
                source_created = str(state.get("created_at") or "")
                break
    for state in _mission_states(root):
        mission_id = str(state.get("mission_id") or "")
        if skip and mission_id == skip:
            continue
        if str(state.get("status") or "") != "complete":
            continue
        other_created = str(state.get("created_at") or "")
        if source_created and other_created and other_created <= source_created:
            continue
        other = _complete_mission_text(state)
        if leftover_phrase_overlap(leftover, other) >= PHRASE_OVERLAP_MIN:
            return f"later_mission:{mission_id or 'unknown'}"
    return ""


def leftover_is_open(
    text: str,
    root: Path,
    *,
    source_mission_id: str = "",
    ledger: CapabilityLedger | None = None,
    lineage_ref: str = "",
) -> bool:
    return not leftover_satisfied_by(
        text,
        root,
        source_mission_id=source_mission_id,
        ledger=ledger,
        lineage_ref=lineage_ref,
    )


def leftover_campaign_done_when(goal: str, ledger: CapabilityLedger | None = None) -> str:
    """Campaign-relative contract a leftover-bound 402-local tick can satisfy."""

    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        plan_campaign_program,
    )

    if ledger is None:
        return HARVESTED_KERNEL_FAILURE_DONE_WHEN
    try:
        steps = plan_campaign_program(ledger, goal or "", max_steps=1)
    except Exception:  # noqa: BLE001 - leftover bind must still choose a contract
        steps = []
    if steps:
        return f"program_passes:{steps[0]};no_skill_route"
    return HARVESTED_KERNEL_FAILURE_DONE_WHEN


def consume_bound_leftover(root: Path, campaign: Any) -> bool:
    """Persist leftover consumption after a leftover-bound local finality."""

    if not campaign_binds_leftover(campaign):
        return False
    handoff = dict(getattr(campaign, "handoff", None) or {})
    summary = str(handoff.get("leftover_summary") or leftover_summary_from_goal(getattr(campaign, "goal", "") or ""))
    if not summary:
        return False
    consume_leftover(
        root,
        summary,
        satisfied_by="local_finality",
        source_mission_id=str(getattr(campaign, "mission_id", "") or ""),
    )
    handoff["leftover_consumed"] = True
    campaign.handoff = handoff
    return True


def _write_leftover_mission(
    root: Path,
    *,
    mission_id: str,
    next_step: str,
    goal: str = "",
    summary: str = "",
    capability_delta: str = "",
    status: str = "complete",
) -> Path:
    mission_dir = Path(root) / ".blackhole-agent" / "unbound" / "missions" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission_id,
        "status": status,
        "stage": "execution",
        "goal": goal,
        "done_when": "",
        "next_step": next_step,
        "last_summary": summary,
        "last_error": "",
        "milestones": [{"capability_delta": capability_delta}] if capability_delta else [],
        "recent_turns": [],
    }
    path = mission_dir / "state.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def builtin_kernel_leftover_proof() -> dict[str, Any]:
    """Hermetic proof: shipped leftovers leave genesis fuel; open leftovers can close."""

    import tempfile

    from blackhole_agent.capability_compounder import Capability, register_capability, save_ledger
    from blackhole_agent.experience_fuel import harvest_experience, leftover_next_step
    from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
    from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, _write_fixture_ledger
    from blackhole_agent.local_mission_sovereignty import (
        ExperienceCandidate,
        ExperienceFuel,
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        bind_local_mission,
        load_campaign,
        local_mission_tick,
    )

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable
    checks["denylists_self"] = "capability.kernel-leftover" in LOCAL_DENYLIST
    checks["harvested_text_is_leftover"] = bool(leftover_next_step(HARVESTED_MISSION_PLANE_LEFTOVER))
    checks["generic_next_step_is_not_leftover"] = leftover_next_step("None. Mission complete.") == ""

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "kernel-leftover",
        ) -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(repo)
            self.goal = goal
            self.done_when = done_when
            self.mission_id = mission_id
            self.stage = "genesis"

    with tempfile.TemporaryDirectory(prefix="kernel-leftover-open-") as tmp:
        root = Path(tmp)
        _write_leftover_mission(
            root,
            mission_id="prior-leftover",
            next_step=HARVESTED_MISSION_PLANE_LEFTOVER,
            goal="Local kernel executes cheap ledger capabilities.",
        )
        fuel = harvest_experience(root, limit=5)
    checks["open_leftover_is_harvested"] = any(
        item.class_id == LEFTOVER_CLASS and "cheap-anchor rotation" in item.summary for item in fuel.candidates
    )

    with tempfile.TemporaryDirectory(prefix="kernel-leftover-marker-") as tmp:
        root = Path(tmp)
        _write_leftover_mission(
            root,
            mission_id="prior-leftover",
            next_step=HARVESTED_MISSION_PLANE_LEFTOVER,
        )
        path = default_ledger_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        ledger = CapabilityLedger()
        register_capability(
            ledger,
            Capability(
                id="capability.kernel-mission-plane",
                name="Kernel mission-plane",
                description="Proved stamp that consumes the harvested leftover.",
                kind="python",
                entry="blackhole_agent.kernel_mission_plane:builtin_fixture_mission_plane",
                proof_command="uv run python -c \"print('ok')\"",
                last_proof_exit_code=0,
            ),
            replace=True,
        )
        save_ledger(path, ledger)
        fuel = harvest_experience(root, limit=5)
        reason = leftover_satisfied_by(HARVESTED_MISSION_PLANE_LEFTOVER, root, source_mission_id="prior-leftover")
        stamped = leftover_claim_consumed(root, HARVESTED_MISSION_PLANE_LEFTOVER)
    checks["proved_marker_consumes_harvested_leftover"] = (
        not any(item.class_id == LEFTOVER_CLASS for item in fuel.candidates)
        and reason.startswith("ledger:capability.kernel-mission-plane")
        and stamped
    )

    with tempfile.TemporaryDirectory(prefix="kernel-leftover-later-") as tmp:
        root = Path(tmp)
        open_text = (
            "Wire the bounded frobnicator program on local ticks once "
            "cheap-anchor rotation is exhausted."
        )
        _write_leftover_mission(root, mission_id="prior-frob", next_step=open_text, goal="Unrelated cheap kernel.")
        _write_leftover_mission(
            root,
            mission_id="later-frob",
            next_step="None. Mission complete.",
            goal="Implemented the bounded frobnicator program after cheap-anchor rotation is exhausted.",
            summary="Closed the leftover frobnicator follow-on in-process.",
            capability_delta="Local ticks now run the bounded frobnicator program after cheap-anchor rotation.",
        )
        fuel = harvest_experience(root, limit=5)
        reason = leftover_satisfied_by(open_text, root, source_mission_id="prior-frob")
    checks["later_mission_overlap_consumes_leftover"] = (
        not any(item.class_id == LEFTOVER_CLASS for item in fuel.candidates) and reason.startswith("later_mission:")
    )

    with tempfile.TemporaryDirectory(prefix="kernel-leftover-unrelated-") as tmp:
        root = Path(tmp)
        unrelated = "Optional follow-on is joining STEWARDSHIP_STACK as one cross-engine charter."
        _write_leftover_mission(root, mission_id="prior-steward", next_step=unrelated)
        path = default_ledger_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        ledger = CapabilityLedger()
        register_capability(
            ledger,
            Capability(
                id="capability.kernel-mission-plane",
                name="Kernel mission-plane",
                description="Unrelated proved stamp.",
                kind="python",
                entry="blackhole_agent.kernel_mission_plane:builtin_fixture_mission_plane",
                proof_command="uv run python -c \"print('ok')\"",
                last_proof_exit_code=0,
            ),
            replace=True,
        )
        save_ledger(path, ledger)
        fuel = harvest_experience(root, limit=5)
    checks["unrelated_leftover_stays_open"] = any(
        item.class_id == LEFTOVER_CLASS and "STEWARDSHIP_STACK" in item.summary for item in fuel.candidates
    )

    operator = _State(Path("."), goal="Operator growth goal.")
    kept = bind_local_mission(operator, harvest=False)
    checks["preserves_operator_goal"] = kept.goal == "Operator growth goal."

    with tempfile.TemporaryDirectory(prefix="kernel-leftover-bind-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        ledger = load_ledger(default_ledger_path(root))
        fuel = ExperienceFuel(
            candidates=[
                ExperienceCandidate(
                    source="unbound",
                    class_id=LEFTOVER_CLASS,
                    summary=HARVESTED_MISSION_PLANE_LEFTOVER,
                    priority=5,
                )
            ]
        )
        binding = bind_local_mission(_State(root), fuel=fuel, harvest=False)
        done = leftover_campaign_done_when(HARVESTED_MISSION_PLANE_LEFTOVER, ledger=ledger)
    checks["leftover_binds_program_passes"] = (
        binding.source.endswith(LEFTOVER_CLASS)
        and binding.done_when.startswith("program_passes:capability.fixture-local-")
        and ";no_skill_route" in binding.done_when
        and done == binding.done_when
        and HARVESTED_MISSION_PLANE_LEFTOVER in binding.goal
    )

    with tempfile.TemporaryDirectory(prefix="kernel-leftover-tick-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _write_leftover_mission(
            root,
            mission_id="prior-leftover",
            next_step=HARVESTED_MISSION_PLANE_LEFTOVER,
            goal="Local kernel executes cheap ledger capabilities.",
        )
        tick = local_mission_tick(_State(root), root)
        campaign = load_campaign(root)
        after = harvest_experience(root, limit=5)
        consumed = leftover_claim_consumed(root, HARVESTED_MISSION_PLANE_LEFTOVER)
    checks["leftover_tick_completes_and_consumes"] = (
        tick.get("status") == "complete"
        and tick.get("done_when_met") is True
        and bool(tick.get("capability_delta"))
        and (tick.get("contract") or {}).get("met") is True
        and bool((campaign.handoff or {}).get("leftover_consumed"))
        and consumed
        and not any(item.class_id == LEFTOVER_CLASS for item in after.candidates)
    )

    empty_done = leftover_campaign_done_when("anything", ledger=None)
    checks["missing_ledger_keeps_static_fallback"] = empty_done == HARVESTED_KERNEL_FAILURE_DONE_WHEN
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_leftover",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
