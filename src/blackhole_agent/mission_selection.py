"""Controller-enforced quality gates for autonomous mission selection.

The autonomous genesis prompt is advisory; this module is the durable policy
boundary.  It compares a proposed mission with recent autonomous missions and
rejects semantic reruns, scalar-only extensions, and saturated capability
families before a milestone can be recorded.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Sequence

DEFAULT_HISTORY_LIMIT = 24
REPETITION_WINDOW = 8
DIVERSITY_WINDOW = 6
DIVERSITY_SATURATION_COUNT = 3
MIN_MARGINAL_VALUE_SCORE = 2
SELECTION_REJECTION_LIMIT = 3
MAX_HISTORY_STATE_BYTES = 5_000_000

_NUMBER_WORDS = frozenset(
    {
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "million",
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
    }
)
_NUMERIC_STEMS = (
    "deci",
    "vigint",
    "trigint",
    "quadragint",
    "quinquagint",
    "sexagint",
    "septuagint",
    "octogint",
    "nonagint",
    "cent",
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "by",
        "can",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "this",
        "to",
        "when",
        "whose",
        "with",
        "work",
    }
)
_DOMAIN_GROUPS: tuple[tuple[str, frozenset[str]], ...] = (
    ("python", frozenset({"python", "pyproject", "pytest", "wheel", "sdist"})),
    ("node", frozenset({"node", "javascript", "typescript", "npm", "package"})),
    ("git-publication", frozenset({"git", "github", "branch", "commit", "publication", "push"})),
    ("kernel-runtime", frozenset({"kernel", "grok", "kimi", "codex", "runtime"})),
    ("worktree", frozenset({"worktree", "checkout", "lineage"})),
    ("capability-ledger", frozenset({"capability", "ledger", "proof", "compose", "forage"})),
    ("browser", frozenset({"browser", "chrome", "web", "page"})),
    ("memory", frozenset({"memory", "recall", "retain", "hindsight"})),
    ("cli-api", frozenset({"cli", "api", "endpoint", "command"})),
)
_SURFACE_TOKENS = frozenset(
    {
        "archive",
        "auth",
        "class",
        "contract",
        "depth",
        "failure",
        "function",
        "instance",
        "integration",
        "level",
        "method",
        "namespace",
        "nested",
        "performance",
        "recovery",
        "reliability",
        "selection",
        "security",
        "timeout",
        "ntp",
        "rfc5905",
        "keyid",
        "radiu",
        "rfc2865",
        "dhcp",
        "rfc2131",
        "yiaddr",
        "ike",
        "rfc7296",
        "spi",
        "sip",
        "rfc3261",
        "callid",
        "stun",
        "rfc5389",
        "txid",
        "turn",
        "rfc5766",
        "relay",
        "nonce",
        "ice",
        "rfc8445",
        "ufrag",
        "foundation",
        "dtls",
        "rfc6347",
        "cookie",
        "epoch",
        "srtp",
        "rfc3711",
        "roc",
        "ssrc",
        "sctp",
        "rfc4960",
        "vtag",
        "tsn",
        "datachannel",
        "rfc8831",
        "ppid",
        "dcep",
        "quic",
        "rfc9000",
        "dcid",
        "pktnum",
        "http3",
        "rfc9114",
        "streamid",
        "qpack",
        "webtransport",
        "rfc9220",
        "sessionid",
        "capsule",
        "datagram",
        "rfc9221",
        "flowid",
        "contextid",
        "masque",
        "rfc9298",
        "targetid",
        "authority",
        "connectip",
        "rfc9484",
        "prefixid",
        "ipaddr",
        "ohttp",
        "rfc9458",
        "configid",
        "gateway",
        "ohsvcb",
        "rfc9540",
        "svcbid",
        "keyconf",
        "httpsig",
        "rfc9421",
        "sigid",
        "sigbase",
        "digestfields",
        "digestfield",
        "rfc9530",
        "digestid",
        "contentdigest",
        "bhttp",
        "rfc9292",
        "messageid",
        "binarymsg",
        "binaryhttp",
        "http11",
        "rfc9112",
        "requestid",
        "startline",
        "httpmessage",
        "http2",
        "rfc9113",
        "settingsid",
        "hpack",
        "preface",
        "httpcache",
        "rfc9111",
        "cacheid",
        "freshness",
        "validator",
        "httpsemantics",
        "httpsemantic",
        "rfc9110",
        "methodid",
        "fieldsection",
        "structuredfields",
        "structuredfield",
        "rfc8941",
        "dictid",
        "sfv",
    }
)
_IMPACT_MARKERS = (
    "end-to-end",
    "measurable",
    "production",
    "reliability",
    "latency",
    "security",
    "failure",
    "regression",
    "operator",
    "user-facing",
    "cross-platform",
    "integration",
    "replace",
    "remove",
    "reduce",
    "prevent",
    "repair",
    "recover",
)
_REPAIR_MARKERS = ("failed", "failure", "blocked", "broken", "repair", "recover", "regression")


@dataclass(frozen=True)
class MissionHistoryEntry:
    mission_id: str
    goal: str
    signature: str
    capability_family: str
    status: str


@dataclass(frozen=True)
class MissionSelectionGate:
    accepted: bool
    reasons: tuple[str, ...]
    candidate_signature: str
    capability_family: str
    repetition_count: int
    repetition_matches: tuple[str, ...]
    recent_family_count: int
    recent_families: tuple[str, ...]
    marginal_value_score: int
    scalar_extension: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_numeric_token(token: str) -> bool:
    if token.isdigit() or token in _NUMBER_WORDS:
        return True
    return token.endswith(("tuple", "uple")) and any(stem in token for stem in _NUMERIC_STEMS)


def _stem_token(token: str) -> str:
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def semantic_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in re.findall(r"[a-z0-9]+", str(text or "").lower().replace("_", " ")):
        if _is_numeric_token(raw) or raw in _STOP_WORDS:
            continue
        token = _stem_token(raw)
        if token and token not in _STOP_WORDS:
            tokens.append(token)
    return tuple(tokens)


def semantic_signature(text: str) -> str:
    return " ".join(semantic_tokens(text))


def capability_family(text: str) -> str:
    tokens = semantic_tokens(text)
    token_set = set(tokens)
    domains = [name for name, markers in _DOMAIN_GROUPS if token_set & markers]
    surfaces = sorted(token_set & _SURFACE_TOKENS)
    parts = [*domains[:2], *surfaces[:5]]
    if parts:
        return "/".join(dict.fromkeys(parts))
    fallback = [token for token in tokens if len(token) >= 4][:5]
    return "/".join(fallback) or "unspecified"


def semantic_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    return max(jaccard, sequence)


def is_scalar_extension(text: str) -> bool:
    raw = " ".join(str(text or "").lower().split())
    tokens = set(semantic_tokens(raw))
    nested_depth = bool({"nested", "namespace"} & tokens) and bool({"level", "depth"} & tokens)
    comparative = any(
        marker in raw
        for marker in (
            "rather than",
            "one more",
            "next level",
            "levels down",
            "level down",
            "increase the depth",
            "increment the depth",
        )
    )
    numeric_from_to = bool(re.search(r"\bfrom\s+\S+\s+to\s+\S+", raw)) and bool(
        re.search(r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b", raw)
    )
    increment_by_one = bool(re.search(r"\b(?:increase|increment|extend)\b.{0,40}\bby\s+(?:1|one)\b", raw))
    return bool((nested_depth and comparative) or numeric_from_to or increment_by_one)


def _read_state(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_HISTORY_STATE_BYTES:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_recent_mission_history(
    repo_path: Path,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
    exclude_mission_id: str = "",
) -> list[MissionHistoryEntry]:
    missions_dir = Path(repo_path) / ".blackhole-agent" / "unbound" / "missions"
    if not missions_dir.is_dir():
        return []
    try:
        paths = sorted(
            (path for path in missions_dir.glob("*/state.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    entries: list[MissionHistoryEntry] = []
    for path in paths:
        state = _read_state(path)
        mission_id = str(state.get("mission_id") or "")
        if not state or (exclude_mission_id and mission_id == exclude_mission_id):
            continue
        goal = str(state.get("goal") or "").strip()
        if not goal:
            for turn in reversed(list(state.get("recent_turns") or [])):
                if isinstance(turn, dict) and str(turn.get("mission_goal") or "").strip():
                    goal = str(turn["mission_goal"]).strip()
                    break
        if not goal:
            continue
        signature = semantic_signature(goal)
        entries.append(
            MissionHistoryEntry(
                mission_id=mission_id or path.parent.name,
                goal=goal,
                signature=signature,
                capability_family=capability_family(goal),
                status=str(state.get("status") or ""),
            )
        )
        if len(entries) >= max(1, int(limit)):
            break
    return entries


def assess_mission_selection(
    repo_path: Path,
    goal: str,
    done_when: str = "",
    *,
    history: Sequence[MissionHistoryEntry] | None = None,
    exclude_mission_id: str = "",
    forced: bool = False,
) -> MissionSelectionGate:
    proposed_goal = " ".join(str(goal or "").split())
    proposed_done = " ".join(str(done_when or "").split())
    text = " ".join(part for part in (proposed_goal, proposed_done) if part)
    signature = semantic_signature(proposed_goal or proposed_done)
    goal_tokens = semantic_tokens(proposed_goal)
    family = capability_family(proposed_goal or proposed_done)
    recent = list(
        history
        if history is not None
        else load_recent_mission_history(repo_path, exclude_mission_id=exclude_mission_id)
    )
    repetition_matches = tuple(
        entry.mission_id
        for entry in recent[:REPETITION_WINDOW]
        if semantic_similarity(signature, entry.signature) >= 0.82
    )
    recent_families = tuple(entry.capability_family for entry in recent[:DIVERSITY_WINDOW])
    family_count = sum(1 for item in recent_families if item == family)
    scalar_extension = is_scalar_extension(text)
    lowered = text.lower()

    marginal_score = 1
    if family not in recent_families:
        marginal_score += 1
    if any(marker in lowered for marker in _IMPACT_MARKERS):
        marginal_score += 1
    if any(marker in lowered for marker in _REPAIR_MARKERS):
        marginal_score += 2
    if scalar_extension:
        marginal_score -= 3
    if "optional later work" in lowered or "same way" in lowered:
        marginal_score -= 1
    if repetition_matches:
        marginal_score -= 1

    reasons: list[str] = []
    if not proposed_goal:
        reasons.append("missing_mission_goal")
    if not proposed_done:
        reasons.append("missing_done_when")
    if proposed_goal and (len(goal_tokens) < 3 or proposed_goal.lower() in {"none", "mission complete"}):
        reasons.append("marginal_value_gate: mission goal lacks a substantive outcome")
    if repetition_matches:
        reasons.append("repetition_gate: semantic near-duplicate of a recent mission")
    if scalar_extension:
        reasons.append("marginal_value_gate: scalar-only extension without a new capability surface")
    elif marginal_score < MIN_MARGINAL_VALUE_SCORE:
        reasons.append(f"marginal_value_gate: score {marginal_score} is below {MIN_MARGINAL_VALUE_SCORE}")
    if family_count >= DIVERSITY_SATURATION_COUNT:
        reasons.append("capability_diversity_gate: capability family is saturated in the recent mission window")
    if forced:
        reasons = [reason for reason in reasons if reason in {"missing_mission_goal", "missing_done_when"}]

    return MissionSelectionGate(
        accepted=not reasons,
        reasons=tuple(reasons),
        candidate_signature=signature,
        capability_family=family,
        repetition_count=len(repetition_matches),
        repetition_matches=repetition_matches,
        recent_family_count=family_count,
        recent_families=recent_families,
        marginal_value_score=marginal_score,
        scalar_extension=scalar_extension,
    )


def render_mission_selection_guard(repo_path: Path) -> str:
    history = load_recent_mission_history(repo_path)
    family_counts = Counter(entry.capability_family for entry in history[:DIVERSITY_WINDOW])
    saturated = [family for family, count in family_counts.most_common() if count >= DIVERSITY_SATURATION_COUNT]
    saturated_text = ", ".join(saturated) if saturated else "(none)"
    return "\n".join(
        (
            "Autonomous mission selection gates (controller-enforced):",
            "- Repetition: reject semantic near-duplicates of recent completed missions, even when only numbers or depth change.",
            "- Marginal value: reject scalar-only extensions; require a materially new behavior, operational repair, or measurable outcome.",
            "- Capability diversity: reject families already selected at least three times in the last six missions.",
            f"- Recently saturated capability families: {saturated_text}",
            "Choose a different capability surface and provide an outcome-level, machine-checkable done_when. "
            f"After {SELECTION_REJECTION_LIMIT} consecutive rejected genesis choices, this mission is blocked so the loop can rotate.",
        )
    )
