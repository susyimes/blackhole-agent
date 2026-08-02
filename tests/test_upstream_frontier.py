"""Unit tests for the upstream frontier onboarding plane (hermetic; no network)."""

from __future__ import annotations

import hashlib
import io
import json
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

    again = uf.onboard_frontier_target("foolib", _PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert again["ok"] and again["reused"]


def test_onboard_frontier_target_rejects_provenance_mismatch(tmp_path) -> None:
    sdist = _make_sdist()
    url = "https://x/foolib-9.9.9.tar.gz"
    fetcher = _fake_fetcher(_index_payload("foolib", "9.9.9", url, "f" * 64), sdist, url)
    with pytest.raises(ValueError, match="provenance mismatch"):
        uf.onboard_frontier_target("foolib", _PRELUDE, stewardship_root=tmp_path, fetcher=fetcher)
    assert not (tmp_path / "foolib-9.9.9" / "manifest.json").exists()
