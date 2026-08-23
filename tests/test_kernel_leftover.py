from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import (
    HARVESTED_MISSION_PLANE_LEFTOVER,
    builtin_kernel_leftover_proof,
    leftover_is_open,
    leftover_marker_ids,
    leftover_phrase_overlap,
)
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_foraging_leftover_marks_foraging_plane():
    leftover = (
        "Mission complete. Follow-on missions could extend foraging to the "
        "node runtime lane, multi-callable bundle foraging, or trend-driven "
        "automatic target selection."
    )
    assert "capability.foraging-plane" in leftover_marker_ids(leftover)
    assert "capability.forage-target-plane" in leftover_marker_ids(leftover)


def test_target_selection_leftover_marks_forage_target_plane():
    leftover = "Optional later work is trend-driven automatic forage-target selection."
    assert "capability.forage-target-plane" in leftover_marker_ids(leftover)


def test_growth_match_leftover_marks_forage_growth_plane():
    leftover = (
        "Optional later work is goal-driven forage matching that ignores "
        "pre-declared catalog provides."
    )
    assert "capability.forage-growth-plane" in leftover_marker_ids(leftover)


def test_apply_growth_leftover_marks_application_growth_plane():
    leftover = (
        "Optional later work is automatically growing an unplannable "
        "application goal through forage matching without a separate plane "
        "invocation."
    )
    assert "capability.application-growth-plane" in leftover_marker_ids(leftover)


def test_live_catalog_leftover_marks_application_live_growth_plane():
    leftover = (
        "Optional later work is live-registry catalog refresh so "
        "application-growth can forage from a live npm/pypi search instead "
        "of a frozen catalog."
    )
    assert "capability.application-live-growth-plane" in leftover_marker_ids(leftover)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "live-registry catalog refresh" in leftover_next_step(prefixed)


def test_registry_overlay_leftover_marks_application_registry_growth_plane():
    leftover = (
        "Optional later work is probing live npm/pypi hits that have no "
        "replay_source so application-growth can forage a covering registry "
        "package without a fixture overlay."
    )
    assert "capability.application-registry-growth-plane" in leftover_marker_ids(leftover)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "no replay_source" in leftover_next_step(prefixed)


def test_harvested_leftover_text_is_still_detected():
    leftover = leftover_next_step(HARVESTED_MISSION_PLANE_LEFTOVER)
    assert "mission-plane" in leftover
    assert leftover_next_step("None. Mission complete.") == ""
    assert leftover_phrase_overlap(
        "bounded frobnicator program cheap-anchor rotation exhausted",
        "bounded frobnicator program after cheap-anchor rotation is exhausted",
    ) >= 2


def test_builtin_proof_consumes_shipped_leftovers(tmp_path):
    report = builtin_kernel_leftover_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_leftover"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["open_leftover_is_harvested"]
    assert report["checks"]["proved_marker_consumes_harvested_leftover"]
    assert report["checks"]["later_mission_overlap_consumes_leftover"]
    assert report["checks"]["unrelated_leftover_stays_open"]
    assert report["checks"]["leftover_binds_program_passes"]
    assert report["checks"]["leftover_tick_completes_and_consumes"]
    assert leftover_is_open("", tmp_path) is False
    assert LOCAL_KERNEL == "local"
    assert "capability.kernel-leftover" in LOCAL_DENYLIST
