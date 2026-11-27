"""Keep the instructions for a logical turn fixed while its Git workspace changes."""

from dataclasses import dataclass
from typing import Any

from blackhole_agent.kernel_salvage import DECISION_ONLY_PROMPT


def compact_text(value: str, *, limit: int, strip_chars: str | None = None) -> str:
    text = value.strip(strip_chars)
    if len(text) <= limit:
        return text
    head = limit // 2
    return f"{text[:head]}\n... compacted by controller ...\n{text[-(limit - head):]}"


def decision_only_prompt(state: Any) -> str:
    parts = [DECISION_ONLY_PROMPT]
    for label, field in (("Mission goal", "goal"), ("Done when", "done_when")):
        value = str(getattr(state, field, "") or "").strip()
        if value:
            parts.append(f"{label}:\n{value}")
    return "\n\n".join(parts)


@dataclass(frozen=True)
class TurnPrompt:
    mission: str
    instructions: str

    def render(self, snapshot: dict[str, Any], *, limit: int, handoff: bool = False) -> str:
        notice = ""
        if handoff:
            notice = (
                "Continue this turn in the persistent mission workspace. Inspect pending edits with "
                "git status --short --untracked-files=all before starting new work.\n"
            )
            if path := snapshot.get("status_file"):
                notice += f"Full Git status file: {path}\n"
            notice += "\n"
        if "error" in snapshot:
            worktree = f"Git snapshot unavailable ({snapshot['error']}). Inspect the mission workspace directly."
        else:
            worktree = f"""Current HEAD: {snapshot.get("head", "")}

Current repository state:
```text
git status --short --untracked-files=all
{snapshot.get("status") or "(clean)"}

git diff --stat
{snapshot.get("diff_stat") or "(no unstaged diff)"}

recent commits
{snapshot.get("recent_commits") or "(none)"}
```"""
        return compact_text(f"{notice}{self.mission}\n\n{worktree}\n\n{self.instructions}", limit=limit)
