"""Upstream frontier plane: onboard the *latest* upstream release as a target.

The discovery plane (``upstream_discovery``) scans pinned historical releases
whose defects are already documented and fixed upstream; findings there are
rediscoveries. The frontier plane closes the reach gap: given only a PyPI
project name it fetches the latest release metadata, downloads the sdist,
pins it by sha256 (from the index metadata, cross-checked against the actual
download), auto-detects the importable source layout, and writes a
stewardship manifest with an empty ``defects`` list — the discovery plane
never reads that list anyway, so a frontier target is scanned blind from the
moment it is onboarded.

The plane is ecosystem-general: ``onboard_npm_frontier_target`` onboards the
latest npm registry release the same way — tarball pinned by the registry's
SRI integrity field and legacy shasum (both cross-checked), package root
auto-detected from the tarball layout, and a node driver contract in which
the prelude runs under ``node`` with ``TARGET_DIR`` bound to the extracted
package root (``require(TARGET_DIR)`` resolves through the target's own
package.json). The manifest records ``ecosystem`` and
``driver.runtime`` so downstream planes can branch on contract, not on
target identity.

The result is an ordinary stewardship target directory:
``stewardship/<name>-<version>/`` with the sdist and a ``manifest.json``
carrying frontier provenance (PyPI index URL, retrieval time, declared
latest version). Everything downstream — discovery scans, repro synthesis,
sealed reports, repair campaigns — works unchanged.

The driver prelude (how generated text is fed to the target) is the one
piece of target knowledge the plane does not invent; it is supplied by the
caller, typically reused from an earlier release of the same project via
``--driver-from``. The prelude is validated before admission: it must
define a callable ``render``. The smoke probe input the driver is proven
against is likewise declared by the caller (``--smoke-input-file``);
it defaults to a markdown-shaped sample for historical renderer targets.

Determinism contract: the manifest records only index-declared metadata and
digests, never timestamps of the scan or download paths; the onboarded
target is reproducible bit-for-bit from the manifest alone.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
STEWARDSHIP_ROOT = REPO_ROOT / "stewardship"

PYPI_INDEX_URL = "https://pypi.org/pypi/{name}/json"
NPM_REGISTRY_URL = "https://registry.npmjs.org/{name}/latest"
DOWNLOAD_TIMEOUT_SECONDS = 60

# Default smoke probe input, shaped for markdown renderers. Non-markdown
# target classes declare their own via ``driver.smoke_input``.
DEFAULT_SMOKE_INPUT = "# frontier smoke\n\ntext with [a](b) and `code`\n"


@dataclass(frozen=True)
class FrontierRelease:
    name: str
    version: str
    sdist_url: str
    sdist_sha256: str
    index_url: str
    upstream_repo: str | None


def _http_get(url: str, timeout: int = DOWNLOAD_TIMEOUT_SECONDS) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "blackhole-agent-frontier"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_latest_release(
    pypi_name: str,
    *,
    index_url: str | None = None,
    fetcher: Any = None,
) -> FrontierRelease:
    """Resolve the latest release's sdist from PyPI metadata.

    ``fetcher`` is injectable for hermetic tests: a callable ``url -> bytes``.
    Only sdists qualify; projects publishing wheels only are rejected.
    """
    get = fetcher or _http_get
    index = index_url or PYPI_INDEX_URL.format(name=pypi_name)
    payload = json.loads(get(index).decode("utf-8"))
    info = payload["info"]
    version = info["version"]
    sdists = [f for f in payload.get("urls", []) if f.get("packagetype") == "sdist"]
    if not sdists:
        raise ValueError(f"{pypi_name} {version}: no sdist published for latest release")
    sdist = sdists[0]
    project_urls = info.get("project_urls") or {}
    upstream_repo = next(
        (
            project_urls[key]
            for key in ("Source", "Repository", "Source Code", "Code", "Homepage")
            if project_urls.get(key)
        ),
        info.get("home_page") or None,
    )
    return FrontierRelease(
        name=info["name"],
        version=version,
        sdist_url=sdist["url"],
        sdist_sha256=sdist["digests"]["sha256"],
        index_url=index,
        upstream_repo=upstream_repo,
    )


@dataclass(frozen=True)
class NpmRelease:
    name: str
    version: str
    tarball_url: str
    integrity: str  # Subresource Integrity form, e.g. "sha512-<base64>"
    shasum: str  # legacy sha1 hex digest
    registry_url: str
    upstream_repo: str | None


def _integrity_hexdigest(integrity: str) -> tuple[str, str]:
    """Decode an npm ``dist.integrity`` value to ``(algorithm, hex digest)``."""
    algorithm, sep, encoded = integrity.partition("-")
    if not sep or algorithm not in hashlib.algorithms_available:
        raise ValueError(f"unsupported npm integrity value: {integrity!r}")
    return algorithm, base64.b64decode(encoded).hex()


def _verify_npm_tarball(tarball_bytes: bytes, release: NpmRelease) -> str:
    """Cross-check a downloaded npm tarball against registry-declared digests.

    Both the SRI integrity field and the legacy sha1 shasum must match.
    Returns the sha256 hex digest (recorded alongside for continuity with
    the pypi manifest shape).
    """
    algorithm, expected_hex = _integrity_hexdigest(release.integrity)
    actual = hashlib.new(algorithm, tarball_bytes).hexdigest()
    if actual != expected_hex:
        raise ValueError(
            f"download provenance mismatch for {release.name}-{release.version}: "
            f"registry declared {release.integrity}, got {algorithm}:{actual}"
        )
    actual_sha1 = hashlib.sha1(tarball_bytes).hexdigest()
    if actual_sha1 != release.shasum:
        raise ValueError(
            f"download provenance mismatch for {release.name}-{release.version}: "
            f"registry declared shasum {release.shasum}, got {actual_sha1}"
        )
    return _sha256_bytes(tarball_bytes)


def fetch_latest_npm_release(
    npm_name: str,
    *,
    registry_url: str | None = None,
    fetcher: Any = None,
) -> NpmRelease:
    """Resolve the latest release's tarball from npm registry metadata.

    ``fetcher`` is injectable for hermetic tests: a callable ``url -> bytes``.
    """
    get = fetcher or _http_get
    index = registry_url or NPM_REGISTRY_URL.format(name=npm_name)
    payload = json.loads(get(index).decode("utf-8"))
    dist = payload["dist"]
    repository = payload.get("repository") or {}
    repo_url = repository.get("url") if isinstance(repository, Mapping) else repository
    if isinstance(repo_url, str) and repo_url.startswith("git+"):
        repo_url = repo_url[len("git+"):]
    if isinstance(repo_url, str) and repo_url.endswith(".git"):
        repo_url = repo_url[: -len(".git")]
    return NpmRelease(
        name=payload["name"],
        version=payload["version"],
        tarball_url=dist["tarball"],
        integrity=dist["integrity"],
        shasum=dist["shasum"],
        registry_url=index,
        upstream_repo=repo_url or None,
    )


def detect_npm_package_root(tarball_bytes: bytes) -> str:
    """Locate the package root inside an npm tarball, without extracting.

    npm tarballs carry a single top-level directory (conventionally
    ``package/``) containing ``package.json``; the returned path is relative
    to the extraction root. Node resolves ``require(<package_root>)`` through
    the manifest's ``main``/``exports`` fields, so the driver prelude needs
    no layout knowledge beyond ``TARGET_DIR``.
    """
    with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
        names = tar.getnames()
    candidates: list[str] = []
    for member in names:
        parts = member.split("/")
        if len(parts) == 2 and parts[1] == "package.json":
            candidates.append(parts[0])
    if not candidates:
        raise ValueError("no package.json found at a single top-level dir in npm tarball")
    candidates.sort(key=len)
    return candidates[0]


def detect_npm_tests_subdir(tarball_bytes: bytes) -> str | None:
    """Locate the target's own test dir inside the npm tarball, if any."""
    with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
        names = tar.getnames()
    candidates: list[str] = []
    for member in names:
        parts = member.split("/")
        if (
            len(parts) >= 3
            and parts[-2] in ("test", "tests")
            and parts[-1].endswith((".js", ".cjs", ".mjs"))
        ):
            candidates.append("/".join(parts[:-1]))
    if not candidates:
        return None
    candidates.sort(key=len)
    return candidates[0]


