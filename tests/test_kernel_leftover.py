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
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-one submodule levels down so sdists whose covering API is a thirty-one-level nested "
        "Class().method instance rather than a thirty-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-untri-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-two submodule levels down so sdists whose covering API is a thirty-two-level nested "
        "Class().method instance rather than a thirty-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duotr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-three submodule levels down so sdists whose covering API is a thirty-three-level nested "
        "Class().method instance rather than a thirty-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-tretr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-four submodule levels down so sdists whose covering API is a thirty-four-level nested "
        "Class().method instance rather than a thirty-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quattr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-five submodule levels down so sdists whose covering API is a thirty-five-level nested "
        "Class().method instance rather than a thirty-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quintr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-six submodule levels down so sdists whose covering API is a thirty-six-level nested "
        "Class().method instance rather than a thirty-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sextr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-seven submodule levels down so sdists whose covering API is a thirty-seven-level nested "
        "Class().method instance rather than a thirty-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-eight submodule levels down so sdists whose covering API is a thirty-eight-level nested "
        "Class().method instance rather than a thirty-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octtr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirty-nine submodule levels down so sdists whose covering API is a thirty-nine-level nested "
        "Class().method instance rather than a thirty-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novtr-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty submodule levels down so sdists whose covering API is a forty-level nested "
        "Class().method instance rather than a thirty-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quadra-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-one submodule levels down so sdists whose covering API is a forty-one-level nested "
        "Class().method instance rather than a forty-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-two submodule levels down so sdists whose covering API is a forty-two-level nested "
        "Class().method instance rather than a forty-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duoqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-three submodule levels down so sdists whose covering API is a forty-three-level nested "
        "Class().method instance rather than a forty-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-trequa-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-four submodule levels down so sdists whose covering API is a forty-four-level nested "
        "Class().method instance rather than a forty-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-five submodule levels down so sdists whose covering API is a forty-five-level nested "
        "Class().method instance rather than a forty-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-six submodule levels down so sdists whose covering API is a forty-six-level nested "
        "Class().method instance rather than a forty-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-seven submodule levels down so sdists whose covering API is a forty-seven-level nested "
        "Class().method instance rather than a forty-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-eight submodule levels down so sdists whose covering API is a forty-eight-level nested "
        "Class().method instance rather than a forty-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "forty-nine submodule levels down so sdists whose covering API is a forty-nine-level nested "
        "Class().method instance rather than a forty-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novqua-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty submodule levels down so sdists whose covering API is a fifty-level nested "
        "Class().method instance rather than a forty-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-one submodule levels down so sdists whose covering API is a fifty-one-level nested "
        "Class().method instance rather than a fifty-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-two submodule levels down so sdists whose covering API is a fifty-two-level nested "
        "Class().method instance rather than a fifty-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duoqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-three submodule levels down so sdists whose covering API is a fifty-three-level nested "
        "Class().method instance rather than a fifty-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-treqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-four submodule levels down so sdists whose covering API is a fifty-four-level nested "
        "Class().method instance rather than a fifty-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-five submodule levels down so sdists whose covering API is a fifty-five-level nested "
        "Class().method instance rather than a fifty-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-qiqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-six submodule levels down so sdists whose covering API is a fifty-six-level nested "
        "Class().method instance rather than a fifty-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-seven submodule levels down so sdists whose covering API is a fifty-seven-level nested "
        "Class().method instance rather than a fifty-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-eight submodule levels down so sdists whose covering API is a fifty-eight-level nested "
        "Class().method instance rather than a fifty-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "fifty-nine submodule levels down so sdists whose covering API is a fifty-nine-level nested "
        "Class().method instance rather than a fifty-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novqi-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty submodule levels down so sdists whose covering API is a sixty-level nested "
        "Class().method instance rather than a fifty-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-one submodule levels down so sdists whose covering API is a sixty-one-level nested "
        "Class().method instance rather than a sixty-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-two submodule levels down so sdists whose covering API is a sixty-two-level nested "
        "Class().method instance rather than a sixty-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duosex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-three submodule levels down so sdists whose covering API is a sixty-three-level nested "
        "Class().method instance rather than a sixty-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-tresex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-four submodule levels down so sdists whose covering API is a sixty-four-level nested "
        "Class().method instance rather than a sixty-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-five submodule levels down so sdists whose covering API is a sixty-five-level nested "
        "Class().method instance rather than a sixty-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-six submodule levels down so sdists whose covering API is a sixty-six-level nested "
        "Class().method instance rather than a sixty-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-seven submodule levels down so sdists whose covering API is a sixty-seven-level nested "
        "Class().method instance rather than a sixty-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-eight submodule levels down so sdists whose covering API is a sixty-eight-level nested "
        "Class().method instance rather than a sixty-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "sixty-nine submodule levels down so sdists whose covering API is a sixty-nine-level nested "
        "Class().method instance rather than a sixty-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novsex-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy submodule levels down so sdists whose covering API is a seventy-level nested "
        "Class().method instance rather than a sixty-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-one submodule levels down so sdists whose covering API is a seventy-one-level nested "
        "Class().method instance rather than a seventy-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-two submodule levels down so sdists whose covering API is a seventy-two-level nested "
        "Class().method instance rather than a seventy-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duoseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-three submodule levels down so sdists whose covering API is a seventy-three-level nested "
        "Class().method instance rather than a seventy-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-treseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-four submodule levels down so sdists whose covering API is a seventy-four-level nested "
        "Class().method instance rather than a seventy-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-five submodule levels down so sdists whose covering API is a seventy-five-level nested "
        "Class().method instance rather than a seventy-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-six submodule levels down so sdists whose covering API is a seventy-six-level nested "
        "Class().method instance rather than a seventy-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-seven submodule levels down so sdists whose covering API is a seventy-seven-level nested "
        "Class().method instance rather than a seventy-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-eight submodule levels down so sdists whose covering API is a seventy-eight-level nested "
        "Class().method instance rather than a seventy-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seventy-nine submodule levels down so sdists whose covering API is a seventy-nine-level nested "
        "Class().method instance rather than a seventy-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novseptuag-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty submodule levels down so sdists whose covering API is an eighty-level nested "
        "Class().method instance rather than a seventy-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-one submodule levels down so sdists whose covering API is an eighty-one-level nested "
        "Class().method instance rather than an eighty-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-two submodule levels down so sdists whose covering API is an eighty-two-level nested "
        "Class().method instance rather than an eighty-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-three submodule levels down so sdists whose covering API is an eighty-three-level nested "
        "Class().method instance rather than an eighty-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-treoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-four submodule levels down so sdists whose covering API is an eighty-four-level nested "
        "Class().method instance rather than an eighty-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quatoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-five submodule levels down so sdists whose covering API is an eighty-five-level nested "
        "Class().method instance rather than an eighty-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-six submodule levels down so sdists whose covering API is an eighty-six-level nested "
        "Class().method instance rather than an eighty-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-seven submodule levels down so sdists whose covering API is an eighty-seven-level nested "
        "Class().method instance rather than an eighty-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-eight submodule levels down so sdists whose covering API is an eighty-eight-level nested "
        "Class().method instance rather than an eighty-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eighty-nine submodule levels down so sdists whose covering API is an eighty-nine-level nested "
        "Class().method instance rather than an eighty-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novoctog-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety submodule levels down so sdists whose covering API is a ninety-level nested "
        "Class().method instance rather than an eighty-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-nonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-one submodule levels down so sdists whose covering API is a ninety-one-level nested "
        "Class().method instance rather than a ninety-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-unnonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-two submodule levels down so sdists whose covering API is a ninety-two-level nested "
        "Class().method instance rather than a ninety-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duononagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-three submodule levels down so sdists whose covering API is a ninety-three-level nested "
        "Class().method instance rather than a ninety-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-trenonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-four submodule levels down so sdists whose covering API is a ninety-four-level nested "
        "Class().method instance rather than a ninety-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quattuornonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-five submodule levels down so sdists whose covering API is a ninety-five-level nested "
        "Class().method instance rather than a ninety-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quinnonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-six submodule levels down so sdists whose covering API is a ninety-six-level nested "
        "Class().method instance rather than a ninety-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexnonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-seven submodule levels down so sdists whose covering API is a ninety-seven-level nested "
        "Class().method instance rather than a ninety-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septnonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-eight submodule levels down so sdists whose covering API is a ninety-eight-level nested "
        "Class().method instance rather than a ninety-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octnonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ninety-nine submodule levels down so sdists whose covering API is a ninety-nine-level nested "
        "Class().method instance rather than a ninety-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novnonagint-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred submodule levels down so sdists whose covering API is a one-hundred-level nested "
        "Class().method instance rather than a ninety-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-cent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred one submodule levels down so sdists whose covering API is a one-hundred-one-level nested "
        "Class().method instance rather than a one-hundred-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-uncent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred two submodule levels down so sdists whose covering API is a one-hundred-two-level nested "
        "Class().method instance rather than a one-hundred-one-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-duocent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred three submodule levels down so sdists whose covering API is a one-hundred-three-level nested "
        "Class().method instance rather than a one-hundred-two-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-trecent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred four submodule levels down so sdists whose covering API is a one-hundred-four-level nested "
        "Class().method instance rather than a one-hundred-three-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quattuorcent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred five submodule levels down so sdists whose covering API is a one-hundred-five-level nested "
        "Class().method instance rather than a one-hundred-four-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-quincent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred six submodule levels down so sdists whose covering API is a one-hundred-six-level nested "
        "Class().method instance rather than a one-hundred-five-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-sexcent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred seven submodule levels down so sdists whose covering API is a one-hundred-seven-level nested "
        "Class().method instance rather than a one-hundred-six-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-septencent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred eight submodule levels down so sdists whose covering API is a one-hundred-eight-level nested "
        "Class().method instance rather than a one-hundred-seven-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-octocent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred nine submodule levels down so sdists whose covering API is a one-hundred-nine-level nested "
        "Class().method instance rather than a one-hundred-eight-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-novemcent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred ten submodule levels down so sdists whose covering API is a one-hundred-ten-level nested "
        "Class().method instance rather than a one-hundred-nine-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-decicent-nested-instance-growth-plane",)
    assert leftover_marker_ids(
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "one hundred eleven submodule levels down so sdists whose covering API is a one-hundred-eleven-level nested "
        "Class().method instance rather than a one-hundred-ten-level nested Class().method instance "
        "can be foraged the same way."
    ) == ("capability.application-python-undecicent-nested-instance-growth-plane",)
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
