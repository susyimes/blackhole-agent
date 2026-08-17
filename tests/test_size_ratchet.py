from pathlib import Path

from blackhole_agent.size_ratchet import (
    FileSize,
    builtin_size_ratchet,
    check_size_ratchet,
    evaluate_size_ratchet,
    measure_repo,
    write_size_ratchet_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_grown_total_fails_and_shrink_or_hold_passes():
    held = evaluate_size_ratchet(
        [FileSize(path="src/blackhole_agent/unbound.py", lines=100)],
        {"baseline_lines": 100, "exceptions": []},
    )
    shrunk = evaluate_size_ratchet(
        [FileSize(path="src/blackhole_agent/unbound.py", lines=90)],
        {"baseline_lines": 100, "exceptions": []},
    )
    grown = evaluate_size_ratchet(
        [FileSize(path="src/blackhole_agent/unbound.py", lines=101)],
        {"baseline_lines": 100, "exceptions": []},
    )
    exception = evaluate_size_ratchet(
        [FileSize(path="src/blackhole_agent/capability_compounder.py", lines=250)],
        {
            "baseline_lines": 300,
            "exceptions": [{"path": "src/blackhole_agent/capability_compounder.py", "max_lines": 200}],
        },
    )

    assert held.ok is True
    assert shrunk.ok is True
    assert grown.ok is False
    assert "exceed baseline" in grown.reason
    assert exception.ok is False
    assert exception.exception_violations


def test_write_manifest_grandfathers_large_files(tmp_path):
    src = tmp_path / "src" / "blackhole_agent"
    tests = tmp_path / "tests"
    src.mkdir(parents=True)
    tests.mkdir()
    (src / "small.py").write_text("x = 1\n", encoding="utf-8")
    (src / "huge.py").write_text("\n".join(f"v{i} = {i}" for i in range(2100)) + "\n", encoding="utf-8")
    (tests / "test_small.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    payload = write_size_ratchet_manifest(tmp_path, grandfather_threshold=2000)
    report = check_size_ratchet(tmp_path)

    assert payload["baseline_lines"] == report["total_lines"]
    assert report["ok"] is True
    assert any(item["path"] == "src/blackhole_agent/huge.py" for item in payload["exceptions"])

    (src / "extra.py").write_text("NEW = 1\n", encoding="utf-8")
    grown = check_size_ratchet(tmp_path)
    assert grown["ok"] is False


def test_measure_skips_pycache(tmp_path):
    src = tmp_path / "src" / "blackhole_agent"
    src.mkdir(parents=True)
    (src / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    cache = src / "__pycache__"
    cache.mkdir()
    (cache / "keep.cpython-312.pyc").write_text("nope", encoding="utf-8")

    files = measure_repo(tmp_path)

    assert [item.path for item in files] == ["src/blackhole_agent/keep.py"]


def test_live_repo_respects_checked_in_ratchet():
    report = check_size_ratchet(REPO_ROOT)

    assert report["baseline_lines"] > 0
    assert report["ok"] is True, report.get("reason")
    assert report["delta"] <= 0


def test_builtin_size_ratchet_is_green():
    assert builtin_size_ratchet()["ok"] is True
