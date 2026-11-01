"""Outcome probe: mission creation uses the creator now on disk.

The 2026-11-01 22:39 storage receipt has no worktree_reclaim key. The loop
process imported create_mission at startup, and the reimport that writes that
key lives inside the published function, so it never ran.

This probe captures a startup creator whose source digest does not match the
checkout file. The checkout file's creator writes a receipt that contains
worktree_reclaim. A matching digest keeps the startup creator, and that
receipt omits the key. A custom command runner also keeps the startup creator.
Both outcomes exit 0.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def _startup_creator(receipt_path: Path, state_path: Path):
    def create_mission(**_kwargs):
        receipt_path.write_text(json.dumps({"creator": "startup"}), encoding="utf-8")
        state_path.write_text("startup", encoding="utf-8")
        return state_path

    return create_mission


def _write_published(repo: Path, receipt_path: Path, state_path: Path) -> None:
    package = repo / "src" / "blackhole_agent"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    receipt = json.dumps(str(receipt_path))
    state = json.dumps(str(state_path))
    (package / "unbound.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "def create_mission(**_kwargs):\n"
        f"    receipt = Path({receipt})\n"
        f"    state = Path({state})\n"
        "    receipt.parent.mkdir(parents=True, exist_ok=True)\n"
        "    state.parent.mkdir(parents=True, exist_ok=True)\n"
        "    receipt.write_text(json.dumps({\n"
        "        'creator': 'published',\n"
        "        'worktree_reclaim': {'ok': True, 'keep_recent': 1},\n"
        "    }), encoding='utf-8')\n"
        "    state.write_text('published', encoding='utf-8')\n"
        "    return state\n",
        encoding="utf-8",
    )


def _read_receipt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _exercise() -> dict:
    from blackhole_agent.controller_adoption import (
        CREATOR_SOURCE_DIGEST,
        file_sha256,
        invoke_published_mission_creator,
    )

    with tempfile.TemporaryDirectory(prefix="bh-creator-probe-") as tmp:
        root = Path(tmp)
        repo = root / "repo"
        receipt_path = root / "receipt.json"
        state_path = root / "state.txt"
        _write_published(repo, receipt_path, state_path)
        captured = _startup_creator(receipt_path, state_path)
        setattr(captured, CREATOR_SOURCE_DIGEST, "0" * 64)
        call = {
            "repo_path": repo,
            "kernel": "grok",
            "model": None,
            "profile": None,
            "target_branch": "main",
            "branch_prefix": "unbound",
            "output_dir": Path(".blackhole-agent/unbound"),
            "worktree_parent": None,
            "timeout_seconds": 30,
        }
        published_state = invoke_published_mission_creator(
            repo,
            captured,
            call,
            reload_default=True,
        )
        published = _read_receipt(receipt_path)
        published_body = state_path.read_text(encoding="utf-8")
        current = file_sha256(repo / "src" / "blackhole_agent" / "unbound.py")
        setattr(captured, CREATOR_SOURCE_DIGEST, current)
        matched_state = invoke_published_mission_creator(
            repo,
            captured,
            call,
            reload_default=True,
        )
        matched = _read_receipt(receipt_path)
        runner_state = invoke_published_mission_creator(
            repo,
            captured,
            {**call, "command_runner": lambda *_args, **_kwargs: None},
            reload_default=True,
        )
        # The matching digest was replaced by the custom-runner call, which
        # must also stay on the startup creator. Restore the stale digest and
        # confirm a custom runner still does not publish.
        receipt_path.write_text("{}", encoding="utf-8")
        setattr(captured, CREATOR_SOURCE_DIGEST, "0" * 64)
        custom_state = invoke_published_mission_creator(
            repo,
            captured,
            {**call, "command_runner": lambda *_args, **_kwargs: None},
            reload_default=True,
        )
        custom = _read_receipt(receipt_path)

    published_ok = (
        published.get("creator") == "published"
        and isinstance(published.get("worktree_reclaim"), dict)
        and published["worktree_reclaim"].get("ok") is True
        and published_body == "published"
        and Path(published_state).name == state_path.name
    )
    matched_ok = (
        matched.get("creator") == "startup"
        and "worktree_reclaim" not in matched
        and Path(matched_state) == state_path
        and runner_state == state_path
    )
    custom_ok = custom.get("creator") == "startup" and "worktree_reclaim" not in custom and custom_state == state_path
    return {
        "passed": published_ok and matched_ok and custom_ok,
        "published_creator": published.get("creator"),
        "published_reclaim": published.get("worktree_reclaim"),
        "matched_creator": matched.get("creator"),
        "matched_reclaim_omitted": "worktree_reclaim" not in matched,
        "custom_runner_creator": custom.get("creator"),
    }


def main() -> int:
    try:
        from blackhole_agent.controller_adoption import invoke_published_mission_creator
    except ImportError:
        print(
            json.dumps(
                {
                    "passed": False,
                    "observed": "the loop still calls the creator captured at startup",
                }
            )
        )
        return 0
    del invoke_published_mission_creator
    try:
        observed = _exercise()
    except Exception as error:  # noqa: BLE001 - unmet outcome must exit 0
        print(json.dumps({"passed": False, "observed": str(error)}))
        return 0
    print(json.dumps({"passed": bool(observed["passed"]), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