def detect_src_subdir(sdist_bytes: bytes, package_name: str) -> str:
    """Locate the importable source dir inside an sdist, without extracting.

    Returns the path (relative to the extraction root) of the directory that
    directly contains ``<package>/__init__.py``. Handles both flat and
    ``src/`` layouts. Importability is verified by path shape only; the
    driver smoke test proves the rest.
    """
    module = package_name.lower().replace("-", "_")
    candidates: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(sdist_bytes), mode="r:gz") as tar:
        names = tar.getnames()
    for member in names:
        parts = member.split("/")
        if (
            len(parts) >= 3
            and parts[-1] == "__init__.py"
            and parts[-2] == module
        ):
            candidates.append("/".join(parts[:-2]))
    if not candidates:
        raise ValueError(f"no importable package '{module}' found in sdist")
    candidates.sort(key=len)  # shallowest layout wins (src/ or flat root)
    return candidates[0]


def detect_tests_subdir(sdist_bytes: bytes) -> str | None:
    """Locate the target's own test suite dir inside the sdist, if any.

    Returns the path (relative to the extraction root) of a directory named
    ``tests`` containing ``test_*.py`` files; the shallowest wins. ``None``
    when the release ships no runnable suite — the repair plane only needs
    this once defects are stewarded.
    """
    with tarfile.open(fileobj=io.BytesIO(sdist_bytes), mode="r:gz") as tar:
        names = tar.getnames()
    candidates: list[str] = []
    for member in names:
        parts = member.split("/")
        if (
            len(parts) >= 3
            and parts[-2] == "tests"
            and parts[-1].startswith("test")
            and parts[-1].endswith(".py")
        ):
            candidates.append("/".join(parts[:-1]))
    if not candidates:
        return None
    candidates.sort(key=len)
    return candidates[0]


