import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import blackhole_agent.kernels.codex_cli as codex_cli
from blackhole_agent.github_growth import build_self_evolution_plan, run_intake_once
from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel
from blackhole_agent.tool_routing import ToolCompatibilityCache, ToolDescriptor


class WebResearchJourneyClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, int]] = []

    def list_repository_events(self, repo: str, *, per_page: int = 100) -> list[dict]:
        self.requests.append((repo, per_page))
        return [
            {
                "id": "web-research-mcp-cancel",
                "type": "PullRequestReviewCommentEvent",
                "actor": {"login": "octocat"},
                "created_at": "2026-06-16T09:37:03Z",
                "payload": {
                    "action": "created",
                    "pull_request": {
                        "title": "Add web research workflow journey regression coverage",
                        "html_url": "https://github.com/omnigent-ai/omnigent/pull/316",
                    },
                    "comment": {
                        "body": (
                            "Cover web research workflow, MCP tool routing, and cancellation recovery as one "
                            "local end-to-end journey."
                        ),
                        "html_url": "https://github.com/omnigent-ai/omnigent/pull/316#discussion_r3419525416",
                    },
                },
            }
        ]


def test_web_research_mcp_and_cancel_recover_journey_regression(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docs").mkdir()
    (repo / "docs" / "self-model.md").write_text("# Self Model\n\nFixture.\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    client = WebResearchJourneyClient()

    digest_result = run_intake_once(
        repos=["omnigent-ai/omnigent"],
        output_dir=output_dir,
        client=client,
        topics=["agent", "test", "workflow"],
        lookback_hours=24,
        repo_path=repo,
        proposal_mode="heuristic",
    )
    plan = build_self_evolution_plan(digest_result.digest, repo_path=repo)
    assert plan is not None

    mcp_web_research = ToolDescriptor(
        name="web_research",
        description="Summarize public repository evidence for a local growth run.",
        parameters={
            "type": "object",
            "properties": {
                "evidence_url": {"type": "string", "format": "uri"},
                "max_items": {"type": "integer", "minimum": 1},
            },
            "required": ["evidence_url"],
            "additionalProperties": False,
        },
        provider="mcp",
        session_id=digest_result.digest["digest_id"],
    )
    route_cache = ToolCompatibilityCache()
    route_key = route_cache.set(mcp_web_research, "stubbed-web-research-route")

    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 16, 9, 37, 3, tzinfo=timezone.utc)

    attempts = 0
    last_message_paths: list[Path] = []

    def interrupt_then_recover(command, **kwargs):
        nonlocal attempts
        attempts += 1
        last_message = Path(command[command.index("--output-last-message") + 1])
        last_message_paths.append(last_message)
        if attempts == 1:
            last_message.write_text("partial web research trace", encoding="utf-8")
            raise subprocess.TimeoutExpired(command, timeout=1, output="research started", stderr="")
        assert not last_message.exists()
        last_message.write_text("web research journey recovered", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="recovered", stderr="")

    monkeypatch.setattr(codex_cli, "datetime", FixedDatetime)
    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=interrupt_then_recover)

    with pytest.raises(TimeoutError, match="Codex CLI timed out after 1 seconds") as timeout_info:
        kernel.run(plan.task, cwd=repo, output_dir=output_dir / "codex", timeout_seconds=1)

    timeout_result_path = output_dir / "codex" / "codex-run-20260616T093703Z.json"
    timeout_run = json.loads(timeout_result_path.read_text(encoding="utf-8"))
    timeout_latest = json.loads((output_dir / "codex" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert timeout_latest == timeout_run
    assert timeout_run["timed_out"] is True
    assert timeout_run["returncode"] == 124
    assert timeout_run["last_message"] == "partial web research trace"
    assert str(timeout_result_path) in str(timeout_info.value)

    recovered = kernel.run(plan.task, cwd=repo, output_dir=output_dir / "codex", timeout_seconds=5)

    latest_digest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    latest_run = json.loads((output_dir / "codex" / "latest-codex-run.json").read_text(encoding="utf-8"))

    assert client.requests == [("omnigent-ai/omnigent", 100)]
    assert latest_digest["items"][0]["source_url"].endswith("#discussion_r3419525416")
    assert latest_digest["proposals"][0]["validation_gate"] == "narrow-local-verification"
    assert "web research workflow" in plan.task
    assert route_key == mcp_web_research.compatibility_key()
    assert route_cache.get(mcp_web_research) == "stubbed-web-research-route"
    assert last_message_paths[0] != last_message_paths[1]
    assert timeout_result_path.exists()
    assert recovered.last_message == "web research journey recovered"
    assert latest_run["timed_out"] is False
    assert latest_run["result_path"].endswith("codex-run-20260616T093703Z-001.json")
