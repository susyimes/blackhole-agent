# Evolution quality and Cursor Agent CLI

## Quality gates

- Autonomous selection groups repeated handshake / sealed digest / later-reader
  recipes by behavior, not protocol/RFC names. Lexical catalog labels remain
  available for descriptor compatibility, but are not novelty evidence.
- Ledger existence, self-proof flags and counts alone are not an outcome contract.
  Old catalog entries remain inventory; if no qualified successor exists, genesis
  stays open for a CLI to choose a real task.
- Automatically bound/resumed missions also pass selection. Only a goal supplied
  to `start --goal` receives `operator_supplied` provenance. Old states lacking
  provenance are conservatively autonomous; weak unfinished contracts may block
  for operator revision without discarding work.
- Execution-stage responses cannot replace the bound `done_when`.
- Large new Python modules/expanded stubs with >=12 implementation functions/classes
  and >=90% normalized AST overlap with a sibling are rejected as renamed copies.
  Small repairs to existing substantial implementations remain possible.
- Six consecutive local fallback turns with no behavior-content changes block the
  mission and preserve its worktree. Dirty filenames, ledger timestamps and
  controller artifacts are not progress. CLI reasoning turns are not bounded by
  this local-only limit; actual content progress or a milestone resets it.

## Reproducible acceptance

Autonomous `milestone`/`complete` responses require `acceptance_probe`, a Python
file inside `tests/acceptance/`. It exits zero and prints a final JSON object with
boolean `passed` and a nonempty `observed` value:

```python
import json
from my_package import reconstruct
actual = reconstruct([b"hel", b"lo"])
print(json.dumps({"passed": actual == "hello", "observed": {"actual": actual}}))
```

The controller runs the same probe bytes in fresh Python processes with private
copies of `src` and the selected runtime files. The baseline reads the specified
Git commit. The candidate reads working-tree contents, including unstaged edits,
deletions and nonignored new files. Acceptance requires a false baseline outcome
and a true candidate outcome. Both runs must finish and produce valid observations.

Put a leading comment such as `# replay-input: locales/fr` in a probe to require
a versioned file or directory in both snapshots. Use one literal repository-relative
path per comment, before the module docstring or imports. A missing required input
stops replay before either run. The optional `tests/acceptance/replay-inputs.txt`
lists paths shared by multiple probes, one per line. Each snapshot includes the
shared files present in its own revision. For example, document-layout probes use
the project's absorbed HTML parser through this list.

The receipt records the resolved commit, selected inputs, probe SHA-256, both
outcomes and process results.
Exact validation-command replay still runs. Probe a real task or independent
reference fixture, not source/version names, ledger flags or `builtin_*_proof`.
This is regression evidence, not independent standards certification or a
tamper-proof judge of model-authored tests.

## Cursor kernel

Manual start example (does not automatically resume a paused loop):

```powershell
uv run blackhole-unbound start --repo-path . --kernel cursor --model auto
```

Omit `--model` to use Cursor's configured default. Discovery checks explicit
`CursorCliConfig.cursor_bin`, `CURSOR_AGENT_BIN`, `cursor-agent` on PATH, then
`%LOCALAPPDATA%\cursor-agent\cursor-agent.cmd`. It never automatically chooses
bare `agent` (also a Grok alias) or the editor's `cursor` command. Point
`CURSOR_AGENT_BIN` at the Cursor-owned binary for an agent-only installation.

The adapter uses print-mode stream JSON, UTF-8 stdin for the full prompt, and
native `--resume` sessions. Windows uses the official launcher's bundled Node
directly to avoid shell quoting/length limits. Only a successful terminal result
can become a decision. Run/preflight artifacts record failures and partial session
IDs for recovery. Discovery, invocation, failover and peer probes all know Cursor;
cross-provider failover clears the old model/session.

Login uses the existing CLI session or `CURSOR_API_KEY`; BA does not rewrite
credentials. Version probes are not auth checks. Mission prompts retain the
single-agent/no-delegation rule; Cursor has no documented `--no-subagents` flag.

Official interfaces: [parameters](https://cursor.com/docs/cli/reference/parameters),
[output format](https://cursor.com/docs/cli/reference/output-format).