def validate_driver_prelude(prelude: str) -> None:
    """The prelude must compile and define ``render`` (checked statically).

    The prelude imports the target package, which is deliberately not
    installed in the controller environment — it runs against the extracted
    target tree. Execution is therefore deferred to the smoke test.
    """
    tree = ast.parse(prelude, filename="<driver-prelude>")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "render":
            return
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "render" for t in node.targets
        ):
            return
    raise ValueError("driver prelude must define render(text, plugins)")


def smoke_test_driver(src_dir: Path, prelude: str, smoke_input: str = DEFAULT_SMOKE_INPUT) -> None:
    """Prove the driver actually drives the onboarded tree, in isolation.

    The smoke input is target-class knowledge, declared alongside the
    prelude: a markdown renderer smokes on markdown text, a TOML parser on
    a TOML document.
    """
    worker = (
        "import sys\n"
        f"sys.path.insert(0, {str(src_dir)!r})\n"
        f"{prelude}\n"
        f"render({smoke_input!r}, [])\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", worker],
        capture_output=True,
        text=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise ValueError(f"driver smoke test failed on frontier tree: {proc.stderr.strip()[:400]}")


_NODE_RENDER_DEF = re.compile(r"\bfunction\s+render\s*\(|\brender\s*=\s*(?:function|\()")


def validate_node_driver_prelude(prelude: str) -> None:
    """The node prelude must statically define ``render`` (checked by shape).

    Execution is deferred to the smoke test, which runs the prelude against
    the extracted target tree under ``node``.
    """
    if not _NODE_RENDER_DEF.search(prelude):
        raise ValueError("node driver prelude must define render(text, plugins)")


def _find_node() -> str:
    node = shutil.which("node")
    if node is None:
        raise ValueError("node runtime not found on PATH; npm frontier targets require node")
    return node


