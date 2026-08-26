from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import (
    HARVESTED_MISSION_PLANE_LEFTOVER,
    builtin_kernel_leftover_proof,
    leftover_claim_consumed,
    leftover_is_open,
    leftover_marker_ids,
    leftover_phrase_overlap,
    leftover_satisfied_by,
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


def test_runtime_deps_leftover_marks_application_runtime_deps_growth_plane():
    leftover = (
        "Optional later work is installing transitive runtime dependencies of a "
        "fetched registry package so application-growth can forage import-unclosed sdists."
    )
    assert leftover_marker_ids(leftover) == ("capability.application-runtime-deps-growth-plane",)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "import-unclosed" in leftover_next_step(prefixed)


def test_node_runtime_deps_leftover_marks_application_node_runtime_deps_growth_plane():
    leftover = (
        "Optional later work is closing declared Node package.json dependencies of a "
        "live-fetched tarball so application-growth can forage import-unclosed npm packages."
    )
    assert leftover_marker_ids(leftover) == ("capability.application-node-runtime-deps-growth-plane",)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.json" in leftover_next_step(prefixed)


def test_node_default_export_leftover_marks_application_node_default_export_growth_plane():
    leftover = (
        "Optional later work is reflecting Node default exports so default-export-only "
        "packages with declared dependencies can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == ("capability.application-node-default-export-growth-plane",)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "default-export-only" in leftover_next_step(prefixed)


def test_node_default_export_object_leftover_marks_application_node_default_export_object_growth_plane():
    leftover = (
        "Optional later work is reflecting Node default-exported objects so packages "
        "whose default export is a namespace of functions rather than a single function "
        "can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-default-export-object-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "default-exported objects" in leftover_next_step(prefixed)


def test_node_default_export_class_leftover_marks_application_node_default_export_class_growth_plane():
    leftover = (
        "Optional later work is reflecting Node default-exported classes so packages "
        "whose default export is a constructable API rather than a namespace object "
        "can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-default-export-class-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "default-exported classes" in leftover_next_step(prefixed)


def test_node_class_static_leftover_marks_application_node_class_static_growth_plane():
    leftover = (
        "Optional later work is reflecting Node class static methods so packages "
        "whose callable API is Class.method rather than new Class().method can be "
        "foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-class-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "class static methods" in leftover_next_step(prefixed)


def test_node_named_class_static_leftover_marks_application_node_named_class_static_growth_plane():
    leftover = (
        "Optional later work is reflecting static methods on named class exports "
        "and nested namespace classes so packages whose API is named Base64.encode "
        "or buffer.Buffer.byteLength rather than a default-exported Class.method "
        "can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-named-class-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "named class exports" in leftover_next_step(prefixed)


def test_node_named_class_instance_leftover_marks_application_node_named_class_instance_growth_plane():
    leftover = (
        "Optional later work is reflecting instance methods on named class exports "
        "so packages whose API is new Parser().parse rather than a default-exported "
        "constructable can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-named-class-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "instance methods on named class exports" in leftover_next_step(prefixed)


def test_node_named_class_construct_leftover_marks_application_node_named_class_construct_growth_plane():
    leftover = (
        "Optional later work is reflecting instance methods whose class constructor "
        "requires arguments so packages whose API is new Parser(options).parse rather "
        "than new Parser().parse can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-node-named-class-construct-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "constructor requires arguments" in leftover_next_step(prefixed)


def test_python_class_instance_leftover_marks_application_python_class_instance_growth_plane():
    leftover = (
        "Optional later work is reflecting Python class instance methods that exist "
        "only after construction so sdists whose API is Parser(opts).loads rather "
        "than a module-level function can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-class-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "Parser(opts).loads" in leftover_next_step(prefixed)


def test_python_class_static_leftover_marks_application_python_class_static_growth_plane():
    leftover = (
        "Optional later work is reflecting Python class static methods so sdists "
        "whose API is Class.method rather than Parser(opts).loads can be foraged "
        "the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-class-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "Class.method" in leftover_next_step(prefixed)


def test_python_nested_namespace_class_static_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class statics "
        "so sdists whose API is package.submodule.Class.method rather than a "
        "top-level Class.method can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-nested-class-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.submodule.Class.method" in leftover_next_step(prefixed)


def test_python_nested_namespace_class_instance_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "so sdists whose API is package.submodule.Class(opts).method rather than "
        "package.submodule.Class.method can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-nested-class-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.submodule.Class(opts).method" in leftover_next_step(prefixed)


def test_python_deep_nested_namespace_class_instance_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "two submodule levels down so sdists whose API is "
        "package.subpackage.submodule.Class(opts).method rather than "
        "package.submodule.Class(opts).method can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-deep-nested-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.submodule.Class(opts).method" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "so sdists whose API is package.submodule.Class(opts).method rather than "
        "package.submodule.Class.method can be foraged the same way."
    ) == ("capability.application-python-nested-class-instance-growth-plane",)


def test_python_nested_namespace_function_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting functions exported only on nested submodules "
        "so sdists whose API is package.subpackage.submodule.func rather than a "
        "class method can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-nested-function-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.submodule.func" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "two submodule levels down so sdists whose API is "
        "package.subpackage.submodule.Class(opts).method rather than "
        "package.submodule.Class(opts).method can be foraged the same way."
    ) == ("capability.application-python-deep-nested-instance-growth-plane",)


def test_python_deep_nested_namespace_function_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting functions exported two submodule levels down "
        "so sdists whose API is package.subpackage.submodule.func rather than "
        "package.submodule.func can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-deep-nested-function-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.submodule.func" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting functions exported only on nested submodules "
        "so sdists whose API is package.subpackage.submodule.func rather than a "
        "class method can be foraged the same way."
    ) == ("capability.application-python-nested-function-growth-plane",)


def test_python_deep_nested_namespace_class_static_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class statics "
        "two submodule levels down so sdists whose API is "
        "package.subpackage.submodule.Class.method rather than a "
        "two-level module function can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-deep-nested-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.submodule.Class.method" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class statics "
        "so sdists whose API is package.submodule.Class.method rather than a "
        "top-level Class.method can be foraged the same way."
    ) == ("capability.application-python-nested-class-static-growth-plane",)


def test_python_triple_nested_namespace_class_static_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class statics "
        "three submodule levels down so sdists whose API is "
        "package.subpackage.subpackage.submodule.Class.method rather than a "
        "two-level package.subpackage.submodule.Class.method can be foraged "
        "the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-triple-nested-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.subpackage.submodule.Class.method" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class statics "
        "two submodule levels down so sdists whose API is "
        "package.subpackage.submodule.Class.method rather than a "
        "two-level module function can be foraged the same way."
    ) == ("capability.application-python-deep-nested-static-growth-plane",)


def test_python_sextuple_nested_namespace_class_static_leftover_marks_growth_plane():
    from pathlib import Path

    leftover = (
        "Optional later work is reflecting Python nested-namespace class statics "
        "six submodule levels down so sdists whose covering API is a six-level "
        "nested Class.method static rather than a five-level nested Class.method "
        "static can be foraged the same way."
    )
    root = Path(".").resolve()
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-sext-nested-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "six-level nested Class.method static" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class statics "
        "five submodule levels down so sdists whose covering Class.method returns a "
        "cwd-independent JSON scalar, rather than an inherited path validator, can "
        "be foraged the same way."
    ) == ("capability.application-python-quint-nested-static-growth-plane",)
    reason = leftover_satisfied_by(leftover, root)
    assert reason.startswith("ledger:capability.application-python-sext-nested-static-growth-plane")
    assert leftover_is_open(leftover, root) is False
    assert leftover_claim_consumed(root, leftover) is True


def test_python_quintuple_nested_namespace_class_static_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class statics "
        "five submodule levels down so sdists whose covering Class.method returns a "
        "cwd-independent JSON scalar, rather than an inherited path validator, can "
        "be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-quint-nested-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "cwd-independent JSON scalar" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "five submodule levels down so sdists whose API is "
        "package.subpackage.subpackage.subpackage.subpackage.submodule.Class().method "
        "rather than a four-level nested Class.method static can be foraged the same way."
    ) == ("capability.application-python-quint-nested-instance-growth-plane",)


def test_python_sextuple_nested_namespace_class_instance_leftover_marks_growth_plane():
    from pathlib import Path

    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "six submodule levels down so sdists whose covering API is a six-level nested "
        "Class().method instance rather than a five-level nested Class().method instance "
        "can be foraged the same way."
    )
    root = Path(".").resolve()
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-sext-nested-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "six-level nested Class().method instance" in leftover_next_step(prefixed)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "five submodule levels down so sdists whose API is "
        "package.subpackage.subpackage.subpackage.subpackage.submodule.Class().method "
        "rather than a four-level nested Class.method static can be foraged the same way."
    ) == ("capability.application-python-quint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seven submodule levels down so sdists whose covering API is a seven-level nested "
        "Class().method instance rather than a six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sept-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eight submodule levels down so sdists whose covering API is an eight-level nested "
        "Class().method instance rather than a seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-oct-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "nine submodule levels down so sdists whose covering API is a nine-level nested "
        "Class().method instance rather than an eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-nona-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ten submodule levels down so sdists whose covering API is a ten-level nested "
        "Class().method instance rather than a nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-deca-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eleven submodule levels down so sdists whose covering API is an eleven-level nested "
        "Class().method instance rather than a ten-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-undec-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twelve submodule levels down so sdists whose covering API is a twelve-level nested "
        "Class().method instance rather than an eleven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-dodec-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirteen submodule levels down so sdists whose covering API is a thirteen-level nested "
        "Class().method instance rather than a twelve-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-trede-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fourteen submodule levels down so sdists whose covering API is a fourteen-level nested "
        "Class().method instance rather than a thirteen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatt-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifteen submodule levels down so sdists whose covering API is a fifteen-level nested "
        "Class().method instance rather than a fourteen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quind-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixteen submodule levels down so sdists whose covering API is a sixteen-level nested "
        "Class().method instance rather than a fifteen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexde-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventeen submodule levels down so sdists whose covering API is a seventeen-level nested "
        "Class().method instance rather than a sixteen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septd-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighteen submodule levels down so sdists whose covering API is an eighteen-level nested "
        "Class().method instance rather than a seventeen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octod-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "nineteen submodule levels down so sdists whose covering API is a nineteen-level nested "
        "Class().method instance rather than an eighteen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novem-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty submodule levels down so sdists whose covering API is a twenty-level nested "
        "Class().method instance rather than a nineteen-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-vigi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-one submodule levels down so sdists whose covering API is a twenty-one-level nested "
        "Class().method instance rather than a twenty-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unvig-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-two submodule levels down so sdists whose covering API is a twenty-two-level nested "
        "Class().method instance rather than a twenty-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duovi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-three submodule levels down so sdists whose covering API is a twenty-three-level nested "
        "Class().method instance rather than a twenty-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-trevi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-four submodule levels down so sdists whose covering API is a twenty-four-level nested "
        "Class().method instance rather than a twenty-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatv-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-five submodule levels down so sdists whose covering API is a twenty-five-level nested "
        "Class().method instance rather than a twenty-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinv-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-six submodule levels down so sdists whose covering API is a twenty-six-level nested "
        "Class().method instance rather than a twenty-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexvi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-seven submodule levels down so sdists whose covering API is a twenty-seven-level nested "
        "Class().method instance rather than a twenty-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septv-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-eight submodule levels down so sdists whose covering API is a twenty-eight-level nested "
        "Class().method instance rather than a twenty-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octov-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twenty-nine submodule levels down so sdists whose covering API is a twenty-nine-level nested "
        "Class().method instance rather than a twenty-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novvi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty submodule levels down so sdists whose covering API is a thirty-level nested "
        "Class().method instance rather than a twenty-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-trigi-nested-instance-growth-plane",)
    reason = leftover_satisfied_by(leftover, root)
    assert reason.startswith("ledger:capability.application-python-sext-nested-instance-growth-plane")
    assert leftover_is_open(leftover, root) is False
    assert leftover_claim_consumed(root, leftover) is True


def test_python_quintuple_nested_namespace_class_instance_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "five submodule levels down so sdists whose API is "
        "package.subpackage.subpackage.subpackage.subpackage.submodule.Class().method "
        "rather than a four-level nested Class.method static can be foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-quint-nested-instance-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.subpackage.subpackage.subpackage.submodule.Class().method" in leftover_next_step(
        prefixed
    )
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "two submodule levels down so sdists whose API is "
        "package.subpackage.submodule.Class(opts).method rather than "
        "package.submodule.Class(opts).method can be foraged the same way."
    ) == ("capability.application-python-deep-nested-instance-growth-plane",)


