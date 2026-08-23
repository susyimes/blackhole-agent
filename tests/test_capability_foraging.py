"""Tests for the capability foraging plane."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_foraging import (
    FIXTURE_EMPTY_PACKAGE,
    FIXTURE_FORAGE_PACKAGE,
    FIXTURE_NODE_EMPTY_PACKAGE,
    FIXTURE_NODE_FORAGE_PACKAGE,
    STEWARDSHIP_ROOT,
    builtin_foraging_plane_proof,
    close_runtime_dependencies,
    detect_import_root,
    detect_node_entry,
    detect_package_runtime,
    hermetic_forage_requests,
    infer_acquisition_spec,
    introspect_module,
    introspect_node_module,
    parse_node_runtime_requires,
    parse_runtime_requires,
    probe_domains_for,
    run_foraging_plane,
    verify_foraging_plane,
    forage_package,
)


def test_probe_domains_are_fixed_and_split() -> None:
    for domain in probe_domains_for("str"):
        assert len(domain["selection"]) >= 2
        assert len(domain["held_out"]) >= 1
        assert not set(domain["selection"]) & set(domain["held_out"])
    assert probe_domains_for("int")[0]["domain"] == "int"
    assert probe_domains_for("dict") == ()


def test_detect_import_root_fixture(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "forage_lab.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    assert detect_import_root(staged, "forage_lab") == (".", "forage_lab")


def test_detect_import_root_src_layout(tmp_path: Path) -> None:
    package = tmp_path / "staged" / "demo-1.0" / "src" / "demo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    assert detect_import_root(tmp_path / "staged", "demo") == ("demo-1.0/src", "demo")


def test_detect_import_root_ambiguous_refused(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "alpha.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    (staged / "beta.py").write_text("def g(x):\n    return x\n", encoding="utf-8")
    try:
        detect_import_root(staged, "missing_hint")
    except ValueError as exc:
        assert "cannot detect a unique import root" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("ambiguous import root must be refused")


def test_introspection_enumerates_public_functions() -> None:
    result = introspect_module(FIXTURE_FORAGE_PACKAGE, "forage_lab", ".")
    assert result["ok"]
    names = [candidate["name"] for candidate in result["candidates"]]
    assert "shout" in names and "whisper" in names and "brittle" in names
    assert "_hidden" not in names and "CONSTANT" not in names


def test_introspection_import_failure_refused(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("import nonexistent_module_xyz\n", encoding="utf-8")
    result = introspect_module(tmp_path, "broken", ".")
    assert not result["ok"]
    assert "import failed" in result["error"]


def test_import_unclosed_sdist_closes_runtime_deps(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import stage_acquisition_source
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "python-slugify", "slug": "python-slugify", "registry": "pypi", "version": "8.0.4"}
    )
    assert fetched and fetched["ok"], fetched
    source = Path(str(fetched["path"]))
    staged = tmp_path / "staged"
    stage_acquisition_source(source, staged)
    requires = parse_runtime_requires(staged)
    assert any(name.replace("_", "-").lower() == "text-unidecode" for name in requires)
    opened = infer_acquisition_spec(
        slug="python-slugify",
        name="python-slugify",
        source=source,
        staging_root=tmp_path / "open",
        hint="slugify",
        close_deps=False,
    )
    assert not opened["ok"]
    assert "import failed" in str(opened.get("error") or "")
    closed = infer_acquisition_spec(
        slug="python-slugify",
        name="python-slugify",
        source=source,
        staging_root=tmp_path / "closed",
        hint="slugify",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "slugify"
    assert closed["spec"].provides == "slugify_output"
    assert any(item.get("name") == "text-unidecode" for item in closed["record"]["runtime_deps"])
    assert closed["spec"].extra_paths
    vendored = close_runtime_dependencies(staged)
    assert vendored["ok"], vendored
    assert "text-unidecode" in vendored["requires"]


def test_import_unclosed_npm_tarball_closes_runtime_deps(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import stage_acquisition_source
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "snake-case", "slug": "snake-case", "registry": "npm", "version": "4.0.0"}
    )
    assert fetched and fetched["ok"], fetched
    source = Path(str(fetched["path"]))
    staged = tmp_path / "staged"
    stage_acquisition_source(source, staged)
    requires = parse_node_runtime_requires(staged)
    assert any(name.lower() == "no-case" for name in requires)
    opened = infer_acquisition_spec(
        slug="snake-case",
        name="snake-case",
        source=source,
        staging_root=tmp_path / "open",
        hint="snake-case",
        runtime="node",
        close_deps=False,
    )
    assert not opened["ok"]
    assert "import failed" in str(opened.get("error") or "")
    closed = infer_acquisition_spec(
        slug="snake-case",
        name="snake-case",
        source=source,
        staging_root=tmp_path / "closed",
        hint="snake-case",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "snakeCase"
    assert closed["spec"].provides == "snake_case_output"
    assert any(item.get("name") == "no-case" for item in closed["record"]["runtime_deps"])
    assert closed["spec"].extra_paths
    vendored = close_runtime_dependencies(staged, runtime="node")
    assert vendored["ok"], vendored
    assert "no-case" in vendored["requires"]


def test_node_introspection_reflects_default_export(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-default","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export default function shout(text) {\n"
        "  if (typeof text !== 'string') throw new TypeError('shout expects a string');\n"
        "  return text.toUpperCase() + '!';\n"
        "}\n",
        encoding="utf-8",
    )
    skipped = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert skipped["ok"], skipped
    assert skipped["candidates"] == []
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert names == ["shout"]
    assert reflected["candidates"][0]["default_export"] is True
    assert reflected["candidates"][0]["default_export_object"] is False
    assert reflected["candidates"][0]["default_export_class"] is False


def test_node_introspection_reflects_default_export_object(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-ns","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "function shout(text) {\n"
        "  if (typeof text !== 'string') throw new TypeError('shout expects a string');\n"
        "  return text.toUpperCase() + '!';\n"
        "}\n"
        "function whisper(text) {\n"
        "  if (typeof text !== 'string') throw new TypeError('whisper expects a string');\n"
        "  return text.toLowerCase();\n"
        "}\n"
        "export default { shout, whisper };\n",
        encoding="utf-8",
    )
    skipped = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert skipped["ok"], skipped
    assert skipped["candidates"] == []
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert names == ["shout", "whisper"]
    assert all(candidate["default_export"] for candidate in reflected["candidates"])
    assert all(candidate["default_export_object"] for candidate in reflected["candidates"])
    assert all(not candidate["default_export_class"] for candidate in reflected["candidates"])


def test_node_introspection_reflects_default_export_class(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-class","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export default class Shouter {\n"
        "  shout(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('shout expects a string');\n"
        "    return text.toUpperCase() + '!';\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    skipped = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert skipped["ok"], skipped
    assert skipped["candidates"] == []
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "shout" in names
    shout = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "shout")
    assert shout["default_export"] is True
    assert shout["default_export_object"] is False
    assert shout["default_export_class"] is True
    assert shout["default_export_class_static"] is False


def test_node_introspection_reflects_default_export_class_static(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-static","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export default class Hasher {\n"
        "  static hash(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('hash expects a string');\n"
        "    return text.toLowerCase() + '!';\n"
        "  }\n"
        "  digest(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('digest expects a string');\n"
        "    return text.toUpperCase();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    skipped = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert skipped["ok"], skipped
    assert skipped["candidates"] == []
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "hash" in names
    hashed = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "hash")
    assert hashed["default_export"] is True
    assert hashed["default_export_object"] is False
    assert hashed["default_export_class"] is False
    assert hashed["default_export_class_static"] is True
    digest = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "digest")
    assert digest["default_export_class"] is True
    assert digest["default_export_class_static"] is False


def test_node_introspection_reflects_named_class_instance(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-named-class","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export class Parser {\n"
        "  parse(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('parse expects a string');\n"
        "    return text.toLowerCase();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    skipped = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert skipped["ok"], skipped
    names = [candidate["name"] for candidate in skipped["candidates"]]
    assert "Parser.parse" in names
    parsed = next(candidate for candidate in skipped["candidates"] if candidate["name"] == "Parser.parse")
    assert parsed["default_export"] is False
    assert parsed["default_export_class"] is False
    assert parsed["named_export_class_static"] is False
    assert parsed["named_export_class"] is True
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    assert "Parser.parse" in [candidate["name"] for candidate in reflected["candidates"]]


def test_node_introspection_reflects_named_class_static(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-named-static","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export class Base64 {\n"
        "  static encode(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('encode expects a string');\n"
        "    return text.toLowerCase();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    skipped = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert skipped["ok"], skipped
    names = [candidate["name"] for candidate in skipped["candidates"]]
    assert "Base64.encode" in names
    encoded = next(candidate for candidate in skipped["candidates"] if candidate["name"] == "Base64.encode")
    assert encoded["default_export"] is False
    assert encoded["default_export_class_static"] is False
    assert encoded["named_export_class_static"] is True
    assert encoded["nested_namespace_class_static"] is False
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    assert "Base64.encode" in [candidate["name"] for candidate in reflected["candidates"]]


def test_node_introspection_reflects_nested_namespace_class_static(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-nested-static","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "class Buffer {\n"
        "  static byteLength(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('byteLength expects a string');\n"
        "    return String(text.length);\n"
        "  }\n"
        "}\n"
        "export const buffer = { Buffer };\n"
        "export default { Buffer };\n",
        encoding="utf-8",
    )
    named_only = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert named_only["ok"], named_only
    named_names = [candidate["name"] for candidate in named_only["candidates"]]
    assert "buffer.Buffer.byteLength" in named_names
    nested = next(
        candidate for candidate in named_only["candidates"] if candidate["name"] == "buffer.Buffer.byteLength"
    )
    assert nested["named_export_class_static"] is False
    assert nested["nested_namespace_class_static"] is True
    assert nested["default_export"] is False
    reflected = introspect_node_module(pkg, "index.mjs")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "Buffer.byteLength" in names or "buffer.Buffer.byteLength" in names
    default_nested = next(
        candidate
        for candidate in reflected["candidates"]
        if candidate["name"] in {"Buffer.byteLength", "buffer.Buffer.byteLength"}
        and candidate.get("nested_namespace_class_static")
    )
    assert default_nested["nested_namespace_class_static"] is True


def test_default_export_only_npm_tarball_closes_runtime_deps(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import stage_acquisition_source
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "humanize-string", "slug": "humanize-string", "registry": "npm", "version": "3.1.0"}
    )
    assert fetched and fetched["ok"], fetched
    source = Path(str(fetched["path"]))
    staged = tmp_path / "staged"
    stage_acquisition_source(source, staged)
    requires = parse_node_runtime_requires(staged)
    assert any(name.lower() == "decamelize" for name in requires)
    opened = infer_acquisition_spec(
        slug="humanize-string",
        name="humanize-string",
        source=source,
        staging_root=tmp_path / "open",
        hint="humanize-string",
        runtime="node",
        close_deps=False,
    )
    assert not opened["ok"]
    assert "import failed" in str(opened.get("error") or "")
    named_only = infer_acquisition_spec(
        slug="humanize-string",
        name="humanize-string",
        source=source,
        staging_root=tmp_path / "named",
        hint="humanize-string",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert not named_only["ok"]
    assert named_only.get("stage") == "select"
    closed = infer_acquisition_spec(
        slug="humanize-string",
        name="humanize-string",
        source=source,
        staging_root=tmp_path / "closed",
        hint="humanize-string",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "humanizeString"
    assert closed["record"]["default_export"] is True
    assert closed["record"]["default_export_object"] is False
    assert closed["record"]["default_export_class"] is False
    assert closed["spec"].provides == "humanize_string_output"
    assert any(item.get("name") == "decamelize" for item in closed["record"]["runtime_deps"])
    assert closed["spec"].extra_paths


def test_default_export_object_npm_tarball_closes_runtime_deps(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import stage_acquisition_source
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "query-string", "slug": "query-string", "registry": "npm", "version": "9.5.0"}
    )
    assert fetched and fetched["ok"], fetched
    source = Path(str(fetched["path"]))
    staged = tmp_path / "staged"
    stage_acquisition_source(source, staged)
    requires = parse_node_runtime_requires(staged)
    assert any(name.lower() == "decode-uri-component" for name in requires)
    opened = infer_acquisition_spec(
        slug="query-string",
        name="query-string",
        source=source,
        staging_root=tmp_path / "open",
        hint="query-string",
        runtime="node",
        close_deps=False,
    )
    assert not opened["ok"]
    assert "import failed" in str(opened.get("error") or "")
    named_only = infer_acquisition_spec(
        slug="query-string",
        name="query-string",
        source=source,
        staging_root=tmp_path / "named",
        hint="query-string",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert not named_only["ok"]
    assert named_only.get("stage") == "select"
    closed = infer_acquisition_spec(
        slug="query-string",
        name="query-string",
        source=source,
        staging_root=tmp_path / "closed",
        hint="query-string",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "extract"
    assert closed["record"]["default_export"] is True
    assert closed["record"]["default_export_object"] is True
    assert closed["record"]["default_export_class"] is False
    assert closed["spec"].provides == "extract_output"
    assert any(item.get("name") == "decode-uri-component" for item in closed["record"]["runtime_deps"])
    assert closed["spec"].extra_paths


def test_default_export_class_npm_tarball_closes_runtime_deps(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import stage_acquisition_source
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "markdown-it", "slug": "markdown-it", "registry": "npm", "version": "14.1.0"}
    )
    assert fetched and fetched["ok"], fetched
    source = Path(str(fetched["path"]))
    staged = tmp_path / "staged"
    stage_acquisition_source(source, staged)
    requires = parse_node_runtime_requires(staged)
    assert any(name.lower() == "argparse" for name in requires)
    opened = infer_acquisition_spec(
        slug="markdown-it",
        name="markdown-it",
        source=source,
        staging_root=tmp_path / "open",
        hint="markdown-it",
        runtime="node",
        close_deps=False,
    )
    assert not opened["ok"]
    assert "import failed" in str(opened.get("error") or "")
    named_only = infer_acquisition_spec(
        slug="markdown-it",
        name="markdown-it",
        source=source,
        staging_root=tmp_path / "named",
        hint="markdown-it",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert not named_only["ok"]
    assert named_only.get("stage") == "select"
    closed = infer_acquisition_spec(
        slug="markdown-it",
        name="markdown-it",
        source=source,
        staging_root=tmp_path / "closed",
        hint="markdown-it",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "render"
    assert closed["record"]["default_export"] is True
    assert closed["record"]["default_export_object"] is False
    assert closed["record"]["default_export_class"] is True
    assert closed["record"].get("default_export_class_static") is False
    assert closed["spec"].provides == "render_output"
    assert any(item.get("name") == "argparse" for item in closed["record"]["runtime_deps"])
    assert closed["spec"].extra_paths


def test_default_export_class_static_npm_tarball_forages_spark_md5(tmp_path: Path) -> None:
    from blackhole_agent.capability_acquisition import stage_acquisition_source
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "spark-md5", "slug": "spark-md5", "registry": "npm", "version": "3.0.2"}
    )
    assert fetched and fetched["ok"], fetched
    source = Path(str(fetched["path"]))
    staged = tmp_path / "staged"
    stage_acquisition_source(source, staged)
    named_only = infer_acquisition_spec(
        slug="spark-md5",
        name="spark-md5",
        source=source,
        staging_root=tmp_path / "named",
        hint="spark-md5",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert not named_only["ok"]
    assert named_only.get("stage") == "select"
    closed = infer_acquisition_spec(
        slug="spark-md5",
        name="spark-md5",
        source=source,
        staging_root=tmp_path / "closed",
        hint="spark-md5",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "hash"
    assert closed["record"]["default_export"] is True
    assert closed["record"]["default_export_object"] is False
    assert closed["record"]["default_export_class"] is False
    assert closed["record"]["default_export_class_static"] is True
    assert closed["spec"].provides == "hash_output"


def test_named_class_static_npm_tarball_forages_ip_address(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "ip-address", "slug": "ip-address", "registry": "npm", "version": "10.5.0"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    named_only = infer_acquisition_spec(
        slug="ip-address",
        name="ip-address",
        source=source,
        staging_root=tmp_path / "named",
        hint="ip-address",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert named_only["ok"], named_only
    assert named_only["record"]["winner"] == "Address4.isValid"
    assert named_only["record"]["named_export_class_static"] is True
    assert named_only["record"]["default_export"] is False
    closed = infer_acquisition_spec(
        slug="ip-address",
        name="ip-address",
        source=source,
        staging_root=tmp_path / "closed",
        hint="ip-address",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "Address4.isValid"
    assert closed["record"]["default_export"] is False
    assert closed["record"]["default_export_object"] is False
    assert closed["record"]["default_export_class"] is False
    assert closed["record"]["default_export_class_static"] is False
    assert closed["record"]["named_export_class_static"] is True
    assert closed["spec"].provides == "address4_is_valid_output"
    assert closed["spec"].callable_name == "Address4.isValid"


def test_named_class_instance_npm_tarball_forages_fast_xml_parser(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "fast-xml-parser", "slug": "fast-xml-parser", "registry": "npm", "version": "5.2.5"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    named_only = infer_acquisition_spec(
        slug="fast-xml-parser",
        name="fast-xml-parser",
        source=source,
        staging_root=tmp_path / "named",
        hint="fast-xml-parser",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert named_only["ok"], named_only
    assert named_only["record"]["winner"] == "XMLBuilder.build"
    assert named_only["record"]["named_export_class"] is True
    assert named_only["record"]["named_export_class_static"] is False
    assert named_only["record"]["default_export"] is False
    closed = infer_acquisition_spec(
        slug="fast-xml-parser",
        name="fast-xml-parser",
        source=source,
        staging_root=tmp_path / "closed",
        hint="fast-xml-parser",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "XMLBuilder.build"
    assert closed["record"]["default_export"] is False
    assert closed["record"]["default_export_object"] is False
    assert closed["record"]["default_export_class"] is False
    assert closed["record"]["default_export_class_static"] is False
    assert closed["record"]["named_export_class_static"] is False
    assert closed["record"]["named_export_class"] is True
    assert closed["spec"].provides == "xmlbuilder_build_output"
    assert closed["spec"].callable_name == "XMLBuilder.build"


def test_node_introspection_reflects_named_class_construct_args(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-ctor","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export class Parser {\n"
        "  constructor(options) {\n"
        "    if (options === undefined) throw new TypeError('Parser options required');\n"
        "    this.options = options;\n"
        "  }\n"
        "  parse(text) {\n"
        "    if (typeof text !== 'string') throw new TypeError('parse expects a string');\n"
        "    return text.toLowerCase();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    named_only = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert named_only["ok"], named_only
    parsed = next(candidate for candidate in named_only["candidates"] if candidate["name"] == "Parser.parse")
    assert parsed["named_export_class"] is True
    assert parsed["constructor_requires_args"] is True
    result = infer_acquisition_spec(
        slug="forage-js-ctor",
        name="forage-js-ctor",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage-js-ctor",
        runtime="node",
        close_deps=False,
        include_default=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "Parser.parse"
    assert result["record"]["constructor_requires_args"] is True
    assert result["record"]["named_export_class"] is True
    assert result["spec"].provides == "parser_parse_output"


def test_node_introspection_reflects_instance_own_methods_after_construct(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"name":"forage-js-own","type":"module"}\n', encoding="utf-8")
    (pkg / "index.mjs").write_text(
        "export class Parser {\n"
        "  constructor(options = {}) {\n"
        "    this.options = options;\n"
        "    this.parse = (text) => {\n"
        "      if (typeof text !== 'string') throw new TypeError('parse expects a string');\n"
        "      return text.toLowerCase();\n"
        "    };\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    named_only = introspect_node_module(pkg, "index.mjs", include_default=False)
    assert named_only["ok"], named_only
    names = [candidate["name"] for candidate in named_only["candidates"]]
    assert "Parser.parse" in names
    parsed = next(candidate for candidate in named_only["candidates"] if candidate["name"] == "Parser.parse")
    assert parsed["named_export_class"] is True


def test_named_class_construct_npm_tarball_forages_eta(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive({"name": "eta", "slug": "eta", "registry": "npm", "version": "4.6.0"})
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    named_only = infer_acquisition_spec(
        slug="eta",
        name="eta",
        source=source,
        staging_root=tmp_path / "named",
        hint="eta",
        runtime="node",
        close_deps=True,
        include_default=False,
    )
    assert named_only["ok"], named_only
    assert named_only["record"]["winner"] == "Eta.compileBody"
    assert named_only["record"]["named_export_class"] is True
    assert named_only["record"]["named_export_class_static"] is False
    assert named_only["record"]["default_export"] is False
    closed = infer_acquisition_spec(
        slug="eta",
        name="eta",
        source=source,
        staging_root=tmp_path / "closed",
        hint="eta",
        runtime="node",
        close_deps=True,
    )
    assert closed["ok"], closed
    assert closed["record"]["winner"] == "Eta.compileBody"
    assert closed["record"]["default_export"] is False
    assert closed["record"]["named_export_class"] is True
    assert closed["spec"].provides == "eta_compile_body_output"
    assert closed["spec"].callable_name == "Eta.compileBody"


def test_pypi_dep_cache_ignores_npm_tgz(tmp_path: Path) -> None:
    from blackhole_agent.capability_foraging import _cached_pypi_archive

    (tmp_path / "mdurl-2.1.0.tgz").write_bytes(b"npm")
    (tmp_path / "mdurl-0.1.2.tar.gz").write_bytes(b"pypi")
    cached = _cached_pypi_archive("mdurl", tmp_path)
    assert cached is not None
    assert cached.name == "mdurl-0.1.2.tar.gz"
    (tmp_path / "mdurl-0.1.2.tar.gz").unlink()
    assert _cached_pypi_archive("mdurl", tmp_path) is None


def test_python_introspection_reflects_class_construct_args(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "forage_parser.py").write_text(
        "class Parser:\n"
        "    def __init__(self, opts):\n"
        "        if opts is None:\n"
        "            raise TypeError('Parser options required')\n"
        "        self.opts = opts\n"
        "    def loads(self, text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('loads expects a string')\n"
        "        return text.lower()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_parser", ".")
    assert reflected["ok"], reflected
    parsed = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "Parser.loads")
    assert parsed["python_class_instance"] is True
    assert parsed["constructor_requires_args"] is True
    result = infer_acquisition_spec(
        slug="forage-parser",
        name="forage-parser",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_parser",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "Parser.loads"
    assert result["record"]["python_class_instance"] is True
    assert result["record"]["constructor_requires_args"] is True
    assert result["spec"].provides == "parser_loads_output"


def test_python_introspection_reflects_instance_own_methods_after_construct(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "forage_own.py").write_text(
        "class Parser:\n"
        "    def __init__(self, opts=None):\n"
        "        options = opts or {}\n"
        "        def loads(text):\n"
        "            if not isinstance(text, str):\n"
        "                raise TypeError('loads expects a string')\n"
        "            return text.lower()\n"
        "        self.loads = loads\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_own", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "Parser.loads" in names
    parsed = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "Parser.loads")
    assert parsed["python_class_instance"] is True
    result = infer_acquisition_spec(
        slug="forage-own",
        name="forage-own",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_own",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "Parser.loads"
    assert result["record"]["python_class_instance"] is True
    assert result["spec"].provides == "parser_loads_output"


def test_python_introspection_reflects_class_static_without_construct(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "forage_hasher.py").write_text(
        "class Hasher:\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        raise TypeError('Hasher cannot be constructed')\n"
        "    @staticmethod\n"
        "    def hash(text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('hash expects a string')\n"
        "        return text.lower()\n"
        "    @classmethod\n"
        "    def encode(cls, text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('encode expects a string')\n"
        "        return text.upper()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_hasher", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "Hasher.hash" in names
    assert "Hasher.encode" in names
    hashed = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "Hasher.hash")
    encoded = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "Hasher.encode")
    assert hashed["python_class_static"] is True
    assert hashed.get("python_class_instance") is not True
    assert encoded["python_class_static"] is True
    result = infer_acquisition_spec(
        slug="forage-hasher",
        name="forage-hasher",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_hasher",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] in {"Hasher.hash", "Hasher.encode"}
    assert result["record"]["python_class_static"] is True
    assert result["record"]["python_class_instance"] is False
    assert result["spec"].callable_name in {"Hasher.hash", "Hasher.encode"}


def test_python_introspection_reflects_nested_namespace_class_instance(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    ns.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (ns / "parser.py").write_text(
        "class Parser:\n"
        "    def __init__(self, opts):\n"
        "        if opts is None:\n"
        "            raise TypeError('Parser options required')\n"
        "        self.opts = opts\n"
        "    def loads(self, text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('loads expects a string')\n"
        "        return text.lower()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "parser.Parser.loads" in names
    assert "Parser.loads" not in names
    parsed = next(
        candidate for candidate in reflected["candidates"] if candidate["name"] == "parser.Parser.loads"
    )
    assert parsed["python_nested_namespace_class_instance"] is True
    assert parsed.get("python_class_instance") is not True
    assert parsed.get("python_class_static") is not True
    assert parsed.get("python_nested_namespace_class_static") is not True
    assert parsed["constructor_requires_args"] is True
    result = infer_acquisition_spec(
        slug="forage-ns-parser",
        name="forage-ns-parser",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "parser.Parser.loads"
    assert result["record"]["python_nested_namespace_class_instance"] is True
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"]["python_nested_namespace_class_static"] is False
    assert result["spec"].callable_name == "parser.Parser.loads"


def test_python_introspection_reflects_deep_nested_namespace_class_instance(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    subpkg = ns / "codec"
    subpkg.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "parser.py").write_text(
        "class Parser:\n"
        "    def __init__(self, opts):\n"
        "        if opts is None:\n"
        "            raise TypeError('Parser options required')\n"
        "        self.opts = opts\n"
        "    def loads(self, text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('loads expects a string')\n"
        "        return text.lower()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "codec.parser.Parser.loads" in names
    assert "parser.Parser.loads" not in names
    assert "Parser.loads" not in names
    parsed = next(
        candidate
        for candidate in reflected["candidates"]
        if candidate["name"] == "codec.parser.Parser.loads"
    )
    assert parsed["python_deep_nested_namespace_class_instance"] is True
    assert parsed.get("python_nested_namespace_class_instance") is not True
    assert parsed.get("python_class_instance") is not True
    assert parsed.get("python_class_static") is not True
    assert parsed.get("python_nested_namespace_class_static") is not True
    assert parsed.get("python_deep_nested_namespace_class_static") is not True
    assert parsed["constructor_requires_args"] is True
    result = infer_acquisition_spec(
        slug="forage-ns-deep-parser",
        name="forage-ns-deep-parser",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "codec.parser.Parser.loads"
    assert result["record"]["python_deep_nested_namespace_class_instance"] is True
    assert result["record"]["python_nested_namespace_class_instance"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"]["python_nested_namespace_class_static"] is False
    assert result["spec"].callable_name == "codec.parser.Parser.loads"


def test_python_introspection_reflects_nested_namespace_function(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    ns.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (ns / "text.py").write_text(
        "def shout(value):\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('shout expects a string')\n"
        "    return value.upper()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "text.shout" in names
    assert "shout" not in names
    shouted = next(candidate for candidate in reflected["candidates"] if candidate["name"] == "text.shout")
    assert shouted["python_nested_namespace_function"] is True
    assert shouted.get("python_deep_nested_namespace_function") is not True
    assert shouted.get("python_class_instance") is not True
    assert shouted.get("python_class_static") is not True
    assert shouted.get("python_nested_namespace_class_instance") is not True
    result = infer_acquisition_spec(
        slug="forage-ns-shout",
        name="forage-ns-shout",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "text.shout"
    assert result["record"]["python_nested_namespace_function"] is True
    assert result["record"]["python_deep_nested_namespace_function"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["spec"].callable_name == "text.shout"


def test_python_introspection_reflects_deep_nested_namespace_function(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    subpkg = ns / "codec"
    subpkg.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "text.py").write_text(
        "def shout(value):\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('shout expects a string')\n"
        "    return value.upper()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "codec.text.shout" in names
    assert "text.shout" not in names
    assert "shout" not in names
    shouted = next(
        candidate for candidate in reflected["candidates"] if candidate["name"] == "codec.text.shout"
    )
    assert shouted["python_deep_nested_namespace_function"] is True
    assert shouted.get("python_nested_namespace_function") is not True
    assert shouted.get("python_deep_nested_namespace_class_instance") is not True
    assert shouted.get("python_class_instance") is not True
    assert shouted.get("python_class_static") is not True
    result = infer_acquisition_spec(
        slug="forage-ns-deep-shout",
        name="forage-ns-deep-shout",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "codec.text.shout"
    assert result["record"]["python_deep_nested_namespace_function"] is True
    assert result["record"]["python_nested_namespace_function"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["spec"].callable_name == "codec.text.shout"


def test_python_introspection_prefers_deep_nested_function_over_one_level(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    subpkg = ns / "codec"
    subpkg.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (ns / "text.py").write_text(
        "def shout(value):\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('shout expects a string')\n"
        "    return value.lower()\n",
        encoding="utf-8",
    )
    (subpkg / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "text.py").write_text(
        "def shout(value):\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('shout expects a string')\n"
        "    return value.upper()\n",
        encoding="utf-8",
    )
    result = infer_acquisition_spec(
        slug="forage-ns-prefer-deep-shout",
        name="forage-ns-prefer-deep-shout",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "codec.text.shout"
    assert result["record"]["python_deep_nested_namespace_function"] is True
    assert result["record"]["python_nested_namespace_function"] is False
    assert result["spec"].callable_name == "codec.text.shout"


def test_python_introspection_skips_reexported_deep_nested_function(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    subpkg = ns / "codec"
    subpkg.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (ns / "util.py").write_text(
        "def helper(value):\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('helper expects a string')\n"
        "    return value\n",
        encoding="utf-8",
    )
    (subpkg / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "text.py").write_text(
        "from forage_ns.util import helper\n"
        "\n"
        "def shout(value):\n"
        "    if not isinstance(value, str):\n"
        "        raise TypeError('shout expects a string')\n"
        "    return value.upper()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "codec.text.shout" in names
    assert "codec.text.helper" not in names
    shouted = next(
        candidate for candidate in reflected["candidates"] if candidate["name"] == "codec.text.shout"
    )
    assert shouted["python_deep_nested_namespace_function"] is True
    result = infer_acquisition_spec(
        slug="forage-ns-skip-reexport",
        name="forage-ns-skip-reexport",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "codec.text.shout"
    assert result["record"]["python_deep_nested_namespace_function"] is True
    assert result["spec"].callable_name == "codec.text.shout"


def test_python_introspection_reflects_deep_nested_namespace_class_static(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    subpkg = ns / "codec"
    subpkg.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "__init__.py").write_text("", encoding="utf-8")
    (subpkg / "text.py").write_text(
        "class Codec:\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        raise TypeError('Codec cannot be constructed')\n"
        "    @staticmethod\n"
        "    def encode(text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('encode expects a string')\n"
        "        return text.upper()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "codec.text.Codec.encode" in names
    assert "text.Codec.encode" not in names
    assert "Codec.encode" not in names
    encoded = next(
        candidate
        for candidate in reflected["candidates"]
        if candidate["name"] == "codec.text.Codec.encode"
    )
    assert encoded["python_deep_nested_namespace_class_static"] is True
    assert encoded.get("python_nested_namespace_class_static") is not True
    assert encoded.get("python_class_static") is not True
    assert encoded.get("python_class_instance") is not True
    assert encoded.get("python_deep_nested_namespace_function") is not True
    result = infer_acquisition_spec(
        slug="forage-ns-deep-codec",
        name="forage-ns-deep-codec",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "codec.text.Codec.encode"
    assert result["record"]["python_deep_nested_namespace_class_static"] is True
    assert result["record"]["python_nested_namespace_class_static"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_deep_nested_namespace_function"] is False
    assert result["spec"].callable_name == "codec.text.Codec.encode"


def test_python_introspection_reflects_nested_namespace_class_static(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    ns = pkg / "forage_ns"
    ns.mkdir(parents=True)
    (ns / "__init__.py").write_text("", encoding="utf-8")
    (ns / "codec.py").write_text(
        "class Codec:\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        raise TypeError('Codec cannot be constructed')\n"
        "    @staticmethod\n"
        "    def encode(text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('encode expects a string')\n"
        "        return text.upper()\n",
        encoding="utf-8",
    )
    reflected = introspect_module(pkg, "forage_ns", ".")
    assert reflected["ok"], reflected
    names = [candidate["name"] for candidate in reflected["candidates"]]
    assert "codec.Codec.encode" in names
    assert "Codec.encode" not in names
    encoded = next(
        candidate for candidate in reflected["candidates"] if candidate["name"] == "codec.Codec.encode"
    )
    assert encoded["python_nested_namespace_class_static"] is True
    assert encoded.get("python_class_static") is not True
    assert encoded.get("python_class_instance") is not True
    result = infer_acquisition_spec(
        slug="forage-ns",
        name="forage-ns",
        source=pkg,
        staging_root=tmp_path / "infer",
        hint="forage_ns",
        close_deps=False,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "codec.Codec.encode"
    assert result["record"]["python_nested_namespace_class_static"] is True
    assert result["record"]["python_class_static"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["spec"].callable_name == "codec.Codec.encode"


def test_python_class_static_sdist_forages_marko(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "marko", "slug": "marko", "registry": "pypi", "version": "2.2.4"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="marko",
        name="marko",
        source=source,
        staging_root=tmp_path / "infer",
        hint="marko",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "HTMLRenderer.escape_html"
    assert result["record"]["python_class_static"] is True
    assert result["record"]["python_class_instance"] is False
    assert result["record"].get("python_nested_namespace_class_static") is not True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "htmlrenderer_escape_html_output"
    assert result["spec"].callable_name == "HTMLRenderer.escape_html"


def test_python_nested_namespace_class_static_sdist_forages_tomlkit(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "tomlkit", "slug": "tomlkit", "registry": "pypi", "version": "0.15.1"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="tomlkit",
        name="tomlkit",
        source=source,
        staging_root=tmp_path / "infer",
        hint="tomlkit",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "api.String.from_raw"
    assert result["record"]["python_nested_namespace_class_static"] is True
    assert result["record"]["python_class_static"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "api_string_from_raw_output"
    assert result["spec"].callable_name == "api.String.from_raw"


def test_python_nested_namespace_class_instance_sdist_forages_mako(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "mako", "slug": "mako", "registry": "pypi", "version": "1.4.1"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="mako",
        name="mako",
        source=source,
        staging_root=tmp_path / "infer",
        hint="mako",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "cmd.Template.has_def"
    assert result["record"]["python_nested_namespace_class_instance"] is True
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"].get("python_nested_namespace_class_static") is not True
    assert result["record"]["constructor_requires_args"] is True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "cmd_template_has_def_output"
    assert result["spec"].callable_name == "cmd.Template.has_def"


def test_python_deep_nested_namespace_class_instance_sdist_forages_html5lib(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "html5lib", "slug": "html5lib", "registry": "pypi", "version": "1.1"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="html5lib",
        name="html5lib",
        source=source,
        staging_root=tmp_path / "infer",
        hint="html5lib",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "filters.sanitizer.Filter.allowed_token"
    assert result["record"]["python_deep_nested_namespace_class_instance"] is True
    assert result["record"]["python_nested_namespace_class_instance"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"].get("python_nested_namespace_class_static") is not True
    assert result["record"]["constructor_requires_args"] is True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "filters_sanitizer_filter_allowed_token_output"
    assert result["spec"].callable_name == "filters.sanitizer.Filter.allowed_token"


def test_python_nested_namespace_function_sdist_forages_packaging(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "packaging", "slug": "packaging", "registry": "pypi", "version": "26.3"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="packaging",
        name="packaging",
        source=source,
        staging_root=tmp_path / "infer",
        hint="packaging",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "utils.canonicalize_name"
    assert result["record"]["python_nested_namespace_function"] is True
    assert result["record"]["python_deep_nested_namespace_function"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"].get("python_nested_namespace_class_static") is not True
    assert result["record"].get("python_nested_namespace_class_instance") is not True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "utils_canonicalize_name_output"
    assert result["spec"].callable_name == "utils.canonicalize_name"


def test_python_deep_nested_namespace_class_static_sdist_forages_isbnlib(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "isbnlib", "slug": "isbnlib", "registry": "pypi", "version": "3.10.14"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="isbnlib",
        name="isbnlib",
        source=source,
        staging_root=tmp_path / "infer",
        hint="isbnlib",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "dev.helpers.File.exists"
    assert result["record"]["python_deep_nested_namespace_class_static"] is True
    assert result["record"]["python_nested_namespace_class_static"] is False
    assert result["record"]["python_deep_nested_namespace_function"] is False
    assert result["record"]["python_nested_namespace_function"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"].get("python_nested_namespace_class_instance") is not True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "dev_helpers_file_exists_output"
    assert result["spec"].callable_name == "dev.helpers.File.exists"


def test_python_deep_nested_namespace_function_sdist_forages_python_stdnum(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "python-stdnum", "slug": "python-stdnum", "registry": "pypi", "version": "2.2"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="python-stdnum",
        name="python-stdnum",
        source=source,
        staging_root=tmp_path / "infer",
        hint="stdnum",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "ad.nrt.compact"
    assert result["record"]["python_deep_nested_namespace_function"] is True
    assert result["record"]["python_nested_namespace_function"] is False
    assert result["record"]["python_class_instance"] is False
    assert result["record"]["python_class_static"] is False
    assert result["record"].get("python_nested_namespace_class_static") is not True
    assert result["record"].get("python_nested_namespace_class_instance") is not True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "ad_nrt_compact_output"
    assert result["spec"].callable_name == "ad.nrt.compact"


def test_python_class_instance_sdist_forages_markdown_it_py(tmp_path: Path) -> None:
    from blackhole_agent.capability_forage_targets import live_registry_archive

    fetched = live_registry_archive(
        {"name": "markdown-it-py", "slug": "markdown-it-py", "registry": "pypi", "version": "4.0.0"}
    )
    assert fetched and fetched.get("ok"), fetched
    source = Path(str(fetched["path"]))
    result = infer_acquisition_spec(
        slug="markdown-it-py",
        name="markdown-it-py",
        source=source,
        staging_root=tmp_path / "infer",
        hint="markdown_it",
        close_deps=True,
    )
    assert result["ok"], result
    assert result["record"]["winner"] == "MarkdownIt.normalizeLink"
    assert result["record"]["python_class_instance"] is True
    assert result["record"]["named_export_class"] is False
    assert result["record"]["default_export"] is False
    assert result["spec"].provides == "markdown_it_normalize_link_output"
    assert result["spec"].callable_name == "MarkdownIt.normalizeLink"
    assert any(item.get("name") == "mdurl" for item in result["record"]["runtime_deps"])


def test_inference_recovers_complete_spec(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-lab",
        name="forage-lab (uncooperative fixture package)",
        source=FIXTURE_FORAGE_PACKAGE,
        staging_root=tmp_path,
        hint="forage_lab",
    )
    assert result["ok"]
    spec = result["spec"]
    assert spec.import_name == "forage_lab"
    assert spec.callable_name == "shout"
    assert spec.requires == ("text",)
    assert len(spec.probes) >= 3
    record = result["record"]
    assert "held-out probe failed" in record["rejected"]["brittle"]


def test_inference_refuses_package_without_candidate(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-empty",
        name="forage-empty (no viable candidate fixture)",
        source=FIXTURE_EMPTY_PACKAGE,
        staging_root=tmp_path,
        hint="forage_empty",
    )
    assert not result["ok"]
    assert result["stage"] == "select"


def test_inference_refuses_missing_callable_behavior(tmp_path: Path) -> None:
    # A candidate that raises on selection probes must never win.
    result = infer_acquisition_spec(
        slug="forage-empty",
        name="forage-empty renamed",
        source=FIXTURE_EMPTY_PACKAGE,
        staging_root=tmp_path,
        hint="",
    )
    assert not result["ok"]


def test_forage_fixture_package_end_to_end(tmp_path: Path) -> None:
    request = hermetic_forage_requests()[0]
    result = forage_package(request)
    assert result["ok"], result
    assert result["capability_id"] == "capability.absorbed-forage-lab"
    assert result["inference"]["winner"] == "shout"


def test_forage_stewardship_sdist_with_inferred_spec() -> None:
    request = {
        "name": "tomli TOML parser (stewardship sdist, inferred spec)",
        "slug": "tomli-foraged",
        "hint": "tomli",
        "source": STEWARDSHIP_ROOT / "tomli-2.4.1" / "tomli-2.4.1.tar.gz",
        "version": "2.4.1",
        "origin": {"kind": "pypi-sdist", "source": "stewardship/tomli-2.4.1/tomli-2.4.1.tar.gz"},
    }
    result = forage_package(request)
    assert result["ok"], result
    assert result["inference"]["import_name"] == "tomli"
    assert result["inference"]["domain"] == "toml"


def test_plane_runs_and_verifies(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_foraging_plane(report_dir)
    assert plane["ok"], plane
    assert plane["grade"]["forages_ok"] == plane["grade"]["forage_count"]
    verification = verify_foraging_plane(report_dir)
    assert verification["ok"], verification


def test_tampered_report_fails_verification(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    plane = run_foraging_plane(report_dir)
    assert plane["ok"]
    report_path = report_dir / "plane-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grade"]["ok"] = not report["grade"]["ok"]
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not verify_foraging_plane(report_dir)["ok"]


def test_builtin_foraging_plane_proof() -> None:
    result = builtin_foraging_plane_proof()
    assert result["ok"], result
    assert result["winner_is_shout"]
    assert result["brittle_rejected"]
    assert result["empty_refused"]
    assert result["tampered_rejected"]
    assert result["node_runtime"]
    assert result["node_winner_is_shout"]
    assert result["node_bundle_has_whisper"]
    assert result["node_forage_ok"]
    assert result["node_bundle_acquired"]
    assert result["used_skill_route_discovery"] is False


def test_detect_node_runtime_and_entry() -> None:
    assert detect_package_runtime(FIXTURE_NODE_FORAGE_PACKAGE) == "node"
    assert detect_package_runtime(FIXTURE_FORAGE_PACKAGE) == "python"
    path_root, entry = detect_node_entry(FIXTURE_NODE_FORAGE_PACKAGE, "forage-js")
    assert path_root == "."
    assert entry == "index.mjs"


def test_node_introspection_enumerates_exported_functions() -> None:
    result = introspect_node_module(FIXTURE_NODE_FORAGE_PACKAGE, "index.mjs")
    assert result["ok"], result
    names = [candidate["name"] for candidate in result["candidates"]]
    assert "shout" in names and "whisper" in names and "brittle" in names
    assert "_hidden" not in names and "CONSTANT" not in names and "needsThree" not in names


def test_node_inference_recovers_bundle(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-js",
        name="forage-js (uncooperative node fixture package)",
        source=FIXTURE_NODE_FORAGE_PACKAGE,
        staging_root=tmp_path,
        hint="forage-js",
        runtime="node",
    )
    assert result["ok"], result
    spec = result["spec"]
    assert spec.runtime == "node"
    assert spec.entry == "index.mjs"
    assert spec.callable_name == "shout"
    assert result["record"]["winner"] == "shout"
    assert "whisper" in result["record"]["bundle"]
    assert "held-out probe failed" in result["record"]["rejected"]["brittle"]
    extras = [item.callable_name for item in result["bundle_specs"]]
    assert "whisper" in extras


def test_node_inference_refuses_package_without_candidate(tmp_path: Path) -> None:
    result = infer_acquisition_spec(
        slug="forage-js-empty",
        name="forage-js-empty",
        source=FIXTURE_NODE_EMPTY_PACKAGE,
        staging_root=tmp_path,
        hint="forage-js-empty",
        runtime="node",
    )
    assert not result["ok"]
    assert result["stage"] == "select"


def test_forage_node_fixture_end_to_end() -> None:
    result = forage_package(
        {
            "name": "forage-js (uncooperative node fixture package)",
            "slug": "forage-js",
            "hint": "forage-js",
            "runtime": "node",
            "source": FIXTURE_NODE_FORAGE_PACKAGE,
            "origin": {"kind": "fixture", "source": "tests/fixtures/external_packages/forage-js"},
        }
    )
    assert result["ok"], result
    assert result["runtime"] == "node"
    assert result["capability_id"] == "capability.absorbed-forage-js"
    assert result["inference"]["winner"] == "shout"
    assert any(item.get("callable") == "whisper" and item.get("ok") for item in result["bundle"])