def smoke_test_node_driver(package_root: Path, prelude: str, smoke_input: str = DEFAULT_SMOKE_INPUT) -> None:
    """Prove a node driver drives the onboarded npm tree, in isolation.

    The prelude runs with ``TARGET_DIR`` bound to the absolute package root;
    ``require(TARGET_DIR)`` resolves through the target's own package.json,
    so the prelude carries no layout knowledge. The worker asserts render
    returns a defined value so a prelude that never calls the target fails.
    """
    node = _find_node()
    worker = (
        '"use strict";\n'
        f"const TARGET_DIR = {json.dumps(str(package_root))};\n"
        f"{prelude}\n"
        f"const __out = render({json.dumps(smoke_input)}, []);\n"
        'if (typeof __out === "undefined") { throw new Error("render returned undefined"); }\n'
    )
    with tempfile.TemporaryDirectory(prefix="frontier-node-smoke-") as scratch:
        worker_path = Path(scratch) / "worker.cjs"
        worker_path.write_text(worker, encoding="utf-8")
        proc = subprocess.run(
            [node, str(worker_path)],
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            cwd=scratch,
        )
    if proc.returncode != 0:
        raise ValueError(f"node driver smoke test failed on frontier tree: {proc.stderr.strip()[:400]}")


def onboard_npm_frontier_target(
    npm_name: str,
    driver_prelude: str,
    *,
    smoke_input: str | None = None,
    stewardship_root: Path | None = None,
    fetcher: Any = None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Fetch, pin, and register the latest npm release of ``npm_name``.

    Idempotent: if the target directory already exists with a matching
    manifest and tarball digests, the existing target is returned unchanged.
    """
    root = stewardship_root or STEWARDSHIP_ROOT
    release = fetch_latest_npm_release(npm_name, fetcher=fetcher)
    dir_name = release.name.lower().replace("@", "").replace("/", "-").replace(" ", "-")
    target_dir = root / f"{dir_name}-{release.version}"
    manifest_path = target_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(durable_read_path(manifest_path).read_text(encoding="utf-8"))
        existing_tarball = target_dir / existing["sdist"]
        if existing_tarball.exists():
            raw = existing_tarball.read_bytes()
            if (
                _sha256_bytes(raw) == existing["sdist_sha256"]
                and hashlib.sha1(raw).hexdigest() == existing["sdist_sha1"]
            ):
                return {"ok": True, "target_dir": str(target_dir), "version": release.version, "reused": True}

    validate_node_driver_prelude(driver_prelude)
    smoke_input = DEFAULT_SMOKE_INPUT if smoke_input is None else smoke_input
    tarball_bytes = (fetcher or _http_get)(release.tarball_url)
    tarball_sha256 = _verify_npm_tarball(tarball_bytes, release)
    package_root = detect_npm_package_root(tarball_bytes)
    tests_subdir = detect_npm_tests_subdir(tarball_bytes)

    target_dir.mkdir(parents=True, exist_ok=True)
    tarball_name = release.tarball_url.rsplit("/", 1)[-1]
    (target_dir / tarball_name).write_bytes(tarball_bytes)

    with tempfile.TemporaryDirectory(prefix="frontier-smoke-") as scratch:
        with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
            tar.extractall(scratch, filter="data")
        smoke_test_node_driver(Path(scratch) / package_root, driver_prelude, smoke_input)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": release.name,
        "version": release.version,
        "kind": "npm-tarball",
        "ecosystem": "npm",
        "frontier": True,
        "sdist": tarball_name,
        "sdist_sha256": tarball_sha256,
        "sdist_sha1": release.shasum,
        "sdist_integrity": release.integrity,
        "source_url": release.tarball_url,
        "npm_registry_url": release.registry_url,
        "retrieved_at": retrieved_at or utc_now_iso(),
        "fixed_in": None,
        "src_subdir": package_root,
        "tests_subdir": tests_subdir,
        "upstream_repo": release.upstream_repo,
        "upstream_changelog": None,
        "driver": {"prelude": driver_prelude, "smoke_input": smoke_input, "runtime": "node"},
        "defects": [],
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "ok": True,
        "target_dir": str(target_dir),
        "version": release.version,
        "reused": False,
        "src_subdir": package_root,
        "sdist_sha256": tarball_sha256,
    }


def onboard_frontier_target(
    pypi_name: str,
    driver_prelude: str,
    *,
    smoke_input: str | None = None,
    stewardship_root: Path | None = None,
    fetcher: Any = None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Fetch, pin, and register the latest release of ``pypi_name``.

    Idempotent: if the target directory already exists with a matching
    manifest and sdist digest, the existing target is returned unchanged.
    """
    root = stewardship_root or STEWARDSHIP_ROOT
    release = fetch_latest_release(pypi_name, fetcher=fetcher)
    target_dir = root / f"{release.name.lower().replace(' ', '-')}-{release.version}"
    manifest_path = target_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(durable_read_path(manifest_path).read_text(encoding="utf-8"))
        existing_sdist = target_dir / existing["sdist"]
        if existing_sdist.exists() and _sha256_bytes(existing_sdist.read_bytes()) == existing["sdist_sha256"]:
            return {"ok": True, "target_dir": str(target_dir), "version": release.version, "reused": True}

    validate_driver_prelude(driver_prelude)
    smoke_input = DEFAULT_SMOKE_INPUT if smoke_input is None else smoke_input
    sdist_bytes = (fetcher or _http_get)(release.sdist_url)
    actual_sha256 = _sha256_bytes(sdist_bytes)
    if actual_sha256 != release.sdist_sha256:
        raise ValueError(
            f"download provenance mismatch for {release.name}-{release.version}: "
            f"index declared {release.sdist_sha256}, got {actual_sha256}"
        )
    src_subdir = detect_src_subdir(sdist_bytes, release.name)
    tests_subdir = detect_tests_subdir(sdist_bytes)

    target_dir.mkdir(parents=True, exist_ok=True)
    sdist_name = release.sdist_url.rsplit("/", 1)[-1]
    (target_dir / sdist_name).write_bytes(sdist_bytes)

    with tempfile.TemporaryDirectory(prefix="frontier-smoke-") as scratch:
        with tarfile.open(fileobj=io.BytesIO(sdist_bytes), mode="r:gz") as tar:
            tar.extractall(scratch, filter="data")
        smoke_test_driver(Path(scratch) / src_subdir, driver_prelude, smoke_input)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": release.name,
        "version": release.version,
        "kind": "pypi-sdist",
        "frontier": True,
        "sdist": sdist_name,
        "sdist_sha256": release.sdist_sha256,
        "source_url": release.sdist_url,
        "pypi_index_url": release.index_url,
        "retrieved_at": retrieved_at or utc_now_iso(),
        "fixed_in": None,
        "src_subdir": src_subdir,
        "tests_subdir": tests_subdir,
        "upstream_repo": release.upstream_repo,
        "upstream_changelog": None,
        "driver": {"prelude": driver_prelude, "smoke_input": smoke_input},
        "defects": [],
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "ok": True,
        "target_dir": str(target_dir),
        "version": release.version,
        "reused": False,
        "src_subdir": src_subdir,
        "sdist_sha256": release.sdist_sha256,
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_driver_from(target_root: Path) -> str:
    """Reuse the driver prelude from an existing stewardship target."""
    manifest = json.loads(durable_read_path(target_root / "manifest.json").read_text(encoding="utf-8"))
    return manifest["driver"]["prelude"]


def load_smoke_input_from(target_root: Path) -> str | None:
    """Reuse the declared smoke input from an existing target, if any."""
    manifest = json.loads(durable_read_path(target_root / "manifest.json").read_text(encoding="utf-8"))
    return manifest["driver"].get("smoke_input")


# ---------------------------------------------------------------------------
# registered proof


def _proof_sdist(package: str, version: str) -> bytes:
    buf = io.BytesIO()
    init_src = b"def render_text(text):\n    return text\n"
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(f"{package}-{version}/src/{package}/__init__.py")
        info.size = len(init_src)
        tar.addfile(info, io.BytesIO(init_src))
    return buf.getvalue()


def _proof_npm_tarball(package: str, version: str) -> bytes:
    buf = io.BytesIO()
    pkg_json = json.dumps({"name": package, "version": version, "main": "index.js"}).encode()
    index_js = b"exports.render_text = function (text) { return text; };\n"
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in (
            ("package/package.json", pkg_json),
            ("package/index.js", index_js),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _proof_npm_leg(scratch: Path) -> dict[str, Any]:
    """Hermetic npm leg: fabricated registry metadata and tarball, real node.

    Onboards a fabricated latest npm release from an injected fetcher; the
    smoke test executes the fabricated package under the real node runtime.
    Asserts digest pinning, tarball round-trip, idempotent reuse, tamper
    re-onboarding, and rejection of a provenance-mismatched download.
    """
    package = "frontier-nodeprobe"
    version = "0.0.1"
    prelude = (
        "function render(text, plugins) {\n"
        "    return require(TARGET_DIR).render_text(text);\n"
        "}\n"
    )
    tarball = _proof_npm_tarball(package, version)
    sha512 = base64.b64encode(hashlib.sha512(tarball).digest()).decode()
    integrity = f"sha512-{sha512}"
    shasum = hashlib.sha1(tarball).hexdigest()
    url = f"https://proof.invalid/{package}/-/{package}-{version}.tgz"
    index = json.dumps(
        {
            "name": package,
            "version": version,
            "dist": {"tarball": url, "integrity": integrity, "shasum": shasum},
            "repository": {"url": "git+https://proof.invalid/x/y.git"},
        }
    ).encode()

    def fetcher(raw_url: str) -> bytes:
        return tarball if raw_url == url else index

    root = scratch / "npm"
    first = onboard_npm_frontier_target(package, prelude, stewardship_root=root, fetcher=fetcher)
    manifest = json.loads((root / f"{package}-{version}" / "manifest.json").read_text(encoding="utf-8"))
    pinned = (
        manifest["sdist_integrity"] == integrity
        and manifest["sdist_sha1"] == shasum
        and manifest["ecosystem"] == "npm"
        and manifest["driver"]["runtime"] == "node"
        and manifest["frontier"] is True
        and manifest["upstream_repo"] == "https://proof.invalid/x/y"
    )
    roundtrip = _sha256_bytes((root / f"{package}-{version}" / manifest["sdist"]).read_bytes()) == manifest["sdist_sha256"]
    reused = onboard_npm_frontier_target(package, prelude, stewardship_root=root, fetcher=fetcher)["reused"]

    tarball_path = root / f"{package}-{version}" / manifest["sdist"]
    raw = tarball_path.read_bytes()
    tarball_path.write_bytes(bytes([raw[0] ^ 0xFF]) + raw[1:])
    tamper = onboard_npm_frontier_target(package, prelude, stewardship_root=root, fetcher=fetcher)
    tamper_detected = not tamper["reused"] and tamper["ok"]

    bad_index = json.dumps(
        {
            "name": package,
            "version": version,
            "dist": {"tarball": url, "integrity": f"sha512-{'A' * 88}", "shasum": "0" * 40},
        }
    ).encode()
    rejected = False
    try:
        onboard_npm_frontier_target(
            package,
            prelude,
            stewardship_root=scratch / "npm-other",
            fetcher=lambda u: tarball if u == url else bad_index,
        )
    except ValueError:
        rejected = True

    ok = bool(first["ok"] and pinned and roundtrip and reused and tamper_detected and rejected)
    return {
        "ok": ok,
        "npm_pinned": pinned,
        "npm_roundtrip": roundtrip,
        "npm_reused": reused,
        "npm_tamper_detected": tamper_detected,
        "npm_mismatch_rejected": rejected,
    }


def builtin_upstream_frontier_proof() -> dict[str, Any]:
    """Prove the frontier plane hermetically: no network, fabricated index.

    Onboards a fabricated latest release from an injected fetcher, asserts
    the manifest pins the index-declared sha256 and the sdist round-trips,
    asserts idempotent reuse, then corrupts the on-disk sdist and asserts
    the plane refuses to reuse the tampered bytes. Finally asserts a
    provenance-mismatched download is rejected before any manifest exists.
    The npm leg repeats the contract for a fabricated npm tarball under the
    real node runtime.
    """
    package = "frontier_probe"
    version = "0.0.1"
    prelude = f"import {package}\n\ndef render(text, plugins):\n    {package}.render_text(text)\n"
    sdist = _proof_sdist(package, version)
    digest = _sha256_bytes(sdist)
    url = f"https://proof.invalid/{package}-{version}.tar.gz"
    index = json.dumps(
        {
            "info": {"name": package, "version": version},
            "urls": [{"packagetype": "sdist", "url": url, "digests": {"sha256": digest}}],
        }
    ).encode()

    def fetcher(raw_url: str) -> bytes:
        return sdist if raw_url == url else index

    scratch = Path(tempfile.mkdtemp(prefix="frontier-proof-"))
    try:
        first = onboard_frontier_target(package, prelude, stewardship_root=scratch, fetcher=fetcher)
        manifest = json.loads((scratch / f"{package}-{version}" / "manifest.json").read_text(encoding="utf-8"))
        pinned = manifest["sdist_sha256"] == digest and manifest["frontier"] is True
        roundtrip = _sha256_bytes((scratch / f"{package}-{version}" / manifest["sdist"]).read_bytes()) == digest
        reused = onboard_frontier_target(package, prelude, stewardship_root=scratch, fetcher=fetcher)["reused"]

        sdist_path = scratch / f"{package}-{version}" / manifest["sdist"]
        raw = sdist_path.read_bytes()
        sdist_path.write_bytes(bytes([raw[0] ^ 0xFF]) + raw[1:])
        tamper = onboard_frontier_target(package, prelude, stewardship_root=scratch, fetcher=fetcher)
        tamper_detected = not tamper["reused"] and tamper["ok"]

        bad_index = json.dumps(
            {
                "info": {"name": package, "version": version},
                "urls": [{"packagetype": "sdist", "url": url, "digests": {"sha256": "f" * 64}}],
            }
        ).encode()
        rejected = False
        try:
            onboard_frontier_target(
                package,
                prelude,
                stewardship_root=scratch / "other",
                fetcher=lambda u: sdist if u == url else bad_index,
            )
        except ValueError:
            rejected = True

        ok = bool(first["ok"] and pinned and roundtrip and reused and tamper_detected and rejected)
        npm_leg = _proof_npm_leg(scratch)
        return {
            "ok": bool(ok and npm_leg["ok"]),
            "pinned": pinned,
            "roundtrip": roundtrip,
            "reused": reused,
            "tamper_detected": tamper_detected,
            "mismatch_rejected": rejected,
            **npm_leg,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="upstream frontier onboarding plane")
    sub = parser.add_subparsers(dest="command", required=True)
    onboard_p = sub.add_parser("onboard", help="onboard the latest release as a frontier target")
    onboard_p.add_argument("pypi_name")
    onboard_p.add_argument(
        "--ecosystem",
        choices=("pypi", "npm"),
        default="pypi",
        help="release ecosystem to onboard from (default: pypi)",
    )
    onboard_p.add_argument(
        "--driver-from",
        default=None,
        help="existing stewardship target dir to reuse the driver prelude from",
    )
    onboard_p.add_argument("--driver-file", default=None, help="file containing a driver prelude")
    onboard_p.add_argument(
        "--smoke-input-file",
        default=None,
        help="file containing the driver smoke probe input (default: markdown-shaped sample; "
        "reused from --driver-from when that manifest declares one)",
    )
    args = parser.parse_args(argv)

    if args.command == "onboard":
        if args.driver_from:
            prelude = load_driver_from(Path(args.driver_from))
        elif args.driver_file:
            prelude = durable_read_path(Path(args.driver_file)).read_text(encoding="utf-8")
        else:
            parser.error("one of --driver-from or --driver-file is required")
        smoke_input: str | None = None
        if args.smoke_input_file:
            smoke_input = durable_read_path(Path(args.smoke_input_file)).read_text(encoding="utf-8")
        elif args.driver_from:
            smoke_input = load_smoke_input_from(Path(args.driver_from))
        if args.ecosystem == "npm":
            result = onboard_npm_frontier_target(args.pypi_name, prelude, smoke_input=smoke_input)
        else:
            result = onboard_frontier_target(args.pypi_name, prelude, smoke_input=smoke_input)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