def test_python_quadruple_nested_namespace_class_static_leftover_marks_growth_plane():
    leftover = (
        "Optional later work is reflecting Python nested-namespace class statics "
        "four submodule levels down so sdists whose API is "
        "package.subpackage.subpackage.subpackage.submodule.Class.method rather than a "
        "three-level package.subpackage.subpackage.submodule.Class.method can be "
        "foraged the same way."
    )
    assert leftover_marker_ids(leftover) == (
        "capability.application-python-quad-nested-static-growth-plane",
    )
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "package.subpackage.subpackage.subpackage.submodule.Class.method" in leftover_next_step(
        prefixed
    )
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class statics "
        "three submodule levels down so sdists whose API is "
        "package.subpackage.subpackage.submodule.Class.method rather than a "
        "two-level package.subpackage.submodule.Class.method can be foraged "
        "the same way."
    ) == ("capability.application-python-triple-nested-static-growth-plane",)


def test_live_fetch_leftover_marks_application_live_fetch_growth_plane():
    leftover = (
        "Optional later work is live-fetch probing of registry hits that have no "
        "on-disk archive so application-growth can forage packages the "
        "stewardship tree has never seen."
    )
    assert leftover_marker_ids(leftover) == ("capability.application-live-fetch-growth-plane",)
    prefixed = "None. Mission complete. " + leftover
    assert leftover_next_step(prefixed).startswith("Optional later work")
    assert "live-fetch probing" in leftover_next_step(prefixed)


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
