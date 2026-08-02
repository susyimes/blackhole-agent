"""Unit tests for the upstream frontier onboarding plane (hermetic; no network)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import tarfile

import pytest

from blackhole_agent import upstream_frontier as uf

_PRELUDE = "import foolib\n\ndef render(text, plugins):\n    foolib.render_text(text)\n"


def _make_sdist(package: str = "foolib", version: str = "9.9.9", layout: str = "src", with_tests: bool = False) -> bytes:
    buf = io.BytesIO()
    init_src = b"def render_text(text):\n    return text\n"
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if layout == "src":
            init_name = f"{package}-{version}/src/{package}/__init__.py"
        else:
            init_name = f"{package}-{version}/{package}/__init__.py"
        info = tarfile.TarInfo(init_name)
        info.size = len(init_src)
        tar.addfile(info, io.BytesIO(init_src))
        if with_tests:
            test_src = b"def test_smoke():\n    assert True\n"
            info = tarfile.TarInfo(f"{package}-{version}/tests/test_smoke.py")
            info.size = len(test_src)
            tar.addfile(info, io.BytesIO(test_src))
    return buf.getvalue()


def _index_payload(name: str, version: str, sdist_url: str, sha256: str) -> bytes:
    return json.dumps(
        {
            "info": {"name": name, "version": version},
            "urls": [
                {"packagetype": "bdist_wheel", "url": "https://x/wheel.whl", "digests": {"sha256": "0" * 64}},
                {"packagetype": "sdist", "url": sdist_url, "digests": {"sha256": sha256}},
            ],
        }
    ).encode()


def _fake_fetcher(index_payload: bytes, sdist_bytes: bytes, sdist_url: str):
    def get(url: str) -> bytes:
        return sdist_bytes if url == sdist_url else index_payload

    return get


def test_fetch_latest_release_prefers_sdist_over_wheel() -> None:
    sdist = _make_sdist()
    digest = hashlib.sha256(sdist).hexdigest()
    fetcher = _fake_fetcher(_index_payload("foolib", "9.9.9", "https://x/foolib-9.9.9.tar.gz", digest), sdist, "https://x/foolib-9.9.9.tar.gz")
    release = uf.fetch_latest_release("foolib", fetcher=fetcher)
    assert release.version == "9.9.9"
    assert release.sdist_sha256 == digest


def test_fetch_latest_release_rejects_wheel_only_project() -> None:
    payload = json.dumps(
        {"info": {"name": "foolib", "version": "1.0"}, "urls": [{"packagetype": "bdist_wheel", "url": "u", "digests": {"sha256": "0" * 64}}]}
    ).encode()
    with pytest.raises(ValueError, match="no sdist"):
        uf.fetch_latest_release("foolib", fetcher=lambda url: payload)


def test_detect_src_subdir_handles_src_and_flat_layouts() -> None:
    assert uf.detect_src_subdir(_make_sdist(layout="src"), "foolib") == "foolib-9.9.9/src"
    assert uf.detect_src_subdir(_make_sdist(layout="flat"), "foolib") == "foolib-9.9.9"
    with pytest.raises(ValueError, match="no importable package"):
        uf.detect_src_subdir(_make_sdist(), "otherlib")


def test_detect_tests_subdir_present_and_absent() -> None:
    assert uf.detect_tests_subdir(_make_sdist(with_tests=True)) == "foolib-9.9.9/tests"
    assert uf.detect_tests_subdir(_make_sdist()) is None


def test_fetch_latest_release_extracts_upstream_repo_from_project_urls() -> None:
    sdist = _make_sdist()
    digest = hashlib.sha256(sdist).hexdigest()
    payload = json.dumps(
        {
            "info": {
                "name": "foolib",
                "version": "9.9.9",
                "project_urls": {"Source": "https://example.invalid/foolib"},
            },
            "urls": [{"packagetype": "sdist", "url": "https://x/f.tar.gz", "digests": {"sha256": digest}}],
        }
    ).encode()
    release = uf.fetch_latest_release("foolib", fetcher=lambda url: payload)
    assert release.upstream_repo == "https://example.invalid/foolib"


def test_validate_driver_prelude_requires_render_definition() -> None:
    uf.validate_driver_prelude(_PRELUDE)
    uf.validate_driver_prelude("render = lambda text, plugins: None\n")
    with pytest.raises(ValueError, match="render"):
        uf.validate_driver_prelude("def other(text):\n    pass\n")
    with pytest.raises(SyntaxError):
        uf.validate_driver_prelude("def render(:\n")


def test_onboard_frontier_target_end_to_end_and_idempotent(tmp_path) -> None:
    sdist = _make_sdist()
    digest = hashlib.sha256(sdist).hexdigest()
    url = "https://x/foolib-9.9.9.tar.gz"
    fetcher = _fake_fetcher(_index_payload("foolib", "9.9.9", url, digest), sdist, url)

    result = uf.onboard_frontier_target("foolib", _PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert result["ok"] and not result["reused"]
    target = tmp_path / "foolib-9.9.9"
    assert (target / "foolib-9.9.9.tar.gz").read_bytes() == sdist
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sdist_sha256"] == digest
    assert manifest["frontier"] is True
    assert manifest["fixed_in"] is None
    assert manifest["defects"] == []
    assert manifest["src_subdir"] == "foolib-9.9.9/src"
    assert manifest["driver"]["prelude"] == _PRELUDE
    assert manifest["driver"]["smoke_input"] == uf.DEFAULT_SMOKE_INPUT

    again = uf.onboard_frontier_target("foolib", _PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert again["ok"] and again["reused"]


def test_onboard_frontier_target_custom_smoke_input(tmp_path) -> None:
    """A non-markdown target declares its own smoke probe input."""
    buf = io.BytesIO()
    init_src = (
        b"def render_text(text):\n"
        b"    if not text.startswith('key'):\n"
        b"        raise ValueError('not a document')\n"
        b"    return text\n"
    )
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("foolib-9.9.9/src/foolib/__init__.py")
        info.size = len(init_src)
        tar.addfile(info, io.BytesIO(init_src))
    sdist = buf.getvalue()
    digest = hashlib.sha256(sdist).hexdigest()
    url = "https://x/foolib-9.9.9.tar.gz"
    fetcher = _fake_fetcher(_index_payload("foolib", "9.9.9", url, digest), sdist, url)

    # The markdown-shaped default is rejected by this driver.
    with pytest.raises(ValueError, match="smoke test failed"):
        uf.onboard_frontier_target("foolib", _PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)

    result = uf.onboard_frontier_target(
        "foolib", _PRELUDE, smoke_input='key = "value"\n', stewardship_root=tmp_path, fetcher=fetcher
    )
    assert result["ok"]
    manifest = json.loads((tmp_path / "foolib-9.9.9" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["driver"]["smoke_input"] == 'key = "value"\n'
    assert uf.load_smoke_input_from(tmp_path / "foolib-9.9.9") == 'key = "value"\n'


def test_onboard_frontier_target_rejects_provenance_mismatch(tmp_path) -> None:
    sdist = _make_sdist()
    url = "https://x/foolib-9.9.9.tar.gz"
    fetcher = _fake_fetcher(_index_payload("foolib", "9.9.9", url, "f" * 64), sdist, url)
    with pytest.raises(ValueError, match="provenance mismatch"):
        uf.onboard_frontier_target("foolib", _PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert not (tmp_path / "foolib-9.9.9" / "manifest.json").exists()


# ---------------------------------------------------------------------------
# npm ecosystem (node driver contract; smoke tests need a real node runtime)


_NODE_PRELUDE = (
    "function render(text, plugins) {\n"
    "    return require(TARGET_DIR).render_text(text);\n"
    "}\n"
)

node_available = pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not on PATH")


def _make_npm_tarball(package: str = "nodeprobe", version: str = "1.2.3") -> bytes:
    buf = io.BytesIO()
    pkg_json = json.dumps({"name": package, "version": version, "main": "index.js"}).encode()
    index_js = b"exports.render_text = function (text) { return text; };\n"
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in (("package/package.json", pkg_json), ("package/index.js", index_js)):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _npm_index_payload(name: str, version: str, tarball_url: str, tarball: bytes) -> bytes:
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(tarball).digest()).decode()
    return json.dumps(
        {
            "name": name,
            "version": version,
            "dist": {"tarball": tarball_url, "integrity": integrity, "shasum": hashlib.sha1(tarball).hexdigest()},
            "repository": {"url": "git+https://x.test/owner/repo.git"},
        }
    ).encode()


def test_fetch_latest_npm_release_normalizes_repository_url() -> None:
    tarball = _make_npm_tarball()
    url = "https://x/nodeprobe/-/nodeprobe-1.2.3.tgz"
    fetcher = _fake_fetcher(_npm_index_payload("nodeprobe", "1.2.3", url, tarball), tarball, url)
    release = uf.fetch_latest_npm_release("nodeprobe", fetcher=fetcher)
    assert release.version == "1.2.3"
    assert release.integrity.startswith("sha512-")
    assert release.upstream_repo == "https://x.test/owner/repo"


def test_detect_npm_package_root_and_tests_subdir() -> None:
    tarball = _make_npm_tarball()
    assert uf.detect_npm_package_root(tarball) == "package"
    assert uf.detect_npm_tests_subdir(tarball) is None


def test_validate_node_driver_prelude() -> None:
    uf.validate_node_driver_prelude(_NODE_PRELUDE)
    uf.validate_node_driver_prelude("const render = (text, plugins) => text;\n")
    with pytest.raises(ValueError, match="must define render"):
        uf.validate_node_driver_prelude("const x = 1;\n")
    # "renderer" is not a render definition.
    with pytest.raises(ValueError, match="must define render"):
        uf.validate_node_driver_prelude("const renderer = make();\n")


@node_available
def test_onboard_npm_frontier_target_roundtrip_reuse_tamper(tmp_path) -> None:
    tarball = _make_npm_tarball()
    url = "https://x/nodeprobe/-/nodeprobe-1.2.3.tgz"
    fetcher = _fake_fetcher(_npm_index_payload("nodeprobe", "1.2.3", url, tarball), tarball, url)

    result = uf.onboard_npm_frontier_target("nodeprobe", _NODE_PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert result["ok"] and not result["reused"]
    manifest = json.loads((tmp_path / "nodeprobe-1.2.3" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "npm-tarball"
    assert manifest["ecosystem"] == "npm"
    assert manifest["driver"]["runtime"] == "node"
    assert manifest["sdist_sha256"] == hashlib.sha256(tarball).hexdigest()
    assert manifest["sdist_sha1"] == hashlib.sha1(tarball).hexdigest()
    assert manifest["src_subdir"] == "package"
    assert manifest["defects"] == []

    reused = uf.onboard_npm_frontier_target("nodeprobe", _NODE_PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert reused["reused"]

    tarball_path = tmp_path / "nodeprobe-1.2.3" / manifest["sdist"]
    raw = tarball_path.read_bytes()
    tarball_path.write_bytes(bytes([raw[0] ^ 0xFF]) + raw[1:])
    tampered = uf.onboard_npm_frontier_target("nodeprobe", _NODE_PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert not tampered["reused"] and tampered["ok"]


@node_available
def test_onboard_npm_frontier_target_rejects_provenance_mismatch(tmp_path) -> None:
    tarball = _make_npm_tarball()
    url = "https://x/nodeprobe/-/nodeprobe-1.2.3.tgz"
    bad_index = json.dumps(
        {
            "name": "nodeprobe",
            "version": "1.2.3",
            "dist": {"tarball": url, "integrity": "sha512-" + "A" * 88, "shasum": "0" * 40},
        }
    ).encode()
    fetcher = _fake_fetcher(bad_index, tarball, url)
    with pytest.raises(ValueError, match="provenance mismatch"):
        uf.onboard_npm_frontier_target("nodeprobe", _NODE_PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert not (tmp_path / "nodeprobe-1.2.3" / "manifest.json").exists()


@node_available
def test_onboard_npm_frontier_target_smoke_failure_rejected(tmp_path) -> None:
    tarball = _make_npm_tarball()
    url = "https://x/nodeprobe/-/nodeprobe-1.2.3.tgz"
    fetcher = _fake_fetcher(_npm_index_payload("nodeprobe", "1.2.3", url, tarball), tarball, url)
    bad_prelude = "function render(text, plugins) { return require(TARGET_DIR).missing(text); }\n"
    with pytest.raises(ValueError, match="smoke test failed"):
        uf.onboard_npm_frontier_target("nodeprobe", bad_prelude, stewardship_root=tmp_path, fetcher=fetcher)


@node_available
def test_builtin_upstream_frontier_proof_covers_npm_leg() -> None:
    proof = uf.builtin_upstream_frontier_proof()
    assert proof["ok"], proof
    assert proof["npm_pinned"] and proof["npm_mismatch_rejected"]
