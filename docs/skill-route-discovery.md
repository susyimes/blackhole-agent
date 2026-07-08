# Skill Route Discovery

External skill repositories are evidence for local routing lessons, not skill
packages to import during the same run. Discovery records should classify the
observed repository shape into review lanes that blackhole-agent can validate
locally: documentation, config, test, or code patch.

The repository lane probe collapses fork-lineage summaries before activation
readiness is reported. A repeated fork of the same upstream skill repository is
supporting evidence, not a second proposal row, unless it carries additional
bounded local validation signals. The probe now reports
`duplicate_candidate_summary_count`, `fork_lineage_collapsed`,
`supporting_summary_count`, supporting candidate names, and supporting source
hashes while still exporting no raw source URLs, evidence URLs, replay commands,
target paths, or upstream bodies. Generic Codex-compatible skill catalogs such
as `rnskill` stay in the documentation/config-oriented pre-activation lane
unless body-free workflow-gate markers are present.

For source digest `github-growth-20260708T104635.460026Z`, pass 2 exposes
`skill_route_discovery_current_digest_20260708T104635_pass2_validation_lane`.
The lane keeps `lingbol088-spec/reverse-flow-skill` in the bounded local test
lane as Codex workflow-gate evidence and keeps `Pluviobyte/rnskill` in the
bounded documentation lane as generic SKILL.md workflow evidence.

The lane now includes `operator_validation_checklist` for each skill-route row.
The checklist names the selected evidence item ids, selected lane, required
pre-activation checks, uncertainty reasons, and explicit activation denials.
For reverse-flow-style evidence, it requires local workflow-gate validation and
downgrades install/run/external-harness pressure. For rnskill-like generic
skill collections, it records that upstream body content has not been locally
inspected and keeps the route documentation-first. `shepherd-agents/shepherd`,
Hy3, and the Blender/Seedance workflow-usecase repository remain adjacent
`agent_harness_eval_required` rows with no direct lanes before local harness
evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T104635`.

For source digest `github-growth-20260708T100635.467596Z`, pass 1 exposes the
current reverse-flow/rnskill/Hy3/workflow-usecase window through
`current_digest_pass1_validation_lane` and
`skill_route_discovery_current_run_pass1_activation_readiness`.
`lingbol088-spec/reverse-flow-skill` maps to
`p1-skill-route-discovery-codex-workflow-gate` in the bounded local test lane
as Codex workflow-gate evidence. `Pluviobyte/rnskill` maps to
`p2-generic-skill-workflow-route-probe` in the bounded documentation lane as a
generic SKILL.md workflow descriptor.

`Tencent-Hunyuan/Hy3` and the Blender/Seedance workflow-usecase collection
remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-general-agent-trends`. They inherit no
`skill_route_discovery` route, open no direct lanes before local harness
evaluation, and may only produce documentation, test, or code_patch follow-up
after that gate. The lane exports proposal IDs, selected item IDs, lane names,
route profiles, source hashes, and command hashes only; raw source URLs,
evidence URLs, replay commands, target paths, upstream bodies, provider launch,
external harness execution, remote execution, and external activation remain
disabled. Replay with:
`python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260708T100635`.

For source digest `github-growth-20260708T092635.428641Z`, pass 3 exposes
`skill_route_discovery_current_digest_20260708T092635_pass3_proposal_replay_lane`.
The lane converts the current proposals into one bounded replay plan:
`p1-skill-route-discovery-catalog` selects the documentation lane,
`p2-skill-route-discovery-tests` selects the test lane, and
`p3-agent-harness-eval-probe` remains `agent_harness_eval_required` before any
general-agent follow-up.

The plan is derived from carried reverse-flow, rnskill, Shepherd, Hy3, and
workflow-usecase evidence only. It exports item ids, lane names, proposal ids,
hashes, and validation labels, not raw source URLs, raw evidence URLs, replay
commands, target paths, or upstream bodies. Runtime action, external skill or
agent activation, external harness execution, provider launch, profile writes,
memory writes, remote execution, push, promotion, restart, and activation remain
disabled. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T092635`.

For source digest `github-growth-20260708T094635.494091Z`, pass 4 adds a
reusable `skill_route_discovery_source_evidence_checklist` to the pass-4
operator replay path. The checklist converts external skill evidence into the
same bounded questions for every candidate: manifest shape, invocation model,
permission assumptions, testability, rollback path, and whether runtime
behavior is required.

The checklist is exposed on both `pass4_operator_replay_manifest` and
`active_pass4_operator_activation_packet`, then mirrored in the operator review
dossier. It uses candidate hashes and counts only; raw candidate names, source
URLs, evidence URLs, replay commands, target paths, and upstream bodies remain
withheld. The checklist does not grant runtime behavior, external skill
activation, external harness execution, provider launch, or remote execution.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k "pass4_completion_handoff_queues_adjacent_general_agent_evidence or current_run_pass4_completion_matrix_matches_proposals"`.

For source digest `github-growth-20260708T050637.590875Z`, pass 4 exposes
`skill_route_discovery_current_digest_20260708T050637_pass4_completion_handoff`.
The handoff closes the current reverse-flow/rnskill/Shepherd/Hy3/workflow-usecase
slice by keeping `lingbol088-spec/reverse-flow-skill` in the bounded local test
lane as Codex workflow-gate evidence and keeping `Pluviobyte/rnskill` in the
bounded documentation lane as generic `SKILL.md` workflow evidence.

`shepherd-agents/shepherd`, `Tencent-Hunyuan/Hy3`, and the Blender/Seedance
workflow-usecase collection remain grouped under
`agent_harness_eval_required` before any implementation follow-up. They inherit
no `skill_route_discovery` route hints, have no direct lanes before local
harness evaluation, and keep runtime action, provider launch, external harness
execution, remote execution, promotion, restart, and external activation
disabled. The handoff exports source hashes and validation-command hashes only,
not raw source URLs, replay commands, target paths, or upstream bodies. Replay
with: `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260708T050637`.

For source digest `github-growth-20260708T042637.744153Z`, pass 2 exposes
`skill_route_discovery_current_digest_20260708T042637_pass2_route_activation_checkpoint`.
The checkpoint turns the active reverse-flow/rnskill/Shepherd/Hy3/workflow-usecase
window into one validation-before-activation packet. Reverse-flow remains a
Codex workflow-gate test lane that must prove `skill_route_discovery_first`;
rnskill remains a generic `SKILL.md` collection in the documentation lane; and
Shepherd, Hy3, and Blender/Seedance workflow-usecase evidence remain adjacent
`agent_harness_eval_required` rows with no inherited skill-route lane.

The packet exports hashes, counts, row status, and lane decisions only. Raw
evidence URLs, replay commands, target paths, upstream bodies, external skill
activation, provider launch, external harness execution, and remote execution
remain disabled. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T042637`.

For source digest `github-growth-20260708T032637.752122Z`, pass 3 advances the
provider-runtime-control slice with
`skill_route_discovery_current_digest_20260708T032637_pass3_provider_runtime_recovery_workflow`.
The workflow is derived from the pass-2 scope recompute gate: reverse-flow stays
in the bounded local test lane as Codex workflow-gate evidence, rnskill stays in
the documentation lane as generic `SKILL.md` workflow evidence, and Shepherd
remains adjacent `agent_harness_eval_required` runtime pressure.

The pass-3 workflow accepts only a body-free `provider_runtime_preflight` sample
before pass-4 handoff. The sample records item IDs, source hashes, diagnostic
field names, recovery hint codes, and replay target hashes; it does not export
raw replay commands, source URLs, evidence URLs, provider config, provider
diagnostics, target paths, or upstream bodies. It resolves the prior
`provider_runtime_preflight_sample_missing` hint for local replay readiness
only. Runtime action, provider launch, external skill activation, external
agent activation, external harness execution, remote execution, profile writes,
memory writes, promotion, push, restart, and success claims remain denied.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T032637`.

For source digest `github-growth-20260708T024637.613270Z`, pass 2 keeps the
reverse-flow/rnskill/Shepherd window on
`skill_route_discovery_current_pass2_scope_recompute_gate` and adds a
`skill_route_discovery_current_pass2_provider_runtime_control` diagnostic panel.
`lingbol088-spec/reverse-flow-skill` remains a bounded local test lane as
Codex workflow-gate evidence, and `Pluviobyte/rnskill` remains a bounded
documentation lane as generic `SKILL.md` collection evidence. Provider/runtime
wording from install, runtime, or Shepherd-style execution claims is treated as
diagnostic pressure only.

The provider-runtime panel reports that a body-free
`provider_runtime_preflight` sample is required before runtime or provider
follow-up can be promoted. It exports recovery hint codes and replay command
hashes, not raw replay commands, provider config, diagnostics, source URLs,
evidence URLs, or upstream bodies. Provider launch, external harness execution,
remote execution, profile writes, memory writes, promotion, restart, and
external activation remain denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T024637`.

For source digest `github-growth-20260708T000200.125943Z`, pass 1 exposes
`skill_route_discovery_current_pass1_focused_review_lane` for the
rnskill/reverse-flow/Shepherd/Hy3 window. `Pluviobyte/rnskill` is kept as
generic `SKILL.md` collection evidence in the bounded documentation lane.
`lingbol088-spec/reverse-flow-skill` is kept as Codex workflow-gate evidence
in the bounded test lane because its public shape includes `skills/reverse-flow`,
`SKILL.md`, local sandbox and CTF framing, staged workflow language, and
diagnostic scripts. `shepherd-agents/shepherd` remains adjacent
`agent_harness_eval_required` evidence for reversible runtime traces; it
inherits no `skill_route_discovery` lane and opens no direct implementation
lane before local harness evaluation.

The same pass records `skill_route_discovery_hy3_provider_mcp_preflight_lane`
for `p4-hy3-provider-mcp-preflight`. Hy3 API and MCP issues are provider/tooling
integration pressure, not activation authority: the lane allows only
documentation, config, or test follow-up for configuration detection, endpoint
shape validation, required environment-key presence, MCP stdio metadata, and
disabled-by-default behavior. Provider runtime launch, external harness
execution, network calls, remote execution, raw evidence URL export, raw
provider config export, API-key hardcoding, and raw secret value export remain
denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T000200`.

For source digest `github-growth-20260708T002159.945917Z`, pass 2 exposes
`skill_route_discovery_current_pass2_scope_recompute_gate`. The gate binds
`lingbol088-spec/reverse-flow-skill` to the bounded local test lane as
`codex_workflow_gate` evidence and binds `Pluviobyte/rnskill` to the
documentation lane as generic `SKILL.md` collection evidence. Both rows record
`controller_recomputed_scope: local_validation_candidate`,
`focused-evidence-review`, and `code_patch_requires_controller_recompute`
before any code patch can proceed from the route evidence.

`shepherd-agents/shepherd` remains adjacent
`agent_harness_eval_required` evidence. It inherits no skill-route lane, has no
direct runtime or code-patch route before local harness evaluation, and keeps
`runtime_action: none`. The gate exports no raw source URLs, replay commands,
target paths, upstream bodies, provider launches, external harness execution,
remote execution, restart, promotion, or activation authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k current_pass2_scope_recompute_gate`.

For source digest `github-growth-20260708T004159.978474Z`, pass 3 exposes
`skill_route_discovery_current_digest_20260708T004159_pass3_operator_handoff`.
The handoff is derived from the pass-2 scope recompute gate rather than from
fresh upstream parsing. It keeps `lingbol088-spec/reverse-flow-skill` in the
local test lane as `codex_workflow_gate` evidence, keeps `Pluviobyte/rnskill`
in the documentation lane as generic `SKILL.md` workflow evidence, and records
that any code_patch follow-up still requires the controller-recomputed local
validation scope.

`shepherd-agents/shepherd` remains an adjacent
`agent_harness_eval_required` row with no direct local lanes before harness
evaluation. It may only produce documentation, test, or code_patch follow-up
after bounded local agent-harness evidence exists. The handoff records rollback
ref
`refs/blackhole/rollback/20260708T004349Z-skill-route-discovery-pass3-current-window`,
records that `docs/self-model.md` stayed unchanged because the current
self-model already supports rollback-backed local validation, and keeps Hy3
provider/MCP pressure as disabled follow-up only. It exports no raw source
URLs, replay commands, upstream bodies, provider launches, external harness
execution, remote execution, promotion, restart, or activation authority. Replay
with:
`python -m pytest tests/test_skill_routing.py -q -k 20260708T004159`.

For source digest `github-growth-20260708T010200.023332Z`, pass 4 completes
the same reverse-flow/rnskill/Shepherd/Hy3 window through
`skill_route_discovery_current_pass4_completion_handoff` inside the local
validation route packet. `lingbol088-spec/reverse-flow-skill` stays in the
bounded local test lane as Codex workflow-gate evidence, and
`Pluviobyte/rnskill` stays in the bounded documentation lane as generic
`SKILL.md` workflow evidence. `shepherd-agents/shepherd` is queued only as
`agent_harness_eval_required` before implementation follow-up.

Hy3 API and MCP issue evidence is recorded as
`skill_route_discovery_pass4_provider_mcp_preflight_followup`: documentation,
config, and test are the only follow-up lanes, while provider runtime launch,
network calls, external harness execution, remote execution, API-key
hardcoding, raw provider config export, raw secret value export, promotion,
restart, and external activation remain denied. The handoff records rollback
ref `refs/rollback/blackhole-agent/20260708T010158Z-skill-route-discovery-pass4`,
leaves `docs/self-model.md` unchanged, and exports no raw source URLs, replay
commands, target paths, or upstream bodies. Replay with:
`$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k 20260708T010200`.

For source digest `github-growth-20260707T234200.022738Z`, pass 4 now exposes
`skill_route_discovery_current_pass4_completion_handoff` for the current
reverse-flow/rnskill/BioNeMo/Agents-A1 window. The handoff binds
`lingbol088-spec/reverse-flow-skill` to
`p1-reverse-flow-skill-route-discovery` in the local test lane as Codex
workflow-gate evidence, binds `NVIDIA-BioNeMo/bionemo-agent-toolkit` to
`p2-generic-skill-workflow-fixtures` in the local test lane as a
domain-specific skill toolkit guard, and binds `Pluviobyte/rnskill` to
`p3-skill-route-discovery-doc` in the documentation lane as generic
`SKILL.md` workflow evidence.

`InternScience/Agents-A1` remains queued under
`p4-agent-harness-eval-gate` as `agent_harness_eval_required`. It inherits no
`skill_route_discovery` lane, opens no direct implementation lane before local
harness evaluation, and may only produce documentation, test, or code_patch
follow-up after that gate. The handoff records rollback ref
`refs/blackhole/rollback/20260708T000000Z-skill-route-discovery-pass4-completion`,
adds an operator review checklist for bounded lanes and activation denials,
and exports no raw source URLs, replay commands, upstream bodies, provider
launches, remote execution, promotion, restart, or activation authority. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260707T234200`.

For source digest `github-growth-20260707T232200.034561Z`, pass 3 exposes
`skill_route_discovery_current_pass3_proposal_lane` for the current
reverse-flow/rnskill/BioNeMo skill-workflow probe. The fixture uses only the
selected digest items for `lingbol088-spec/reverse-flow-skill`,
`Pluviobyte/rnskill`, and `NVIDIA-BioNeMo/bionemo-agent-toolkit`.

`p1_skill_route_discovery_probe` keeps the Codex reverse-flow repository in
the bounded local test lane, `p2_codex_skill_workflow_profile` checks the
`codex_workflow_gate` profile through the bounded config lane, and
`p3_generic_skill_workflow_docs` keeps generic `SKILL.md` collection evidence
in the documentation lane. `p4_bionemo_domain_skill_toolkit_guard` keeps the
domain-specific BioNeMo skill-toolkit signal in the test lane until local
citation, advice, data, and provider boundaries are validated.

All rows keep documentation, config, test, and code_patch as the only allowed
local lanes, require focused local validation, and keep runtime adoption,
external skill activation, provider launch, external harness execution, remote
execution, raw source URL export, raw evidence URL export, raw target path
export, and upstream body export disabled. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T232200`.

For source digest `github-growth-20260707T222110.418015Z`, pass 4 completes
the active reverse-flow/rnskill/BioNeMo/Agents-A1 window through
`skill_route_discovery_current_pass4_completion_handoff`. The handoff binds
`Pluviobyte/rnskill` to the bounded documentation lane as a generic SKILL.md
collection, binds `lingbol088-spec/reverse-flow-skill` to the bounded test lane
as a Codex workflow-gate skill route, and keeps
`NVIDIA-BioNeMo/bionemo-agent-toolkit` in the bounded test lane as a
domain-specific skill toolkit guard before any provider, data, citation, or
advice boundary is activated.

`InternScience/Agents-A1` remains queued in `general_agent_recovery_workflow`
under `agent_harness_eval_required`. It inherits no `skill_route_discovery`
lane, opens no direct implementation lane before local harness evaluation, and
may only produce documentation, test, or code_patch follow-up after that gate.
The handoff records rollback ref
`refs/rollback/blackhole-agent/20260708T022108Z-skill-route-discovery-pass4`,
records that `docs/self-model.md` stayed unchanged because this run had a
concrete behavior path, and exports no raw source URLs, replay commands,
target paths, upstream bodies, provider launches, memory or profile writes,
promotion, restart, remote execution, or activation authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T222110`.

For source digest `github-growth-20260707T220110.405293Z`, pass 3 exposes the
active reverse-flow/rnskill/BioNeMo/Agents-A1 window through
`skill_route_discovery_current_pass3_proposal_lane`. The lane binds
`p1-skill-route-discovery-fixtures` to a local test row for
`lingbol088-spec/reverse-flow-skill`, binds `p2-skill-route-discovery-doc` to
the generic `Pluviobyte/rnskill` documentation row, and keeps
`NVIDIA-BioNeMo/bionemo-agent-toolkit` in a domain-specific skill toolkit test
guard before any provider, data, citation, or advice boundary is activated.

`InternScience/Agents-A1` remains a general-agent project row under
`p3-agent-harness-eval-gate`: it inherits no `skill_route_discovery` lane,
opens no direct local lanes before evaluation, and may only proceed to
documentation, test, or code_patch after a bounded local harness result exists.
The pass-3 lane records rollback ref
`refs/blackhole/rollback/20260707T220110Z-skill-route-discovery-pass3-current-window`,
leaves `docs/self-model.md` unchanged because the current self-model already
supports rollback-backed local validation, and exports no raw source URLs,
replay commands, upstream bodies, provider launches, remote execution,
promotion, restart, or activation authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T220110`.

For source digest `github-growth-20260707T212110.239635Z`, pass 1 exposes the
active reverse-flow/rnskill/BioNeMo/Agents-A1/Shepherd window through
`skill_route_discovery_current_pass1_focused_review_lane`. The lane maps
`lingbol088-spec/reverse-flow-skill` to the bounded local test lane because the
public repository is a Codex/AI Agent workflow skill with `skills/reverse-flow`,
`SKILL.md`, local sandbox framing, staged analysis, and diagnostic scripts. It
maps `Pluviobyte/rnskill` to the documentation lane as a generic multi-skill
collection.

`NVIDIA-BioNeMo/bionemo-agent-toolkit` stays in the same skill-route discovery
surface as a domain-specific skill toolkit guard: it may produce only
documentation, config, test, or code_patch candidates until local validation
proves a concrete citation, data, advice, and provider boundary. Install,
runtime execution, provider launch, upstream dataset import, and external skill
activation remain denied. `InternScience/Agents-A1` and
`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows
and inherit no skill-route lane before local harness evaluation. The pass-1
lane records rollback ref
`refs/blackhole/rollback/20260707T212110Z-skill-route-discovery-pass1`, leaves
`docs/self-model.md` unchanged because the existing preference already supports
rollback-backed local behavior changes, and exports no raw source URLs, replay
commands, upstream bodies, provider launches, remote execution, promotion,
restart, or activation authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T212110`.

For source digest `github-growth-20260707T200110.283498Z`, pass 1 exposes the
current skill-route-discovery window through
`skill_route_discovery_current_pass1_focused_review_lane`. The lane maps
`lingbol088-spec/reverse-flow-skill` to the bounded local test lane because its
public evidence is a Codex/AI Agent skill package with `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox framing, install examples, and
workflow-gate pressure. The same lane maps `Pluviobyte/rnskill` to the bounded
documentation lane as a generic multi-skill `SKILL.md` collection.

`InternScience/Agents-A1` and `TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows. They inherit no `skill_route_discovery`
lane and expose no direct documentation, test, or code_patch lane before local
harness evaluation. The pass-1 lane records the rollback ref
`refs/blackhole/rollback/20260707T200110-skill-route-discovery-pass1`, records
that `docs/self-model.md` stayed unchanged because this run had a concrete
behavior path, and exports no raw source URLs, replay commands, upstream
bodies, provider launches, remote execution, promotion, restart, or activation
authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T200110`.

For source digest `github-growth-20260707T194110.112744Z`, pass 4 completes
the active reverse-flow/rnskill/Shepherd window through
`skill_route_discovery_current_digest_20260707T194110_pass4_completion_handoff`.
The handoff maps `lingbol088-spec/reverse-flow-skill` to the bounded local test
lane as Codex workflow-gate evidence and maps `Pluviobyte/rnskill` to the
bounded documentation lane as generic skill repository evidence. Both rows keep
documentation, config, test, and code_patch as the only local outputs before
activation; install, run, enable, provider, external harness, and runtime
wording remains diagnostic pressure only.

`shepherd-agents/shepherd` remains under
`p3-agent-harness-eval-shepherd`, while `InternScience/Agents-A1` and
`TianhangZhuzth/Fundamental-Ava` remain under
`p4-agent-harness-eval-comparative-agent-projects`. They inherit no
`skill_route_discovery` lane and expose no direct documentation, test, or
code_patch lane before bounded local agent-harness evaluation. The pass-4
handoff records the rollback artifact for this kernel run, records that
`docs/self-model.md` stayed unchanged because it already matches the
rollback-backed local validation preference, and exports no raw source URLs,
replay commands, target paths, upstream bodies, provider launches, memory or
profile writes, promotion, restart, remote execution, or activation authority.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T194110`.

For source digest `github-growth-20260707T190110.064980Z`, pass 3 now exposes
the active reverse-flow/rnskill/Shepherd window through
`skill_route_discovery_current_digest_20260707T190110_pass3_validation_lane`
and its activation-review packet. The lane carries forward the pass-2 mapping:
`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate test row,
and `Pluviobyte/rnskill` remains the generic skill collection documentation
row. The controller recomputes both as `local_validation_candidate` under
`focused-evidence-review`; requested install, run, enable, provider, external
harness, and runtime wording remains diagnostic pressure only.

`shepherd-agents/shepherd` and its PR #18 activity stay under
`p3_agent_harness_eval_shepherd` as `agent_harness_eval_required`.
`InternScience/Agents-A1` and `TianhangZhuzth/Fundamental-Ava` stay under
`p4_agent_harness_eval_comparative_agent_projects`. No adjacent general-agent
row receives a direct documentation, test, or code_patch lane before bounded
agent-harness evaluation. The pass-3 packet records the current rollback
artifact and exports no raw source URLs, replay commands, target paths,
upstream bodies, provider launches, memory/profile writes, remote execution,
restart, promotion, or activation authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T190110`.

For source digest `github-growth-20260707T190110.064980Z`, pass 2 exposes the
active reverse-flow/rnskill/Shepherd window through
`skill_route_discovery_current_digest_20260707T190110_pass2_validation_lane`.
The lane maps `lingbol088-spec/reverse-flow-skill` to the bounded local test
lane as Codex workflow-gate evidence, because the public repository presents a
`skills/reverse-flow` package shape, `SKILL.md` workflow framing, local
sandbox/CTF boundaries, and diagnostic script examples. Its install, run,
script, provider, external harness, and runtime wording remains diagnostic
pressure only.

`Pluviobyte/rnskill` remains a generic `SKILL.md` collection and maps to the
bounded documentation lane. Its marketplace, `npx`, manual install, enable,
plugin, and run examples are route evidence for documentation/config/test/code
patch follow-up only, not activation authority.

`shepherd-agents/shepherd` and the carried PR #18 activity remain
`agent_harness_eval_required` under `p3_agent_harness_eval_shepherd`; they are
harness-evaluation evidence for reversible traces, replay, and repository
maintenance activity, not a skill-route lane or runtime path. Agents-A1 and
Fundamental-Ava remain adjacent comparative agent-harness rows under
`p4_agent_harness_eval_comparative_agent_projects`. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T190110`.

For source digest `github-growth-20260707T180109.989440Z`, pass 3 exposes the
active reverse-flow/rnskill/Shepherd window through
`skill_route_discovery_current_digest_20260707T180109_pass3_validation_lane`.
The lane maps `lingbol088-spec/reverse-flow-skill` to the bounded local test
lane as a Codex workflow-gate skill route and maps `Pluviobyte/rnskill` to the
bounded documentation lane as a generic skill collection. Both rows accept only
documentation, config, test, or code_patch outputs before activation.

`shepherd-agents/shepherd` and its PR #35 activity remain
`agent_harness_eval_required` under
`p3_agent_harness_eval_shepherd_cluster`; the PR signal is harness-evaluation
evidence for reversible runtime maintenance, not a skill-route lane or runtime
activation path. Agents-A1 and Fundamental-Ava remain adjacent general-agent
rows under `p4_general_agent_project_eval_matrix`. The lane records the current
rollback artifact, keeps the self-model unchanged, and exports no raw source
URLs, replay commands, target paths, upstream bodies, provider launches,
profile or memory writes, remote execution, or external harness execution.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T180109`.

For source digest `github-growth-20260707T172109.646188Z`, pass 1 exposes the
active Shepherd/reverse-flow/rnskill window through
`current_run_pass1_activation_readiness`. The lane maps
`lingbol088-spec/reverse-flow-skill` to the bounded local test lane and
`Pluviobyte/rnskill` to the bounded documentation lane. Install, run, provider,
external harness, and remote-execution wording remains diagnostic pressure
only.

`shepherd-agents/shepherd` is held behind
`p1-shepherd-agent-harness-eval` as `agent_harness_eval_required`. Its reusable
lesson is the retained, reversible workflow shape: inspectable traces,
retained outputs, replay, rollback, and external-supervisor activation. That
lesson is represented as a pass-1 runner control plane with intake, midflight,
recovery, replay, and report stages; it does not activate Shepherd, install an
upstream skill, launch a provider, or grant runtime authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T172109`.

For source digest `github-growth-20260707T174109.873436Z`, pass 2 exposes the
active skill-route-discovery window through
`skill_route_discovery_current_digest_20260707T174109_pass2_validation_lane`.
`lingbol088-spec/reverse-flow-skill` remains a Codex workflow-gate row in the
bounded local test lane, while `Pluviobyte/rnskill` remains a generic
`SKILL.md` collection in the documentation lane. Both rows accept only
documentation, config, test, or code_patch outputs before activation.

`shepherd-agents/shepherd`, `InternScience/Agents-A1`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows. Shepherd's reversible runtime signal is
usable harness-evaluation evidence, not a direct runtime route; no adjacent
general-agent project receives a local implementation lane before bounded
harness evaluation. The lane records the rollback artifact for this run and
leaves the self-model unchanged because it already prefers rollback-backed
local validation over ornamental edits. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T174109`.

For source digest `github-growth-20260707T162109.466559Z`, pass 2 binds
the active reverse-flow/rnskill proposals to the existing pass-2 operator lane
and exposes `current_pass2_activation_recovery_workflow` inside the activation
checkpoint. `lingbol088-spec/reverse-flow-skill` remains the Codex workflow
gate skill-route row in the local test lane, while `Pluviobyte/rnskill`
remains a generic `SKILL.md` collection in the documentation lane. Both rows
accept only documentation, config, test, or code_patch outputs before
activation.

The recovery workflow makes the supervisor handoff explicit: confirm the
rollback point, recompute controller routes, replay bounded skill-route lanes,
hold adjacent agent projects for local harness evaluation, and keep external
activation disabled until validation and supervisor promotion complete.
`InternScience/Agents-A1` and `shepherd-agents/shepherd` remain
`agent_harness_eval_required` rows with no direct implementation lanes before
evaluation. The workflow exports hashes, item IDs, phase names, and booleans
only; raw upstream URLs, raw replay commands, provider launch, remote
execution, memory/profile writes, restart, push, and rollback execution remain
disabled. Replay with:
`python -m pytest tests/test_proposal_eval.py -q -k 20260707T162109`.

For source digest `github-growth-20260707T160109.409581Z`, pass 1 opens the
current skill-route-discovery window through
`skill_route_discovery_current_digest_20260707T160109_pass1_validation_lane`.
The lane maps `lingbol088-spec/reverse-flow-skill` to
`p1_skill_route_discovery_probe` in the local test lane and maps generic
skill collection evidence including `Pluviobyte/rnskill` to
`p2_skill_route_docs` in the documentation lane. Both rows accept only
documentation, config, test, or code_patch outputs after focused local
validation; install, enable, run, script execution, provider runtime, external
skill activation, external harness execution, memory write, and remote
execution wording stays diagnostic.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain queued under
`p3_agent_harness_eval_fixture` as `agent_harness_eval_required`. They inherit
no skill-route lane, expose no direct local lanes before harness evaluation,
and may only produce documentation, test, or code_patch follow-up after a
bounded local harness result exists. The pass-1 packet is operator-visible and
body-free: it exports item IDs, lane names, hashes, booleans, and local
contract fields only. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T160109`.

For source digest `github-growth-20260707T150109.515302Z`, pass 2 exposes
`skill_route_discovery_current_digest_20260707T150109_pass2_validation_lane`.
The lane compares the active reverse-flow and rnskill proposals before any
activation path: `lingbol088-spec/reverse-flow-skill` remains a Codex
workflow-gate candidate in the local test lane, and `Pluviobyte/rnskill`
remains a generic `SKILL.md` collection in the documentation lane. Both keep
documentation, config, test, and code_patch as the only accepted local outputs.
Install, enable, run, script execution, provider runtime, external harness,
memory write, and remote execution pressure is retained only as stripped
diagnostic evidence.

The same lane keeps `shepherd-agents/shepherd`,
`InternScience/Agents-A1`, and `TianhangZhuzth/Fundamental-Ava` in
`agent_harness_eval_required`. Shepherd's advisory memory-context signal is
not a memory or profile write route; it requires a local harness result before
documentation, test, or code_patch follow-up can be promoted. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T150109`.

For source digest `github-growth-20260707T154109.440320Z`, pass 4 completes
the same skill-route-discovery slice through
`skill_route_discovery_current_digest_20260707T154109_pass4_completion_handoff`.
The handoff makes the operator-visible final path explicit: the Codex workflow
proposal `p1-skill-route-discovery-codex-workflow` maps
`lingbol088-spec/reverse-flow-skill` to the bounded local test lane, while
`p2-generic-skill-workflow-discovery` keeps `Pluviobyte/rnskill` in the
documentation lane. Both rows accept only documentation, config, test, or
code_patch outputs before activation.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain `agent_harness_eval_required` rows under
`p3-agent-harness-eval-fixture`. They do not inherit `skill_route_discovery`,
have no direct local lanes before bounded harness evaluation, and may only
produce documentation, test, or code_patch follow-up after that evaluation
passes. The final handoff records the rollback ref and artifact for the current
kernel run, exports validation commands only as hashes, and leaves activation,
restart, promotion, provider launch, external harness execution, remote
execution, memory writes, and runtime action disabled for the supervisor.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T154109`.

For source digest `github-growth-20260707T152109.445461Z`, pass 3 deepens the
reusable `skill_route_discovery_repository_lane_probe` rather than adding an
activation path. Reverse-flow-style repositories must now expose a
body-free `workflow_gate_validation_contract` before a Codex workflow gate is
considered locally valid: the probe requires an activation-phrase marker, a
local sandbox or CTF boundary, staged workflow evidence, and diagnostic script
examples, while exporting none of the raw upstream body or activation phrase.
The contract selects the local test lane and keeps secondary workflow routing,
external skill activation, external harness execution, provider launch, and
remote execution denied until focused local validation passes.

The same fixture keeps `Pluviobyte/rnskill` as a generic skill workflow
documentation candidate and keeps `InternScience/Agents-A1`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` ignored by the
skill route probe with `agent_harness_eval_required` as the prerequisite lane.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T152109`.

For source digest `github-growth-20260707T140109.483291Z`, pass 3 exposes
`skill_route_discovery_current_digest_20260707T140109_pass3_runner_control_plane`.
The pass-3 runner control plane makes the current route workflow legible as
intake, midflight, recovery, replay, and report stages, with a body-free
workflow handoff and artifact manifest. `lingbol088-spec/reverse-flow-skill`
remains a Codex workflow-gate skill-route candidate in the local test lane, and
`Pluviobyte/rnskill` remains a generic skill-workflow candidate in bounded
local lanes only. `InternScience/Agents-A1` and `shepherd-agents/shepherd`
remain adjacent `agent_harness_eval_required` evidence, inherit no skill-route
lane, and expose no direct runtime, provider, remote execution, or external
harness route before local harness evaluation. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k 20260707T140109`.

For source digest `github-growth-20260707T130110.277132Z`, pass 4 completes
the current skill-route-discovery window through
`skill_route_discovery_current_digest_20260707T130110_pass4_completion_handoff`.
The handoff maps `lingbol088-spec/reverse-flow-skill` to the local test lane
as a Codex workflow-gate candidate and maps `Pluviobyte/rnskill` to the
documentation lane as a generic `SKILL.md` collection. Both remain bounded to
documentation, config, test, or code_patch; install, enable, run, script,
provider-runtime, external-harness, and remote-execution pressure is retained
only as stripped diagnostic evidence.

The same handoff keeps `InternScience/Agents-A1`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` behind
`agent_harness_eval_required`. They inherit no skill-route lane and expose no
direct implementation lane before local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T130110`.

Proposal interpretation for `skill_route_discovery` must accept only
documentation, config, test, or code_patch work. Accepted proposals cite only
selected digest `item_id` values in `evidence_refs`; repository URLs, truncated
items, and newly discovered external evidence are rejected or kept as
uncertainty, never as activation evidence.

For source digest `github-growth-20260707T121946.674633Z`, pass 2 exposes
`skill_route_discovery_current_digest_20260707T121946_pass2_validation_lane`.
The lane keeps `lingbol088-spec/reverse-flow-skill` in the local test lane
because its public package shape includes a Codex/AI Agent skill directory,
`SKILL.md`, local sandbox framing, scripts, and staged reverse-analysis
workflow language. Its install, run, script, runtime, provider, and external
harness wording remains diagnostic pressure only.

`Pluviobyte/rnskill` maps to the generic skill workflow documentation lane
because it is a multi-skill `SKILL.md`-compatible collection with `skills/`,
docs, tools, marketplace metadata, and manual install examples. The same pass
keeps a route-classification coverage row for rnskill metadata so unsupported
install/enable/run/provider/external-harness pressure cannot become a local
lane.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain `agent_harness_eval_required`. They inherit
no `skill_route_discovery` lane, expose no direct implementation lane before
local harness evaluation, and may only produce documentation, test, or
code_patch follow-up after a bounded harness result exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T121946`.

For source digest `github-growth-20260707T110834.493888Z`, pass 1 records a
proposal replay fixture for the active anchors
`p1_reverse_flow_skill_route_discovery`,
`p2_rnskill_generic_skill_route_discovery`, and
`p3_skill_route_discovery_docs`. The fixture maps
`trend:lingbol088-spec/reverse-flow-skill-1` and
`trend:Pluviobyte/rnskill-1` only through selected item IDs, rejects
`https://github.com/Pluviobyte/rnskill` as a proposal citation, and keeps
runtime action, upstream skill activation, external harness execution, provider
launch, and remote execution disabled. Replay with:
`python -m pytest tests/test_proposal_eval.py -q -k current_skill_route_discovery`.

For source digest `github-growth-20260707T094834.633335Z`, pass 1 exposes the
active window through `skill_route_discovery_current_pass1_focused_review_lane`.
The lane binds `p1-skill-route-discovery-codex-workflow` to the
`lingbol088-spec/reverse-flow-skill` Codex workflow-gate test route and binds
`p2-generic-skill-workflow-routing` to the `Pluviobyte/rnskill` generic skill
workflow documentation route. Both rows remain bounded to documentation,
config, test, or code_patch lanes with local validation required.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain under `p3-agent-harness-eval-lane` as
`agent_harness_eval_required` rows. They inherit no skill-route lane and expose
no direct implementation lane before bounded local harness evaluation. The
packet also records `p5-self-model-alignment-note` as unchanged because the
current self-model already prefers rollback-backed local validation over an
ornamental self-model edit. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T094834`.

For source digest `github-growth-20260707T104834.422978Z`, pass 4 completes
the current `skill-route-discovery` slice through
`skill_route_discovery_current_digest_20260707T104834_pass4_completion_handoff`.
The handoff is the operator-visible closure surface for this window:
`lingbol088-spec/reverse-flow-skill` maps to
`p1_reverse_flow_skill_route_discovery` in the bounded local test lane, and
`Pluviobyte/rnskill`/generic skill workflow evidence maps to
`p2_generic_skill_workflow_probe` in the documentation lane. Both rows retain
documentation, config, test, and code_patch as the only allowed local outputs;
install, enable, run, script execution, provider runtime, external harness, and
remote execution remain diagnostic pressure only.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` are grouped under `p3_agent_harness_eval_suite` as
`agent_harness_eval_required` rows. They inherit no skill-route lane, expose no
direct local lane before harness evaluation, and may only lead to
documentation, test, or code_patch follow-up after local agent-harness results
exist. The handoff records the rollback ref and rollback artifact for this run
and notes that `docs/self-model.md` was left unchanged because it already
states the run preference for rollback-backed local validation over ornamental
self-model edits. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T104834`.

For source digest `github-growth-20260707T092834.330063Z`, pass 4 completes
the active window through
`skill_route_discovery_current_digest_20260707T092834_pass4_completion_handoff`.
The handoff maps `lingbol088-spec/reverse-flow-skill` to the Codex workflow
gate test lane and maps generic skill workflow evidence, including
`Pluviobyte/rnskill`, to the documentation lane while preserving config, test,
and code_patch as bounded local candidates only. General-agent projects such as
`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain `agent_harness_eval_required`; they inherit
no skill-route lane and expose no direct implementation lanes before local
harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T092834`.

For source digest `github-growth-20260707T090834.684862Z`, pass 3 exposes the
active window through
`skill_route_discovery_current_digest_20260707T090834_pass3_reverse_flow_probe`.
The lane turns reverse-flow-style skill evidence into a local test probe, keeps
generic skill workflow evidence grouped under `skill_route_discovery`, and binds
documentation and config follow-up to local validation before activation.

The accepted outputs remain documentation, config, test, and code_patch only.
Install, enable, run, script, provider-runtime, external-harness, and
remote-execution wording is diagnostic pressure, not an activation lane.
Adjacent general-agent projects remain `agent_harness_eval_required`; they do
not inherit skill-route lanes and expose no direct follow-up lanes until local
harness evaluation passes. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T090834`.

For source digest `github-growth-20260707T084834.433829Z`, pass 2 exposes the
active window through
`skill_route_discovery_current_digest_20260707T084834_pass2_validation_lane`.
The lane binds the current proposal IDs to bounded local validation:
`p1-skill-route-discovery-reverse-flow` maps
`lingbol088-spec/reverse-flow-skill` to the Codex workflow-gate test lane,
while `p2-generic-skill-workflow-discovery-rnskill` maps
`Pluviobyte/rnskill` to the generic skill workflow documentation lane. Both
rows keep documentation, config, test, and code_patch as the only allowed local
outputs, and install, enable, run, script, provider-runtime,
external-harness, and remote-execution signals remain diagnostic pressure.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain under
`p3-agent-harness-eval-for-general-agent-trends` as adjacent
`agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, expose no direct lanes before local harness
evaluation, and may only produce documentation, test, or code_patch follow-up
after that gate. The lane records the rollback artifact for this run and keeps
runtime action, external skill or agent activation, external harness execution,
provider launch, remote execution, raw source URLs, evidence URLs, target paths,
upstream bodies, and replay commands out of controller output. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T084834`.

For source digest `github-growth-20260707T082834.484151Z`, pass 1 exposes the
active window through `skill_route_discovery_current_run_pass1_activation_readiness`.
The readiness panel maps `lingbol088-spec/reverse-flow-skill` to the Codex
workflow-gate test lane and `Pluviobyte/rnskill` to the generic skill workflow
documentation lane. Candidate-name scoping is explicit so the generic rnskill
row does not absorb reverse-flow merely because both share skill workflow
language.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows.
They do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, or remote
execution before bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T082834`.

For source digest `github-growth-20260707T074834.250116Z`, pass 4 completes
the active `skill-route-discovery` slice through
`skill_route_discovery_current_digest_20260707T074834_pass4_local_route_discovery`.
The packet turns the current evidence into a supervisor-visible replay surface:
`lingbol088-spec/reverse-flow-skill` maps to the Codex workflow-gate test lane
with expected entrypoint markers such as `skills/reverse-flow/SKILL.md`, an
activation phrase, local sandbox or CTF boundary, and script examples treated
as diagnostic pressure only. `Pluviobyte/rnskill` maps to the generic skill
workflow documentation lane with expected markers for `skills/*/SKILL.md`,
manual project skill install shape, plugin or tooling metadata, and per-skill
invocation constraints before activation.

Adjacent general-agent projects, including Shepherd-style reversible runtime
evidence, are queued for `agent_harness_eval_required` rather than direct local
implementation. Their required probe fields are runnable entrypoint, dependency
isolation, permission boundary, reproducible task, measurable behavior, and
rollback artifact. The packet exports item IDs, lane names, hashes, booleans,
and body-free summaries only; raw source URLs, replay commands, target paths,
upstream bodies, runtime action, external skill activation, external harness
execution, provider launch, and remote execution remain denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T074834`.

For source digest `github-growth-20260707T072834.240470Z`, pass 3 exposes the
active proposal queue through
`skill_route_discovery_current_digest_20260707T072834_pass3_proposal_replay_plan`.
The plan binds `p1_skill_route_discovery_codex_workflow_gate` to the
reverse-flow Codex workflow-gate test lane and
`p2_generic_skill_workflow_discovery` to the rnskill generic skill workflow
documentation lane. Both rows keep documentation, config, test, and code_patch
as the only bounded local lanes and record `local_validation_required` before
activation.

The same plan routes `InternScience/Agents-A1`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` through
`p3_agent_harness_eval_queue` with no direct implementation lanes before local
agent-harness evaluation. `p4_no_external_url_expansion_guard` records that the
operator-visible packet exports hashes, item IDs, lane names, booleans, and
body-free summaries only; raw source URLs, raw evidence URLs, upstream bodies,
runtime action, external skill activation, external harness execution, provider
launch, and remote execution remain denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T072834`.

For source digest `github-growth-20260707T062834.999092Z`, pass 4 completes the
current `skill-route-discovery` slice through
`skill_route_discovery_current_pass4_completion_handoff`. The handoff binds
`lingbol088-spec/reverse-flow-skill` to the local test lane as a Codex workflow
gate skill-route candidate and `Pluviobyte/rnskill` to the documentation lane
as a generic skill workflow candidate. Both rows keep documentation, config,
test, and code_patch as the only bounded local lanes, require local validation,
and treat install, run, script, provider-runtime, external-harness, and remote
execution wording as diagnostic pressure only.

The same handoff queues `InternScience/Agents-A1`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` through
`general_agent_recovery_workflow` before any general-agent follow-up. That
workflow requires a local `agent_harness_eval_required` fixture with runnable
scenario, expected output, pass/fail signal, rollback artifact, and non-secret
configuration fields. Until that local evaluation exists, direct code/config
proposal, runtime action, external harness execution, provider launch, and
remote execution remain blocked. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T062834`.

For source digest `github-growth-20260707T060834.141592Z`, pass 3 now exposes
`skill_route_discovery_current_digest_20260707T060834_pass3_lane_acceptance`
through `current_digest_pass3_activation_review_lane`. The lane replays the
current reverse-flow plus rnskill split as an operator-visible acceptance
packet before pass 4: `lingbol088-spec/reverse-flow-skill` keeps the Codex
workflow-gate test lane, `Pluviobyte/rnskill` keeps the generic skill workflow
documentation lane, and both remain limited to documentation, config, test, or
code_patch outputs after focused local validation.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` stay in `agent_harness_eval_required`. They do not
inherit `skill_route_discovery`, select no implementation lane before harness
evaluation, and may only produce documentation, test, or code_patch follow-up
after a local harness result exists. The packet exports item IDs, route
profiles, lane names, hashes, and booleans only; raw source URLs, raw evidence
URLs, raw replay commands, upstream bodies, runtime action, external skill
activation, external agent activation, external harness execution, provider
launch, and remote execution remain denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T060834`.

For source digest `github-growth-20260707T052834.687686Z`, pass 1 now exposes
`skill_route_discovery_current_pass1_focused_review_lane` inside the validation
route packet. The lane binds the active anchors
`p1-skill-route-discovery-reverse-flow`,
`p2-generic-skill-workflow-discovery`, and
`p3-agent-harness-eval-fixture` to bounded local validation before any
activation surface exists. It also records the follow-up anchors
`p4-route-policy-doc-note` and `p5-route-metadata-consistency-check` as
operator-visible route policy and metadata checks.

`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate row and
selects the local test lane. `Pluviobyte/rnskill` remains the generic skill
workflow row and selects the documentation lane. Both keep config, test, or
code_patch as bounded queued lanes with local validation required; install,
run, script execution, provider runtime, external harness execution, and remote
execution are diagnostic pressure only.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain `agent_harness_eval_required` rows for the
agent-harness fixture proposal. They do not inherit `skill_route_discovery`,
have no direct implementation lane before local harness evaluation, and may
only produce documentation, test, or code_patch follow-up after that gate.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T052834`.

For source digest `github-growth-20260707T050834.384415Z`, pass 4 closes the
current skill-route-discovery window through
`skill_route_discovery_current_pass4_completion_handoff` on the validation
route packet. The handoff records a rollback ref, a rollback artifact path,
body-free source hashes, validation command hashes, and a supervisor sequence:
confirm rollback, review bounded rows, run focused local validation, then hand
off without kernel restart or external activation.

`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate row in the
local test lane. Its `skills/reverse-flow/SKILL.md`, references, scripts, local
sandbox, CTF or crackme framing, install examples, and run examples are route
evidence only. `Pluviobyte/rnskill` remains the generic skill workflow row and
selects the documentation lane while retaining config, test, and code_patch as
queued bounded lanes. Install, run, script execution, provider runtime,
external harness execution, and remote execution pressure stays diagnostic.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain `agent_harness_eval_required` rows. They do
not inherit `skill_route_discovery`, have no direct implementation lane before
local harness evaluation, and may only produce documentation, test, or
code_patch follow-up after that gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T050834`.

For source digest `github-growth-20260707T044834.430159Z`, pass 3 adds an
operator-visible `current_pass3_proposal_lane` to
`skill_route_discovery_validation_route_packet`. The lane binds the active
controller proposals `p1_skill_route_discovery_probe`,
`p2_skill_route_discovery_docs`, and `p3_skill_routing_config_fixture` to
bounded local outputs before pass-4 activation review.

`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate skill
route row and selects the local test lane. `Pluviobyte/rnskill` remains the
generic skill workflow row and supports documentation and config proposal
bindings. Install, run, script execution, provider runtime, external harness,
and remote-execution pressure is preserved only as stripped diagnostic pressure.
Adjacent general-agent projects remain `agent_harness_eval_required` and do
not inherit `skill_route_discovery`. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T044834`.

For source digest `github-growth-20260707T042834.998931Z`, pass 2 advances the
active skill-route-discovery window through
`skill_route_discovery_validation_route_packet`. `lingbol088-spec/reverse-flow-skill`
is retained as a Codex workflow-gate skill route candidate. `Pluviobyte/rnskill`
is retained as a generic skill workflow candidate because the bounded evidence
contains agent, skill, skills, workflow, skills directory, plugin metadata, and
SKILL.md-oriented signals. Install, run, script, provider, runtime,
external-harness, and remote-execution pressure remains diagnostic only.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows.
They inherit no `skill_route_discovery` lane, expose no direct implementation
lane before local harness evaluation, and may only produce documentation, test,
or code_patch follow-up after that gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T042834`.

For source digest `github-growth-20260707T040834.499584Z`, pass 1 keeps the
active route-discovery window replayable through
`skill_route_discovery_validation_route_packet`.
`lingbol088-spec/reverse-flow-skill` remains a Codex workflow-gate skill route
candidate, and `Pluviobyte/rnskill` is treated as a generic skill workflow
candidate when the frozen digest carries agent, skill, skills, workflow, and
skill-package evidence. Both rows validate before adjacent general-agent rows
and are limited to documentation, config, test, or code_patch lanes.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain `agent_harness_eval_required`; they inherit
no skill-route lane and expose no direct implementation lane before local
harness evaluation. The replay packet exports item ids, lane names, route
profiles, and hashes only. It denies raw source URL export, evidence URL
expansion, replay-command export, runtime action, external skill activation,
external harness execution, provider launch, and remote execution. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T040834`.

For source digest `github-growth-20260707T034835.249830Z`, pass 4 completes
the current skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The handoff maps
`lingbol088-spec/reverse-flow-skill` to
`p1-skill-route-discovery-reverse-flow` because it carries explicit Codex/AI
Agent skill workflow markers: `skills/reverse-flow/SKILL.md`, references,
scripts, local sandbox framing, and install/run language. Those install, run,
script, provider, external-harness, and runtime signals remain diagnostic
pressure only; the selected local outputs are documentation and test, and the
allowed skill-route lanes remain documentation, config, test, and code_patch.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`,
`shepherd-agents/shepherd`, and the workflow-usecase item remain adjacent
`agent_harness_eval_required` rows, even when their `route_hints` are empty.
They do not inherit `skill_route_discovery`, expose no direct documentation,
test, code_patch, runtime, provider, external-harness, or remote-execution lane
before local harness evaluation, and may only produce documentation, test, or
code_patch follow-up after that bounded eval passes. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T034835`.

For source digest `github-growth-20260707T005555.490893Z`, pass 4 completes
the current skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The handoff keeps
`lingbol088-spec/reverse-flow-skill` under
`p1-skill-route-discovery-reverse-flow` in the local test lane because the
public repository exposes a Codex/AI Agent workflow skill package with
`skills/reverse-flow/SKILL.md`, references, scripts, local sandbox defaults,
CTF/crackme framing, install examples, run examples, and staged workflow
language. Those install, run, script, provider, runtime, external-harness, and
remote-execution signals are diagnostic pressure only.

`InternScience/Agents-A1`, `shepherd-agents/shepherd`, and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` remain under
`p2-general-agent-harness-eval` until a local harness evaluation exists. They
do not inherit `skill_route_discovery`, expose no direct implementation lane
before evaluation, and may only lead to documentation, test, or code_patch
follow-up after local harness evidence. The companion documentation row
`p3-route-classification-docs` records that route distinction. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T005555`.

For source digest `github-growth-20260707T005555.490893Z`, pass 3 exposes the
active window through `current_digest_pass3_replay_packet`. The packet maps
`lingbol088-spec/reverse-flow-skill` to
`p1-skill-route-discovery-reverse-flow` because the public repository exposes a
Codex/AI Agent skill workflow shape under `skills/reverse-flow/SKILL.md`, with
references, scripts, local sandbox defaults, CTF/crackme framing, install/run
examples, and staged workflow language. Those install, run, script, provider,
runtime, external-harness, and remote-execution signals remain downgraded route
pressure only; the selected local lane is test and the allowed lanes remain
documentation, config, test, and code_patch.

`InternScience/Agents-A1` and `shepherd-agents/shepherd` map to
`p2-general-agent-harness-eval` as general-agent project evidence. They do not
inherit `skill_route_discovery`, expose no direct implementation lane before
local harness evaluation, and may only produce documentation, test, or
code_patch follow-up after that gate. `Evolink-AI/Awesome-Blender-Seedance-
Workflow-Usecases` maps separately to `p3-workflow-usecase-evaluation` because
workflow/usecase catalog evidence is not an executable skill route without a
skill package marker such as `SKILL.md`.

The replay packet is body-free and record-only: it exports proposal IDs,
selected item IDs, lane names, source hashes, and replay command hashes while
denying raw source URL export, raw replay command export, upstream body export,
runtime action, external skill or agent activation, external harness execution,
provider launch, and remote execution. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T005555`.

For source digest `github-growth-20260707T001555.490520Z`, pass 1 carries two
connected lessons. `lingbol088-spec/reverse-flow-skill` remains a Codex/AI
Agent skill workflow candidate: the public repository exposes
`skills/reverse-flow/SKILL.md`, references, scripts, local sandbox and CTF or
crackme framing, install examples, and run examples. Those signals map only to
documentation, config, test, or code_patch lanes through
`skill_route_discovery`; install, run, provider, runtime, external-harness, and
remote-execution pressure is diagnostic only.

The companion `shepherd-agents/shepherd` issue reports a CLI-backed provider
lane failing with `rc=1`, no model iterations, empty usage, and an empty result
envelope while the doctor command was green. The local preflight expectation is
now explicit: a CLI provider that returns a non-zero exit with an empty result
envelope is classified as `provider_cli_empty_envelope_refused` before any
agent lane runs. The diagnostic keeps only bounded metadata such as exit code,
empty-envelope/refusal booleans, recovery hint code, and launch denial; raw
stderr, provider bodies, envelope bodies, credentials, upstream bodies, and raw
source evidence stay unexported. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k cli_empty_envelope_refusal`.

For source digest `github-growth-20260706T235555.501156Z`, pass 4 completes
the skill-route-discovery slice through
`current_digest_pass4_completion_handoff` using the current proposal IDs.
`lingbol088-spec/reverse-flow-skill` maps to
`p1_skill_route_discovery_reverse_flow_skill` because the public repository is
a Codex/AI Agent skill workflow package with `skills/reverse-flow`, `SKILL.md`,
references, scripts, local sandbox and CTF/crackme framing, and install/run
examples. Those install, run, script, provider, runtime, and external-harness
signals remain diagnostic pressure only; the selected local lane is test, and
documentation, config, test, and code_patch are the only allowed lanes.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` map to
`p2_agent_harness_eval_for_general_agent_trends`. They remain
`agent_harness_eval_required`, inherit no `skill_route_discovery` route, expose
no direct local lanes before evaluation, and may produce only documentation,
test, or code_patch follow-up after local agent-harness validation. The handoff
is record-only and body-free: it exports proposal IDs, selected item IDs, lane
names, source hashes, and replay command hashes while denying raw URLs, raw
commands, upstream bodies, runtime action, external skill or agent activation,
external harness execution, provider launch, and remote execution. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T235555`.

For source digest `github-growth-20260706T233555.493310Z`, pass 3 deepens the
bounded repository lane probe for `lingbol088-spec/reverse-flow-skill`. The
public evidence shows a `skills/reverse-flow/SKILL.md` package for AI Agent and
Codex workflows, with references, scripts, local sandbox/CTF/crackme defaults,
install examples, and run examples. The local mapping remains classification
only: reverse-flow selects the test lane after focused local validation, while
documentation, config, test, and code_patch remain the only accepted outputs.

The probe now exposes an operator-visible route boundary checklist and next
action. Unsupported install, run, execute, provider-runtime, runtime-execution,
external-harness, and remote-execution pressure is counted as stripped
diagnostic pressure, not a lane. Repositories that mention Codex, workflow, or
developer skill without a skill package marker are forced to
`agent_harness_eval_required` and do not inherit `skill_route_discovery`.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k repository_lane_probe`.

For source digest `github-growth-20260706T225555.484632Z`, pass 1 advances the
active skill-route-discovery slice by adding `benchmark_meta_agent_probe_lane`
inside `agent_harness_eval_lane`. `shepherd-agents/shepherd` and pull request
30 are treated as meta-agent and benchmark-style harness evidence: reversible
traces, replay, supervision, retained outputs, and benchmark evaluation claims
become a local-only fixture probe with declared benchmark tasks, evaluation
dimensions, expected measurable outcome, and explicit side-effect denial.

The lane is not a runtime integration path. It denies network access,
credential access, provider launch, external harness execution, remote
execution, unreviewed workspace writes, raw source URL export, and upstream body
export. Existing general-agent rows that mention benchmark or evaluation but
lack probe detail remain incomplete inside this lane until local fixture fields
are supplied; they do not change direct implementation eligibility. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k benchmark_meta_agent_probe`.

For source digest `github-growth-20260706T223555.499005Z`, pass 4 completes
the current route-discovery slice with `current_digest_pass4_completion_handoff`.
`lingbol088-spec/reverse-flow-skill` maps to
`p2-skill-route-discovery-for-reverse-flow` because the evidence has an
explicit Codex/AI Agent skill workflow shape: `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox defaults, CTF/crackme framing,
and install or run wording. That wording remains diagnostic pressure only; the
selected local lane is test and the allowed lanes remain documentation, config,
test, and code_patch.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` map to
`p1-agent-harness-eval-matrix` as general-agent project evidence. They do not
inherit `skill_route_discovery`, expose no direct local lanes before evaluation,
and may produce only documentation, test, or code_patch follow-up after a local
agent-harness result exists. The operator packet is body-free and record-only:
it exports proposal IDs, selected item IDs, lane names, source hashes, and
replay command hashes while denying raw source URLs, replay commands, upstream
bodies, runtime action, external skill or agent activation, external harness
execution, provider launch, and remote execution. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T223555`.

For source digest `github-growth-20260706T221555.480207Z`, pass 3 exposes
`current_pass3_validation_route_packet` inside the existing replay lane.
`lingbol088-spec/reverse-flow-skill` is the only skill-route row because the
evidence shows a Codex/AI Agent package under `skills/reverse-flow`,
`SKILL.md`, references, scripts, and local sandbox or CTF framing. It remains a
bounded local validation candidate in the test lane, with documentation,
config, test, and code_patch as the only allowed local lanes.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` are
general-agent project rows for this pass. Even when their summaries mention
agents, evaluation, workflow, replay, rollback, or runtime substrates, negated
skill-package evidence such as no selected skill package, no `SKILL.md`
evidence, or no explicit skill workflow route signal keeps them behind
`agent_harness_eval_required`. They inherit no `skill_route_discovery` route,
have no direct implementation lanes before local harness evaluation, and may
only produce documentation, test, or code_patch follow-up after that bounded
harness result exists.

The packet is item-id-only: each row's `evidence_refs` contains only its
selected digest `item_id`, never repository URLs or added external evidence.
Replay commands are exported only as hashes, and runtime action, upstream skill
activation, upstream agent activation, external harness execution, provider
launch, remote execution, raw source URL export, raw evidence URL export, and
upstream body export remain disabled. Replay with:
`python -m pytest tests/test_proposal_eval.py -q -k current_pass3_validation_route_packet`.

For source digest `github-growth-20260706T213555.505315Z`, pass 1 makes the
current reverse-flow plus general-agent split replayable under
`current_digest_pass1_validation_lane`. `lingbol088-spec/reverse-flow-skill`
enters `p1-skill-route-discovery-reverse-flow` because the evidence carries
Codex, AI Agent, `skills/reverse-flow`, `SKILL.md`, local sandbox, CTF/crackme,
script, reference, and staged workflow signals. Its accepted local lanes remain
bounded to documentation, config, test, or code_patch, and install/run/runtime
pressure is diagnostic only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` enter `p2-agent-harness-eval-fixtures` as
general-agent projects with empty route hints. They do not inherit
`skill_route_discovery`, select no direct implementation lane before local
harness evaluation, and may only produce documentation, test, or code_patch
follow-up after a bounded harness result defines the task, expected measurable
outcome, rollback expectation, and controller-owned approval gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T213555`.

For source digest `github-growth-20260706T211555.777190Z`, pass 4 completes
the current skill-route-discovery slice by adding a local
`workflow_orchestration_eval_lane` inside `agent_harness_eval_lane`.
`shepherd-agents/shepherd` is used as general-agent workflow evidence only: its
public shape suggests reversible traces, fork, replay, revert, sandboxing,
supervision, retained outputs, and validation, but those claims now become
body-free local pass/fail criteria rather than runtime adoption.

The lane also accepts the carried `lingbol088-spec/reverse-flow-skill` route
evidence as workflow-language pressure without activating the upstream skill.
Each row requires complete project probe fields, records expected controller
recomputation inputs, and denies network access, credential access, provider
launch, external harness execution, remote execution, and unreviewed workspace
writes. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or local_harness_eval_runs"`.

For source digest `github-growth-20260706T203555.443958Z`, pass 2 adds an
operator-visible `agent_harness_eval_queue` inside
`current_digest_pass2_local_validation_lane`. The reverse-flow-skill evidence
stays in `p1_skill_route_discovery_reverse_flow` as a bounded local test lane
because it presents a Codex/AI Agent skill workflow shape; install, run,
script, provider, runtime, external-harness, external skill activation, and
remote execution pressure remains diagnostic only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` now become fixture-ready rows under
`p2_agent_harness_eval_queue`. Each row declares a scenario class, required
fixture fields, expected measurable outcome, rollback expectation, controller
approval gate, validation requirement propagation into `agent_harness_eval_lane`,
and no direct implementation lane before local harness evidence exists. The
queue exports item IDs, names, source hashes, route metadata, and validation
requirements only; raw source URLs, upstream bodies, replay commands, provider
launch, external harness execution, external agent activation, and remote
execution remain disabled. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T203555`.

For source digest `github-growth-20260706T201555.949510Z`, pass 1 exposes an
operator-visible `agent_harness_eval_intake_checklist` inside
`current_digest_pass1_validation_lane`. The reverse-flow-skill evidence maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane because it shows
a Codex/AI Agent workflow skill shape under `skills/reverse-flow`, staged local
analysis workflow language, scripts, references, local sandbox/CTF framing, and
install/run pressure that remains diagnostic only. The accepted local lanes are
still only documentation, config, test, or code_patch.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` are queued under
`p2_agent_harness_eval_queue` as general-agent projects with empty
`route_hints`. They remain proposal-only until a local harness task, expected
measurable outcome, rollback expectation, and controller-owned approval gate are
defined. They do not inherit `skill_route_discovery`, select no implementation
lane before harness eval, and cannot open runtime, provider, external harness,
or remote-execution paths. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T201555`.

For source digest `github-growth-20260706T183555.452657Z`, pass 4 completes
the current skill-route-discovery slice through
`current_digest_pass4_completion_handoff`. The reverse-flow skill item maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane and
`p3-route-classification-regression-doc` in the documentation lane. Both rows
must preserve `skill_route_discovery_first`, cite selected item IDs, and remain
bounded to documentation, config, test, or code_patch. Install, run, script,
provider, runtime, external harness, external skill activation, and remote
execution pressure stays diagnostic only.

`p2-agent-harness-eval-general-projects` covers the adjacent general-agent
project items in the same window. Those rows use
`agent_harness_eval_required`, inherit no `skill_route_discovery` lane, expose
no direct implementation lane before a local harness result, and may only
produce documentation, test, or code_patch follow-up after that gate. The
handoff exports proposal IDs, selected evidence item IDs, lane names, source
hashes, and replay command hashes only; raw source URLs, raw replay commands,
upstream bodies, provider launch, remote execution, and runtime action remain
disabled. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T183555`.

For source digest `github-growth-20260706T181555.593867Z`, pass 3 exposes
`current_digest_pass3_replay_packet` as the operator-visible replay surface for
the active reverse-flow plus general-agent window. The packet turns
`lingbol088-spec/reverse-flow-skill` into two bounded proposal rows:
`p1-skill-route-discovery-reverse-flow` in the local test lane and
`p3-document-routing-policy-boundaries` in the documentation lane. Both rows
preserve `skill_route_discovery_first`, require focused local validation, and
allow only documentation, config, test, or code_patch lanes. Install, run,
script execution, provider runtime, external harness, external skill
activation, and remote execution wording remains downgraded route pressure.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
`p2-agent-harness-eval-general-trends` rows with
`agent_harness_eval_required`. They inherit no skill-route lane, expose no
direct implementation lane before local harness evaluation, and may only
produce documentation, test, or code_patch follow-up after that gate. The
packet exports proposal IDs, selected evidence item IDs, lane names, source
hashes, and replay command hashes only; raw source URLs, raw replay commands,
upstream bodies, provider launch, remote execution, and runtime action remain
disabled. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T181555`.

For source digest `github-growth-20260706T173555.511473Z`, pass 1 reopens the
slice with a documentation-first route split. `lingbol088-spec/reverse-flow-skill`
enters `p2-skill-route-discovery-reverse-flow` because the approved evidence
shows a Codex/AI Agent skill package shape under `skills/reverse-flow`, staged
local reverse-analysis workflow language, local sandbox/CTF/crackme framing,
scripts, references, and install/run examples. That evidence maps only to
documentation, config, test, or code_patch lanes after focused local
validation. Install, run, script execution, vulnerability-analysis, runtime,
provider, external-harness, external skill activation, and remote-execution
pressure remains diagnostic only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` stay in
`p1-agent-harness-eval-general-projects` as `agent_harness_eval_required`
rows. They do not inherit `skill_route_discovery` and expose no direct
documentation, test, code_patch, runtime, runner, scheduling, memory,
tool-routing, provider, external-harness, or remote-execution lane before a
local harness result exists. `p3-agent-harness-routing-doc` records that
decision rule for general-agent trend ingestion. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T173555`.

For source digest `github-growth-20260706T175555.480042Z`, pass 2 makes the
active split replayable as a route-priority validation packet.
`lingbol088-spec/reverse-flow-skill` is the priority-0 skill workflow row
because the public evidence exposes a `skills/reverse-flow` package, `SKILL.md`,
references, scripts, local sandbox defaults, CTF/crackme framing, and Codex
workflow language. It selects the local test lane while documentation, config,
and code_patch remain queued bounded lanes. Install, run, script execution,
provider, runtime, external-harness, external skill activation, and remote
execution pressure remains diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` are priority-10
general-agent project rows. They keep `agent_harness_eval_required`, inherit no
`skill_route_discovery` route, expose no direct implementation lane before
local harness evaluation, and may only produce documentation, test, or
code_patch follow-up after that gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T175555`.

For source digest `github-growth-20260706T171555.486656Z`, pass 4 closes the
current capability slice with an operator-visible
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
enters through `skill_route_discovery` first because the evidence is a
reverse-flow skill workflow shape; unsupported install, run, script, provider,
runtime, and external-harness pressure is downgraded to diagnostics. The allowed
local lanes remain only documentation, config, test, and code_patch.

The same window keeps `InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` as
`agent_harness_eval_required` rows. They do not inherit `skill_route_discovery`
and cannot produce direct documentation, config, test, code_patch, runtime,
provider, or external-harness changes before local agent-harness evaluation.
Replay with: `python -m pytest tests/test_skill_routing.py -q -k 20260706T171555`.

For source digest `github-growth-20260706T165555.533885Z`, pass 3 adds a
ready follow-through surface for the current mixed evidence window.
`lingbol088-spec/reverse-flow-skill` remains a skill/workflow candidate because
the public repository exposes a Codex/AI Agent skill package shape, `SKILL.md`,
workflow scripts, and local sandbox or CTF framing. That evidence may map only
to documentation, config, test, or code_patch lanes through
`skill_route_discovery`; install, run, upstream execution, provider launch,
external harness use, and remote execution remain diagnostic pressure.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent project evidence. The `agent_harness_eval_lane` output now emits
`general_agent_project_route_plan`, an operator-visible route plan that
classifies these rows as `general_agent_project`, selects
`agent_harness_eval_required` before behavior adoption, exposes no direct lanes
before evaluation, and allows only documentation, test, or code_patch after a
probe-complete local harness result. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or current_window_general_agent_projects"`.

For source digest `github-growth-20260706T163555.630406Z`, pass 2 exposes the
active mixed-evidence window through `skill_route_discovery_validation_route_packet`.
`lingbol088-spec/reverse-flow-skill` enters first as the explicit
`skill_route_discovery` row because the public repository shape shows a Codex
skill package, `SKILL.md`, references, scripts, local sandbox and CTF/crackme
framing, install examples, and run examples. The route packet maps that signal
only to documentation, config, test, or code_patch lanes, keeps the selected
evidence reference as the item ID, and treats install, run, script execution,
provider, runtime, external harness, external skill activation, and remote
execution wording as diagnostic pressure.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent project rows. They are queued behind
`agent_harness_eval_required`, inherit no `skill_route_discovery` route, and
have no direct implementation lane before a local harness result exists. Replay
with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T163555`.

For source digest `github-growth-20260706T145556.011572Z`, pass 1 reopens the
active skill-route-discovery window with a bounded local validation lane.
`lingbol088-spec/reverse-flow-skill` remains the skill/workflow row because the
public repository exposes a `skills/reverse-flow` package shape, `SKILL.md`,
references, scripts, local sandbox and CTF/crackme framing, install examples,
and run examples. Those signals may select only documentation, config, test, or
code_patch lanes after focused local validation; install, run, script
execution, runtime, provider, external harness, external skill activation, and
remote execution pressure stays diagnostic.

`shepherd-agents/shepherd`, `InternScience/Agents-A1`,
`QwenLM/Qwen-AgentWorld`, and `TianhangZhuzth/Fundamental-Ava` remain adjacent
general-agent evidence. They enter `agent_harness_eval_required`, inherit no
`skill_route_discovery` lane, and expose no direct implementation lane before a
bounded local harness result exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T145556`.

For source digest `github-growth-20260706T143556.012746Z`, pass 4 completes
the active skill-route-discovery window through
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
is classified as a Codex/AI Agent skill workflow because the public repository
exposes a `skills/reverse-flow` package shape, `SKILL.md`, references, scripts,
local sandbox and CTF/crackme framing, install examples, and run examples.
Those signals may close only through bounded local lanes: documentation,
config, test, or code_patch, with focused validation required. Install, run,
script execution, runtime, provider, external harness, external skill
activation, and remote execution pressure remains diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent project evidence under
`p2-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery`, expose no direct local implementation lane before
local harness evaluation, and after that gate may only produce documentation,
test, or code_patch follow-up. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T143556`.

For source digest `github-growth-20260706T141555.983852Z`, pass 3 keeps
`lingbol088-spec/reverse-flow-skill` in the bounded skill-route lane because
the public repository exposes a `skills/reverse-flow` skill package shape,
local sandbox defaults, workflow scripts, and explicit install/run pressure.
That pressure remains route evidence only: no upstream skill code is installed,
run, activated, or used as controller behavior.

The same mixed window routes `InternScience/Agents-A1`,
`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` through `agent_harness_eval_required`. The
`route_family_agent_harness_intake` surface now turns those adjacent
general-agent rows into a local harness intake queue before activation. It
records the required project-shape probe fields for `agent_harness_eval_lane`,
hashes source URLs, keeps direct implementation lanes empty before evaluation,
and allows only documentation, test, or code_patch after a local harness result.
Runtime action, upstream execution, provider launch, external harness
execution, remote execution, raw source URLs, and upstream bodies remain
disabled. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_current_digest_20260706T141555_pass3_agent_harness_intake`.

For source digest `github-growth-20260706T135555.942816Z`, pass 2 keeps
`lingbol088-spec/reverse-flow-skill` in the bounded skill-route lane and routes
the current `InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` project
signals through `agent_harness_eval_required`. The pass also exposes
`provider_config_preflight_redaction_review` for the Shepherd provider CLI
empty-envelope issue. That review is body-free and review-only: it may record
that empty-envelope diagnostics are useful, but it must not export command
bodies, tokens, private payloads, provider values, upstream bodies, raw source
URLs, runtime execution, provider launch, or external harness execution.

Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T135555`.

For source digest `github-growth-20260706T133555.891986Z`, pass 1 keeps
`lingbol088-spec/reverse-flow-skill` in the bounded skill-route lane and
routes `InternScience/Agents-A1` plus `shepherd-agents/shepherd` activity
through `agent_harness_eval_lane`. The harness lane now exposes
`activity_intake_panel`, a body-free operator surface for repository trend,
push, issue-comment, opened-PR, and merged-PR shapes. Shepherd's controller
extraction and strict typecheck PR signals are treated as local harness
evidence only: before behavior adoption they select
`agent_harness_eval_required`, and after that gate they may produce only
documentation, test, or code_patch follow-up. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`.

For source digest `github-growth-20260706T131555.999132Z`, pass 4 completes
the active route-discovery slice through
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
is the skill/workflow row because the public repository exposes a
`skills/reverse-flow` package, `SKILL.md`, references, scripts, local sandbox
defaults, install examples, and run examples. Those signals may select only the
bounded local lanes documentation, config, test, or code_patch after focused
validation; install, run, script execution, runtime, provider, external
harness, external skill activation, and remote execution pressure remains
diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent evidence under `p2-agent-harness-eval-trending-projects`. They
do not inherit `skill_route_discovery`, have no direct implementation lane
before local harness evaluation, and after that gate may only produce
documentation, test, or code_patch follow-up. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T131555`.

For source digest `github-growth-20260706T111130.944672Z`, pass 3 exposes
`current_digest_pass3_route_to_validation_lane` as the operator replay surface
for the active reverse-flow slice. `lingbol088-spec/reverse-flow-skill` enters
`p1-skill-route-discovery-reverse-flow` through `skill_route_discovery` first
and may select only documentation, config, test, or code_patch local lanes with
focused validation required. Install, run, script execution, runtime,
provider, and external harness pressure is recorded as downgraded diagnostics,
not activation authority.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`shepherd-agents/shepherd` enter `p2-agent-harness-trend-eval` as
`agent_harness_eval_required` rows. They do not inherit `skill_route_discovery`,
select no implementation lane before local harness evaluation, and after that
gate may only yield documentation, test, or code_patch follow-up. The
documentation lane `p3-route-classification-docs` records this boundary against
`allowed_kinds`, `allowed_route_hints`, the narrow safety boundary, and the
controller rule that final scope and gate are recomputed locally. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T111130`.

For source digest `github-growth-20260706T103129.849391Z`, pass 1 opens the
active skill-route discovery slice with `current_digest_pass1_validation_lane`.
`380359884/reverse-flow-skill` is treated as fork-lineage evidence for the
same Codex and AI Agent skill workflow shape: `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox defaults, install examples, run
examples, and staged workflow language. It maps to
`p1_reverse_flow_skill_route_discovery` in the local test lane and may expose
only documentation, config, test, or code_patch lanes with local validation
required. Install, run, script execution, vulnerability-analysis, runtime,
provider, external harness, external skill activation, external agent
activation, and remote execution pressure remains diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent evidence under
`p3_agent_harness_eval_for_general_agent_trends`. They do not inherit
`skill_route_discovery`, have no direct implementation lane before local
agent-harness evaluation, and after that gate may only produce documentation,
test, or code_patch follow-up. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T103129`.

For source digest `github-growth-20260706T101129.935845Z`, pass 4 completes
the active route-discovery slice through
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
is the skill/workflow row because its public repository exposes a
`skills/reverse-flow` package, `SKILL.md`, references, scripts, local sandbox
defaults, install examples, and run examples. Those signals are useful only as
`skill_route_discovery` evidence until local validation chooses a bounded lane:
documentation, config, test, or code_patch. Install, run, script execution,
runtime, provider, external harness, external skill activation, and remote
execution pressure remains diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent evidence under `p3-agent-harness-eval-fixtures`. They do not
inherit a skill-route lane and have no direct implementation lane before local
agent-harness evaluation. After that gate, only documentation, test, or
code_patch follow-up may be considered. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T101129`.

For source digest `github-growth-20260706T093129.770380Z`, pass 2 records the
active route-discovery slice as both a pass-2 local validation lane and a
`skill_route_discovery_validation_route_packet`. The reverse-flow-skill trend
enters `skill_route_discovery` first because the evidence item carries an
explicit skill/workflow route hint and local skill-package shape. Its accepted
evidence references remain selected `item_id` values only, and its local lane
set is bounded to documentation, config, test, or code_patch with runtime action
disabled.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain adjacent
general-agent rows. They require `agent_harness_eval_required` before any
documentation, test, or code_patch follow-up and inherit no skill-route lane.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T093129`.

For source digest `github-growth-20260706T091129.696426Z`, pass 1 starts the
active route-discovery slice by making the adjacent general-agent lane more
inspectable before activation. `InternScience/Agents-A1`,
`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` are general agent, benchmark, simulation, or runtime
substrate evidence. They remain under `agent_harness_eval_lane`, not
`skill_route_discovery`, and the local replay now exposes an
`agent_harness_eval_result_schema` with required evidence-item inputs, expected
body-free output sections, candidate-capability source, pass-criteria source,
fail-criteria source, and per-project result path.

The active fixture
`agent_harness_eval_lane_20260706T091129_general_agent_projects.json` records
candidate capabilities, required inputs, expected outputs, and pass/fail
criteria without importing upstream code or exporting raw source URLs. The
allowed follow-up lanes remain only documentation, test, or code_patch after
the local harness contract passes. Runtime action, external agent activation,
external harness execution, provider launch, remote execution, and raw upstream
body export remain disabled. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or 20260706T091129"`.

For source digest `github-growth-20260706T085129.999580Z`, pass 4 completes
the active route-discovery slice through `current_digest_pass4_completion_handoff`.
`lingbol088-spec/reverse-flow-skill` is the skill/workflow evidence row because
its public shape carries `skills/reverse-flow`, `SKILL.md`, references, scripts,
local sandbox/CTF framing, install examples, run examples, and staged Codex
workflow language. It must enter `skill_route_discovery` first and may select
only documentation, config, test, or code_patch after local validation; install,
run, script execution, vulnerability-analysis, runtime, provider, external
harness, external skill activation, and remote execution pressure remains
diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain general
agent project rows under `p2-agent-harness-eval-fixtures`. They do not inherit
`skill_route_discovery`, have no direct implementation lane before bounded
local harness evaluation, and after that gate may only produce documentation,
test, or code_patch follow-up. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T085129`.

For source digest `github-growth-20260706T064239.027225Z`, pass 4 completes
the active window through `current_digest_pass4_completion_handoff`.
`lingbol088-spec/reverse-flow-skill` remains the skill/workflow row because its
public shape carries Codex/AI Agent package signals: `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox/CTF framing, install examples,
run examples, and staged workflow language. Those signals may select only the
bounded local lanes documentation, config, test, or code_patch after local
route discovery; install, run, script execution, vulnerability-analysis,
runtime, provider, external harness, external skill activation, and remote
execution pressure remains diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain general-agent evidence under
`p2-agent-harness-eval-fixtures`. ForkEvent and IssuesEvent signals associated
with these projects may raise local harness priority, but they do not
independently trigger documentation, test, code_patch, runtime, provider,
external harness, remote-execution, or controller behavior. Before bounded
local harness evaluation, these rows stay `agent_harness_eval_required` with
`skill_route_discovery_inherited: false`; after that gate, only documentation,
test, or code_patch may be considered. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T064239`.

For source digest `github-growth-20260706T062238.861950Z`, pass 3 exposes the
active window through `current_digest_pass3_route_to_validation_lane`.
`lingbol088-spec/reverse-flow-skill` is the skill/workflow row because its
public shape carries Codex/AI Agent package signals: `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox/CTF framing, install examples,
run examples, and staged workflow language. Those signals may select only the
bounded local lanes documentation, config, test, or code_patch after local
route discovery; install, run, script execution, vulnerability-analysis,
runtime, provider, external harness, external skill activation, and remote
execution pressure remains diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
general-agent evidence. They enter `agent_harness_eval_required`, inherit no
`skill_route_discovery` lane, and expose no documentation, test, code_patch,
runtime, provider, external harness, or remote-execution route before a bounded
local harness result. After that gate, only documentation, test, or code_patch
may be considered. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T062238`.

For source digest `github-growth-20260706T060238.927687Z`, pass 2 advances the
active window through `current_digest_pass2_local_validation_lane`.
`lingbol088-spec/reverse-flow-skill` is the skill-workflow row because its
public shape carries Codex/AI Agent skill-package signals: `skills/reverse-flow`,
`SKILL.md`, references, scripts, local sandbox/CTF framing, install examples,
run examples, and staged workflow language. Those signals select the local test
lane for `p2-skill-route-discovery-reverse-flow-skill` and keep install, run,
script execution, vulnerability-analysis, runtime, provider, external harness,
external skill activation, and remote execution pressure downgraded.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` stay adjacent
`agent_harness_eval_required` rows under
`p1-agent-harness-eval-trending-python-agents`. They do not inherit
`skill_route_discovery`, have no direct implementation lane before local
harness evaluation, and may only produce documentation, test, or code_patch
after that gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T060238`.

For source digest `github-growth-20260706T054239.844393Z`, pass 1 records the
active window through `skill_route_discovery_validation_route_packet`.
`lingbol088-spec/reverse-flow-skill` is the bounded exemplar: its public
Codex/AI Agent skill workflow signals map to `skill_route_discovery` and may
select only documentation, config, test, or code_patch local lanes before any
activation. `InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain general
agent evidence; they require `agent_harness_eval_required`, inherit no
skill-route lane, and expose no direct runtime or code_patch route before local
harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T054239`.

For source digest `github-growth-20260706T052238.803216Z`, pass 4 completes
the active `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
and its `zhenluwang23-sys/reverse-flow-skill` fork-lineage row remain
`skill_route_discovery` evidence because their public shape carries a Codex/AI
Agent skill package, `skills/reverse-flow`, `SKILL.md`, references, scripts,
local sandbox/CTF framing, install examples, run examples, and staged workflow
language. Those signals justify only documentation, config, test, or code_patch
validation lanes. Install, script execution, vulnerability-analysis, runtime,
provider, external harness, external skill activation, and remote execution
pressure stays diagnostic only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain
adjacent `agent_harness_eval_required` rows under
`p3_agent_harness_eval_fixtures`. They do not inherit `skill_route_discovery`
and have no direct documentation, test, code_patch, runtime, provider, external
harness, or remote-execution lane before a bounded local agent-harness result.
After that gate, only documentation, test, or code_patch may be considered.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T052238`.

For source digest `github-growth-20260706T050238.819252Z`, pass 3 exposes the
active window through `current_digest_pass3_route_to_validation_lane`.
`lingbol088-spec/reverse-flow-skill` remains a `skill_route_discovery` item:
its public shape includes a Codex/AI Agent skill package, `skills/reverse-flow`,
`SKILL.md`, references, scripts, sandbox/CTF framing, install examples, and run
examples. Those signals justify only bounded local lanes: documentation,
config, test, or code_patch. The current operator-visible rows select test for
`p1-skill-route-discovery-reverse-flow` and documentation for
`p3-route-hint-documentation-contract`; install, run, script execution,
vulnerability-analysis, provider, external harness, runtime, and remote
execution pressure stays downgraded.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` are adjacent general-agent projects under
`p2-agent-harness-eval-for-general-agent-trends`. They do not inherit
`skill_route_discovery`, have no direct local implementation lane before a
bounded local harness result, and may only produce documentation, test, or
code_patch after that evaluation gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T050238`.

For source digest `github-growth-20260706T044238.826915Z`, pass 2 exposes a
`validation_route_packet` on the existing `skill_route_discovery_lane` harness
output. The packet is the operator-visible route split for mixed evidence:
`lingbol088-spec/reverse-flow-skill` enters `skill_route_discovery` first and
may choose only documentation, config, test, or code_patch local lanes, while
`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain `agent_harness_eval_required` rows.
General-agent rows have no direct implementation lanes before local harness
evaluation; after that gate, only documentation, test, or code_patch may be
considered. Runtime action, provider launch, external harness execution,
external skill or agent activation, remote execution, and raw upstream URL/body
export remain disabled. Replay with:
`python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "validation_route_packet or 20260706T044238"`.

For source digest `github-growth-20260706T042239.700823Z`, pass 1 exposes the
active `skill-route-discovery` window through
`current_digest_pass1_validation_lane`. The reverse-flow-skill trend maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane because its
public shape carries explicit Codex/AI Agent skill workflow signals:
`skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox and CTF
framing, install examples, run examples, and staged workflow language. Install,
script execution, vulnerability-analysis, runtime execution, provider launch,
external harness execution, external skill activation, and remote execution
remain diagnostic pressure only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows before any implementation route. The active
proposal IDs `p2_agent_harness_eval_queue` and
`p3_agent_harness_eval_fixture` make the queue and fixture obligations visible:
general-agent projects have no direct lanes before bounded local harness
evaluation, and after that evaluation only documentation, test, or code_patch
may be considered. `p4_shepherd_workflow_probe` records the same rule for
workflow-oriented agent evidence without importing Shepherd-specific behavior.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T042239`.

For source digest `github-growth-20260706T040238.831794Z`, pass 4 completes
the active `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill trend maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane and keeps
`skill_route_discovery_first`, selected item IDs, body-free route metadata, and
controller recomputation of final scope before activation. Install, script
execution, vulnerability-analysis, runtime execution, provider launch, external
harness execution, external skill activation, and remote execution remain
diagnostic pressure only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` remain adjacent
`agent_harness_eval_required` rows under
`p2-agent-harness-eval-trending-agent-projects`. The Shepherd workflow and
automation signal is recorded as a local harness case, not as direct controller,
scheduling, runner, or tool-routing authority. Before bounded local harness
evaluation, these rows have no direct documentation, test, code_patch, runtime,
provider, external harness, or remote-execution lane. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T040238`.

For source digest `github-growth-20260706T034238.736996Z`, pass 3 exposes
the active `skill-route-discovery` window through
`current_digest_pass3_route_to_validation_lane`. The direct
`lingbol088-spec/reverse-flow-skill` trend maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane and
`p3_document_route_policy_for_trend_evidence` in the documentation lane. Both
rows preserve `skill_route_discovery_first`, selected item IDs, and the bounded
local lane envelope: documentation, config, test, or code_patch. Install,
script execution, vulnerability-analysis, runtime, provider, external harness,
external skill activation, and remote execution remain downgraded diagnostics.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under
`p2_agent_harness_eval_trending_agent_projects`. They do not inherit
`skill_route_discovery`, select no direct implementation lane, and keep
runtime, provider, external harness, and remote execution disabled until a
bounded local agent-harness result exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T034238`.

For source digest `github-growth-20260706T032238.788896Z`, pass 2 exposes the
active `skill-route-discovery` window through
`current_digest_pass2_local_validation_lane`. The direct
`lingbol088-spec/reverse-flow-skill` item maps to `p1-skill-route-discovery`
in the local test lane because its public shape carries Codex and AI Agent
skill workflow signals: `skills/reverse-flow`, `SKILL.md`, references,
scripts, local sandbox and CTF framing, install examples, and staged workflow
language. Install, script execution, vulnerability-analysis, runtime,
provider, external harness, external skill activation, and remote execution
remain downgraded diagnostics before activation.

`QwenLM/Qwen-AgentWorld`, `InternScience/Agents-A1`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under `p2-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery` and have no direct documentation,
test, code_patch, runtime, provider, external harness, or remote-execution lane
before bounded local agent-harness evaluation. The documentation row
`p3-route-policy-doc-clarification` records the same split using selected item
IDs and body-free route metadata. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T032238`.

For source digest `github-growth-20260706T024238.951790Z`, pass 4 completes
the active `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill item maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane and
`p3-document-routing-policy-for-trend-items` in the documentation lane. Both
rows preserve `skill_route_discovery_first`, selected item IDs, body-free route
metadata, and the controller rule that final scope and gates are recomputed
locally. Install, script execution, vulnerability-analysis, runtime execution,
provider launch, external harness execution, external skill activation, and
remote execution remain diagnostic pressure only.

`QwenLM/Qwen-AgentWorld`, `InternScience/Agents-A1`, and workflow-only
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` close the same pass
under `p2-agent-harness-eval-general-trends` as adjacent
`agent_harness_eval_required` rows. They do not inherit `skill_route_discovery`
and have no direct documentation, test, code_patch, runtime, provider, external
harness, or remote-execution lane before bounded local agent-harness
evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T024238`.

For source digest `github-growth-20260706T022238.766569Z`, pass 3 exposes the
active `skill-route-discovery` window through
`current_digest_pass3_route_to_validation_lane`. The direct
`lingbol088-spec/reverse-flow-skill` item and the carried `Betertiny` and
`a2731912893-dotcom` fork-lineage items collapse into one reverse-flow lineage
candidate under `p1-skill-route-discovery-reverse-flow`. The selected local lane
is `test`; all fork evidence remains supporting lineage pressure rather than an
independent adoption trigger. Install, script execution, vulnerability-analysis,
runtime execution, provider launch, external harness execution, external skill
activation, and remote execution remain downgraded diagnostics before local
validation.

`QwenLM/Qwen-AgentWorld` maps to
`p2-agent-harness-eval-qwen-agentworld`, while `InternScience/Agents-A1` and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` map to
`p3-agent-harness-eval-multi-repo-baseline`. These adjacent rows do not inherit
`skill_route_discovery`; before a bounded local agent-harness evaluation they
have no direct runtime route, no direct code_patch route, no provider launch, no
external harness execution, and no remote execution. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T022238`.

For source digest `github-growth-20260706T020239.308113Z`, pass 2 exposes the
active `skill-route-discovery` window through
`current_digest_pass2_local_validation_lane`. The reverse-flow-skill evidence
maps to `p2_skill_route_discovery_reverse_flow` in the local test lane because
its body-free repository shape carries Codex and AI Agent skill workflow
signals: `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox
and CTF framing, staged workflow language, install examples, and
vulnerability-analysis pressure. Those signals remain diagnostic route evidence
only. Install, script execution, vulnerability-analysis, runtime execution,
provider launch, external harness execution, external skill activation, and
remote execution stay denied before local validation.

`QwenLM/Qwen-AgentWorld` maps to
`p2_agent_harness_eval_qwen_agentworld`, while `InternScience/Agents-A1` and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` map to
`p3_agent_harness_eval_multi_repo_baseline`. The Seedance workflow-usecase row
does not inherit `skill_route_discovery`; workflow-topic evidence without an
explicit skill-route signal enters the same `agent_harness_eval_required` path.
Before bounded local harness evaluation, these adjacent rows have no direct
runtime route, no direct code_patch route, no provider launch, no external
harness execution, and no remote execution. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260706T020239`.

For source digest `github-growth-20260705T161641.350480Z`, pass 4 completes
the active `skill-route-discovery` window by making the workflow-only boundary
explicit in the reusable classifier. `lingbol088-spec/reverse-flow-skill`
remains a disabled skill-route candidate when the frozen evidence carries
Codex/AI Agent skill package markers such as `skills/reverse-flow`,
`SKILL.md`, references, scripts, and local sandbox/CTF framing. Its runtime,
install, and script pressure is diagnostic only; the local lanes remain bounded
to documentation, config, test, or code_patch.

Workflow-usecase repositories such as
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` no longer collapse into
a generic ignored bucket when they lack explicit skill package or skill-route
signals. The classifier records
`workflow_usecase_without_skill_route_signal`,
`workflow_usecase_repository`, and `agent_harness_eval_required`, then denies
skill-route inheritance, direct runtime routing, direct code_patch routing,
external harness execution, provider launch, and remote execution before local
agent-harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k workflow_usecases_to_agent_harness_eval`.

For source digest `github-growth-20260705T153637.166417Z`, pass 2 exposes the
active `skill-route-discovery` window through
`current_digest_pass2_local_validation_lane`. The
`trend:lingbol088-spec/reverse-flow-skill-1` row maps to
`proposal_skill_route_discovery_reverse_flow_skill` in the local test lane
because its body-free repository shape carries Codex/AI Agent skill workflow
signals: `skills/reverse-flow`, `SKILL.md`, references, scripts, local
sandbox/CTF framing, staged reverse workflow language, install examples, and
vulnerability-analysis pressure. Those signals remain diagnostic route
evidence only. Install, script execution, vulnerability-analysis, runtime,
provider, external harness, and remote execution pressure is downgraded before
activation.

`trend:QwenLM/Qwen-AgentWorld-1` maps to
`proposal_agent_harness_eval_qwen_agentworld`, while
`trend:InternScience/Agents-A1-1`,
`trend:TianhangZhuzth/Fundamental-Ava-1`, and
`trend:Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases-1` map to the
general agent-harness cluster. They stay as adjacent
`agent_harness_eval_required` rows with no inherited `skill_route_discovery`,
no direct runtime lane, no direct code_patch lane, no provider launch, no
external harness execution, and no remote execution before bounded local
harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T153637`.

For source digest `github-growth-20260705T151637.013264Z`, pass 1 opens the
active `skill-route-discovery` window through
`current_digest_pass1_validation_lane`. The
`trend:lingbol088-spec/reverse-flow-skill-1` row is classified from body-free
metadata and safe repository layout signals as a Codex/AI Agent skill workflow:
`skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox/CTF
framing, install examples, and vulnerability-analysis pressure. That pressure
is diagnostic only. The selected local lanes remain bounded to documentation,
config, test, or code_patch; install, script execution, provider launch,
external harness execution, runtime execution, and remote execution remain
denied.

`trend:InternScience/Agents-A1-1`, `trend:QwenLM/Qwen-AgentWorld-1`, and
`trend:TianhangZhuzth/Fundamental-Ava-1` map to
`p1-agent-harness-trending-project-eval` as adjacent
`agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery` and cannot open direct runtime or code_patch lanes
before bounded local harness evaluation. The workflow-usecase row
`trend:Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases-1` maps to
`p3-workflow-usecase-eval-documentation` and stays in the same harness-gated
boundary before any tool, runner, provider, or workflow integration. Replay
with: `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k
20260705T151637`.

For source digest `github-growth-20260705T145637.046753Z`, pass 4 completes
the active `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. The
`trend:lingbol088-spec/reverse-flow-skill-1` fixture row maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane and
`p3_route_reason_documentation` in the documentation lane. The handoff requires
`skill_route_discovery_first`, selected item IDs, focused local validation, and
only the bounded local lanes: documentation, config, test, or code_patch.
Install, script execution, vulnerability-analysis, runtime, provider, external
harness, and remote execution pressure remains diagnostic route evidence.

`trend:QwenLM/Qwen-AgentWorld-1`, `trend:InternScience/Agents-A1-1`,
`trend:TianhangZhuzth/Fundamental-Ava-1`, and the workflow-topic
`trend:Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases-1` close the same
pass under `p2_agent_harness_eval_for_general_projects` as adjacent
`agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before bounded
local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T145637`.

For source digest `github-growth-20260705T141637.046693Z`, pass 2 now exposes
the active `skill-route-discovery` window through
`current_digest_pass2_local_validation_lane`. The
`lingbol088-spec/reverse-flow-skill` evidence maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane and to
`p4-route-classification-regression-coverage` in the documentation lane because
the public repository shape is a Codex/AI Agent skill workflow with
`skills/reverse-flow`, `SKILL.md`, references, scripts, local CTF/sandbox
framing, install examples, and vulnerability-analysis pressure. Those signals
remain diagnostic route evidence only: install, script execution, provider
launch, vulnerability-analysis, external harness execution, runtime execution,
and remote execution stay denied.

`QwenLM/Qwen-AgentWorld` is recorded under
`p2-agent-harness-eval-qwen-agentworld`, while `InternScience/Agents-A1` and
`TianhangZhuzth/Fundamental-Ava` are recorded under
`p3-general-agent-project-batch-eval`. All three remain adjacent
`agent_harness_eval_required` rows with no inherited `skill_route_discovery`,
no direct runtime route, no direct code_patch route, no provider launch, and no
external harness execution before bounded local harness evaluation. Replay
with: `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k
20260705T141637`.

For source digest `github-growth-20260705T143637.069684Z`, pass 3 advances the
same active window through `current_digest_pass3_route_to_validation_lane`. The
`lingbol088-spec/reverse-flow-skill` evidence remains a Codex/AI Agent skill
workflow signal and maps to `p1-skill-route-discovery-reverse-flow` in the
local test lane. Its package layout, `SKILL.md`, references, scripts, local
CTF/sandbox framing, install examples, staged reverse workflow, and
vulnerability-analysis pressure are route evidence only; install, script
execution, provider launch, external harness execution, runtime execution, and
remote execution remain denied.

`QwenLM/Qwen-AgentWorld` maps to `p2-agent-harness-eval-qwen-agentworld`, while
`TianhangZhuzth/Fundamental-Ava` maps to
`p3-agent-harness-eval-fundamental-ava`. `InternScience/Agents-A1` is retained
as adjacent window context under `p4-agent-harness-eval-agents-a1`. All three
general-agent rows remain `agent_harness_eval_required`, do not inherit
`skill_route_discovery`, and cannot open direct runtime or code_patch lanes
before bounded local harness evaluation. The pass-3 operator packet records the
rollback check, bounded skill-route replay, agent-harness verification, and
pass-4 continuation sequence without exporting raw URLs, replay commands, or
upstream bodies. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T143637`.

For source digest `github-growth-20260705T135637.037461Z`, pass 1 opens the
active `skill-route-discovery` window through
`current_digest_pass1_validation_lane`. The
`lingbol088-spec/reverse-flow-skill` evidence maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane because the
public repository exposes a Codex/AI Agent skill workflow shape:
`skills/reverse-flow`, `SKILL.md`, references, scripts, local CTF/sandbox
framing, staged workflow language, install examples, and vulnerability-analysis
pressure. Those signals remain route evidence only: install, script execution,
provider launch, external harness execution, vulnerability-analysis, runtime
execution, and remote execution stay denied.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under
`p2_agent_harness_eval_trending_agent_projects`. The workflow-only
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` item remains under
`p3_workflow_signal_harness_for_blender_seedance`: workflow-topic evidence
without an explicit skill-route signal does not inherit `skill_route_discovery`
and cannot open direct runtime, workflow-routing, or code_patch lanes before
bounded local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T135637`.

For source digest `github-growth-20260705T122958.181363Z`, pass 1 opens the
active `skill-route-discovery` window through
`current_digest_pass1_validation_lane`. The
`lingbol088-spec/reverse-flow-skill` evidence maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane and to
`p5-workflow-usecase-documentation-eval` in the documentation lane because the
public repository exposes a Codex/AI Agent skill workflow shape:
`skills/reverse-flow`, `SKILL.md`, references, scripts, local CTF/sandbox
framing, staged workflow language, install examples, and vulnerability-analysis
pressure. That pressure remains diagnostic only: install, script execution,
external activation, provider launch, external harness execution, and remote
execution stay denied.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
`InternScience/Agents-A1` remain adjacent `agent_harness_eval_required` rows
under their proposal IDs. They do not inherit `skill_route_discovery`, direct
runtime routing, direct code_patch authority, external harness execution,
provider launch, or remote execution before bounded local harness evaluation.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T122958`.

For source digest `github-growth-20260705T120958.048870Z`, pass 4 completes
the active `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. The
`lingbol088-spec/reverse-flow-skill` evidence closes as
`p1-skill-route-discovery-reverse-flow` in the local test lane and
`p3-agent-project-routing-doc` in the documentation lane. The handoff preserves
`skill_route_discovery_first`, selected digest item IDs, body-free route
metadata, focused local validation, and only the bounded local lanes:
documentation, config, test, or code_patch. Install, script execution,
vulnerability-analysis, runtime, provider, external harness, and remote
execution pressure remains downgraded diagnostic evidence.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`,
`InternScience/Agents-A1`, and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` close the same pass
under `p2-general-agent-harness-eval-fixture` as adjacent
`agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before a
bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T120958`.

For source digest `github-growth-20260705T114958.132774Z`, pass 3 advances the
active `skill-route-discovery` window through
`current_digest_pass3_route_to_validation_lane`. The
`lingbol088-spec/reverse-flow-skill` signal maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane because the
public repository exposes a Codex/AI Agent skill package shape:
`skills/reverse-flow`, `SKILL.md`, references, local CTF/sandbox framing,
install examples, scripts, and a staged reverse workflow. Install, script,
runtime, provider, external harness, vulnerability-analysis, and remote
execution pressure remains downgraded diagnostic evidence.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`,
`InternScience/Agents-A1`, and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` remain adjacent
`agent_harness_eval_required` rows under
`p2_general_agent_harness_trend_eval`. The Seedance workflow-usecase item is
also recorded under `p3_workflow_agent_harness_eval`: workflow-topic evidence
without an explicit skill-route signal does not inherit `skill_route_discovery`
and cannot open direct runtime or code_patch lanes before bounded local harness
evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T114958`.

For source digest `github-growth-20260705T112958.062294Z`, pass 2 advances the
active `skill-route-discovery` window through
`current_digest_pass2_local_validation_lane`. The `lingbol088-spec/reverse-flow-skill`
signal maps to `p1-skill-route-discovery-reverse-flow` in the local test lane:
its public shape is a Codex and AI Agent skill package with `skills/reverse-flow`,
`SKILL.md`, references, local CTF/sandbox framing, staged reverse workflow,
install examples, and scripts. Those signals remain route evidence only.
Install, script execution, vulnerability-analysis, external harness execution,
provider launch, runtime execution, and remote execution are downgraded
diagnostics.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`,
`InternScience/Agents-A1`, and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` stay under
`p2-agent-harness-eval-suite` as adjacent `agent_harness_eval_required` rows.
They do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, or remote
execution before bounded local harness evaluation. `p3-agent-routing-documentation`
records the operator rule: skill/workflow route hints can open only
documentation, config, test, or code_patch lanes, while workflow-topic or
general-agent evidence without an explicit skill route hint must use the
agent-harness lane. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T112958`.

For source digest `github-growth-20260705T110958.050064Z`, pass 1 opens the
active `skill-route-discovery` window through
`current_digest_pass1_validation_lane`. The `lingbol088-spec/reverse-flow-skill`
signal maps to `p2-skill-route-discovery-for-reverse-flow-skill` in the local
code_patch lane because the public repository shape is a Codex and AI Agent
skill workflow with `skills/reverse-flow`, `SKILL.md`, references, local
CTF/sandbox framing, install examples, scripts, and runtime pressure. That
pressure remains diagnostic: install, script execution, external activation,
provider launch, harness execution, and remote execution stay denied.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`,
`InternScience/Agents-A1`, and the workflow-topic
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` evidence enter
`p1-agent-harness-eval-for-general-agent-trends` as adjacent
`agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before bounded
local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T110958`.

For source digest `github-growth-20260705T100958.062665Z`, pass 2 advances the
current `skill-route-discovery` window through
`current_digest_pass2_local_validation_lane`. `lingbol088-spec/reverse-flow-skill`
maps to `p1-skill-route-discovery-reverse-flow` in the local test lane because
the public repository shape is a Codex and AI Agent skill package with
`skills/reverse-flow`, `SKILL.md`, local CTF/sandbox framing, staged reverse
workflow, install examples, and scripts. Install, script, runtime, external
activation, provider launch, harness execution, and remote-execution pressure
remain downgraded diagnostics.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`,
`InternScience/Agents-A1`, and the workflow-topic
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` evidence stay under
`p2-agent-harness-eval-general-agent-projects` as adjacent
`agent_harness_eval_required` rows. The `p3-workflow-topic-agent-harness-eval`
documentation lane records the rule: workflow-topic repositories without an
explicit skill-route signal do not inherit `skill_route_discovery`; they enter
the general agent-harness evaluation path with no direct runtime, code_patch,
provider, external harness, or remote-execution lane before local harness
evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T100958`.

For source digest `github-growth-20260705T092958.273399Z`, pass 4 closes the
current `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill cluster is
treated as one lineage candidate: the Huiiyi and yzx20051 fork-style signals
corroborate the direct `lingbol088-spec/reverse-flow-skill` route evidence, but
do not create extra activation routes. The pass maps the lineage to
`p1-skill-route-discovery-reverse-flow` in the local test lane and
`p2-skill-route-discovery-docs` in the documentation lane. Both rows require
`skill_route_discovery_first`, selected item IDs, focused local validation, and
bounded lanes only: documentation, config, test, or code_patch.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
`InternScience/Agents-A1` remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-routing`.
They do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, or remote
execution before bounded local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T092958`.

For source digest `github-growth-20260705T082958.436037Z`, pass 1 opens the
current `skill-route-discovery` window through
`current_digest_pass1_validation_lane`. The reverse-flow-skill signal maps to
`p1_skill_route_discovery_reverse_flow` in the local test lane because the
public repository shape is a Codex and AI Agent skill workflow with a
`skills/reverse-flow` package, local CTF/sandbox framing, workflow steps,
install examples, and scripts. The lane now exposes profile validation
requirements for `codex_workflow_gate` and `generic_skill_workflow`, keeps
`skill_route_discovery_first`, and treats install, script execution, runtime,
provider launch, external activation, and remote execution as diagnostic only.

For source digest `github-growth-20260705T084958.837379Z`, pass 2 now exposes
`current_digest_pass2_local_validation_lane` for the same active window.
`lingbol088-spec/reverse-flow-skill` maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane and
`p3-route-classification-docs` in the documentation lane because the public
shape includes a `skills/reverse-flow` package, `SKILL.md`, references, scripts,
Codex workflow language, and local sandbox/CTF framing. The lane records the
recognized workflow markers, keeps `skill_route_discovery_first`, and downgrades
install, script, runtime, external activation, provider launch, harness
execution, and remote execution to diagnostics.

The same pass keeps `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `InternScience/Agents-A1` under
`p2-agent-harness-eval-trending-agent-projects` as adjacent
`agent_harness_eval_required` rows. They expose bounded harness ranking inputs
for capability fit, expected local benefit, route safety, and testability, but
do not inherit `skill_route_discovery`, direct runtime routes, direct code_patch
routes, external harness execution, provider launch, or remote execution before
local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T084958`.

`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
`InternScience/Agents-A1` remain adjacent `agent_harness_eval_required` rows.
They do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, or remote
execution before bounded local harness evaluation. Replay with:
`PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k 20260705T082958`.

For source digest `github-growth-20260705T080817.787301Z`, pass 4 completes the
current `skill-route-discovery` window through
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
is the only skill-route candidate in this pass: its public shape is a Codex and
AI Agent skill workflow with a `skills/reverse-flow` package, local CTF/sandbox
framing, staged reverse-analysis workflow, install examples, and scripts. The
completion handoff maps that evidence to the local test lane under
`p1-skill-route-discovery-reverse-flow` and to the documentation lane under
`p3-document-growth-route-policy`. Both rows preserve
`skill_route_discovery_first`, cite selected item IDs, require local validation,
and keep upstream install, script, runtime, external activation, provider
launch, harness execution, remote execution, raw URLs, raw replay commands, and
upstream bodies out of the operator surface.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` close the same pass as adjacent
`agent_harness_eval_required` rows under
`p2-agent-harness-eval-trending-agent-projects`. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority, or
implementation lanes before bounded local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T080817`.

For source digest `github-growth-20260705T074818.241950Z`, pass 3 exposes
`current_digest_pass3_route_to_validation_lane` for the active
skill-route-discovery window. `lingbol088-spec/reverse-flow-skill` and
`dreamwho/reverse-flow-skill` collapse into one reverse-flow lineage candidate:
the fork corroborates the route evidence but does not create a second
activation path. The candidate maps to `p1_reverse_flow_skill_discovery` in the
local test lane and `p2_skill_route_documentation_contract` in the
documentation lane. The interpretation contract is: accepted lanes are only
documentation, config, test, or code_patch; selected digest item IDs and
body-free summaries are required; upstream install, script, runtime, provider,
external activation, harness execution, and remote-execution pressure remains
diagnostic; raw source URLs, raw replay commands, target paths, and upstream
bodies are not exported from the operator lane.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under `p3_agent_harness_eval_fixture`. They
do not inherit skill-route lanes, direct runtime routes, or direct code_patch
authority before local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T074818`.

For source digest `github-growth-20260705T072819.148283Z`, pass 2 exposes
`current_digest_pass2_local_validation_lane` for the active route-discovery
window. `lingbol088-spec/reverse-flow-skill` and the carried
`Ovlvllo/reverse-flow-skill` evidence collapse into one reverse-flow lineage
candidate. The row maps to `p1_reverse_flow_skill_route_discovery` in the local
test lane, while `p2_skill_workflow_routing_docs` records the documentation
interpretation: route hints can choose only documentation, config, test, or
code_patch lanes, and final implementation scope remains controller-recomputed
after focused local validation. Upstream install, script, runtime, external
activation, provider launch, and remote-execution pressure stays diagnostic.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` stay adjacent
`agent_harness_eval_required` rows under `p3_agent_harness_eval_fixture`.
They do not inherit `skill_route_discovery`, do not receive implementation
lanes before local harness evaluation, and cannot launch external harnesses,
providers, agents, or remote execution from trend evidence. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T072819`.

For source digest `github-growth-20260705T070818.682441Z`, pass 1 exposes
`current_digest_pass1_validation_lane` for the active route-discovery window.
`lingbol088-spec/reverse-flow-skill` maps to
`p1-skill-route-discovery-reverse-flow` in the local test lane because its
public shape is an Agent/Codex skill workflow with a `skills/reverse-flow`
package, `SKILL.md`, local CTF/sandbox framing, workflow steps, install
examples, and script examples. The row must prove
`skill_route_discovery_first`; upstream install, script, runtime, external
activation, provider launch, and remote-execution pressure remains diagnostic
only.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and
`TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under
`p2-agent-harness-eval-general-agent-trends`. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before a
bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T070818`.

For source digest `github-growth-20260705T060819.666814Z`, pass 2 exposes
`current_pass2_skill_route_operator_lane` from the proposal route map.
`lingbol088-spec/reverse-flow-skill` remains the Codex-specific skill workflow
row and must confirm `skill_route_discovery_first` before any local lane is
accepted. `NVIDIA-BioNeMo/bionemo-agent-toolkit` remains a generic skill
workflow row: skills, plugins, or catalog language can open only documentation,
config, test, or code_patch outputs after local validation, and generic plugin
language alone is not a Codex workflow-gate signal. `Qwen-AgentWorld` and
`Fundamental-Ava` stay adjacent `agent_harness_eval_required` rows with no
direct lanes before local harness evaluation. Replay with:
`python -m pytest tests/test_github_growth.py -q -k current_pass2_skill_route_operator_lane`.

For source digest `github-growth-20260705T054818.762095Z`, pass 1 exposes
`current_pass1_skill_route_validation_matrix` from the proposal route map.
`lingbol088-spec/reverse-flow-skill` is classified as the Codex-specific
regression half: it must prove `skill_route_discovery_first`, selects the local
test lane, and keeps upstream install/run/script pressure diagnostic only.
`NVIDIA-BioNeMo/bionemo-agent-toolkit` is classified as the generic skill
workflow half: it enters `skill_route_discovery` first and may proceed only to
documentation, config, test, or code_patch after local validation.
`Qwen-AgentWorld` and `Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows; they do not inherit `skill_route_discovery`
or direct implementation lanes before local harness evaluation. Replay with:
`pytest tests/test_github_growth.py -q -k current_pass1_skill_route_validation_matrix`.

For source digest `github-growth-20260705T042818.506501Z`, pass 1 exposes a
bounded `current_digest_pass1_validation_lane` for the active window.
`lingbol088-spec/reverse-flow-skill` maps to
`p1-skill-route-discovery-codex-workflow-gate` in the local test lane because
its public shape is a Codex and AI Agent skill workflow with
`skills/reverse-flow/SKILL.md`, local sandbox/CTF framing, scripts, install
examples, and runtime pressure. The row must prove
`skill_route_discovery_first`; upstream install or runtime wording remains
diagnostic only.

`NVIDIA-BioNeMo/bionemo-agent-toolkit` maps to
`p2-generic-skill-workflow-discovery` as generic agent-skills workflow evidence.
It may open only documentation, config, test, or code_patch local lanes after
focused validation; upstream skills CLI install examples and ready-to-call
skill language do not activate external code. `Qwen-AgentWorld`,
`Fundamental-Ava`, and
`Awesome-Blender-Seedance-Workflow-Usecases` remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-general-agent-trends`. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before bounded
local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T042818`.

For source digest `github-growth-20260704T192436.767658Z`, pass 2 exposes a
normalized `route_activation_contract` inside
`current_digest_pass2_local_validation_lane`. The contract is operator-visible
and checks three preactivation facts together: skill-route rows are bounded to
documentation, config, test, or code_patch; Codex workflow-gate rows prove
`skill_route_discovery_first`; and adjacent general-agent projects remain in
`agent_harness_eval_required`.

`lingbol088-spec/reverse-flow-skill` maps to
`p2-codex-skill-workflow-gate` in the local test lane because the public
repository shape exposes a Codex/AI Agent skill workflow with a
`skills/reverse-flow` package, `SKILL.md`, local sandbox and CTF framing,
scripts, install examples, and runtime pressure. That pressure is diagnostic
only: install, execution, external skill activation, provider launch, remote
execution, raw source URL export, replay-command export, and upstream body
export stay denied.

`zhengxi-views` maps to `p1-skill-route-discovery-fixtures` in the local test
lane as source-cited Agent Skill evidence with `SKILL.md`, `skill.yml`,
references, evals, scripts, automation/MCP pressure, and an advice boundary.
`Qwen-AgentWorld` remains adjacent under
`p3-agent-harness-eval-baseline`; it does not inherit `skill_route_discovery`,
direct runtime routing, direct code_patch authority, external harness
execution, provider launch, or remote execution before bounded local harness
evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k "current_run_pass2_local_validation_lane or 20260704T192436"`.

For source digest `github-growth-20260704T190435.517226Z`, pass 1 exposes the
active `skill-route-discovery` window through
`current_run_pass1_activation_readiness`. `lingbol088-spec/reverse-flow-skill`
maps to `proposal_skill_route_discovery_codex_reverse_flow` in the local test
lane because the public repository shape is a Codex/AI Agent skill workflow
with `skills/reverse-flow`, `SKILL.md`, sandbox/CTF framing, install examples,
scripts, and runtime pressure. The local lane must prove
`skill_route_discovery_first`; upstream install or execution pressure remains
diagnostic only.

`zhengxi-views` maps to `proposal_skill_route_discovery_zhengxi_views` in the
documentation lane as generic/source-cited skill workflow evidence with an
advice boundary. `Qwen-AgentWorld` remains adjacent
`agent_harness_eval_required` under
`proposal_agent_harness_eval_qwen_agentworld`: it does not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before bounded
local harness evaluation exists. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k 20260704T190435`.

For source digest `github-growth-20260704T182436.018333Z`, pass 3 accepts the
active `skill-route-discovery` slice through
`current_run_pass3_validation_lane` and the derived
`current_run_pass3_acceptance_lane`. `lingbol088-spec/reverse-flow-skill`, with
the carried `820101274/reverse-flow-skill` lineage URL, maps to
`p1-skill-route-discovery-codex-workflow` in the local test lane because its
public shape is a Codex/AI Agent skill workflow with `skills/reverse-flow`,
`SKILL.md`, local sandbox/CTF framing, scripts, install examples, and runtime
pressure. The local route must record `skill_route_discovery_first` before any
secondary workflow interpretation, and install or runtime pressure remains
diagnostic only.

`zhengxi-views` maps to `p2-generic-skill-workflow-discovery` in the
documentation lane: generic skill workflow evidence can inform only
documentation, config, test, or code_patch candidates until local validation
succeeds. `Qwen-AgentWorld` remains adjacent
`agent_harness_eval_required` under `p3-agent-harness-eval-fixtures`; it does
not inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, or remote execution
before bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k current_run_pass3`.

For source digest `github-growth-20260704T180435.622778Z`, pass 2 validates
the active `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. `zhengxi-views` maps to a
source-cited and generic skill workflow test lane because its public repository
shape includes `SKILL.md`, `skill.yml`, references, evals, scripts,
source-cited research language, and an explicit advice boundary. Its WorkBuddy,
MCP, data-fetching, and financial-domain pressure remains validation metadata;
it does not grant provider launch, external activation, or advice behavior.

`lingbol088-spec/reverse-flow-skill`, with the carried
`820101274/reverse-flow-skill` lineage URL, maps to the Codex workflow-gate test
lane. The classifier records `skill_route_discovery_first` before any secondary
workflow interpretation, and downgrades install, script, runtime, external
activation, provider launch, and remote-execution pressure to diagnostics only.

Qwen-AgentWorld remains an adjacent `agent_harness_eval_required` row under
`p3-agent-harness-qwen-agentworld`: it does not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, or remote execution before bounded
local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T180435`.

For source digest `github-growth-20260704T174435.250220Z`, pass 1 opens the
active `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The `lingbol088-spec/reverse-flow-skill`
repository and the carried `820101274/reverse-flow-skill` fork are one
reverse-flow lineage candidate, not two activation routes. The row maps to
`p1-reverse-flow-skill-route-discovery` in the local test lane, records
`skill_route_discovery_first`, and treats upstream install or runtime wording as
diagnostic-only pressure. `zhengxi-views` maps to
`p2-generic-skill-workflow-discovery` in the documentation lane: generic
skill-related repositories without implementation-specific local evidence enter
`skill_route_discovery` first and require local validation before documentation,
config, test, or code_patch changes.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`. They
do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, provider launch, external harness execution, or remote
execution before bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T174435`.

For source digest `github-growth-20260704T172435.309658Z`, pass 4 completes the
active `skill-route-discovery` slice through a current-digest completion
handoff and final closure. `zhengxi-views` is a source-cited Agent Skill signal:
its `SKILL.md`, `skill.yml`, references, evals, scripts, WorkBuddy/MCP workflow
language, and advice boundary map to `p1-skill-route-discovery-zhengxi-views`
in the local test lane. `reverse-flow-skill` maps to
`p2-codex-workflow-skill-gate` in the local test lane and must preserve
`skill_route_discovery_first`; upstream install or runtime pressure remains
diagnostic only.

Qwen-AgentWorld and Fundamental-Ava close the window as adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld`. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code patch authority,
provider launch, external harness execution, or remote execution before bounded
local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T172435`.

For source digest `github-growth-20260704T162434.547303Z`, pass 1 opens the
active `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The reviewed
`lingbol088-spec/reverse-flow-skill` evidence is a Codex and AI Agent skill
workflow repository shape: it exposes a `skills/reverse-flow` package,
`SKILL.md`, local sandbox/CTF framing, workflow steps, and install/script
examples. Locally, that maps to `p1-skill-route-discovery-codex-workflow` in
the test lane with `skill_route_discovery_first`; install and runtime pressure
remain diagnostics and do not become activation authority.

`zhengxi-views` maps to `p2-generic-skill-workflow-discovery-docs` in the
documentation lane. It may inform documentation, config, test, or code_patch
work only after focused local validation from selected digest item IDs and
body-free summaries; trend metadata alone is not implementation evidence.
Qwen-AgentWorld and Fundamental-Ava remain under
`p3-agent-harness-eval-fixtures` as adjacent `agent_harness_eval_required`
rows. They do not inherit `skill_route_discovery`, direct runtime routing, or
direct code_patch authority before local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T162434`.

For source digest `github-growth-20260704T160434.504032Z`, pass 4 completes
the active `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The `lingbol088-spec` reverse-flow
skill repository and the carried `iamcaozhi` fork are one Codex workflow skill
lineage candidate: the fork contributes route pressure and selected item-ID
evidence, but does not create separate activation authority. The row maps to
`p1_reverse_flow_skill_route_discovery` in the local test lane, keeps
`skill_route_discovery_first`, and downgrades upstream install or runtime
pressure to diagnostics only.

`zhengxi-views` maps to `p2_skill_route_discovery_documentation` as a
generic/source-cited skill workflow documentation lane inside the same bounded
documentation, config, test, or code_patch envelope. Qwen-AgentWorld,
Fundamental-Ava, and Awesome-Blender-Seedance-Workflow-Usecases remain adjacent
`agent_harness_eval_required` rows under
`p3_agent_harness_eval_qwen_agentworld`; they do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, or remote execution before local
harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T160434`.

For source digest `github-growth-20260704T152434.856651Z`, pass 2 adds an
operator-visible `current_pass2_route_evidence_lane_source` packet inside the
pass-2 handoff. The packet derives each skill-route row from controller-owned
`route_hints` and `route_classification`, not from repository labels, proposal
text, or raw upstream bodies. Reverse-flow-style skill evidence and generic
skill workflow evidence must resolve to `skill_route_discovery` first when the
classifier sees `skill_term` plus `mixed_skill_workflow_probe` pressure; the
only local lanes remain documentation, config, test, or code_patch. The packet
is metadata-only and keeps install, execute, provider launch, external skill
activation, remote execution, source URL export, and upstream body export
denied. Replay with:
`python -m pytest tests/test_proposal_eval.py -q -k pass2_route_evidence_lane_source`.

For source digest `github-growth-20260704T150434.812972Z`, pass 1 keeps
reverse-flow-style skill evidence in a bounded probe lane. The
`lingbol088-spec/reverse-flow-skill` repository and the carried
`iamcaozhi/reverse-flow-skill` fork are one lineage candidate: upstream
installation, script, run, execute, or runtime pressure is recorded as
diagnostic pressure, not as a requested local action. The candidate remains
disabled, may expose only documentation, config, test, or code_patch lanes,
and must preserve the Codex workflow-gate rule that
`skill_route_discovery_first` is proven before any secondary workflow or
activation path. `zhengxi-views` remains generic/source-cited skill workflow
evidence for bounded local validation, while Qwen-AgentWorld-style general
agent projects remain adjacent `agent_harness_eval_required` rows with
`skill_route_discovery_inherited: false`. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k reverse_flow_fork_lineage`.

For source digest `github-growth-20260704T144434.510329Z`, pass 4 completes the
active `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The final handoff binds
`zhengxi-views` to `p1-skill-route-discovery-zhengxi-views` as a local test
lane for generic skill workflow evidence and binds `reverse-flow-skill` to
`p2-codex-skill-workflow-gate` as a Codex workflow-gate test lane. Both rows
must remain inside documentation, config, test, or code_patch candidates, and
the Codex row must prove `skill_route_discovery_first` before any secondary
workflow gate. Install and runtime pressure from upstream repositories remains
diagnostic only.

Qwen-AgentWorld, Fundamental-Ava, and
Awesome-Blender-Seedance-Workflow-Usecases remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery`, cannot open direct runtime or code_patch lanes before
local harness evidence exists, and may only produce documentation, test, or
code_patch follow-up after bounded local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T144434`.

For source digest `github-growth-20260704T142434.764913Z`, pass 3 advances the
active `skill-route-discovery` slice through
`current_digest_pass3_route_to_validation_lane`. `reverse-flow-skill` and
`zhengxi-views` are grouped under `p1-skill-route-discovery-fixture` as a local
test-lane replay: their upstream install or runtime pressure is diagnostic
only, and the selected lanes remain inside documentation, config, test, or
code_patch. The same packet exposes `p2-codex-workflow-gate-documentation` for
the reverse-flow Codex workflow gate and `p4-route-classification-matrix` for
the source-cited generic skill workflow route.

Qwen-AgentWorld, Fundamental-Ava, and Awesome-Blender-Seedance-Workflow-Usecases
remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-smoke-tests`; they do not inherit
`skill_route_discovery`, direct runtime routing, or direct code_patch authority
before bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T142434`.

For source digest `github-growth-20260704T134434.634232Z`, pass 1 opens the
active `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The `reverse-flow-skill` and
`zhengxi-views` evidence are grouped under
`p1-skill-route-discovery-fixture`: they may select only documentation,
config, test, or code_patch lanes, with the current selected lane set exposing
test, documentation, and config work for local validation.

The reverse-flow row also feeds
`p2-codex-workflow-gate-documentation`; mixed skill and Codex workflow signals
must preserve `skill_route_discovery_first` before any secondary workflow gate,
runtime behavior, provider launch, external skill activation, or remote
execution is considered. `p4-route-classification-matrix` makes the current
proposal IDs, selected item IDs, route profiles, lane names, and denial
booleans replayable without raw upstream bodies or source URL export.

Awesome-Blender-Seedance-Workflow-Usecases and Qwen-AgentWorld remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-smoke-tests`; they do not inherit
`skill_route_discovery`, direct runtime routing, or direct code_patch authority
before bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T134434`.

For source digest `github-growth-20260704T130435.072372Z`, pass 4 completes the
active `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The `reverse-flow-skill` evidence
maps to `p1-skill-route-discovery-codex-workflow-gate` in the local test lane,
must preserve `skill_route_discovery_first`, and treats upstream install or
runtime pressure as diagnostics rather than allowed lanes. The `zhengxi-views`
evidence maps to `p2-generic-skill-workflow-documentation` in the
documentation lane with selected item IDs only.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-general-agent-projects`; they do not inherit
`skill_route_discovery`, direct runtime routing, or direct code_patch authority
before bounded local harness evaluation exists. The handoff is record-only for
an external supervisor and exports body-free proposal IDs, selected item IDs,
route profiles, lane names, hashes, and denial booleans. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T130435`.

For source digest `github-growth-20260704T130435.072372Z`, pass 3 advances the
active `skill-route-discovery` slice through
`current_digest_pass3_route_to_validation_lane`. The `reverse-flow-skill`
evidence is treated as a Codex workflow-gate skill signal under
`p1-skill-route-discovery-codex-workflow-gate`: it must select the local
`test` lane, prove `skill_route_discovery_first`, and keep upstream install,
script, runtime, provider, external activation, and remote-execution pressure
diagnostic only.

The `zhengxi-views` evidence maps to
`p2-generic-skill-workflow-documentation` as a generic/source-cited skill
workflow documentation lane. Its documented validation envelope is exactly the
`skill_route_discovery` lane set: documentation, config, test, or code_patch.
Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-general-agent-projects`; they do not inherit
`skill_route_discovery`, direct runtime routing, or direct code_patch authority
before bounded local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T130435`.

For source digest `github-growth-20260704T124434.742366Z`, pass 2 advances the
active `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The direct
`lingbol088-spec/reverse-flow-skill` signal and the carried
`ddzxj870/reverse-flow-skill` fork-lineage signal collapse into one
reverse-flow candidate in the local test lane: the row must prove
`skill_route_discovery_first`, may expose only documentation, config, test, or
code_patch as local lanes, and keeps upstream install, runtime, provider,
external activation, and remote-execution pressure diagnostic only.

`zhengxi-views` remains a generic and source-cited skill-workflow documentation
lane, not a direct behavior import. The documentation-gate row records that
`skill_route_discovery` work cites selected digest item IDs rather than
truncated IDs or raw external URLs. Qwen-AgentWorld and Fundamental-Ava remain
adjacent `agent_harness_eval_required` rows under
`p4_agent_project_harness_eval`; they do not inherit `skill_route_discovery`,
have no direct runtime or code_patch route before bounded harness evaluation,
and may only produce documentation, test, or code_patch follow-up after that
evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T124434`.

For source digest `github-growth-20260704T114435.950310Z`, pass 3 advances the
active `skill-route-discovery` slice through
`current_digest_pass3_route_to_validation_lane`. The `reverse-flow-skill`
evidence maps to `p1-skill-route-discovery-codex-workflow` in the local test
lane because the public repository shape carries Codex, AI Agent, skill,
workflow, local sandbox, CTF, scripts, and install/runtime pressure. That
pressure is downgraded to diagnostics: `skill_route_discovery_first` must be
proved before any secondary workflow-gate interpretation, and install,
runtime, provider launch, external activation, and remote execution stay
denied.

The `zhengxi-views` evidence maps to
`p2-generic-skill-workflow-routing-fixture` in the local test lane as a generic
and source-cited skill workflow route fixture. Qwen-AgentWorld and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-documentation`; they do not inherit
`skill_route_discovery`, open no direct runtime or code_patch lane before local
harness evaluation, and may only produce documentation, test, or code_patch
follow-up after that evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T114435`.

For source digest `github-growth-20260704T110437.006867Z`, pass 1 advances the
active `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The `reverse-flow-skill` evidence maps
to `p1-skill-route-discovery-codex-workflow` in the local test lane because the
public repository presents a Codex/AI Agent skill package with a trigger term,
local sandbox/CTF framing, scripts, and workflow-gate pressure. That pressure
must remain `skill_route_discovery_first`: install, runtime execution, provider
launch, external activation, and remote execution stay denied.

The `zhengxi-views` evidence maps to
`p2-generic-skill-workflow-route-discovery` in the documentation lane as a
generic/source-cited skill workflow checklist. `p5-route-classification-coverage`
keeps the active route-classification coverage replayable by checking proposal
IDs, selected item IDs, route profiles, lane names, and denial booleans.
Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows: they do not inherit `skill_route_discovery`,
open no direct runtime or code_patch route before bounded local harness
evaluation, and may only produce documentation, test, or code_patch follow-up
after that evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T110437`.

For source digest `github-growth-20260704T104434.469778Z`, pass 4 completes
the active `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The `reverse-flow-skill` evidence
maps to `p1-skill-route-discovery-reverse-flow` in the local test lane because
the public repository shape presents a Codex/AI Agent skill workflow with
`SKILL.md`, scripts, local sandbox and CTF framing, and install/runtime
pressure. That pressure remains diagnostic only, and the row must preserve
`skill_route_discovery_first` before any workflow or controller change is
considered.

The `zhengxi-views` evidence maps to `p2-skill-route-discovery-zhengxi` in the
documentation lane as a generic/source-cited skill workflow with explicit
advice-boundary metadata. Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-qwen-agentworld`;
they do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, provider launch, external harness execution, or remote
execution before bounded harness evaluation exists. The handoff exports
body-free proposal IDs, selected item IDs, route profiles, lane names, hashes,
and denial booleans while keeping raw source URLs, replay commands, target
paths, and upstream bodies out of the operator packet. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T104434`.

For source digest `github-growth-20260704T100436.608033Z`, pass 2 advances the
active `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The `zhengxi-views` evidence maps
to `p1-skill-route-discovery-zhengxi-views` in the local test lane because the
repository shape is an Agent Skill package with source-citation and advice
boundary metadata. The `reverse-flow-skill` evidence maps to
`p2-codex-skill-workflow-gate`, also in the local test lane, and must preserve
`skill_route_discovery_first` before any secondary Codex workflow or runtime
interpretation.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, or remote execution before a
bounded harness result exists. The pass-2 surface exports body-free proposal
IDs, selected item IDs, route profiles, lane names, hashes, and denial booleans
while keeping raw source URLs, replay commands, target paths, and upstream
bodies out of the operator packet. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T100436`.

For source digest `github-growth-20260704T094434.421996Z`, pass 1 opens the
active `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow skill evidence under
`p1-skill-route-discovery-codex-workflow`: it selects the local test lane,
must preserve `skill_route_discovery_first`, and keeps upstream install,
script, runtime, provider, external activation, and remote-execution pressure
diagnostic only. The `zhengxi-views` evidence maps to
`p2-generic-skill-workflow-route-doc` in the documentation lane, while
`p5-route-summary-metadata` makes the current proposal IDs, selected item IDs,
route profiles, and bounded lane names replayable.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`, have no direct local lanes before
bounded harness evaluation, and may only produce documentation, test, or
code_patch follow-up after that evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T094434`.

For source digest `github-growth-20260704T091310.009322Z`, pass 4 completes the
active `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
`reverse-flow-skill` evidence is treated under
`p1-skill-route-discovery-codex-workflow-gate`: it selects the local test lane,
must preserve `skill_route_discovery_first`, and downgrades install or runtime
pressure to diagnostics. The `zhengxi-views` evidence is interpreted under
`p2-generic-skill-workflow-discovery-lane` as generic/source-cited skill
workflow documentation, with local validation required before any config, test,
or code_patch follow-up.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-general-agent-projects`. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up after a
bounded harness result exists. The pass-4 handoff exposes an operator
completion packet, recovery workflow, and record-only activation contract while
denying runtime action, external skill activation, external harness execution,
provider launch, remote execution, push, promotion, and kernel restart. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260704T091310`.

For source digest `github-growth-20260704T085309.981717Z`, pass 3 advances the
active `skill-route-discovery` slice through
`current_digest_pass3_route_to_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Agent/Codex skill workflow
evidence under `p1-skill-route-discovery-reverse-flow`: it selects the local
test lane, preserves `skill_route_discovery_first`, and downgrades install or
runtime pressure to diagnostics. The `zhengxi-views` evidence is interpreted
under `p2-generic-skill-workflow-discovery-doc` as generic/source-cited skill
workflow documentation, with local validation required before any config, test,
or code_patch follow-up.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-fixture`. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up after a
bounded harness result exists. The pass-3 operator packet exports body-free
proposal IDs, hashes, lane names, and denial booleans while denying runtime
action, external skill activation, external harness execution, provider launch,
remote execution, and kernel restart. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T085309`.

For source digest `github-growth-20260704T083309.688268Z`, pass 2 advances the
active `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence:
it enters `p1-skill-route-discovery-validation-path`, selects the local test
lane, preserves `skill_route_discovery_first`, and keeps upstream install or
runtime pressure as diagnostics only. The `zhengxi-views` evidence enters
`p2-skill-agent-route-decision-rule` as generic/source-cited skill workflow
documentation.

Qwen-AgentWorld and Awesome-Blender-Seedance-Workflow-Usecases are adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-before-code-adoption`. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up after a
bounded harness result exists. The pass-2 operator surface exports body-free
IDs, hashes, lane names, and denial booleans while denying raw source URL
export, upstream body export, runtime action, provider launch, external harness
execution, remote execution, push, promotion, and kernel restart. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T083309`.

For source digest `github-growth-20260704T075310.454539Z`, pass 4 completes the
active `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
`reverse-flow-skill` evidence remains a Codex reverse-flow skill workflow row
under `p1-skill-route-discovery-reverse-flow`: it selects the local test lane,
keeps `skill_route_discovery_first`, and downgrades install or runtime pressure
to diagnostics rather than allowed lanes. The `zhengxi-views` evidence remains
a generic/source-cited skill workflow row under
`p2-skill-route-discovery-generic`, selecting documentation inside the
documentation, config, test, and code_patch envelope.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld`. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up after a
bounded harness result exists. The pass-4 handoff exposes an operator
completion packet and recovery workflow, exports body-free IDs, hashes, lane
names, and denial booleans, and leaves promotion, push, restart, and activation
to the external supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T075310`.

For source digest `github-growth-20260704T073310.401263Z`, pass 3 advances the
active `skill-route-discovery` slice through
`current_digest_pass3_route_to_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as a Codex reverse-flow skill workflow
row under `p1-skill-route-discovery-codex-workflow`: it selects the local test
lane, preserves `skill_route_discovery_first`, and keeps install or runtime
pressure as downgraded diagnostics rather than allowed lanes. The
`zhengxi-views` evidence is routed under
`p2-generic-skill-route-discovery-fixture` as a generic/source-cited skill
workflow test fixture; it remains bounded to documentation, config, test, and
code_patch candidates with focused local validation required before activation.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-general-agent-projects`. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up after a
bounded harness result exists. The pass-3 operator packet exports body-free
proposal IDs, hashes, lane names, and denial booleans while denying provider
launch, external harness execution, remote execution, and kernel restart.
Replay with: `python -m pytest tests/test_skill_routing.py -q -k 20260704T073310`.

For source digest `github-growth-20260704T071309.705655Z`, pass 2 binds the
active `skill-route-discovery` slice to
`current_digest_pass2_local_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence
under `p1-skill-route-discovery-codex-workflow`: it must preserve
`skill_route_discovery_first`, selects the local test lane, and downgrades
install/runtime pressure to diagnostics only. The allowed local lane envelope
remains documentation, config, test, or code_patch, with no upstream skill
activation, external harness execution, provider launch, remote execution, or
kernel restart.

The `zhengxi-views` evidence routes under
`p2-generic-skill-workflow-discovery` as a documentation lane for a generic and
source-cited skill workflow checklist. Qwen-AgentWorld and Fundamental-Ava
remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-agentworld`: they do not inherit
`skill_route_discovery`, have no direct runtime or code_patch lane before
bounded harness evaluation, and may only produce documentation, test, or
code_patch follow-up after that evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T071309`.

For source digest `github-growth-20260704T055309.687829Z`, pass 2 advances the
current `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence:
it selects the local test lane, preserves `skill_route_discovery_first`, and
may expose only documentation, config, test, or code_patch as eligible local
lanes. Upstream install, runtime execution, provider launch, external skill
activation, and remote execution remain denied.

The `zhengxi-views` evidence is routed under
`p2-generic-skill-route-discovery` as a generic/source-cited skill workflow
documentation lane with local validation required. Qwen-AgentWorld is routed
under `p3-agentworld-harness-eval`, and Fundamental-Ava under
`p4-fundamental-ava-agent-eval`; both remain adjacent
`agent_harness_eval_required` rows with no direct local lanes before bounded
local harness evaluation. Fork or trend activity can increase review interest
but does not bypass that gate. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T055309`.

For source digest `github-growth-20260704T053309.188012Z`, pass 1 opens the
current `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence
under `p1-skill-route-discovery-codex-workflow`: it selects the local test lane
and may expose only documentation, config, test, or code_patch as eligible local
lanes. Install, runtime execution, provider launch, upstream skill activation,
and remote execution remain denied even when upstream README examples mention
them.

The `zhengxi-views` evidence remains a generic/source-cited skill workflow row
under `p2-generic-skill-route-documentation` and selects the documentation lane.
Proposal interpretation for this lane should cite selected evidence item IDs,
not raw source URLs, so replay can check the frozen digest context without
promoting upstream repository URLs into authority. Qwen-AgentWorld and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-fixtures`; they do not inherit `skill_route_discovery` or
receive direct documentation, test, code_patch, runtime, provider, external
harness, or remote execution authority before local harness evaluation. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260704T053309`.

For source digest `github-growth-20260704T051308.904452Z`, pass 4 completes the
current `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
`reverse-flow-skill` evidence remains Codex workflow-gate skill evidence under
`p1-skill-route-discovery-codex-workflow`: it selects the local test lane,
records `skill_route_discovery_first`, and keeps install/runtime pressure as
diagnostic-only metadata. `zhengxi-views` remains a generic/source-cited skill
workflow row under `p2-generic-skill-workflow-probe` and selects the
documentation lane.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld`; they do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, or remote execution. The pass-4
handoff now exposes an `operator_recovery_workflow` with rollback-artifact,
focused-validation, supervisor-record-only, and no-kernel-restart gates. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260704T051308`.

For source digest `github-growth-20260704T043308.886255Z`, pass 2 advances the
current `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence:
it enters `p1-skill-route-discovery-codex-workflow` in the local test lane,
records `skill_route_discovery_first`, and validates only the expected skill
metadata shape, routing triggers, and workflow-gate behavior. Upstream install,
script, runtime, provider, external activation, and remote execution pressure
does not become a local lane.

The `zhengxi-views` evidence enters
`p2-generic-skill-workflow-discovery` as a documentation lane for a generic
skill workflow checklist covering topic match, allowed lanes,
`local_validation_required`, and rejection conditions. Qwen-AgentWorld and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld` and
`p4-agent-harness-eval-fundamental-ava`; they do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, or remote execution before a local
harness result exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T043308`.

For source digest `github-growth-20260704T041308.895594Z`, pass 1 opens the
current `skill-route-discovery` slice through
`current_digest_pass1_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence:
it enters `p1-skill-route-discovery-for-codex-workflows` in the local test lane
and must stay discovery-first before any workflow, install, runtime, provider,
or external activation path. The combined reverse-flow and `zhengxi-views`
evidence also feeds `p4-route-classification-regression-fixtures` and
`p5-skill-discovery-to-doc-config-codepatch-contract`, where selected lanes are
limited to test or code_patch and the allowed lane set remains documentation,
config, test, or code_patch only.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p2-agent-harness-eval-gate-for-general-agent-projects`. The
Awesome-Blender-Seedance workflow/usecase repository is routed to
`p3-workflow-usecase-evaluation-lane`: workflow keywords alone do not inherit
`skill_route_discovery`, expose no direct local lanes before harness evaluation,
and may only produce documentation, test, or code_patch work after a local
agent-harness result exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T041308`.

For source digest `github-growth-20260704T033308.879043Z`, pass 3 advances the
current `skill-route-discovery` slice through
`current_digest_pass3_route_to_validation_lane`. The lingbol088-spec
`reverse-flow-skill` repository and the ptrhamon fork are treated as
reverse-flow-style Codex workflow-gate skill evidence because the public shape
exposes `skills/reverse-flow/SKILL.md`, references, scripts, local sandbox/CTF
workflow framing, and install or runtime pressure. That pressure is downgraded
to diagnostics: `p1_reverse_flow_skill_route_discovery` selects the local test
lane, must prove `skill_route_discovery_first`, and may expose only
documentation, config, test, or code_patch.

The same pass keeps `p2_skill_workflow_documentation_gate` documentation-first
for generic/source-cited skill workflow evidence from `zhengxi-views`.
Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows under
`p3_general_agent_harness_eval_fixture`; they do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch work after that bounded
harness result exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T033308`.

For source digest `github-growth-20260704T031308.789628Z`, pass 2 advances the
current `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The reverse-flow skill evidence,
including the lingbol088-spec repository and its Link-Start mirror, and the
`zhengxi-views` Agent Skill evidence are routed through
`p1-skill-route-discovery-index` to prove that skill-term repositories with
`skill_route_discovery` hints expose only documentation, config, test, or
code_patch local lanes. Codex-adjacent reverse-flow evidence also maps to
`p2-codex-workflow-gate-doc`, which records the discover-first,
validate-locally rule before any workflow-gate, install, runtime, provider, or
external activation interpretation.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
The Blender/Seedance workflow-usecase row is routed to
`p4-workflow-usecase-triage-note`. These rows do not inherit
`skill_route_discovery`, have no direct runtime or code_patch lane before a
local harness result, and may only produce documentation, test, or code_patch
work after bounded harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T031308`.

For source digest `github-growth-20260704T023308.798072Z`, pass 4 completes the
current `skill-route-discovery` slice through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
`reverse-flow-skill` evidence is Codex workflow-gate skill evidence: it maps to
`p1-skill-route-discovery-codex-workflow`, selects the local test lane, and must
prove `skill_route_discovery_first` before any secondary workflow, install,
runtime, provider, external activation, or remote-execution interpretation. The
`zhengxi-views` evidence remains a generic/source-cited Skill workflow signal
under `p2-generic-skill-workflow-route-doc`, selecting documentation inside the
documentation, config, test, and code_patch envelope only.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`, have no direct implementation lane
before local harness evaluation, and may only produce documentation, test, or
code_patch work after that bounded evaluation exists. The pass-4 handoff exports
body-free proposal IDs, lane names, hashes, and denial booleans; activation,
restart, push, promotion, and provider execution stay with the external
supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T023308`.

For source digest `github-growth-20260704T015308.851001Z`, pass 2 advances the
current `skill-route-discovery` slice through
`current_digest_pass2_local_validation_lane`. The lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence:
it selects the local test lane, must prove `skill_route_discovery_first`, and
does not grant install, upstream script execution, provider launch, external
skill activation, or remote execution. The `zhengxi-views` evidence is a
generic/source-cited Skill workflow signal and selects the documentation lane
inside the documentation, config, test, and code_patch envelope only.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-trending-agent-projects`, while the workflow-only
Seedance usecase row is routed to `p4-workflow-usecase-evaluation`. These rows
do not inherit `skill_route_discovery`, have no direct runtime or code_patch
lane before a local harness result, and may only produce documentation, test,
or code_patch work after bounded harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T015308`.

For source digest `github-growth-20260704T013308.804283Z`, pass 1 opens the
current skill-route-discovery slice through
`current_digest_pass1_validation_lane`. The leetesla and lingbol088-spec
`reverse-flow-skill` evidence is treated as Codex workflow-gate skill evidence:
it can select the local test lane, must stay inside documentation, config, test,
or code_patch, and does not grant install, runtime execution, provider launch,
external skill activation, or remote execution authority. The generic
skill_workflow handling rule is documentation-first: skill terminology can
propose local docs, config, tests, or code patches only after focused local
validation. Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` backlog rows because they lack direct
skill-workflow route signals; they do not inherit `skill_route_discovery` or
direct implementation lanes before a bounded harness evaluation exists. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260704T013308`.

For source digest `github-growth-20260704T011308.815521Z`, pass 4 completes the
current skill-route-discovery slice through
`current_digest_pass4_completion_handoff`. The `zhengxi-views` evidence is a
source-cited Agent Skill workflow signal because the public repository exposes
`SKILL.md`, `skill.yml`, references, evals, scripts, and an explicit
non-investment-advice boundary; it maps to
`p1-skill-route-discovery-zhengxi-views` in the documentation lane before any
behavior change. The `reverse-flow-skill` evidence is Codex workflow-gate skill
evidence; it maps to `p2-skill-route-discovery-reverse-flow` in the local test
lane, must record `skill_route_discovery_first`, and downgrades install,
runtime, provider, and external activation pressure to diagnostics only.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld`. Qwen-AgentWorld's benchmark and world
model shape can inform a future local harness checklist, but it does not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, remote execution, or activation
authority. The pass-4 operator packet requires rollback metadata and focused
local validation, exports only body-free IDs, hashes, lanes, and denial
booleans, and leaves promotion, push, restart, and activation to the external
supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T011308`.

For source digest `github-growth-20260704T004924.800316Z`, pass 3 advances the
active skill-route-discovery window through
`current_digest_pass3_route_to_validation_lane`. The lingbol088-spec
reverse-flow-skill evidence is treated as a Codex workflow-gate skill signal:
it selects the local test lane, must expose `skill_route_discovery_first`, and
cannot directly enable install, runtime execution, provider launch, external
skill activation, or remote execution. The zhengxi-views evidence remains a
generic/source-cited Agent Skill workflow signal and routes to documentation
before any activation interpretation.

Qwen-AgentWorld, Fundamental-Ava, and the workflow-only Seedance usecase signal
remain adjacent `agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up lanes after a
bounded harness result exists. The pass-3 operator validation packet exports
body-free hashes, IDs, lane names, and denial booleans rather than raw URLs,
replay commands, target paths, upstream bodies, provider inputs, or activation
authority. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704_pass3`.

For source digest `github-growth-20260704T184436.169593Z`, pass 4 completes
the current skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
reverse-flow-skill signal maps to `p1-skill-route-discovery-codex-workflow`
in the local test lane, must prove `skill_route_discovery_first`, and keeps
install or runtime pressure diagnostic only. The zhengxi-views signal maps to
`p2-generic-skill-route-discovery` in the documentation lane because it is a
generic/source-cited skill workflow. Both routes may expose only documentation,
config, test, or code_patch lanes.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`, have no direct local lanes before
local harness evaluation, and cannot enable runtime action, direct code_patch,
provider launch, external harness execution, remote execution, or external
activation. The operator completion packet is body-free and record-only:
rollback metadata, focused validation, route matrices, and denial booleans are
visible for supervisor replay, while raw URLs, replay commands, upstream
bodies, push, promotion, restart, and activation stay outside the kernel.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T184436`.

For source digest `github-growth-20260703T234924.826468Z`, pass 4 completes the
active skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
reverse-flow-skill evidence maps to `p1-skill-route-discovery-reverse-flow` in
the local test lane and must prove `skill_route_discovery_first` before any
secondary Codex workflow, install, runtime, provider, or external activation
interpretation. The zhengxi-views evidence maps to
`p2-skill-route-discovery-zhengxi` in the documentation lane because it is a
generic/source-cited Agent Skill workflow signal. Both rows remain bounded to
documentation, config, test, or code_patch.

The same final handoff keeps agent-apprenticeship, Qwen-AgentWorld, and
Fundamental-Ava behind `p3-agent-harness-eval-general-trends`. They do not
inherit `skill_route_discovery`, have no direct local lanes before harness
evaluation, and cannot enable runtime action, direct code_patch, provider
launch, external harness execution, remote execution, or external activation.
The operator completion packet requires rollback metadata and focused local
validation, exports only body-free lane matrices and hashes, and leaves
promotion, push, restart, and activation to the external supervisor. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260703T234924`.

For source digest `github-growth-20260703T221922.915909Z`, pass 1 opens the
active skill-route-discovery window through
`current_digest_pass1_validation_lane`. The lingbol088-spec reverse-flow-skill
evidence maps to `p1-skill-route-discovery-codex-workflow` in the local test
lane and must record `skill_route_discovery_first` before any secondary Codex
workflow, install, runtime, provider, or external activation interpretation.
The zhengxi-views evidence maps to `p2-generic-skill-workflow-discovery` in the
documentation lane because it is generic/source-cited Agent Skill workflow
evidence. `p4-route-metadata-consistency-check` binds both rows to a local test
lane that verifies route hints, route profiles, selected item IDs, and bounded
local lanes remain metadata only.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p3-agent-harness-eval-for-general-agent-projects`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T221922`.

For source digest `github-growth-20260703T215923.849099Z`, pass 4 completes
the active skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The lingbol088-spec
reverse-flow-skill evidence maps to `p1_skill_route_discovery_reverse_flow` in
the local test lane and must record `skill_route_discovery_first` before any
secondary Codex workflow, install, runtime, provider, or external activation
interpretation. The zhengxi-views signal maps to
`p2_skill_route_discovery_generic` in the documentation lane because its shape
is a generic/source-cited Agent Skill workflow. Both rows remain bounded to
documentation, config, test, or code_patch lanes.

The same completion handoff keeps agent-apprenticeship and Qwen-AgentWorld
behind `p3_agent_harness_eval_trending_agent_projects`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. The
`activation_handoff_contract` is record-only and supervisor-facing: it confirms
the final pass is observed, the capability slice is complete, local validation
is required, and activation remains outside the kernel. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T215923`.

For source digest `github-growth-20260703T205924.382214Z`, pass 1 opens the
active skill-route-discovery window through
`current_digest_pass1_validation_lane`. The lingbol088-spec reverse-flow-skill
signal maps to `p1-skill-route-discovery-codex-workflow` in the local test
lane and must record `skill_route_discovery_first` before any secondary Codex
workflow, install, runtime, provider, or external activation interpretation.
The zhengxi-views signal maps to
`p2-generic-skill-workflow-discovery-doc` in the documentation lane because its
shape is a generic/source-cited skill workflow. Both rows may expose only
documentation, config, test, or code_patch lanes.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p3-agent-harness-eval-fixtures`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. Source URLs are
carried only as frozen fixture inputs; proposal interpretation is based on
selected item IDs and body-free summaries. Replay with:
`python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260703T205924`.

For source digest `github-growth-20260703T203923.819609Z`, pass 4 completes
the active skill-route-discovery window through
`current_digest_pass4_completion_handoff`. TaoDevil and lingbol088-spec
reverse-flow-skill evidence maps to `p3-codex-skill-workflow-probe` in the
local test lane and must record `skill_route_discovery_first` before any
secondary workflow-gate interpretation. The zhengxi-views evidence maps to
`p2-skill-route-discovery-zhengxi` in the documentation lane because the
repository shape is a generic/source-cited skill workflow with citation and
advice-boundary metadata.

The same handoff keeps agent-apprenticeship, Qwen-AgentWorld, and
Fundamental-Ava behind `p1-agent-harness-eval-general-trends`. They do not
inherit `skill_route_discovery`, have no direct local lanes before harness
evaluation, and cannot enable runtime action, direct code_patch, provider
launch, external harness execution, remote execution, or external activation.
The operator completion packet requires rollback metadata and focused
validation, exports only body-free lane matrices and hashes, and leaves
promotion, push, restart, and replay to the external supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T203923`.

For source digest `github-growth-20260703T201923.796362Z`, pass 3 exposes the
active skill-route-discovery window through
`current_digest_pass3_route_to_validation_lane`. TaoDevil and lingbol088-spec
reverse-flow-skill evidence maps to
`p1_skill_route_discovery_codex_workflow_gate` in the local test lane and must
prove `skill_route_discovery_first` before any secondary workflow-gate,
install, runtime, provider, or external activation interpretation. The
zhengxi-views evidence maps to
`p2_skill_route_discovery_generic_workflow` in the documentation lane because
its public shape is a generic/source-cited skill workflow with citation and
advice-boundary metadata. Both rows may expose only documentation, config,
test, or code_patch lanes.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p3_agent_harness_eval_trending_projects`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T201923`.

For source digest `github-growth-20260703T195925.017787Z`, pass 2 exposes the
active skill-route-discovery window through
`current_digest_pass2_local_validation_lane`. The TaoDevil and lingbol088-spec
reverse-flow-skill signals map to `p1_skill_route_discovery_probe` in the local
test lane and must prove `skill_route_discovery_first` before any secondary
workflow, runtime, install, provider, or external activation interpretation.
The zhengxi-views signal maps to `p2_skill_workflow_documentation` as
source-cited skill workflow documentation. Both rows may resolve only to
documentation, config, test, or code_patch lanes.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p3_agent_harness_eval_fixtures`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. Replay with:
`python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260703T195925`.

For source digest `github-growth-20260703T191923.842600Z`, pass 4 completes
the skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill signal maps
to `p1_skill_route_discovery_reverse_flow` in the local test lane and must
record `skill_route_discovery_first` before any secondary workflow or runtime
interpretation. The zhengxi-views signal maps to
`p2_skill_workflow_documentation_lane`, keeping source-cited skill workflow
evidence in documentation-first local validation. Both rows may resolve only to
documentation, config, test, or code_patch lanes.

The same completion handoff keeps agent-apprenticeship, Qwen-AgentWorld, and
Fundamental-Ava behind `p3_general_agent_harness_eval_fixture`. They do not
inherit `skill_route_discovery`, have no direct local lanes before harness
evaluation, and cannot enable runtime action, direct code_patch, provider
launch, external harness execution, remote execution, or external activation.
The operator packet requires rollback metadata and focused validation, exports
only body-free lane matrices and hashes, and leaves promotion, push, restart,
and replay to the external supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T191923`.

For source digest `github-growth-20260703T183923.572332Z`, pass 2 advances the
skill-route-discovery window through `current_digest_pass2_local_validation_lane`.
The reverse-flow-skill signal maps to `p1-skill-route-discovery-reverse-flow`
in the local test lane and must preserve `skill_route_discovery_first` before
any secondary Codex workflow or runtime interpretation. The zhengxi-views
signal maps to `p2-generic-skill-route-discovery` as documentation evidence and
`p4-route-hint-to-lane-config-check` as a config preflight; both stay bounded to
documentation, config, test, and code_patch lanes.

The same lane keeps agent-apprenticeship and Qwen-AgentWorld behind
`p3-agent-harness-eval-fixtures`. They do not inherit `skill_route_discovery`,
have no direct local lanes before harness evaluation, and cannot enable runtime
action, direct code_patch, provider launch, external harness execution, remote
execution, or external activation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T183923`.

For source digest `github-growth-20260703T181923.507461Z`, pass 1 reopens the
skill-route-discovery window through `current_digest_pass1_validation_lane`.
The reverse-flow-skill signal maps to `p1-skill-route-discovery-reverse-flow`
in the local test lane and must report `skill_route_discovery_first` before
any secondary Codex workflow or runtime interpretation. The zhengxi-views
signal maps to `p2-skill-route-discovery-zhengxi` as a documentation lane for
generic, source-cited skill workflow evidence.

The same lane keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p3-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T181923`.

For source digest `github-growth-20260703T175922.824303Z`, pass 4 completes
the current skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill signal maps
to `p2-skill-route-discovery-codex-workflow-gate` in the local test lane only;
the route must record `skill_route_discovery_first` before any secondary
workflow interpretation. The zhengxi-views signal maps to
`p3-skill-route-discovery-generic-workflow` as a documentation-first generic
skill-workflow lane. Both lanes remain bounded to documentation, config, test,
and code_patch validation.

The same handoff keeps agent-apprenticeship, Qwen-AgentWorld, and
Fundamental-Ava behind `p1-agent-harness-eval-general-agent-trends`. They do
not inherit `skill_route_discovery`, have no direct local lanes before harness
evaluation, and cannot enable runtime action, direct code_patch, provider
launch, external harness execution, remote execution, or external activation.
The operator packet requires rollback metadata and focused validation, exports
only body-free lane matrices and hashes, and leaves promotion, push, restart,
and replay to the external supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T175922`.

For source digest `github-growth-20260703T171922.860113Z`, pass 2 exposes the
active skill-route-discovery window through
`current_digest_pass2_local_validation_lane` and
`current_digest_pass2_active_slice_review_lane`. The reverse-flow-skill signal
is treated as Codex workflow-gate evidence for
`p1-skill-route-discovery-fixture` and must record
`skill_route_discovery_first` before any runtime interpretation. The
zhengxi-views signal is routed to `p3-route-hint-docs` and
`p5-skill-workflow-config-preflight`, with the local lane envelope limited to
documentation, config, test, and code_patch.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p2-agent-harness-eval-routing`. They do not inherit
`skill_route_discovery`, have no direct runtime or code_patch route before a
local harness result, and cannot enable provider launch, external harness
execution, remote execution, or external activation. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k 20260703T171922`.

For source digest `github-growth-20260703T165923.653509Z`, pass 1 reopens the
active skill-route-discovery window through
`current_digest_pass1_validation_lane`. The reverse-flow-skill signal is a
Codex-oriented skill workflow gate: it must record
`skill_route_discovery_first`, selects only the local `test` lane, and keeps
unsupported runtime wording out of the controller lane rather than treating it
as activation authority. The zhengxi-views signal documents the decision rule for generic and
source-cited skill evidence: skill-term repositories may enter documentation,
config, test, or code_patch validation lanes only, with runtime action left as
`none` until controller approval and focused local validation pass.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
behind `p3-agent-harness-eval-preflight`. Those general-agent rows do not
inherit `skill_route_discovery`, have no direct local lanes before harness
evaluation, and cannot enable direct runtime, direct code_patch, provider
launch, external harness execution, remote execution, or external activation.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T165923`.

For source digest `github-growth-20260703T163922.937607Z`, pass 4 completes
the active skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill signal is a
Codex-oriented skill workflow gate and maps only to
`p1-skill-route-discovery-codex-workflow-gate` in the local test lane after
recording `skill_route_discovery_first`. The zhengxi-views signal remains the
generic skill-workflow documentation lane under
`p2-generic-skill-workflow-route-doc`; it may propose documentation, config,
test, or code_patch only after local checks.

The same handoff keeps agent-apprenticeship, Qwen-AgentWorld, and
Fundamental-Ava behind `p3-agent-harness-eval-gate`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. The operator
completion packet requires rollback metadata and focused validation, exports a
body-free validation matrix, and leaves restart, promotion, push, and replay to
the external supervisor. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T163922`.

For source digest `github-growth-20260703T161922.895398Z`, pass 3 exposes the
active skill-route-discovery window through
`current_digest_pass3_route_to_validation_lane` and its nested
`pass3_operator_validation_packet`. The reverse-flow-skill item is treated as
Codex workflow-gate evidence and must record `skill_route_discovery_first`
before any secondary workflow or runtime interpretation; it selects the local
test lane only inside the documentation, config, test, and code_patch envelope.
The zhengxi-views item is routed to
`p2_skill_route_discovery_documentation_lane` so source-cited skill workflow
handling is documented before activation.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
as adjacent `agent_harness_eval_required` rows under
`p3_general_agent_harness_eval_tests`. They do not inherit
`skill_route_discovery`, have no direct runtime or code_patch route before a
local harness result, and cannot enable provider launch, external harness
execution, remote execution, or external activation. The pass-3 packet exports
body-free IDs, hashes, lane names, and denial booleans rather than raw URLs,
replay commands, target paths, upstream bodies, or activation authority. Replay
with: `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260703T161922`.

For source digest `github-growth-20260703T153924.100531Z`, pass 1 exposes the
active skill-route-discovery window through
`current_digest_pass1_validation_lane`. The Codex-oriented
`reverse-flow-skill` signal is routed through `p1-skill-route-discovery-codex-gate`
and must prove `skill_route_discovery_first` before broader agent or workflow
handling. The generic `zhengxi-views` Agent Skill signal is routed through
`p2-generic-skill-route-discovery-fixture`, with local lanes limited to
documentation, config, test, and code_patch.

The same pass keeps agent-apprenticeship and Qwen-AgentWorld as adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`, have no direct runtime or
code_patch route before local harness evaluation, and cannot enable provider
launch, external harness execution, remote execution, or external activation.
Replay with: `python -m pytest tests/test_harness_eval.py -q -k 20260703T153924`.

For source digest `github-growth-20260703T145923.276089Z`, pass 3 exposes the
active skill-route-discovery window through
`current_digest_pass3_activation_review_lane`. The reverse-flow-skill fork
cluster remains Codex workflow-gate evidence only: it must record
`skill_route_discovery_first`, selects the local test lane, carries unsupported
install/runtime pressure as downgraded evidence, and stays bounded to
documentation, config, test, and code_patch before any secondary workflow
interpretation. The zhengxi-views source-cited Agent Skill row also selects the
test lane for generic skill-term routing validation, with citation and advice
boundaries preserved as route metadata rather than activation authority.

The same pass keeps agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava
as adjacent `agent_harness_eval_required` rows under
`p3_agent_harness_eval_general_projects`. They do not inherit
`skill_route_discovery`, have no direct local lane before harness evaluation,
and cannot enable direct runtime, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. The lane includes
an `operator_recovery_packet` requiring a rollback ref, rollback artifact,
changed-file review, and focused local validation before pass 4. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T145923`.

For source digest `github-growth-20260703T151923.811435Z`, pass 4 completes
the same window through `current_digest_pass4_completion_handoff`. The Kylin2021,
lingbol088-spec, and poker117 reverse-flow-skill rows are correlated Codex skill
workflow evidence, not install or runtime authority: the selected lane remains
`test`, `skill_route_discovery_first` is required, and install/runtime pressure
is exported only as a downgrade signal. The generic zhengxi-views skill workflow
row remains documentation-first, bounded to documentation, config, test, and
code_patch after local validation.

The final handoff also carries agent-apprenticeship, Qwen-AgentWorld, and
Fundamental-Ava as adjacent `agent_harness_eval_required` rows. They do not
inherit `skill_route_discovery`, have no direct lanes before harness evaluation,
and cannot enable runtime action, direct code_patch, provider launch, external
harness execution, remote execution, or external activation. The operator
completion packet requires rollback metadata and focused validation and exports
hashes, lane names, IDs, and booleans rather than raw URLs, replay commands,
target paths, upstream bodies, or runtime tokens. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k current_digest_20260703T151923`.

For source digest `github-growth-20260703T143923.402501Z`, pass 2 exposes the
active skill-route-discovery window through
`current_digest_pass2_local_validation_lane`. The Kylin2021, lingbol088-spec,
and poker117 `reverse-flow-skill` fork cluster is treated as correlated Codex
workflow-gate evidence, not as install or runtime authority: the selected lane
is `test`, `skill_route_discovery_first` remains required, and unsupported
install/runtime pressure is downgraded. The `zhengxi-views` source-cited Agent
Skill item takes the documentation lane so its decision path, citation boundary,
advice boundary, and uncertainty stay visible before activation.

The same pass keeps Qwen-AgentWorld and Fundamental-Ava as adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`, and they cannot select direct
runtime, direct code_patch, provider launch, external harness execution, remote
execution, or external activation before local harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T143923`.

For source digest `github-growth-20260703T141923.320717Z`, pass 1 groups the
Kylin2021, lingbol088-spec, and poker117 `reverse-flow-skill` fork evidence as
one Codex/generic skill-route validation lane. The upstream shape exposes AI
Agent/Codex skill packaging, `skills/reverse-flow/SKILL.md`, scripts, local
sandbox/CTF framing, and install/runtime wording, so the local route selects
only the test lane from documentation, config, test, and code_patch while
downgrading unsupported activation pressure. `zhengxi-views` remains a
documentation-first source-cited skill workflow row. Qwen-AgentWorld and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows with no
direct local lanes before harness evaluation. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T141923`.

For source digest `github-growth-20260703T135922.969245Z`, pass 4 completes
the skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The handoff adds an
operator-visible `validation_lane_matrix`: reverse-flow-style Codex skill
workflow evidence stays in the local test lane after
`skill_route_discovery_first`; generic skill-workflow evidence stays in the
documentation lane; and general agent projects without skill-workflow signals
stay in `agent_harness_eval_required` with no direct local lane before harness
evaluation. The exported handoff is body-free and keeps runtime action,
external activation, provider launch, external harness execution, remote
execution, raw URL export, replay-command export, target-path export, and
upstream-body export denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k current_digest_20260703T135922`.

For source digest `github-growth-20260703T115316.886295Z`, pass 3 now replays
the active skill-route-discovery window through
`current_digest_pass3_route_to_validation_lane`. The Codex-oriented
`reverse-flow-skill` row exposes `route_probe_decisions` and
`skill_route_discovery_first`, then selects only the local test lane from the
bounded documentation, config, test, and code_patch set. The generic
`zhengxi-views` skill workflow row remains documentation-lane evidence until
local validation justifies more.

The same pass keeps Qwen-AgentWorld and Fundamental-Ava as adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`, and they have no direct runtime,
direct code_patch, provider launch, external harness execution, remote
execution, or external activation path before local harness evaluation. Replay
with: `python -m pytest tests/test_skill_routing.py -q -k 20260703T115316`.

For source digest `github-growth-20260703T094050.021818Z`, pass 2 now routes the
active skill-route discovery proposals through
`current_digest_pass2_local_validation_lane`. The Codex-oriented
`reverse-flow-skill` row must prove `skill_route_discovery_first` under the
`codex_workflow_gate` profile before any workflow handling, while
`zhengxi-views` validates the generic skill workflow fixture path. Both rows are
bounded to documentation, config, test, and code_patch lanes; the selected local
lane is test, local validation remains required, and final implementation scope
is still controller-recomputed after review.

The same pass keeps Qwen-AgentWorld and Fundamental-Ava as adjacent
`agent_harness_eval_required` rows. They do not inherit `skill_route_discovery`
and cannot produce direct implementation, runtime, provider, external harness,
or remote-execution proposals until a local agent-harness fixture records
capability, safety, rollback, and validation coverage. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260703T094050`.

For source digest `github-growth-20260703T102050.412488Z`, pass 4 now closes
the active skill-route-discovery window through
`current_digest_pass4_completion_handoff`. The reverse-flow-skill evidence is
kept in the local test lane under the `codex_workflow_gate` profile and must
record `skill_route_discovery_first` before any secondary workflow handling.
The zhengxi-views evidence is kept in the documentation lane with source
citation and advice-boundary validation. Qwen-AgentWorld is kept as an adjacent
`agent_harness_eval_required` row: it does not inherit `skill_route_discovery`
and has no direct runtime or code_patch lane before local harness evaluation.
The handoff exports only body-free IDs, hashes, profiles, and lane names, while
external skill activation, external agent activation, provider launch, external
harness execution, remote execution, raw URL export, replay-command export,
target-path export, and upstream-body export remain denied. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k current_digest_20260703T102050`.

For source digest `github-growth-20260703T084049.971768Z`, pass 3 now exposes
`current_pass3_operator_validation_gate` inside the route readiness index. The
gate is body-free and uses selected `item_id` values only. A Codex-oriented
skill repository such as `reverse-flow-skill` must confirm
`skill_route_discovery_first` before any workflow, runtime, or secondary
agent-harness interpretation; the only eligible local lanes remain
documentation, config, test, and code_patch, with runtime action set to `none`.

The same gate keeps generic Agent Skill evidence such as `zhengxi-views` in the
bounded skill-route validation envelope and keeps general-agent items such as
Qwen-AgentWorld and Fundamental-Ava behind `agent_harness_eval_required`.
Adjacent agent rows do not inherit `skill_route_discovery`, and they do not
enable provider launch, external harness execution, remote execution, external
skill or agent activation, raw source URL export, raw evidence URL export, or
upstream-body export before a local harness result exists.

For source digest `github-growth-20260703T082050.341048Z`, pass 2 of the
current skill-route-discovery window is replayed by
`skill_route_discovery_current_digest_20260703T082050_pass2_validation_lane`.
The reviewed reverse-flow-skill evidence is treated as a Codex workflow gate
because its public shape exposes Agent/Codex skill packaging, a
`skills/reverse-flow/SKILL.md` layout, scripts, local sandbox/CTF/crackme
framing, and install/runtime pressure. That pressure is downgraded; the only
accepted local lanes remain documentation, config, test, and code_patch, with
local validation required and runtime action set to `none`.

The same pass keeps zhengxi-views as generic/source-cited skill-workflow
evidence. Its `SKILL.md`, `skill.yml`, references, evals, scripts, citation
boundary, and advice disclaimer are useful route signals, but they do not
authorize runtime adoption, provider launch, external skill activation, raw
upstream export, or direct install. Adjacent general-agent proposals such as
Qwen-AgentWorld and Fundamental-Ava remain behind `agent_harness_eval_required`
with no implementation lane selected until local harness evidence exists.

For the `github-growth-20260703T025735.929695Z` pass-3 lane, Codex-adjacent
skill repositories use a discovery-first interpretation. `reverse-flow-skill`
and `zhengxi-views` remain `skill_route_discovery` evidence only, with follow-up
limited to documentation, config, test, or code_patch after local validation.
The Codex workflow-gate row records `skill_route_discovery_first` before any
local workflow change. General agent or workflow-only repositories such as
Qwen-AgentWorld, Fundamental-Ava, and Awesome-Blender-Seedance-Workflow-Usecases
stay in `agent_harness_eval_required` with no direct implementation lane until
a local harness evaluation result exists.

For the `github-growth-20260703T040049.885608Z` pass-1 lane, the same split is
reopened as a bounded local validation lane. A repository summary carrying
agent, Codex, skill, and workflow signals maps to the `codex_workflow_gate`
profile only after `skill_route_discovery_first` is recorded; its allowed local
lanes remain documentation, config, test, and code_patch, with test selected for
the focused validation pass. Generic skill-workflow evidence is documentation
triage unless a later local validation result justifies another bounded lane.
General agent project trends such as Qwen-AgentWorld and Fundamental-Ava remain
adjacent `agent_harness_eval_required` rows and do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch routing,
provider launch, external harness execution, remote execution, or external
agent activation before local harness evaluation.

For the `github-growth-20260703T060050.289743Z` pass-3 lane, the current
reverse-flow evidence is exposed through
`current_digest_pass3_route_to_validation_lane` rather than a standalone
fixture. The repository trend and its issue warning are folded into the same
body-free reverse-flow candidate, selecting a local test lane for
`p1-skill-route-discovery-reverse-flow` and recording verification uncertainty
before any implementation route. Generic skill-workflow evidence from
reverse-flow-skill and zhengxi-views remains bounded to documentation, config,
test, or code_patch through `p2-generic-skill-route-discovery-fixture`.
Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and
Fundamental-Ava stay in `agent_harness_eval_required` under
`p3-agent-harness-eval-general-projects`; they do not inherit
`skill_route_discovery`, direct runtime, direct code_patch, provider launch,
external harness execution, or remote execution before local harness
evaluation.

For the `github-growth-20260703T064052.697831Z` pass-1 lane, the carried
reverse-flow-skill fork cluster is treated as correlated route pressure, not as
extra implementation authority. The chishubiao, kaijiang666, lanmomoling, and
lingbol088-spec rows expose the same public Codex/AI Agent skill-package shape:
`skills/reverse-flow/SKILL.md`, local sandbox or CTF reverse-analysis framing,
scripts, and workflow-gate language. The local lane selects `test` for
`p1_reverse_flow_skill_route_discovery` and records unsupported install,
provider-runtime, or runtime-execution pressure as downgraded lanes only. Fork
activity does not authorize installing, executing, provider launch, external
skill activation, external harness execution, remote execution, raw URL export,
or upstream-body export.

The same pass keeps zhengxi-views in
`p2_zhengxi_views_skill_probe` as documentation-first skill-route evidence
before any config or code change. Awesome-Blender-Seedance-Workflow-Usecases,
Qwen-AgentWorld, and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows; workflow-only or general-agent evidence
does not inherit `skill_route_discovery`, and only documentation, test, or
code_patch may be considered after local harness evaluation.

For the `github-growth-20260703T070049.855381Z` pass-2 lane, the same fork
cluster is promoted from first-pass route pressure into a replayable local
validation lane. `p1-skill-route-discovery-codex-workflow` selects the local
test lane only after the candidate records expose `skill_route_discovery_first`
for the Codex workflow gate. `p2-generic-skill-route-discovery` records the
generic skill-workflow path as documentation-first: sufficient evidence is a
body-free repository summary, selected digest item IDs or a frozen fixture,
route profiles, bounded lane inventory, downgraded unsupported lane pressure,
and a focused local validation result. The only follow-up lanes remain
documentation, config, test, and code_patch.

The pass-2 surface keeps Qwen-AgentWorld and Fundamental-Ava in
`p3-agent-harness-eval-baseline`, and the workflow-only Seedance usecase row in
`p4-workflow-agent-eval-lane`. Those rows do not inherit skill-route discovery,
have no direct implementation lane before local harness evaluation, and do not
authorize runtime action, install, provider launch, external skill activation,
external harness execution, remote execution, raw source URL export, raw replay
command export, or upstream-body export.

Source digest `github-growth-20260703T074049.962015Z` completes the four-pass
window with an operator-visible pass-4 handoff. The reverse-flow-skill fork
cluster is treated as correlated Codex skill-route evidence, not as additional
runtime authority: every fork row must begin at `skill_route_discovery_first`
and remain inside documentation, config, test, or code_patch lanes with local
validation required. The codex workflow-gate documentation lane records the
interpretation path before any workflow behavior is changed.

The same closure keeps zhengxi-views as generic/source-cited skill-workflow
evidence and keeps Qwen-AgentWorld in `agent_harness_eval_required`. General
agent projects do not inherit `skill_route_discovery`, and they have no direct
runtime or code_patch lane before local harness evaluation; only documentation,
test, or code_patch may be considered after that evaluation is represented.

Source digest `github-growth-20260702T152626.587436Z` starts pass 1 of the
active `skill-route-discovery` window with a digest-specific replay lane for the
current proposal IDs. The zhengxi-views signal is treated as public Agent Skill
route evidence because the repository shape exposes `SKILL.md`, `skill.yml`,
references, evals, scripts, source-citation workflow boundaries, and
non-investment-advice limits. That evidence maps to
`p1-skill-route-discovery-zhengxi-views` in the local test lane only inside the
bounded documentation, config, test, and code_patch envelope.

Qwen-AgentWorld and its fork signal are treated as duplicate ecosystem evidence
for the same general-agent evaluation lane, not as separate implementation
targets. Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows; they do not inherit `skill_route_discovery`
and cannot select documentation, test, code_patch, runtime, provider, external
harness, or remote-execution follow-up before local harness evaluation. The
Fundamental-Ava documentation row records the required pre-implementation
checklist: runnable surface, configuration assumptions, tool-routing
implications, rollback path, and non-network validation.

Source digest `github-growth-20260702T154626.821848Z` advances pass 2 of the
active window with `current_digest_pass2_local_validation_lane`. The
zhengxi-views RepositoryTrend remains the only direct
`skill_route_discovery` candidate because its public shape includes `SKILL.md`,
`skill.yml`, references, evals, scripts, source-citation workflow boundaries,
and non-investment-advice limits. It maps to `p1-skill-route-discovery-lane`
in the local test lane only, while the complete lane envelope stays limited to
documentation, config, test, and code_patch.

Qwen-AgentWorld and Fundamental-Ava are carried as adjacent
`agent_harness_eval_required` rows under
`p2-agent-harness-eval-for-general-agent-trends` and
`p3-agent-harness-fixture-coverage`. They do not inherit
`skill_route_discovery`, do not select direct runtime or direct code_patch
routes, and require local harness evaluation before documentation, test, or
code_patch follow-up can be chosen. The pass-2 surface exports bounded route
metadata and hashes only; raw source URLs, raw evidence URLs, replay commands,
target paths, upstream bodies, provider launch, external harness execution,
remote execution, and external skill or agent activation remain denied.

Source digest `github-growth-20260702T175118.267162Z` advances pass 3 of the
active window with `current_digest_pass3_activation_review_lane`. The
zhengxi-views signal is still the only direct `skill_route_discovery` candidate:
its public repository shape exposes `SKILL.md`, `skill.yml`, references, evals,
scripts, source-citation workflow boundaries, and non-investment-advice limits.
It maps to `p1_skill_route_discovery_zhengxi_views` in the local test lane only,
inside the bounded documentation, config, test, and code_patch envelope.

Qwen-AgentWorld, Fundamental-Ava, looper, and workflow-only usecase evidence
remain adjacent `agent_harness_eval_required` rows under
`p2_agent_harness_eval_fixture_general_agent_projects`. They do not inherit
`skill_route_discovery`; their direct lanes before harness evaluation are empty,
and only documentation, test, or code_patch can be considered after local
agent-harness evaluation. Workflow topic matches alone are recorded by
`p3_workflow_agent_harness_eval` as documentation triage, not runtime workflow
adoption, provider launch, external harness execution, remote execution, or raw
upstream export.

Source digest `github-growth-20260702T191118.378892Z` continues pass 3 of the
active window with an operator-visible activation review lane for the current
proposal IDs. The zhengxi-views evidence remains the only direct
`skill_route_discovery` row because the public repository shape contains an
Agent Skill manifest, skill markdown, references, scripts, evals,
source-citation boundaries, and non-investment-advice limits. It maps to
`p1_skill_route_discovery_zhengxi_views` in the local test lane only, inside
the bounded documentation, config, test, and code_patch envelope.

Qwen-AgentWorld, Fundamental-Ava, looper, and the workflow-only Seedance usecase
repository are grouped behind `p2_agent_harness_eval_general_agent_projects` as
adjacent `agent_harness_eval_required` evidence. They do not inherit
`skill_route_discovery`; their direct lanes before harness evaluation remain
empty, and only documentation, test, or code_patch can be considered after a
local agent-harness result exists. The Seedance workflow-usecase proposal is
recorded separately as `p3_workflow_adjacent_agent_eval_seedance` documentation
triage, not as runtime workflow adoption, provider launch, external harness
execution, remote execution, or raw upstream export.

Source digest `github-growth-20260702T181118.185142Z` completes pass 4 of the
same window with `current_digest_pass4_completion_handoff`. The pass closes
zhengxi-views through `p1_skill_route_discovery_lane` in the local test lane and
keeps the allowed lane envelope limited to documentation, config, test, and
code_patch.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`agent_harness_eval_required` evidence under `p2_agent_harness_eval_fixture`.
The Awesome-Blender-Seedance-Workflow-Usecases item is recorded only as a
workflow-keyword boundary for `p3_workflow_agent_eval_documentation`: a workflow
topic without a skill-route hint or skill layout signal is insufficient for
`skill_route_discovery` and must pass local agent-harness evaluation before any
documentation, test, or code_patch follow-up is selected.

Source digest `github-growth-20260702T162626.606010Z` completes pass 4 of the
same `skill-route-discovery` window with an explicit
`current_digest_pass4_completion_handoff`. The zhengxi-views trend remains the
only direct `skill_route_discovery` candidate and closes through local test plus
documentation lanes inside the documentation, config, test, and code_patch
envelope.

Qwen-AgentWorld and Fundamental-Ava stay as adjacent
`agent_harness_eval_required` rows, with direct runtime and direct code_patch
routes disabled until a local harness evaluation exists. The
Awesome-Blender-Seedance-Workflow-Usecases signal is recorded as a workflow-only
repository boundary: a workflow keyword without an explicit skill-route hint
does not bypass `agent_harness_eval_required`, does not activate runtime
workflow adoption, and does not authorize provider launch, external harness
execution, remote execution, or raw upstream export.

Source digest `github-growth-20260702T070714.706511Z` completes the active
pass-4 lane for `p1-skill-route-discovery-agent-skills`,
`p2-agent-harness-eval-gate`, and `p3-route-hint-docs`. The selected skill
workflow item IDs `trend:NVIDIA-BioNeMo/bionemo-agent-toolkit-1` and
`trend:lyra81604/zhengxi-views-1` may map only to documentation, config, test,
or code_patch candidates, with this completion surface selecting test plus
documentation. Unsupported pressure such as install, runtime execution, or
provider runtime is recorded only as downgraded lane pressure.

The general-agent item IDs `trend:QwenLM/Qwen-AgentWorld-1` and
`trend:TianhangZhuzth/Fundamental-Ava-1` remain in
`agent_harness_eval_required` under `p2-agent-harness-eval-gate`. They do not
inherit `skill_route_discovery`, and they have no direct documentation, config,
test, code_patch, runtime, provider, external harness, or remote-execution route
until a local agent harness evaluation selects a bounded follow-up lane.

Source digest `github-growth-20260702T082714.780681Z` completes pass 4 of the
active `skill-route-discovery` window with an operator-visible completion
handoff for the carried proposal names. zhengxi-views closes through the local
test lane as source-cited skill-route evidence, while BioNeMo Agent Toolkit
closes through the documentation lane as toolkit-style skill catalog evidence.
Both rows remain bounded to documentation, config, test, or code_patch, require
local validation, and deny install, runtime execution, provider launch,
external skill activation, external agent activation, external harness
execution, remote execution, raw URL export, replay-command export, target-path
export, and upstream-body export.

The same handoff records Qwen-AgentWorld and Fundamental-Ava as adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery`, and no direct documentation, test, code_patch, runtime,
provider, external harness, or remote-execution follow-up is selected before a
local agent harness evaluation exists. Repeated forks of
`Awesome-Blender-Seedance-Workflow-Usecases` are exposed only as a weak workflow
popularity cluster: the cluster is an aggregate demand signal, contributes zero
independent implementation evidence, increments no candidate lane counts, and
requires a local validation lane before any action.

Source digest `github-growth-20260702T074714.911556Z` advances pass 2 of the
active `skill-route-discovery` window with the current proposal names:
`p1-skill-route-discovery-zhengxi-views`,
`p2-skill-route-discovery-bionemo-toolkit`,
`p3-agent-harness-eval-general-projects`, and
`p4-route-policy-doc-clarification`. The pass keeps zhengxi-views and BioNeMo
Agent Toolkit as skill/workflow route evidence only. zhengxi-views contributes
`SKILL.md`, `skill.yml`, references, scripts, evals, citation boundaries, and a
non-investment-advice limit; BioNeMo contributes skill directories, workflow
directories, plugin marketplace metadata, and `skills.sh.json` catalog signals.
Those signals may map only to documentation, config, test, or code_patch local
lanes, with local validation required before any activation review.

Qwen-AgentWorld and Fundamental-Ava remain adjacent general-agent evidence under
`p3-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery` and cannot jump directly to documentation, config, test,
code_patch, runtime, provider launch, external harness execution, remote
execution, raw URL export, replay-command export, target-path export, or
upstream-body export before a local `agent_harness_eval_required` path succeeds.

Source digest `github-growth-20260702T052715.136537Z` continues pass 3 of the
active `skill-route-discovery` window with selected item IDs
`trend:NVIDIA-BioNeMo/bionemo-agent-toolkit-1` and
`trend:lyra81604/zhengxi-views-1` as bounded discovery input only. BioNeMo's
agent skill catalog, plugin marketplace, workflow directory, and `skills.sh.json`
signals map to the local test lane; zhengxi-views' `SKILL.md`, `skill.yml`,
references, scripts, evals, citation boundaries, and non-investment-advice
limits map to the local test lane plus a documentation boundary. Neither item is
permission to install, import, execute, launch a provider, export raw upstream
material, or activate an external skill. The only skill-route lanes available
from these signals remain documentation, config, test, and code_patch, and each
lane requires focused local validation before activation review.

Qwen-AgentWorld and Fundamental-Ava remain adjacent general-agent trend evidence
for this digest. They are queued for `agent_harness_eval_required` before any
documentation, test, code_patch, runtime, provider, external harness, or remote
execution path can be selected, and they do not inherit `skill_route_discovery`
from the BioNeMo or zhengxi rows.

Source digest `github-growth-20260702T064714.829371Z` continues pass 3 with an
operator-visible validation-before-activation surface for the current proposal
names. zhengxi-views is treated as source-cited Agent Skill evidence because the
public repository exposes `SKILL.md`, `skill.yml`, references, scripts, evals,
citation boundaries, and a non-investment-advice limit. It may map only to the
bounded documentation, config, test, or code_patch envelope, with this pass
selecting the local test lane and requiring focused local validation before any
activation review.

BioNeMo Agent Toolkit is treated as skill/workflow route evidence because the
public repository presents agent skill catalogs, workflow directories, plugin
marketplace metadata, and `skills.sh.json`. This pass selects documentation for
the BioNeMo handling contract; the allowed local lanes remain only
documentation, config, test, and code_patch, and no install, import, provider
launch, external skill activation, external harness execution, or runtime action
is implied.

Qwen-AgentWorld and Fundamental-Ava remain adjacent `general_agent_project`
evidence under `p3-agent-harness-eval-general-projects`. Before local harness
evaluation, their direct allowed lanes are empty: they do not inherit
`skill_route_discovery` and cannot jump directly to documentation, test,
code_patch, config, runtime, provider, external harness, or remote-execution
work. After harness evidence exists, the only follow-up lane inventory exposed by
this surface is documentation, test, or code_patch.

Source digest `github-growth-20260702T062714.806950Z` continues pass 2 of the
active `skill-route-discovery` window with a replayable local validation lane
for the current proposal names. BioNeMo Agent Toolkit and zhengxi-views are
interpreted as public skill-workflow evidence only: BioNeMo contributes skill
directories, plugin marketplace metadata, workflow directories, and a
`skills.sh.json` catalog, while zhengxi-views contributes `SKILL.md`,
`skill.yml`, references, scripts, evals, source-citation boundaries, and
non-investment-advice limits. The pass maps `p1_skill_route_discovery_docs_tests`
to the local test lane and `p3_route_metadata_documentation` to the
documentation lane, with the global lane envelope still limited to
documentation, config, test, and code_patch.

Qwen-AgentWorld and Fundamental-Ava are held as adjacent
`general_agent_project` evidence under `p2_agent_harness_eval_cluster`. Their
general-agent benchmark, autonomous-agent, and simulation signals require a
separate local `agent_harness_eval_required` replay before any documentation,
test, code_patch, runtime, provider, external harness, or remote-execution
follow-up can be selected. This pass explicitly denies runtime action, upstream
skill or agent activation, provider launch, external harness execution, remote
execution, raw URL export, replay-command export, target-path export, and
upstream-body export.

Source digest `github-growth-20260702T054714.674075Z` completes pass 4 of the
active `skill-route-discovery` window with
`current_digest_20260702T054714_pass4_completion_handoff`. BioNeMo Agent Toolkit
and zhengxi-views are frozen as the two skill-adjacent repository fixtures for
`p1-skill-route-discovery-trending-skill-repos`: BioNeMo contributes public
agent-skill catalog, plugin marketplace, workflow directory, and `skills.sh.json`
signals, while zhengxi-views contributes Agent Skill, source-citation,
validation, manifest, and non-advice boundary signals. The completion handoff
may select only documentation, config, test, or code_patch local lanes; this pass
selects test plus the documentation policy row
`p3-route-hint-policy-documentation`.

Qwen-AgentWorld and Fundamental-Ava are kept as adjacent
`general_agent_project` evidence under
`p2-agent-harness-eval-for-general-agent-projects`. They remain
`agent_harness_eval_required` before any documentation, test, code_patch,
runtime, provider, external harness, remote execution, raw URL export, replay
command export, or upstream-body export path can be selected. This closes the
four-pass slice as a supervisor replay surface, not as upstream skill
activation.

Source digest `github-growth-20260702T040714.731937Z` advances pass 3 of the
active `skill-route-discovery` window with an operator-visible activation
review lane for the current proposals. zhengxi-views and BioNeMo Agent Toolkit
remain separate skill-route rows in the local test lane: zhengxi-views carries
generic plus source-cited workflow profiles, while BioNeMo carries the toolkit
skill-catalog profile. Both may select only documentation, config, test, or
code_patch and require local validation before any activation handoff.

Qwen-AgentWorld and Fundamental-Ava remain adjacent general-agent evidence under
`p3-agent-harness-eval-general-projects`. They do not inherit
`skill_route_discovery` and cannot receive direct runtime, direct code_patch,
provider launch, external harness execution, remote execution, raw URL export,
replay-command export, or upstream-body export before local harness evaluation.

Source digest `github-growth-20260702T044714.817246Z` starts pass 1 of the next
active `skill-route-discovery` window with a replayable validation lane for the
current proposal IDs. BioNeMo Agent Toolkit maps to
`p1-skill-route-discovery-agent-skills` in the local test lane from selected
item ID evidence. The route-decision documentation row
`p3-route-decision-docs-for-trend-digests` may cite only selected item IDs and
frozen body-free summaries while explaining why BioNeMo and zhengxi-views are
bounded skill-route evidence.

Qwen-AgentWorld and Fundamental-Ava stay adjacent under
`p2-agent-harness-eval-trending-agent-projects`. They require
`agent_harness_eval_required` before documentation, test, code_patch, runtime,
provider, external harness, or remote execution work is selected, and they do
not inherit `skill_route_discovery` from the skill-route rows.

Source digest `github-growth-20260702T050714.674520Z` advances pass 2 of the
active window by making the Python skill-route and general-agent split
replayable for the current proposal names. BioNeMo Agent Toolkit and
zhengxi-views are the two skill-workflow records: their explicit skill terms,
catalog or `SKILL.md` layout, validation scripts, and metadata signals select
only local documentation and test lanes inside the documentation, config, test,
or code_patch envelope. Local validation remains required before activation.

Qwen-AgentWorld, Fundamental-Ava, and looper are separate
`general_agent_project` evidence in this pass. Without skill workflow route
hints or a local harness result, they stay in
`agent_harness_eval_required` under
`p2-agent-harness-eval-fixture-general-projects`; they do not inherit
`skill_route_discovery` and cannot receive direct runtime, direct code_patch,
provider launch, external harness execution, remote execution, raw URL export,
replay-command export, or upstream-body export before harness criteria pass.
This split is not safety review because the evidence is public repository
routing metadata and no offensive behavior, unauthorized access, or privacy
leakage route is selected.

Source digest `github-growth-20260702T034714.900431Z` continues pass 2 of the
active `skill-route-discovery` window with an operator validation manifest for
the two current skill-term trend items. BioNeMo Agent Toolkit and zhengxi-views
enter only as bounded skill-route evidence, with allowed local lanes limited to
documentation, config, test, or code_patch and local validation required before
any activation handoff.

Qwen-AgentWorld and Fundamental-Ava remain adjacent general-agent project
evidence in this pass. They require `agent_harness_eval_required` before any
documentation, test, code_patch, runtime, provider, external harness, or remote
execution path is selected; they do not inherit `skill_route_discovery` from the
skill-term rows.

Source digest `github-growth-20260702T030714.684585Z` completes pass 4 of the
active `skill-route-discovery` window with a candidate-specific completion
handoff. The pass keeps zhengxi-views and BioNeMo Agent Toolkit as separate
skill-route rows even though both include `generic_skill_workflow` signals:
zhengxi-views closes through the source-cited domain-research test lane, while
BioNeMo closes through a toolkit-style skill catalog test lane. Both rows remain
limited to documentation, config, test, or code_patch and require focused local
validation before any supervisor replay.

Qwen-AgentWorld and Fundamental-Ava remain adjacent `agent_harness_eval_required`
evidence in this completion handoff. They do not inherit `skill_route_discovery`,
direct runtime routing, direct code_patch authority, provider launch, external
harness execution, remote execution, raw URL export, replay-command export, or
upstream-body export before a separate local harness evaluation exists.

Source digest `github-growth-20260702T022714.857893Z` advances pass 2 of the
active `skill-route-discovery` window with a body-free local validation handoff.
BioNeMo-style agent skill evidence enters through generic skill workflow
signals: skill directories, agent/plugin marketplace metadata, workflow
directories, and a `skills.sh.json` catalog. zhengxi-views contributes the
source-cited Agent Skill variant with `SKILL.md`, manifest, references, scripts,
evals, citation boundaries, and non-investment-advice limits.

The pass-2 lane maps those skill rows only to documentation, config, test, or
code_patch; install, runtime execution, provider launch, raw URL export, replay
command export, target-path export, and upstream-body export remain denied.
Qwen-AgentWorld and Fundamental-Ava remain adjacent general-agent project
evidence under `agent_harness_eval_required`. They do not inherit
`skill_route_discovery`, direct runtime routing, or direct code_patch authority
before a separate local harness evaluation selects a bounded follow-up lane.

Source digest `github-growth-20260702T005748.786759Z` completes the current
four-pass `skill-route-discovery` window with a pass-4 handoff and final
closure packet. The two skill-term repository items,
`trend:NVIDIA-BioNeMo/bionemo-agent-toolkit-1` and
`trend:lyra81604/zhengxi-views-3`, may close only through bounded local
documentation and test lanes; install, provider runtime, runtime execution, raw
URL export, upstream body export, and external activation remain denied.

`trend:QwenLM/Qwen-AgentWorld-5` and
`trend:TianhangZhuzth/Fundamental-Ava-4` stay adjacent as
`agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
provider launch, external harness execution, or remote execution before a local
agent harness evaluation selects a bounded follow-up lane.

Source digest `github-growth-20260701T235748.704258Z` opens pass 1 of the
active window by binding the carried proposal IDs `p1` through `p5` to a
current validation lane. zhengxi-views is the only skill-route candidate in
this pass: focused review shows a public Agent Skill package shape with
`SKILL.md`, `skill.yml`, references, scripts, evals, source-citation
boundaries, and a non-investment-advice limit. It may select only bounded local
documentation, config, test, or code_patch lanes, with the local test lane used
for `p1-skill-route-discovery-zhengxi-views`.

Qwen-AgentWorld and Fundamental-Ava remain general-agent project evidence
without skill route hints or a local harness result. They stay in
`agent_harness_eval_required` before any follow-up lane is selected.
open-reverselab is retained as review-only automation/reverse-engineering
context at the offensive-behavior boundary. This pass denies runtime action,
external skill or agent activation, external harness execution, provider
launch, remote execution, raw URL export, replay-command export, target-path
export, and upstream-body export.

Source digest `github-growth-20260701T223748.552762Z` opens pass 1 of the
active `skill-route-discovery` window with a bounded local validation lane for
the carried proposal IDs. Focused public review keeps zhengxi-views as the only
skill-route candidate because its repository metadata exposes Agent Skill
structure such as `SKILL.md`, `skill.yml`, `references/`, `scripts/`, and
`evals/`, plus source-citation and non-investment-advice boundaries. It maps to
`p1-skill-route-discovery-zhengxi-views` in the local test lane, while
`p3-agent-harness-eval-fundamental-ava-looper` records the documentation
boundary. Both rows remain bounded to documentation, config, test, or
code_patch with `runtime_action: none`.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent general-agent
project evidence under `p2-agent-harness-eval-qwen-agentworld`. Without skill
workflow route hints or a local harness result, they do not inherit
`skill_route_discovery` and cannot select documentation, test, code_patch,
controller, runtime, provider, external harness, or remote-execution follow-up
lanes before `agent_harness_eval` passes.

Source digest `github-growth-20260701T225748.582279Z` advances pass 2 with a
supervisor handoff surface for the same bounded lane. The handoff records the
current proposal hashes, skill-route row counts, adjacent agent-project counts,
candidate source hashes, selected local lanes, and operator sequence without
exporting raw evidence URLs, replay commands, target paths, or upstream bodies.
It keeps zhengxi-views in documentation and test validation lanes, keeps
Qwen-AgentWorld, Fundamental-Ava, and looper behind
`agent_harness_eval_required`, and records the automation/bug agent proposal as
review-only at the offensive-behavior boundary. The handoff is explicitly for
external supervisor replay; it denies kernel restart, promotion, provider
launch, external harness execution, remote execution, profile writes, memory
writes, and upstream skill activation.

Source digest `github-growth-20260701T215748.459700Z` advances pass 3 of the
active `skill-route-discovery` window with a route-to-validation replay surface.
Focused review of the carried public evidence keeps zhengxi-views as the only
skill-route candidate: the repository visibly exposes `SKILL.md`, `skill.yml`,
`references/`, `scripts/`, and `evals/`, plus source-citation and
non-investment-advice boundaries. It maps to
`p1_skill_route_discovery_zhengxi_views` in the local test lane and
`p3_document_agent_trend_growth_policy` in the documentation lane. Both rows
remain bounded to documentation, config, test, or code_patch and keep
`runtime_action: none`.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent general-agent
project evidence under `p2_agent_harness_eval_trending_agent_projects`. They
do not inherit `skill_route_discovery`; no documentation, test, code_patch,
runtime, provider, external harness, or remote-execution follow-up is selected
until a local `agent_harness_eval` replay passes. The open-reverselab anchor is
recorded only as review context because it is outside this pass's carried
evidence URLs and touches the automation/bug safety boundary.

Source digest `github-growth-20260701T204302.417004Z` completes pass 4 of the
current `skill-route-discovery` window with a replayable pass-4 handoff for the
active proposal IDs. The zhengxi-views repository is the only skill-route
candidate because the reviewed public metadata exposes an Agent Skill package
shape (`SKILL.md`, `skill.yml`, references, evals, scripts), source-citation
constraints, and a non-investment-advice boundary. It maps to the local test
lane plus the documentation boundary row, with allowed local lanes limited to
documentation, config, test, and code_patch.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent general-agent
project evidence under `p2-agent-harness-eval-trending-agent-projects`. They do
not inherit `skill_route_discovery` and do not receive direct runtime routing,
direct code_patch authority, provider launch, external harness execution, remote
execution, raw URL export, replay-command export, target-path export, or
upstream-body export before a separate local `agent_harness_eval` result selects
a bounded follow-up lane.

Source digest `github-growth-20260701T211748.482618Z` opens pass 1 of the next
`skill-route-discovery` window with an operator-visible automation/bug
checklist inside the local harness output. zhengxi-views remains bounded to
local skill-route lanes because the reviewed public metadata exposes Agent
Skill package structure, source-citation constraints, and a
non-investment-advice boundary. Qwen-AgentWorld, Fundamental-Ava, and looper
remain adjacent general-agent evidence under `agent_harness_eval_required`.

The open-reverselab proposal is handled only by
`automation_bug_agent_eval_checklist`: its automation, bug, CTF, reverse
engineering, and MCP-tool signals require body-free repository summary,
`agent_harness_eval_lane` replay, offensive-behavior boundary review, no
upstream tool or sample execution, and no runner or controller influence before
local evaluation. The checklist exports hashes rather than raw URLs or upstream
bodies and denies runtime action, direct code_patch routing, provider launch,
external harness execution, remote execution, and controller influence.

Source digest `github-growth-20260701T213749.224965Z` advances pass 2 with an
acceptance surface for the active skill-route lane. The zhengxi-views evidence
is accepted only as a progressive Agent Skill package candidate: root manifest
review, progressively loaded references, source-citation checks,
non-investment-advice boundaries, rollback evidence, and focused local
validation are required before activation. The accepted local lanes remain
documentation and test within the global documentation, config, test, or
code_patch envelope.

Qwen-AgentWorld, Fundamental-Ava, and looper stay adjacent
`agent_harness_eval_required` projects in this pass. The surface names their
required body-free probe fields and allowed follow-up lanes after evaluation,
but still denies inherited `skill_route_discovery`, direct runtime routing,
direct code_patch routing, external harness execution, provider launch, remote
execution, raw source URL export, raw evidence URL export, and upstream-body
export.

Source digest `github-growth-20260701T194302.427071Z` opens pass 1 of the
current `skill-route-discovery` window with a bounded local validation lane for
skill/workflow repository metadata. zhengxi-views is the only skill-route
candidate because the carried evidence and focused public review show concrete
Agent Skill package structure (`SKILL.md`, `skill.yml`, references, evals, and
scripts) plus source-citation and non-investment-advice boundaries. It maps to
`p1_skill_route_discovery_zhengxi_views` in the local test lane and
`p3_agent_harness_eval_fundamental_ava` in the documentation lane. Both rows
may select only documentation, config, test, or code_patch and grant no runtime
action, provider launch, external harness execution, external skill activation,
remote execution, profile write, memory write, raw URL export, or upstream body
export.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`p2_agent_harness_eval_qwen_agentworld` evidence under
`agent_harness_eval_required`. Their general-agent or loop-workflow repository
signals can justify only a local harness-evaluation replay before any
documentation, test, code_patch, controller, runtime, or provider follow-up is
selected. The open-reverselab automation/bug proposal remains review-only at
the offensive-behavior boundary and has no route influence in this lane.

Source digest `github-growth-20260701T200302.486485Z` advances pass 2 by
making body-free repository layout metadata load-bearing for evidence-item
classification. A zhengxi-views-style item can now carry `observed_paths` and
`metadata_files` such as `SKILL.md`, `skill.yml`, `references/`, `scripts/`,
and `evals/`; the router infers `skill_markdown`, `skill_manifest`,
`reference_directory`, `validation_script`, and
`progressive_skill_package` without reading upstream file bodies. The local
harness exposes the resulting progressive package contract so operators can see
that manifest and reference validation must happen before activation.

The same pass keeps Qwen-AgentWorld, Fundamental-Ava, and looper out of
`skill_route_discovery` when they arrive without skill route hints. Their
general-agent evidence remains a separate `agent_harness_eval_required`
concern before any follow-up lane is selected. Unsupported upstream pressure
such as install, runtime execution, or provider runtime remains downgraded or
ignored; the exported harness result keeps local validation required and denies
runtime action, external skill activation, external harness execution, provider
launch, remote execution, raw source URL export, raw evidence URL export, and
upstream body export.

Source digest `github-growth-20260701T190302.389615Z` advances pass 3 of the
active `skill-route-discovery` window with a current replay lane rather than
another generic fixture alias. zhengxi-views is the skill-route candidate
because the public repository exposes Agent Skill structure (`SKILL.md`,
`skill.yml`, references, evals, scripts) plus source-citation and
non-investment-advice boundaries. It maps to `p1_skill_route_discovery_zhengxi_views`
in the local test lane and `p3-route-classification-docs` in the documentation
lane. Both rows may select only documentation, config, test, or code_patch and
grant no runtime action, provider launch, external harness execution, external
skill activation, remote execution, profile write, memory write, raw URL export,
or upstream body export.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`p2-agent-harness-eval-suite` evidence under `agent_harness_eval_required`.
Their repository-level general-agent signals can justify only a local harness
evaluation replay before any documentation, test, or code_patch follow-up lane
is selected. The open-reverselab automation/bug proposal remains an anchoring
review note for the safety boundary; without carried evidence in this digest
lane, it does not add runtime influence.

Source digest `github-growth-20260701T182302.451939Z` opens the next pass-1
window with a local validation lane for the active proposals. zhengxi-views is
the only skill-route candidate because the public repository exposes concrete
Agent Skill structure (`SKILL.md`, `skill.yml`, references, evals, scripts, and
source-citation plus non-investment-advice boundaries). It maps to
`p1-skill-route-discovery-zhengxi-views` in the local test lane and
`p3-agent-harness-eval-fundamental-ava` in the documentation lane. Both rows may
select only documentation, config, test, or code_patch, keep local validation
required, and grant no runtime action, provider launch, external harness
execution, external skill activation, remote execution, profile write, memory
write, or raw upstream export.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`p2-agent-harness-eval-agentworld` evidence under `agent_harness_eval_required`.
General-agent project relevance without route hints may inform future local
harness evaluation, but does not by itself justify direct runtime, controller,
documentation, config, test, or code_patch changes. The open-reverselab
automation/bug anchor is review-only at the offensive-behavior boundary and has
no route influence in this pass.

Source digest `github-growth-20260701T180302.906845Z` completes pass 4 of the
current `skill-route-discovery` window with a final supervisor replay lane.
`trend:lyra81604/zhengxi-views-1` is the only skill-route candidate because the
reviewed repository metadata exposes Agent Skill structure, including `SKILL.md`,
`skill.yml`, references, evals, scripts, source-citation boundaries, and a
non-investment-advice boundary. It maps only to bounded test and documentation
lanes for `p1_skill_route_discovery_for_trending_skill_workflow` and
`p3_agent_harness_eval_documentation`; unsupported runtime or provider pressure
is stripped.

`trend:QwenLM/Qwen-AgentWorld-1`,
`trend:TianhangZhuzth/Fundamental-Ava-1`, and `trend:ksimback/looper-1` remain
general-agent project evidence under
`p2_agent_harness_eval_fixture_for_general_agent_projects`. They stay in
`agent_harness_eval_required` and do not inherit `skill_route_discovery`,
runtime routing, direct code_patch selection, provider launch, external harness
execution, remote execution, profile writes, memory writes, raw source URL
export, replay-command export, target-path export, or upstream-body export until
a local harness evaluation result selects a bounded follow-up lane.

Source digest `github-growth-20260701T174302.497335Z` advances pass 3 with a
digest-specific activation review lane. `p1_skill_route_discovery_zhengxi_views`
is the only skill-route row and remains bounded to documentation, config, test,
or code_patch with test selected for focused local validation. Qwen-AgentWorld,
Fundamental-Ava, and looper are grouped under
`p2_agent_harness_eval_general_projects`; they may lead to documentation, test,
or code_patch only after `agent_harness_eval_required` passes and still grant no
runtime action, external harness execution, provider launch, or inherited skill
route. The automation/bug proposal remains review-only at the safety boundary.

Source digest `github-growth-20260701T165922.952638Z` starts pass 1 of the
active `skill-route-discovery` window with
`current_digest_pass1_validation_lane` specialized to the current proposal IDs.
`p1-skill-route-discovery-for-zhengxi-views` is the only skill-route proposal
and selects the local test lane because the body-free zhengxi-views evidence
contains both agent and skill workflow signals. Its allowed lanes remain only
documentation, config, test, or code_patch. Qwen-AgentWorld, Fundamental-Ava,
and looper remain adjacent `p2-agent-harness-eval-fixtures` rows under
`agent_harness_eval_required`, with no inherited `skill_route_discovery`, no
direct runtime route, no direct code_patch route, no external harness
execution, and no provider launch before local harness validation. The
`p4-automation-bug-agent-eval-case` anchor is review-only at the
offensive-behavior boundary and has no route influence.

Source digest `github-growth-20260701T171923.099727Z` advances pass 2 by
making adjacent general-agent recovery visible inside the current digest lane.
zhengxi-views remains the only skill-route candidate and maps to bounded test
and documentation lanes for `p1_skill_route_discovery_zhengxi_views` and
`p3_open_reverselab_bug_automation_eval`. Qwen-AgentWorld, Fundamental-Ava,
and looper stay under `p2_agent_harness_eval_trending_agent_projects` with
`agent_harness_eval_required`; open-reverselab is recorded as a review-only
automation row at the offensive-behavior boundary. The new
`adjacent_agent_recovery_contract` lists the body-free project probe fields,
local harness replay requirement, safety review condition, and denied runtime
or external execution gates before any documentation, test, or code_patch
follow-up can be selected.

Source digest `github-growth-20260701T151922.933466Z` completes pass 4 of the
current window with `current_digest_pass4_final_closure` specialized to the
active proposal IDs. zhengxi-views remains the only skill-route candidate and
closes through bounded test and documentation lanes for generic skill workflow
and source-cited domain research validation. The closure is operator-visible
and supervisor-facing; it does not activate the external skill.

Source digest `github-growth-20260701T163923.124908Z` finishes the next pass-4
theme window by making the adjacent general-agent recovery path explicit.
Qwen-AgentWorld, Fundamental-Ava, and looper still do not inherit
`skill_route_discovery`, but their `agent_harness_eval_lane` readiness contract
now includes an `agent_harness_eval_recovery_workflow`. That workflow tells the
supervisor which body-free project probe fields, claim mappings, review-queue
steps, and local replay command must be satisfied before any documentation,
test, or code_patch follow-up lane is permitted. It still denies runtime
action, external harness execution, provider launch, remote execution, raw
source URL export, and upstream body export.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows before any documentation, test, or code_patch
follow-up can be selected. open-reverselab is also counted as an
automation/reverse-engineering review row under
`review_only_before_agent_harness_eval`. These rows do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, remote execution, profile writes,
memory writes, raw URL export, replay-command export, target-path export, or
upstream-body export.

Source digest `github-growth-20260701T102533.298615Z` completes pass 4 of the
current `skill-route-discovery` window with a replayable local completion
fixture. The zhengxi-views evidence is the only skill-route candidate: its
`SKILL.md`, references, citation traceability, evaluation material, and
not-investment-advice boundary keep it in bounded documentation and test lanes
for local validation.

Source digest `github-growth-20260701T131922.972375Z` reopens pass 2 with an
active skill-route discovery lane rather than an activation path. The
zhengxi-views repository remains the single skill-route candidate because the
available public metadata shows agent-skill topics, `SKILL.md`, `skill.yml`,
references, evals, scripts, source-citation boundaries, and a non-investment
advice note. The controller maps that evidence only to documentation, config,
test, or code_patch lanes and selects local test plus documentation review for
this pass.

Source digest `github-growth-20260701T133922.800774Z` advances the active slice
to pass 3 with a current activation-review lane, but still without activation
authority. zhengxi-views remains the only skill-route row and maps to
`p1_skill_route_discovery_zhengxi_views` in the local test lane plus
`p3_agent_trend_route_documentation` in the documentation lane. Both rows may
select only documentation, config, test, or code_patch, strip provider-runtime
and runtime-execution pressure, require selected digest item IDs and route
validation gates, and export only hashes plus lane metadata.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`p2_agent_harness_eval_trending_agent_projects` rows under
`agent_harness_eval_required`. Their public trend evidence can justify only a
local harness-eval gate before any documentation, test, or code_patch follow-up
is selected. They do not inherit `skill_route_discovery`, direct runtime
routing, direct code_patch authority, external harness execution, provider
launch, remote execution, profile writes, memory writes, raw URL export,
replay-command export, target-path export, or upstream-body export.

Qwen-AgentWorld, Fundamental-Ava, and looper are adjacent general-agent project
trends in this pass. They remain `agent_harness_eval_required` and cannot
inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw URL export, replay-command export,
target-path export, or upstream-body export until a local harness result
chooses a bounded follow-up lane. The automation-and-bug route anchor remains
review-only at the offensive-behavior boundary and has no route influence.

Qwen-AgentWorld and Fundamental-Ava are carried as adjacent general-agent
projects, not skill workflow repositories. They remain
`agent_harness_eval_required` until a local harness evaluation passes, and they
do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, remote
execution, profile writes, memory writes, raw URL export, replay-command export,
target-path export, or upstream-body export. The pass-4 fixture exports hashes,
counts, lane names, route profiles, selected local lanes, and denial booleans
only.

Source digest `github-growth-20260701T141923.059729Z` starts the next pass-1
window with an explicit local validation lane for the active route proposals.
The zhengxi-views signal remains the only skill-route candidate and maps to
`p1-skill-route-discovery-zhengxi-views` in the local test lane. The lane
records its generic skill workflow and source-cited domain research profiles,
keeps local validation required, and allows only documentation, config, test,
or code_patch lanes before activation.

Qwen-AgentWorld remains adjacent under `p2-agent-harness-eval-agentworld`.
Fundamental-Ava and open-reverselab are visible under
`p3-agent-harness-comparison-set`; open-reverselab is also recorded as
security-adjacent review-only context at the offensive-behavior boundary. None
of these adjacent project rows inherits `skill_route_discovery`, direct runtime
routing, direct code_patch authority, external harness execution, provider
launch, remote execution, profile writes, memory writes, raw URL export,
replay-command export, target-path export, or upstream-body export.

Source digest `github-growth-20260630T112714.533021Z` starts pass 1 of the
current `skill-route-discovery` window with a digest-specific validation lane
for the active proposal IDs. The zhengxi-views signal is the only skill-route
candidate and maps to `p1_skill_route_discovery_zhengxi_views` in the local test
lane plus `p3_document_agent_trend_triage_rules` in the documentation lane. Both
lanes may select only documentation, config, test, or code_patch and keep local
validation required before any activation.

Qwen-AgentWorld, Fundamental-Ava, looper, and AgentChat are adjacent
general-agent project signals under `p2_agent_harness_eval_trending_projects`.
They remain `agent_harness_eval_required` until their project behavior is
inspected locally through the harness-eval contract. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, remote execution, raw URL export,
replay-command export, target-path export, or upstream-body export. Evidence
URLs in the digest are input references only; route outputs keep hashes,
selected item IDs, counts, lane names, and denial booleans rather than adding
new raw evidence URLs.

Source digest `github-growth-20260701T100533.329031Z` advances pass 3 of the
same slice with `current_digest_pass3_route_to_validation_lane`. The lane is an
operator-visible route-to-validation packet for the active proposal IDs:
zhengxi-views maps to `p1-skill-route-discovery-zhengxi-views` in the local
test lane and `p3-document-agent-trend-routing-policy` in the documentation
lane, while Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`p2-agent-harness-eval-trending-projects` rows. The packet permits only
documentation, config, test, or code_patch skill-route lanes before activation
and permits no general-agent outputs until a local `agent_harness_eval` result
exists.

The pass-3 packet exports selected digest item IDs, lane names, proposal IDs,
source hashes, replay-command hashes, and denial booleans. It does not export
raw GitHub URLs, raw replay commands, target paths, upstream bodies, provider
launch, external harness execution, external skill or agent activation, remote
execution, profile writes, memory writes, or restart authority.

Source digest `github-growth-20260630T110714.560687Z` completes pass 4 of the
current `skill-route-discovery` window by making the adjacent
`agent_harness_eval` completion path project-visible. zhengxi-views remains the
skill-route signal and may enter only documentation, config, test, or
code_patch lanes with local validation. Qwen-AgentWorld and looper remain
general-agent evidence, but the local `agent_harness_eval_lane` now emits an
`agent_harness_eval_project_completion_matrix` inside the implementation
readiness contract so the supervisor can see, per project, whether intake
metadata is complete, claims are mapped to local capabilities, bounded follow-up
lanes are selected, the replay gate passed, and the review queue is ready.

The new matrix is still local and body-free. It can mark documentation, test, or
code_patch follow-up as permitted only after the local harness replay passes for
each project. It does not grant `skill_route_discovery` inheritance, direct
runtime routing, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, replay-command export,
target-path export, or upstream-body export.

Source digest `github-growth-20260630T100715.128640Z` starts pass 1 of the
current `skill-route-discovery` window by making zhengxi-views-style push
activity explicitly corroborating-only. The repository trend item supplies the
concrete Agent Skill workflow evidence and may enter only documentation, config,
test, or code_patch lanes with local validation required. Related generic
`PushEvent` items can raise activity pressure for the same project, but they are
recorded as low-detail freshness signals and are not independent implementation
evidence unless a non-generic selected item supplies repository or validation
detail.

The current pass remains body-free and local-only. It does not activate external
skills, run upstream code or harnesses, launch providers, export raw source URLs,
write profiles or memory, grant remote execution, or let general-agent evidence
inherit `skill_route_discovery`.

Source digest `github-growth-20260630T102715.054031Z` advances pass 2 with
`current_pass2_lane_handoff`, an operator-visible replay checkpoint for the
active lane. The zhengxi-views row remains the only skill-route row and may
select only documentation, config, test, or code_patch with focused local
validation. Qwen-AgentWorld and looper remain adjacent
`agent_harness_eval_required` rows until a local harness evaluation result
exists, and low-detail fork or lineage evidence without a validation target does
not add a route lane. The handoff exports item IDs, lane names, proposal IDs,
source hashes, validation commands, and denial booleans only; raw source URLs,
raw evidence URLs, raw replay commands, raw target paths, upstream bodies,
runtime action, provider launch, external harness execution, profile writes,
memory writes, remote execution, and external skill or agent activation remain
denied.

Source digest `github-growth-20260630T092714.616189Z` advances pass 3 of the
active `skill-route-discovery` window with a current activation-review lane
instead of older pass-3 proposal aliases. zhengxi-views maps to
`p1_skill_route_discovery_for_zhengxi_views` in the local test lane and
`p3_document_route_policy_for_trending_agent_inputs` in the documentation lane.
Both rows are bounded to documentation, config, test, or code_patch with local
validation required and runtime action denied.

Qwen-AgentWorld, looper, and AgentChat are represented together under
`p2_agent_harness_eval_fixture_for_general_agent_projects`. They remain
adjacent `agent_harness_eval_required` rows and do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, profile writes, memory writes,
remote execution, raw source URL export, replay-command export, target-path
export, or upstream-body export.

Source digest `github-growth-20260630T082714.446734Z` completes pass 4 of the
current `skill-route-discovery` window with a digest-specific local-kernel
handoff. zhengxi-views remains the only skill-route candidate and closes through
bounded documentation and test lanes for generic skill workflow and
source-cited-domain-research validation. Qwen-AgentWorld, looper, and
open-reverselab remain adjacent `agent_harness_eval_required` rows; the pass-4
closure makes their comparison checklist operator-visible before any
documentation, test, or code_patch follow-up is selected.

Source digest `github-growth-20260630T084715.195137Z` starts the next pass-1
`skill-route-discovery` window with a current local validation lane. The
zhengxi-views evidence is treated as a skill-shaped public repository signal and
maps only to `p1-skill-route-discovery-zhengxi-views` in the local test lane.
The lane preserves generic skill workflow and source-cited research route
profiles, strips unsupported provider-runtime pressure, and requires local
validation before activation.

Source digest `github-growth-20260630T090714.437117Z` advances pass 2 of this
window with the current proposal IDs. zhengxi-views maps to
`p1_skill_route_discovery_zhengxi_views` in the local test lane and
`p3_document_route_policy_for_trend_items` in the documentation lane; both rows
may select only documentation, config, test, or code_patch and keep runtime
action denied.

Qwen-AgentWorld, looper, and AgentChat are intentionally covered as
empty-route-hint general-agent rows. They remain under
`p2_agent_harness_eval_trending_python_agents` and require local
`agent_harness_eval_required` before documentation, test, or code_patch scope is
chosen. The open-reverselab anchor remains review-only at the
offensive-behavior boundary with no route influence.

Qwen-AgentWorld, looper, and AgentChat remain adjacent general-agent evidence
under `agent_harness_eval_required`; they do not inherit `skill_route_discovery`
or direct runtime, scheduler, loop-control, provider, external harness, remote
execution, profile-write, memory-write, raw URL export, replay-command export,
target-path export, or upstream-body authority. The open-reverselab anchor stays
review-only at the offensive-behavior boundary with no route influence.

The completion surface is body-free and supervisor-facing. It records route
profiles, selected local lanes, validation hashes, adjacent general-agent count,
and denial booleans only. It does not activate external skills or agents, run
external harnesses, launch providers, write profiles or memory, export raw
source URLs or upstream bodies, or restart the kernel.

Source digest `github-growth-20260630T074714.730934Z` advances pass 2 of the
active `skill-route-discovery` window with a digest-specific
`current_digest_pass2_local_validation_lane`. The zhengxi-views evidence is
skill-shaped and now maps to two bounded local lanes:
`p1-skill-route-discovery-lane` in the test lane and
`p3-route-hint-documentation` in the documentation lane. Both rows preserve
only documentation, config, test, or code_patch as selectable local lanes and
keep `runtime_action: none`.

Qwen-AgentWorld, looper, and open-reverselab remain adjacent general-agent
evidence under `p2-agent-harness-eval-fixtures`; they require local
`agent_harness_eval` before documentation, test, or code_patch implementation
scope is selected and do not inherit `skill_route_discovery`. open-reverselab
is also recorded as review-only security-adjacent context at the
offensive-behavior boundary. The pass-2 focused review and active-slice review
surfaces are ready for supervisor replay, but they do not activate external
skills, run external harnesses, launch providers, write profiles or memory,
export raw upstream URLs, export raw replay commands, or restart the kernel.

Source digest `github-growth-20260630T072714.658769Z` starts the next pass-1
`skill-route-discovery` window with a digest-specific local validation fixture.
The zhengxi-views evidence is skill-shaped and maps to
`p1-skill-route-discovery-zhengxi-views` in the bounded local test lane.
Qwen-AgentWorld and looper remain adjacent `agent_harness_eval_required`
evidence before any runtime, scheduler, runner, or direct code_patch route can
be considered. open-reverselab is recorded as security-adjacent automation
context under the offensive-behavior review boundary and has no route influence.

The pass-1 fixture exports only body-free lane metadata. It strips
`provider_runtime` and `runtime_execution` pressure from local lanes, keeps
external skill activation, external agent activation, external harness
execution, provider launch, remote execution, profile writes, memory writes, raw
URL export, replay-command export, and upstream body export denied, and relies
on the supervisor to perform any later activation handoff.

Source digest `github-growth-20260630T070714.426957Z` completes the fourth pass
of the current `skill-route-discovery` slice with an operator-visible
`current_digest_pass4_completion_handoff` and matching
`current_digest_pass4_final_closure`. The zhengxi-views row maps to
`p1_skill_route_discovery_zhengxi_views` in the local test lane and strips
unsupported provider-runtime pressure before it can become route authority.

Qwen-AgentWorld, looper, and AgentChat remain adjacent general-agent evidence
under `p2_agent_harness_eval_general_projects`. Their route is
`agent_harness_eval_required` only; they do not inherit skill-route authority,
direct runtime routing, direct code_patch authority, external harness
execution, provider launch, profile writes, memory writes, remote execution,
raw source URL export, replay-command export, target-path export, or upstream
body export. The final handoff is replay metadata for the external supervisor,
not a restart or activation path.

Source digest `github-growth-20260630T060714.387302Z` starts the current
pass-1 `skill-route-discovery` window with a digest-specific
`current_digest_pass1_validation_lane`. zhengxi-views-style public Agent Skill
evidence maps to `p1_skill_route_discovery_zhengxi_views` in the local test
lane and may select only documentation, config, test, or code_patch with
`local_validation_required: true`.

Qwen-AgentWorld, looper, and AgentChat remain adjacent general-agent evidence
under `p2_agent_harness_eval_general_projects`. Automation-tagged
open-reverselab remains adjacent under
`p3_automation_agent_eval_open_reverselab` and is recorded as review-only
security-adjacent context at the offensive-behavior boundary. These rows stay
in `agent_harness_eval_required`; they do not inherit `skill_route_discovery`,
direct runtime routing, direct code_patch authority, external harness
execution, provider launch, profile writes, memory writes, remote execution,
raw source URL export, replay-command export, or upstream body export.

Source digest `github-growth-20260630T062715.310093Z` advances pass 2 of the
same slice by making the adjacent `agent_harness_eval` route more explicit
before implementation work. General-agent projects such as Qwen-AgentWorld,
looper, and AgentChat must now satisfy an
`agent_harness_eval_implementation_readiness_contract` that records candidate
local capabilities, required preflight checks, and pass/fail criteria before
documentation, test, or code_patch follow-up lanes are permitted. The contract
blocks when any general-agent claim is unmapped, the project intake probe is
incomplete, the bounded lane replay has not passed, or the review queue is not
ready.

This pass does not change the skill-route boundary. zhengxi-views-style public
Agent Skill evidence remains eligible only for documentation, config, test, or
code_patch lanes with local validation required. General-agent evidence still
does not inherit `skill_route_discovery`, direct runtime routing, external
harness execution, provider launch, remote execution, profile writes, memory
writes, raw URL export, replay-command export, or upstream body export.

Source digest `github-growth-20260630T042714.877059Z` completes pass 4 of the
current `skill-route-discovery` window by adding a closure checklist to the
local-kernel handoff. The checklist is operator-visible and body-free: it
separates bounded skill-route lanes, adjacent general-agent evaluation gates,
local replay readiness, and activation-boundary closure before supervisor
handoff.

The zhengxi-views row remains skill-route evidence and may select only
documentation, config, test, or code_patch with local validation required.
Qwen-AgentWorld, open-reverselab, and looper remain adjacent
`agent_harness_eval_required` evidence; the checklist makes that gate explicit
before implementation scope is selected. It does not grant external skill
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw URL export, replay-command export, target
path export, or upstream body export.

Source digest `github-growth-20260630T032714.526268Z` starts the next pass-1
`skill-route-discovery` window with a digest-specific
`current_digest_pass1_validation_lane`. zhengxi-views-style public Agent Skill
evidence maps to `p1-skill-route-discovery-zhengxi-views` in the local test
lane and may select only documentation, config, test, or code_patch. Unsupported
provider-runtime pressure is stripped before it can become route authority.

Qwen-AgentWorld remains adjacent general-agent evidence under
`p2-agent-harness-eval-agentworld`. open-reverselab and looper remain adjacent
general-agent routing coverage under `p3-general-agent-routing-coverage`, with
open-reverselab also recorded as review-only security-adjacent context at the
offensive-behavior boundary. These rows stay in `agent_harness_eval_required`;
they do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, profile
writes, memory writes, remote execution, raw source URL export, replay-command
export, or upstream body export.

Source digest `github-growth-20260630T034714.764347Z` advances pass 2 of the
same window with a digest-specific `current_digest_pass2_local_validation_lane`.
When the current digest contains zhengxi-views-style skill evidence but no
COMPASS or game/frontend skill profiles, the pass-2 lane derives the required
skill-route proposal from the present evidence instead of blocking on absent
profiles from older windows. The selected local lane is the test lane for
`p1-skill-route-discovery-zhengxi-views`, bounded to documentation, config,
test, or code_patch outputs.

Qwen-AgentWorld remains adjacent general-agent evaluation evidence under
`p2-agent-harness-eval-agentworld`. open-reverselab and looper remain
`agent_harness_eval_required` rows under `p3-general-agent-routing-coverage`,
with open-reverselab recorded as offensive-boundary review-only context. This
pass exposes a supervisor-visible replay surface and preactivation trust
boundary only; it does not activate external skills, run external harnesses,
launch providers, export raw upstream URLs, write profiles or memory, or grant
direct runtime/code_patch authority to general-agent evidence.

Source digest `github-growth-20260630T040714.847135Z` advances pass 3 of this
window with a digest-specific `current_digest_pass3_activation_review_lane`.
State-handoff rows are now evidence-driven: when the digest carries
zhengxi-views-style skill workflow evidence plus general-agent projects but no
`skill_ecosystem_state_handoff` candidate, the pass-3 lane emits only
`p1_skill_route_discovery_lane` and `p2_agent_harness_eval_fixture` instead of
blocking on an absent COMPASS-style handoff.

The zhengxi-views row remains bounded to documentation, config, test, or
code_patch with `runtime_action: none` and local validation required.
Qwen-AgentWorld, open-reverselab, and looper remain adjacent
`agent_harness_eval_required` evidence; they do not inherit
`skill_route_discovery`, cannot launch external harnesses or providers, and
cannot justify direct runtime integration before local harness evaluation.

Source digest `github-growth-20260629T235904.365838Z` starts pass 1 of the
active `skill-route-discovery` window with a digest-specific
`current_digest_pass1_validation_lane`. COMPASS-style skill ecosystem handoff
evidence maps to `p1-skill-route-discovery-compass` in the local test lane.
zhengxi-views-style generic skill workflow evidence maps to
`p2-generic-skill-workflow-probe` in the documentation lane. Both rows may
select only documentation, config, test, or code_patch, require focused local
validation, and downgrade unsupported install or provider-runtime pressure
before it can become route authority.

Qwen-AgentWorld and looper remain adjacent general-agent evidence for this
pass. They are visible only as `agent_harness_eval_required` rows under
`p3-agent-harness-eval-agentworld` and `p4-agent-harness-eval-looper`; they do
not inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, profile writes, memory
writes, remote execution, raw source URL export, replay-command export, or
upstream body export. This pass records a bounded local validation lane only;
it does not activate external skills, external agents, providers, memory, or
profiles.

Source digest `github-growth-20260630T001904.371161Z` advances pass 2 of the
active `skill-route-discovery` window with a current replay fixture for
`current_digest_pass2_local_validation_lane`. zhengxi-views-style public Skill
evidence is treated as a bounded generic/source-cited skill workflow route: it
may select only documentation, config, test, or code_patch after focused local
validation, and the current pass records the documentation lane first.
COMPASS-style skill ecosystem evidence stays in the local test lane for
state-handoff boundary checks.

Qwen-AgentWorld and looper remain adjacent general-agent evidence in this
pass. They are visible only as `agent_harness_eval_required` rows and do not
inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, profile writes, memory
writes, remote execution, raw source URL export, replay-command export, or
upstream body export. The current pass is a validation lane and supervisor
replay surface only; it does not install, import, execute, or activate upstream
repositories.

Source digest `github-growth-20260629T225904.339664Z` advances pass 2 of the
active `skill-route-discovery` window with a harness-visible
`current_digest_pass2_local_validation_lane`. COMPASS-style skill ecosystem
handoff evidence maps to `p1-skill-route-discovery-compass` in the local test
lane. zhengxi-style generic skill workflow evidence maps to
`p2-generic-skill-route-coverage-zhengxi` in the documentation lane. Both rows
may select only documentation, config, test, or code_patch, keep
`local_validation_required: true`, and deny install, provider runtime,
execution, profile writes, memory writes, and external activation.

Qwen-AgentWorld and looper remain adjacent general-agent evidence for pass 2.
They are reported only as `agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld` and `p4-agent-loop-runner-eval`; they
do not inherit `skill_route_discovery` or direct runtime/code_patch authority
before local harness evaluation. The security-agent anchor remains review-only
at the offensive-behavior boundary.

Source digest `github-growth-20260629T213904.316042Z` advances pass 2 of the
active `skill-route-discovery` window with an operator-visible pass-2 replay
surface. COMPASS-style skill ecosystem evidence and zhengxi-views-style generic
skill workflow evidence now feed the same bounded rows for
`p1-skill-route-discovery-catalog` and `p2-skill-route-regression-tests`.
Those rows may select only documentation or test lanes from the fixed local
lane set: documentation, config, test, and code_patch. Unsupported install,
provider-runtime, and runtime-execution pressure is downgraded before it can
become lane authority.

The pass-2 operator surface reports proposal IDs, selected local lanes,
validation command hashes, rollback and changed-file review requirements, and
the adjacent general-agent eval count. It does not export raw repository URLs,
raw evidence URLs, raw replay commands, target paths, upstream bodies, or any
activation authority. Qwen-AgentWorld and looper remain adjacent
`agent_harness_eval_required` evidence under
`p3-agent-harness-eval-for-general-agent-projects`; they may lead only to
documentation, test, or code_patch after local harness evaluation and do not
inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, profile writes, memory
writes, or remote execution.

Source digest `github-growth-20260629T223904.363629Z` starts pass 1 of the
active `skill-route-discovery` window with an explicit
`current_digest_pass1_validation_lane` replay surface. COMPASS-style skill
ecosystem handoff evidence maps to `p1-skill-route-discovery-compass` in the
local test lane. zhengxi-views-style generic skill workflow evidence maps to
`p2-generic-skill-route-coverage-zhengxi` in the documentation lane. Both rows
may select only documentation, config, test, or code_patch and keep
`runtime_action: none`, `local_validation_required: true`, and external skill,
agent, harness, provider, profile, memory, and remote execution authority
denied.

Qwen-AgentWorld and looper remain adjacent general-agent evidence for this
pass. They are represented as `agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld` and `p4-agent-loop-runner-eval`; they
do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, profile
writes, memory writes, remote execution, raw URL export, replay-command export,
or upstream body export. `p5-security-agent-risk-gated-eval` remains a
review-only anchor at the offensive-behavior boundary and has no route
influence.

Source digest `github-growth-20260701T145922.935225Z` adds
`route_evidence_activation_gate` inside
`current_digest_pass3_activation_review_lane`. The gate is a compact
controller-visible pass-3 summary: zhengxi-views-style skill evidence may enter
only documentation, config, test, or code_patch validation lanes; adjacent
general-agent projects such as Qwen-AgentWorld and Fundamental-Ava remain
`agent_harness_eval_required`; and automation or reverse-engineering pressure
such as open-reverselab stays non-executable unless a later controller
recompute assigns an explicit bounded local lane. The gate always reports
`runtime_action: none`, denies external skill, agent, harness, provider, and
remote activation, and exports no raw upstream URLs or bodies.

Source digest `github-growth-20260629T215904.320352Z` advances pass 3 of the
active `skill-route-discovery` window with
`current_digest_pass3_activation_review_lane`. The lane turns the current
regression, COMPASS handoff, and general-agent harness fixture proposals into
one supervisor-visible activation review packet. COMPASS-style state handoff
and zhengxi-views-style agent plus skill workflow evidence may still select
only documentation, config, test, or code_patch lanes, with selected item IDs,
validation gates, replay-command hashes, rollback evidence, and focused local
validation required before pass 4. Qwen-AgentWorld and looper stay in
`agent_harness_eval_required`; they may not inherit `skill_route_discovery` or
receive direct runtime, direct code_patch, external harness, provider launch,
profile write, memory write, remote execution, raw URL export, replay-command
export, target-path export, or upstream body export authority.

Source digest `github-growth-20260629T203904.306145Z` advances pass 3 of the
active `skill-route-discovery` window by teaching
`current_source_digest_pass3_operator_lane` about the current proposal names.
COMPASS-style skill ecosystem evidence now maps to
`p1-skill-route-discovery-compass-skills` in the local test lane for
state-handoff boundary validation. zhengxi-views-style generic skill workflow
evidence maps to `p2-skill-route-discovery-generic-skill-workflow` in the local
test lane for fixture-backed route classification. Both rows keep
documentation, config, test, and code_patch as the only allowed outputs and
require selected digest item IDs, route-profile validation requirements,
rollback coverage, expected harness outputs, and focused local validation.

Qwen-AgentWorld and looper remain adjacent general-agent projects for this
pass. They are visible only as `agent_harness_eval_required` rows: Qwen under
`p3-agent-harness-eval-agentworld` and looper under
`p4-agent-harness-eval-looper`. They may lead to documentation, test, or
code_patch after local harness evaluation, but they do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, profile writes, memory writes,
remote execution, raw source URL export, raw evidence URL export, replay-command
export, target-path export, or upstream body export.

Source digest `github-growth-20260629T201904.282006Z` advances pass 2 of the
active `skill-route-discovery` window by adding an explicit
`skill_ecosystem_handoff_path` inside
`current_digest_pass2_local_validation_lane`. The path binds the active
proposal IDs `p1-skill-route-discovery-index`,
`p2-skill-ecosystem-handoff-doc`, and `p3-agent-harness-eval-baseline` to the
same bounded evidence used by the pass-2 route rows. COMPASS-style skill
ecosystem evidence selects the local test lane for metadata-only state handoff
validation. zhengxi-views-style generic skill workflow evidence selects the
documentation lane for handoff documentation. Both may lead only to
documentation, config, test, or code_patch after focused local validation.

Qwen-AgentWorld and looper remain adjacent general-agent projects in this
pass. They are represented by the baseline `agent_harness_eval_required` path
with documentation, test, or code_patch as possible outputs only after local
harness evaluation exists. They do not inherit `skill_route_discovery`, direct
runtime routing, direct code_patch authority, external harness execution,
provider launch, profile writes, memory writes, remote execution, raw source
URL export, raw evidence URL export, target-path export, replay-command export,
or upstream body export. Unsupported install, provider-runtime, and
runtime-execution pressure is downgraded before it can become lane authority.

Source digest `github-growth-20260629T193904.337686Z` completes pass 4 of the
active `skill-route-discovery` window by adding
`route_boundary_checklist` to `current_digest_pass4_completion_handoff`.
COMPASS Skills and zhengxi-views are treated as skill workflow evidence and
may select only bounded local skill-route lanes: documentation, config, test,
or code_patch. The active local test lane verifies that their skill terms do
not open install, provider-runtime, runtime-execution, profile-write, or
memory-write authority.

Qwen-AgentWorld and looper remain general agent projects in the same handoff.
They are represented only as `agent_harness_eval_required` rows with allowed
harness-evaluation outputs of documentation, test, or code_patch after a local
harness-eval route exists. They do not inherit `skill_route_discovery`, direct
runtime routing, direct code_patch authority, external harness execution,
provider launch, remote execution, profile writes, memory writes, raw source
URL export, raw evidence URL export, target-path export, replay-command export,
or upstream body export.

Source digest `github-growth-20260629T195904.271855Z` starts pass 1 of the
next active `skill-route-discovery` window with proposal IDs
`p1-skill-route-discovery-compass-skills`, `p2-generic-skill-workflow-probe`,
`p3-agent-harness-eval-qwen-agentworld`, `p4-agent-harness-eval-looper`, and
`p5-security-agent-review-boundary-autocve`. The pass-1 lane maps COMPASS-style
skill ecosystem handoff evidence to the local test lane and zhengxi-views-style
agent plus skill workflow evidence to the documentation lane. Both rows expose
only documentation, config, test, or code_patch as allowed local lanes, keep
`local_validation_required: true`, and strip install or provider-runtime
wording before it can become allowed lane authority.

Qwen-AgentWorld and looper remain adjacent general-agent projects for this
pass. They are represented as separate `agent_harness_eval_required` rows and
do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, profile
writes, memory writes, remote execution, raw source URL export, raw evidence
URL export, target-path export, replay-command export, or upstream body export.

Source digest `github-growth-20260629T191904.276263Z` advances pass 3 of the
active `skill-route-discovery` window by binding the current proposal IDs to
`current_source_digest_pass3_operator_lane`. COMPASS-style skill ecosystem
evidence maps to the local test lane for state/profile handoff validation, and
zhengxi-views-style generic skill workflow evidence maps to the documentation
lane while preserving `route_hint: skill_route_discovery`. Both rows expose
only documentation, config, test, or code_patch as local lanes and require
focused local validation before activation. Qwen-AgentWorld and looper remain
adjacent `agent_harness_eval_required` rows under the current general-agent
proposal; they do not inherit skill-route authority, direct runtime routing,
direct code_patch routing, external harness execution, provider launch, remote
execution, profile writes, memory writes, raw source URL export, raw evidence
URL export, replay-command export, target-path export, or upstream body export.

Source digest `github-growth-20260629T183904.255941Z` starts pass 1 of the
active `skill-route-discovery` window with an explicit local validation fixture
for the current proposal IDs. COMPASS-style skill ecosystem evidence keeps
`route_hint: skill_route_discovery`, selects the local test lane, and exposes
only documentation, config, test, or code_patch as allowed lanes even when raw
upstream evidence suggests install. zhengxi-views-style generic skill workflow
evidence selects the documentation lane under the same bounded lane set even
when raw evidence suggests provider runtime. Qwen-AgentWorld and looper are
recorded only as adjacent `agent_harness_eval_required` rows with
`skill_route_discovery_inherited: false`; they do not authorize direct runtime
routing, direct code_patch routing, external harness execution, provider
launch, profile writes, memory writes, remote execution, raw URL export,
replay-command export, or upstream body export. The AutoCVE anchor remains a
security-adjacent review note only.

Source digest `github-growth-20260629T181904.229847Z` completes pass 4 of the
active `skill-route-discovery` window with the current
`current_digest_pass4_completion_handoff`. The handoff binds
`proposal-001-skill-route-discovery-compass-skills` to the local test lane for
COMPASS-style skill ecosystem/state-handoff evidence and binds
`proposal-002-generic-skill-workflow-discovery` to the documentation lane for
zhengxi-views-style generic skill workflow evidence. Both rows remain limited
to documentation, config, test, or code_patch outputs with
`local_validation_required: true`. Qwen-AgentWorld and looper are carried only
as adjacent `proposal-003-agent-harness-eval-qwen-agentworld` rows under
`agent_harness_eval_required`; they do not inherit `skill_route_discovery`,
direct runtime routing, direct code_patch authority, external harness
execution, provider launch, profile writes, memory writes, remote execution,
raw source URL export, raw evidence URL export, target-path export,
replay-command export, or upstream body export.

Source digest `github-growth-20260629T175904.233445Z` advances pass 3 of the
active `skill-route-discovery` window through
`current_source_digest_pass3_operator_lane`. COMPASS-style skill ecosystem
handoff evidence maps to a bounded local test lane, while zhengxi-views-style
generic skill workflow evidence maps to a bounded documentation lane. Both
routes retain `local_validation_required: true`, export only hashed source and
replay metadata, and cannot authorize install, provider runtime, profile write,
memory write, remote execution, or upstream activation. Qwen-AgentWorld and
looper remain adjacent `agent_harness_eval_required` rows and may propose only
documentation, test, or code_patch work after a local harness evaluation
fixture; they do not inherit `skill_route_discovery`.

Source digest `github-growth-20260629T173904.211836Z` advances pass 2 of the
active `skill-route-discovery` window with a current-digest local validation
lane for `p1-skill-route-discovery-compass-skills`,
`p2-skill-route-discovery-zhengxi-views`, and adjacent
`p3-agent-harness-qwen-agentworld` / `p4-agent-harness-looper` evidence.
COMPASS-style skill ecosystem handoff evidence selects the local test lane for
metadata-only state/profile boundary validation before any profile write,
memory write, install, or execution. zhengxi-views-style generic skill workflow
evidence selects the documentation lane for checklist-style route discovery.
Qwen-AgentWorld and looper remain `agent_harness_eval_required` rows: they do
not inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, remote execution, raw
source URL export, raw evidence URL export, target-path export, replay-command
export, profile writes, memory writes, or upstream body export. The security
adjacent AutoCVE anchor remains a review note only; no offensive,
unauthorized-access, or exfiltration behavior is implemented by this lane.

Source digest `github-growth-20260629T171904.272271Z` starts pass 1 of the
active `skill-route-discovery` window with `p1-skill-route-discovery-compass`,
`p2-generic-skill-workflow-zhengxi`,
`p3-agent-harness-qwen-agentworld`, and `p4-agent-harness-looper`.
COMPASS-style skill ecosystem evidence selects the local test lane so handoff,
profile, and task-memory metadata can be validated without installing,
executing, writing profiles, or writing memory. zhengxi-views-style generic
skill workflow evidence selects the documentation lane and remains bounded to
documentation, config, test, or code_patch before activation. Qwen-AgentWorld
and looper stay adjacent as separate `agent_harness_eval_required` rows; they
do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch routing, external harness execution, provider launch, remote
execution, profile writes, memory writes, raw source URL export, raw evidence
URL export, target-path export, replay-command export, or upstream body export.

Source digest `github-growth-20260629T165904.193832Z` completes the
provider-runtime-control pass-4 window by projecting the existing
`provider_runtime_completion_handoff` and `provider_runtime_final_diagnostics`
into `local_kernel_handoff.provider_runtime_supervisor_card`. The card is
body-free and replay-only: it reports the provider sample gate status,
provider-runtime replay readiness, success-claim eligibility, recovery hint
hashes, replay command hashes, and supervisor next action without exporting raw
provider config, preflight inputs, diagnostics, URLs, replay commands, target
paths, or upstream bodies. COMPASS-style skill ecosystem evidence and
zhengxi-views-style generic skill workflow evidence still route only to
documentation, config, test, or code_patch lanes; Qwen-AgentWorld remains an
adjacent `agent_harness_eval_required` row and does not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch routing,
external harness execution, provider launch, remote execution, profile writes,
or memory writes.

Source digest `github-growth-20260629T153904.276953Z` completes pass 4 of the
current skill-route-discovery window with explicit operator rows for
`p1-skill-route-discovery-fixtures`, `p2-skill-routing-doc-clarification`, and
adjacent `p3-agent-harness-eval-gate`. COMPASS-style skill ecosystem evidence
and zhengxi-views-style generic skill workflow evidence are replayed together
as bounded local validation candidates: the fixture proposal selects the test
lane and the documentation proposal selects the documentation lane, while both
remain limited to documentation, config, test, or code_patch outputs with
`local_validation_required: true`. Qwen-AgentWorld and looper remain adjacent
`agent_harness_eval_required` rows and do not inherit `skill_route_discovery`,
direct runtime routing, direct code_patch routing, external harness execution,
provider launch, remote execution, profile writes, memory writes, raw source
URL export, raw evidence URL export, target-path export, replay-command export,
or upstream body export. This interpretation is a local routing and validation
contract only; it grants no runtime permissions and does not authorize upstream
skill or agent activation.

Source digest `github-growth-20260629T101324.100619Z` starts a new pass-1
`skill-route-discovery` window for the anchored proposals
`p1-skill-route-discovery-compass`, `p2-skill-route-discovery-generic`, and
`p3-agent-harness-eval-general-agent-projects`. The local replay surface now
maps COMPASS-style skill ecosystem evidence to a test lane and generic skill
workflow evidence to a documentation lane, both bounded to documentation,
config, test, or code_patch before activation. Qwen-AgentWorld and looper stay
adjacent as `agent_harness_eval_required` rows: they do not inherit
`skill_route_discovery`, direct runtime authority, direct code_patch authority,
external harness execution, provider launch, remote execution, profile writes,
memory writes, raw source URL export, raw evidence URL export, target-path
export, replay-command export, or upstream body export.

Source digest `github-growth-20260629T103324.012579Z` advances pass 2 of the
same slice with an operator-visible local validation lane for
`p1-skill-route-discovery-registry`, `p2-agent-harness-eval-fixtures`, and
`p3-skill-route-docs`. COMPASS-style skill ecosystem evidence maps to the
local test lane, zhengxi-views-style generic skill workflow evidence maps to
the documentation lane, and both rows remain bounded to documentation, config,
test, or code_patch with `local_validation_required: true`. Qwen-AgentWorld and
looper stay adjacent as `agent_harness_eval_required` evidence: they do not
inherit `skill_route_discovery`, direct runtime authority, direct code_patch
authority, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
target-path export, replay-command export, or upstream body export before a
local harness-evaluation route exists.

Source digest `github-growth-20260629T081941.626098Z` starts pass 1 of the
active `skill-route-discovery` window with `zhengxi-views`,
`Qwen-AgentWorld`, `looper`, and `compass-skills` as anchoring proposal
evidence. The reusable lesson selected from `zhengxi-views` is the
root-manifest-plus-references package shape: a `SKILL.md` entry point, root
`skill.yml` manifest, `references/` material, and scripts should become a
bounded progressive skill-package contract, not immediate upstream activation.
The local lane map now marks that shape as `progressive_skill_package`, exposes
manifest/reference validation requirements on candidate inventory and proposal
lanes, and keeps runtime action, external skill activation, external harness
execution, provider launch, remote execution, raw target paths, raw evidence
URLs, and upstream bodies denied. `Qwen-AgentWorld` and `looper` remain
adjacent general-agent evidence unless a separate local harness-evaluation
route validates them.

Source digest `github-growth-20260629T091323.954837Z` advances pass 2 of the
same active `skill-route-discovery` slice with a replayable local lane for
COMPASS Skills, zhengxi-views, Qwen-AgentWorld, and looper. COMPASS-style skill
ecosystem evidence selects a local test lane for state/profile handoff route
metadata without profile writes or memory writes. zhengxi-views-style generic
skill workflow evidence selects the documentation lane for bounded
manifest/workflow interpretation. Qwen-AgentWorld and looper are now visible as
distinct adjacent `agent_harness_eval_required` rows in focused review; neither
inherits `skill_route_discovery`, direct runtime authority, direct code_patch
authority, external harness execution, provider launch, remote execution, raw
URL export, target-path export, replay-command export, or upstream body export.
The security-adjacent AutoCVE proposal remains review-only under
`offensive-behavior-human-review`; no offensive, unauthorized-access, or
exfiltration behavior is implemented by this lane.

Source digest `github-growth-20260629T093324.244697Z` advances pass 3 by
binding the active proposals to `pass3_current_wake_acceptance_packet` before
the final handoff. zhengxi-views-style skill metadata selects the local test
lane for bounded route discovery; COMPASS-style skill ecosystem handoff selects
a documentation checklist lane before any profile, memory, config, or code
change; Qwen-AgentWorld and looper remain adjacent
`agent_harness_eval_required` evidence. The packet keeps unsupported install,
provider runtime, and runtime execution pressure out of allowed local lanes and
exports only hashes, counts, proposal IDs, selected item IDs, validation gates,
and denial booleans. It does not export raw source URLs, replay commands,
target paths, or upstream bodies, and it does not authorize upstream skill or
agent activation, external harness execution, provider launch, profile writes,
memory writes, remote execution, or direct code_patch work for general-agent
projects before a local harness-evaluation result exists.

Source digest `github-growth-20260629T095324.174533Z` completes the planned
pass-4 skill-route-discovery window by specializing
`current_digest_pass4_completion_handoff` for the current proposal IDs.
COMPASS-style skill ecosystem evidence maps to
`proposal-001-skill-route-discovery-compass-skills` in the local test lane,
and zhengxi-views-style generic skill workflow evidence maps to
`proposal-002-generic-skill-workflow-validation` in the local code_patch lane.
Both rows remain bounded to documentation, config, test, or code_patch,
require focused local validation, and export only selected item IDs, hashes,
route profiles, lane names, and denial booleans. Qwen-AgentWorld and looper
stay adjacent under `proposal-003-agent-harness-eval-fixture` as
`agent_harness_eval_required`; they do not inherit `skill_route_discovery`,
direct runtime routing, direct code_patch routing, external harness execution,
provider launch, remote execution, profile writes, memory writes, raw replay
commands, raw source URLs, raw evidence URLs, target paths, or upstream bodies.

Source digest `github-growth-20260629T075941.978810Z` completes pass 4 of the
active `skill-route-discovery` window with
`current_digest_pass4_final_closure`. The closure binds
`p1-skill-route-discovery-compass` to a local test lane for proving
COMPASS-style state handoff repositories remain bounded to documentation,
config, test, or code_patch before any profile or memory write exists. It binds
`p2-skill-route-discovery-generic` to a documentation lane for the
zhengxi-views generic skill workflow interpretation path, including
`local_validation_required` before activation. `p3-agent-harness-qwen-agentworld`
is carried only as adjacent `agent_harness_eval_required` evidence: it does not
inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
target-path export, replay-command export, or upstream body export.

Source digest `github-growth-20260629T073942.884739Z` advances pass 3 of the
active `skill-route-discovery` window with a current-wake acceptance packet for
`p1-skill-route-discovery-compass`, `p2-generic-skill-workflow-probe`, and
`p3-agent-harness-eval-qwen`. COMPASS-style skill ecosystem handoff evidence is
accepted only as a local test lane that validates route metadata, handoff
signals, and profile/memory boundaries before activation. zhengxi-views-style
generic skill workflow evidence is accepted as a documentation lane for the
generic probe checklist. Qwen-AgentWorld remains adjacent
`agent_harness_eval_required` evidence: it does not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, remote execution, profile writes,
memory writes, raw source URL export, raw evidence URL export, replay-command
export, or upstream body export.

Source digest `github-growth-20260629T063941.864598Z` advances pass 2 of the
active `skill-route-discovery` window with a profile-aware local validation
lane for `p1-skill-route-discovery-compass-skills`,
`p2-generic-skill-workflow-probe`, and adjacent
`p3-agent-harness-qwen-agentworld`. COMPASS-style skill ecosystem evidence now
selects a local test lane that checks skill manifests, route metadata, and
state/profile handoff conventions without installing, executing, writing
profiles, or writing memory. zhengxi-views-style skill workflow evidence
selects the documentation lane for the generic probe: enough evidence means
manifest detection, non-execution inspection, bounded lane mapping,
uncertainty recording, and rollback coverage. Qwen-AgentWorld repository and
issue evidence remains `agent_harness_eval_required`; it may inform a local
checklist for install shape, entrypoints, dependency boundaries, task-loop
assumptions, observable behaviors, and evaluation dimensions, but it does not
inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw URL export, replay-command export, or
upstream body export.

Source digest `github-growth-20260629T055941.732014Z` completes the current
pass-4 `skill-route-discovery` window with an operator-visible completion
handoff for the active proposals `p1-compass-skill-ecosystem-handoff`,
`p2-skill-route-discovery-local-fixture`, and adjacent
`p3-general-agent-harness-eval-queue`. COMPASS-style skill ecosystem evidence
selects a documentation lane that records validation gates before any adoption,
profile write, or memory write. zhengxi-views-style Python agent skill evidence
selects a local test lane that proves skill-like repositories classify only to
documentation, config, test, or code_patch. Qwen-AgentWorld and looper remain
adjacent `agent_harness_eval_required` rows: they do not inherit
`skill_route_discovery`, direct runtime authority, direct code_patch authority,
external harness execution, provider launch, remote execution, profile writes,
memory writes, raw URL export, replay-command export, or upstream body export
until a local harness evaluation profile is assigned.

Source digest `github-growth-20260629T061942.961537Z` starts the next pass-1
`skill-route-discovery` window with a replayable current-window fixture for
`p1-skill-route-discovery-compass-skills`,
`p2-skill-route-discovery-zhengxi-views`, and adjacent
`p3-agent-harness-qwen-agentworld`. COMPASS-style skill ecosystem evidence is
treated as a local route-probe test lane: it can verify that handoff/profile
signals stay bounded to documentation, config, test, or code_patch before any
profile or memory write exists. zhengxi-views-style generic skill workflow
evidence selects a documentation lane that records the expected local
validation path before any code or config change. Qwen-AgentWorld repository
and issue activity remain adjacent `agent_harness_eval_required` evidence; they
do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, external harness execution, provider launch, remote
execution, profile writes, memory writes, raw URL export, replay-command export,
or upstream body export.

Source digest `github-growth-20260629T002729.571892Z` starts the current
pass-1 `skill-route-discovery` window with an operator-visible bounded lane for
`p1-skill-route-discovery-zhengxi-views`,
`p2-skill-ecosystem-state-handoff`, and
`p3-agent-harness-eval-general-projects`. zhengxi-views-style public
agent-skill evidence selects the local test lane for skill-term route
validation. COMPASS-style skill ecosystem handoff evidence selects a
documentation lane to record the state/profile boundary before any profile or
memory write is considered. Qwen-AgentWorld and Looper remain adjacent
`agent_harness_eval_required` rows; they may inform documentation, test, or
code_patch harness evaluation only after local harness evidence exists, and do
not inherit `skill_route_discovery`, direct runtime routing, direct code_patch
selection, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw URL export, replay-command export, or
upstream body export.

Source digest `github-growth-20260628T234729.567549Z` adds a focused pass-3
operator lane for the active `skill-route-discovery` wake. The lane maps
`p1-skill-route-discovery-zhengxi-views` to a local test lane for bounded
skill-route validation and maps `p3-threejs-game-skills-route` to a
documentation lane for the `game_frontend_workflow` profile. It intentionally
does not require an unrelated COMPASS/state-handoff row when that proposal is
not part of the active wake. `p2-agent-harness-qwen-agentworld` remains an
adjacent `agent_harness_eval_required` row: it may collect install shape,
entrypoints, dependency boundaries, task-loop assumptions, observable
behaviors, and evaluation dimensions before any controller, runner, workflow,
or code_patch route is considered. The packet exports selected item IDs,
source hashes, bounded lanes, validation gates, and replay-command hashes only;
runtime action, upstream skill or agent activation, external harness
execution, provider launch, profile writes, memory writes, remote execution,
raw source URLs, raw evidence URLs, raw target paths, replay commands, and
upstream bodies remain denied.

Source digest `github-growth-20260628T230729.580958Z` adds an operator-visible
pass-1 readiness lane for the active `skill-route-discovery` window. The lane
maps `p1-skill-route-discovery-views` to a bounded generic skill workflow test
lane, `p3-threejs-game-skill-profile` to a documentation lane for
`game_frontend_workflow`, and `p4-compass-skills-state-handoff` to a config
lane for metadata-only state handoff. The same readiness surface carries
`p2-agent-harness-eval-qwen-agentworld` as adjacent
`agent_harness_eval_required` evidence rather than inheriting
`skill_route_discovery`; `p5-agent-harness-eval-looper` remains an anchoring
proposal ID until body-free local evidence is present. The panel exports only
hashes for replay commands and keeps runtime action, upstream skill activation,
external harness execution, provider launch, profile writes, memory writes,
remote execution, raw source URLs, raw evidence URLs, and upstream bodies
denied before local validation.

Source digest `github-growth-20260628T224729.591354Z` closes the current
four-pass skill-route-discovery window with a replayable pass-4 fixture for the
active proposal IDs `proposal-skill-route-discovery-generic-001`,
`proposal-threejs-game-skill-routing-002`, and
`proposal-skill-ecosystem-handoff-003`. The fixture keeps zhengxi-views-style
generic skill workflow evidence in `generic_skill_workflow` when no stronger
source-cited domain signals are present, maps Three.js game skill evidence to
`game_frontend_workflow`, and maps COMPASS-style state handoff evidence to
`skill_ecosystem_state_handoff`. The final local-kernel handoff may expose only
documentation, config, test, or code_patch lanes, requires local validation and
external supervisor replay, and continues to deny runtime action, upstream skill
activation, external harness execution, provider launch, remote execution, raw
source URLs, raw evidence URLs, and upstream bodies.

Source digest `github-growth-20260628T220729.598607Z` tightens the pass-2
operator completion surface so it carries the active proposal IDs from the
skill-route-discovery window. zhengxi-views-style generic or source-cited skill
evidence maps to the local test lane, Three.js game/frontend skill workflow
evidence maps to the documentation lane before any code patch, and
COMPASS-style ecosystem handoff evidence maps to the config lane. The completion
lane uses the registry source digest rather than stale pass metadata, and still
requires rollback evidence, focused local validation, changed-file review, and
external supervisor handoff before activation.

Source digest `github-growth-20260628T222729.564410Z` advances the same slice
for pass 3 by making the active proposal IDs operator-visible in
`current_digest_pass3_focused_validation_packet`.
`p1-skill-route-discovery-zhengxi-views` selects the local test lane for
generic skill workflow discovery, `p2-threejs-game-skill-profile` selects the
documentation lane for game/frontend skill profile routing, and
`p3-skill-ecosystem-state-handoff` selects the config lane for metadata-only
handoff routing. Unsupported install, provider runtime, and runtime execution
pressure is excluded from the exported operator packet and is not part of
`allowed_local_lanes`; it does not authorize upstream skill activation,
external harness execution, provider launch, profile writes, memory writes, or
remote execution. Adjacent Qwen-AgentWorld-style evidence remains
`agent_harness_eval_required` and does not inherit `skill_route_discovery`.

This note is grounded in source digest `github-growth-20260618T062043.878926Z`,
refined by `github-growth-20260618T171207.138935Z`, clarified by
`github-growth-20260618T193207.157147Z`, reaffirmed by
`github-growth-20260618T215207.204133Z`, and extended by
`github-growth-20260618T233207.218276Z`. The source digest
`github-growth-20260619T001207.230597Z` rechecked the same route class and
added the requirement that selected digest `item_id` values remain visible in
item-derived lane maps. Source digest `github-growth-20260620T005207.516587Z`
extended the replay fixture to the current four carried skill evidence items,
including fork-lineage evidence, while preserving selected `item_id` citations
instead of URL citations. Source digest
`github-growth-20260621T021207.784187Z` added a core lane-map probe for mixed
Codex/agent/skill/workflow repositories so `skill_route_discovery` stays first
before any broader agent-harness evaluation. Source digest
`github-growth-20260621T033207.842733Z` carried the same pass-2 route window and
adds an operator-visible pass-2 handoff packet for the selected bounded lane,
queued bounded lanes, and blocked secondary harness route. Source digest
`github-growth-20260621T043207.872197Z`
adds a current-window pass-1 fixture that keeps the carried COMPASS, Three.js,
and FableCodex evidence in selected-item lanes before activation. Source digest
`github-growth-20260621T113207.793637Z` extends the same pass-2 window with
`LeanEntropy/threejs-phaser-game-skills`, a fork-lineage game-engine skill
signal. Phaser and game-engine language are interpreted as
`game_frontend_workflow` profile evidence only; they can select local
documentation, config, test, or code_patch lanes, but do not permit install,
execute, scaffold, asset generation, provider launch, or upstream skill
activation.
Source digest `github-growth-20260627T074311.075116Z` adds a current-window
Three.js fork-cluster validation lane. The carried repositories
`MartinYeung5/threejs-game-skills`, `TheLostRiver/threejs-game-skills`,
`majidmanzarpour/threejs-game-skills`, and `mrkr/threejs-game-skills` share the
same game-skill package shape: skills directories, installer or scripts,
scaffold/helper material, QA/browser validation language, and optional provider
asset-generation notes. The local lesson is not to install or execute any of
those packages. The harness collapses the cluster into one
`game_frontend_workflow` route, selects the local `test` validation lane first,
queues only documentation, config, and code_patch as bounded follow-up lanes,
and keeps upstream scaffold execution, provider launch, asset generation, and
external skill activation denied.
Source digest `github-growth-20260622T053431.406906Z` keeps the same
COMPASS/FableCodex/Three.js/Omnigent route window active for pass 2 and adds
core lane-map handoff metadata so every recognized skill repository produces a
selected local validation lane plus queued bounded lanes before activation.
Source digest `github-growth-20260622T093432.348800Z` adds
`lyra81604/zhengxi-views` as a source-cited domain research agent skill signal.
This is classified as `source_cited_domain_research`: it may select local
documentation, config, test, or code_patch validation lanes for citation and
advice-boundary checks, but it does not permit upstream dataset import,
provider-backed advice generation, financial advice, install, execution,
scaffold, or external skill activation.
Source digest `github-growth-20260622T154624.499439Z` replays the active
provider-runtime-control pass-2 window across FableCodex, COMPASS Skills,
zhengxi-views, and Three.js Game Skills. Provider/runtime wording in these
skill workflow records is interpreted only as a request for body-free
diagnostics, recovery hints, and locally replayable validation. It does not add
a provider-runtime lane, external harness lane, install lane, execution lane, or
remote activation path.
Source digest `github-growth-20260623T155349.080210Z` completes the pass-4
skill-route-discovery window across FableCodex, COMPASS Skills, zhengxi-views,
Three.js Game Skills, and Omnigent movement evidence. `zhengxi-views` stays in
the `source_cited_domain_research` profile and can complete only through a local
test lane that checks citation and advice boundaries. Omnigent-style harness
movement remains a blocked secondary bridge after skill-route validation; it
does not authorize external harness execution, provider launch, remote
execution, or upstream skill activation.
Source digest `github-growth-20260624T055355.537474Z` reuses the same
upstream-evidence-to-capability window for pass 3 and makes the local
interpretation explicit: `skill_route_discovery` is a bounded local capability
route, not a skill activation route. It may map only to documentation, config,
test, or code_patch work; each selected lane must carry local validation before
activation. FableCodex-style workflow evidence can select the
`codex_workflow_gate` profile, COMPASS-style state or collaboration evidence can
select `skill_ecosystem_state_handoff`, source-cited domain skill evidence can
select `source_cited_domain_research`, and Three.js or Phaser skill bundles can
select `game_frontend_workflow`. These profiles are examples for routing and
review only. Proposal evidence refs must cite selected digest `item_id` values,
not raw repository URLs, owner/repository names, truncated item IDs, or
non-selected evidence. The review layer may derive accepted source URLs from the
selected item IDs, but candidates must not supply or expand them.

Source digest `github-growth-20260627T090310.946057Z` starts another
skill-route-discovery pass focused on converting carried proposal evidence into
bounded local lanes before activation. The local lane map now emits
`proposal_intake_lane`, an operator-facing review surface that groups active
proposal IDs by route profile: generic or source-cited skill evidence maps to
`p1-skill-route-discovery-generic`, Three.js/browser-game skill evidence maps
to `p2-game-frontend-skill-profile`, and COMPASS-style state/profile handoff
evidence maps to `p3-skill-ecosystem-handoff`. This surface records candidate
names, source hashes, selected bounded lanes, validation gates, validation
targets, and replay commands. It does not add lanes, export raw source URLs,
export raw target paths, read upstream bodies, install upstream skills, execute
external harnesses, launch providers, write memory/profile state, perform
remote execution, or grant runtime action.

Source digest `github-growth-20260627T092310.871194Z` continues the same
skill-route-discovery window with COMPASS Skills, zhengxi-views, and Three.js
Game Skills as the active focused-evidence-review set. The local lane map now
also emits `focused_evidence_review_lane`, which groups the active pass
proposal IDs `p1-skill-route-discovery-baseline`,
`p2-skill-ecosystem-documentation`, and
`p3-game-frontend-skill-validation` before activation. This surface is a
bounded review lane only: it may choose documentation, config, test, or
code_patch validation work, and it must carry a frozen fixture or selected item
IDs, a rollback artifact, focused local validation, and a review note. It does
not add evidence URLs, export raw source URLs, export target paths, read
upstream bodies, install or enable upstream skills, execute external harnesses,
launch providers, perform remote execution, or grant runtime action.

Source digest `github-growth-20260627T100311.166711Z` completes the current
skill-route-discovery pass by adding `pass4_local_lane_validation` to the same
lane map. This packet checks the carried COMPASS, zhengxi-views, and Three.js
skill workflow examples as one final local validation surface: each row must
keep `route_hint: skill_route_discovery`, select only documentation, config,
test, or code_patch lanes, carry `local_validation_required: true`, and deny
runtime action, upstream skill activation, external harness execution, provider
launch, remote execution, raw source URL export, raw target path export, and
upstream body export. Adjacent Qwen-AgentWorld-style general-agent or benchmark
projects do not inherit this route unless they have skill workflow signals.
Without those signals, they stay in `agent_harness_eval_required` with no
direct local change proposals until a local agent-harness evaluation route is
established.

Source digest `github-growth-20260627T212729.541663Z` closes the planned
pass-4 skill-route-discovery window with `current_pass_profile_closure`, a
completion-report surface keyed to the active proposal IDs
`proposal-skill-route-discovery-general-001`,
`proposal-game-skill-profile-002`, and
`proposal-skill-state-handoff-003`. The closure binds zhengxi-views-style
source-cited skill workflows to the local test lane, Three.js game skill
workflows to the local test lane, and COMPASS-style state handoff ecosystems to
the local config lane. It is body-free and bounded: rows may expose selected
item IDs, source hashes, selected local lanes, validation commands, and replay
steps only. Unsupported install, runtime execution, provider runtime, upstream
skill activation, external harness execution, remote execution, raw source URL
export, target path export, and upstream body export remain denied. Adjacent
Qwen-AgentWorld-style harness evidence stays in `agent_harness_eval_required`
and does not inherit `skill_route_discovery` unless later evidence shows a
skill workflow route shape.

Source digest `github-growth-20260627T102312.650770Z` starts the next
skill-route-discovery pass by adding `current_pass_validation_cases` to the
lane map. This operator surface names the active proposal IDs
`p1_skill_route_discovery_generic_views`,
`p2_skill_route_discovery_game_frontend`, and
`p3_skill_ecosystem_state_handoff_config`, then binds each to a matched route
profile, selected local lane, validation target, and replay command. Generic
Python agent-skill workflow evidence may satisfy the first case through
`generic_skill_workflow`; source-cited variants remain in
`source_cited_domain_research` and keep the stricter test lane. Game frontend
signals may choose only a documentation/config/test/code_patch lane after
`skill_route_discovery`, and COMPASS-style state handoff signals remain bounded
to local config or validation metadata. The surface exports source hashes and
selected item IDs only, denies runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw source URL
export, raw target path export, and upstream body export.

Source digest `github-growth-20260627T110310.772544Z` continues that pass with
`pass3_activation_handoff`. The handoff maps the current proposal IDs
`p1-skill-route-discovery-zhengxi-views`,
`p2-game-frontend-skill-route`, and
`p3-skill-ecosystem-state-handoff` to the validation cases already derived from
zhengxi-views, Three.js Game Skills, and COMPASS Skills evidence. Its purpose is
operator replay before final-pass completion: each row carries the selected
bounded local lane, validation gate, validation target, replay command,
candidate source hashes, and activation blockers. It is not an activation grant.
Runtime action, external skill activation, external harness execution, provider
launch, remote execution, profile writes, memory writes, raw source URL export,
raw evidence URL export, raw target path export, and upstream body export remain
denied.

## Current Digest Pass 1 Focused Evidence Review Lane

Source digest `github-growth-20260628T202729.536231Z` starts a new pass-1
skill-route-discovery window with `pass1_focused_evidence_review_lane`. The lane
is an operator-facing compatibility surface for fresh anchoring proposal IDs
that may not yet be indexed by older pass-1 replay queue aliases.

For the current digest shape, the lane maps Three.js game skill repositories to
`game_frontend_workflow` in the local `test` lane, generic skill workflow
evidence to `generic_skill_workflow` in the local `documentation` lane, and
COMPASS-style state handoff evidence to `skill_ecosystem_state_handoff` in the
local `config` lane. If an anchoring proposal is absent from the pass-1 replay
queue, the lane may fall back to the ready `profile_lane_acceptance_contract`
and `validation_lane_plan` rows, exporting only proposal IDs, route profiles,
selected local lanes, validation gates, selected item IDs, source hashes, and
diagnostics.

The lane is not activation. Documentation, config, test, and code_patch remain
the only skill-route lanes. Runtime action, upstream skill activation, external
harness execution, provider launch, remote execution, raw source URL export, raw
evidence URL export, and upstream body export remain denied.

Source digest `github-growth-20260627T114310.634245Z` starts a fresh pass over
the same skill-route-discovery slice with Three.js Game Skills, zhengxi-views,
and COMPASS Skills evidence. The local regression fixture
`current_window_pass1_skill_route_lanes.json` converts those public repository
signals into classification records only. Three.js/browser-game evidence
selects `game_frontend_workflow`; generic skill workflow evidence can select
`generic_skill_workflow`; COMPASS-style route/profile evidence selects
`skill_ecosystem_state_handoff`. Each route may expose only documentation,
config, test, or code_patch lanes and must cite selected proposal or digest item
IDs. Unsupported install, runtime, provider, or execution lanes are downgraded
out of the proposal lane map. Public activity such as stars, forks, trend
presence, or fork-lineage references is supporting context only: it does not
increase candidate count, proposal lane count, activation readiness, or runtime
authority.

Source digest `github-growth-20260627T190729.505995Z` opens another pass-1
window over the same skill-route-discovery slice. The lane map now emits
`active_window_pass1_route_lanes`, an operator-facing packet keyed to the active
proposal IDs `p1-skill-route-discovery-generic`,
`p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff`. Generic or source-cited skill evidence such
as zhengxi-views must expose documentation, config, test, and code_patch as
bounded local lanes, with the test lane selected first for citation and
advice-boundary validation. Three.js game/frontend skill evidence can select a
documentation lane, but any code_patch work remains behind local frontend
validation. COMPASS-style state handoff evidence can select a config lane, but
profile and memory writes remain denied. Adjacent general-agent evidence such
as Qwen-AgentWorld stays in `agent_harness_eval_required` and does not inherit
skill-route runtime or code_patch authority.

Source digest `github-growth-20260627T192729.517144Z` advances the next pass-2
window by adding `current_pass2_validation_lane`. The lane binds the active
proposal IDs `p1-skill-route-discovery-general`, `p2-agent-harness-eval`, and
`p3-game-frontend-skill-profile` into one operator-visible replay surface.
Generic public skill workflow evidence may select only documentation, config,
test, or code_patch local lanes and must carry selected item IDs, validation
gates, and a focused local replay command. Three.js/browser-game skill evidence
continues to require the `game_frontend_workflow` validation gate before any
frontend code_patch work. Qwen-AgentWorld-style general-agent benchmark evidence
is recorded only as an adjacent `agent_harness_eval_required` row; it must first
provide install shape, entrypoints, dependency boundaries, task-loop
assumptions, observable behaviors, and evaluation dimensions before it can
influence runner, scheduling, memory, or controller behavior. The pass-2 lane
exports no raw source URLs, raw evidence URLs, raw target paths, or upstream
bodies, and it denies runtime action, external skill or agent activation,
external harness execution, provider launch, and remote execution.

Source digest `github-growth-20260628T112729.897169Z` continues pass 2 with
`current_pass2_activation_readiness`, keyed to the active proposal IDs
`p1-skill-route-discovery-compass-zhengxi`,
`p2-threejs-game-skill-workflow-doc`, and
`p3-agent-harness-eval-general-agent-projects`. COMPASS-style state handoff,
source-cited zhengxi-views skill evidence, and Three.js game/frontend skill
evidence may select only documentation, config, test, or code_patch local
lanes, all with `local_validation_required: true`. Game/frontend skill workflow
signals should be evaluated first as route metadata and local validation
coverage; they do not imply scaffold execution, browser asset generation, or a
frontend code patch before the bounded lane is selected. Qwen-AgentWorld-style
general-agent evidence remains `agent_harness_eval_required` and exposes no
implementation lanes until a local agent-harness evaluation result is present.
The surface is body-free and keeps runtime action, external skill or agent
activation, external harness execution, provider launch, remote execution, raw
source URL export, and upstream body export denied.

Source digest `github-growth-20260627T204729.546585Z` keeps that pass-2 window
focused on bounded local lane activation candidates. The pass-2 handoff packet
now emits `activation_candidate_lane`, which is derived from the selected
current-pass lane, queued bounded lanes, profile acceptance contracts, and local
artifact review proofs. A row can be ready only when its lane is one of
documentation, config, test, or code_patch, its route profiles have accepted
validation gates, its artifact targets are represented by hashes, and its local
validation remains required. This surface is a local diff candidate queue for
external supervisor replay. It does not export raw source URLs, raw evidence
URLs, raw target paths, or upstream bodies, and it keeps runtime action,
external skill activation, external agent activation, external harness
execution, provider launch, and remote execution denied.

Source digest `github-growth-20260627T120310.659503Z` advances pass 2 by adding
a route-classification fixture lane for the same proposal family. Frozen
fixtures may place `route_hints`, `route_profiles`, allowed local lanes, and
layout or metadata signals under a nested `route_classification` object so the
digest can hand off compact evidence without importing upstream bodies. The
loader still validates that the candidate is disabled, the source is a plain
public GitHub repository URL, and the resulting lanes are bounded to
documentation, config, test, or code_patch. Unsupported nested lanes such as
provider_runtime, runtime_execution, and install are downgraded out of proposal
lanes. The emitted `pass2_fixture_validation_lane` gives operators one replay
surface that checks route class, selected bounded lane, evidence item IDs or
frozen fixture presence, and `local_validation_required: true` before any later
activation handoff.

Source digest `github-growth-20260627T180729.492580Z` continues pass 2 with a
growth-route summary artifact for the same COMPASS Skills, zhengxi-views, and
Three.js Game Skills window. The lane map now emits
`growth_route_summary_artifact`, derived from the pass-2 fixture validation
lane, profile lane handoff, and validation handoff. It gives operators one
compact body-free summary of proposal IDs, route profiles, selected bounded
lanes, downgraded unsupported lane pressure, selected evidence item IDs,
validation targets, and replay-command hashes. It deliberately does not export
raw GitHub URLs, raw replay commands, local target paths, or upstream bodies,
and it continues to deny runtime action, external skill or agent activation,
external harness execution, provider launch, remote execution, profile writes,
and memory writes.

Source digest `github-growth-20260627T132310.624297Z` keeps pass 2 active and
adds `pass2_profile_lane_handoff` beside the fixture validation lane. This
operator surface maps the active proposal IDs
`proposal-skill-route-discovery-generic-zhengxi-views`,
`proposal-game-frontend-skill-profile-doc-test`, and
`proposal-skill-ecosystem-state-handoff-config-doc` to their observed route
profiles, selected local validation lane, replay command, source hashes, and
selected evidence item IDs. It also records downgraded unsupported lane pressure
such as provider_runtime, runtime_execution, and install without exporting raw
source URLs. The handoff remains body-free and non-executable: runtime action,
external skill activation, external harness execution, provider launch, remote
execution, profile writes, memory writes, raw evidence URL export, target path
export, and upstream body export stay denied.

Source digest `github-growth-20260627T122310.714088Z` advances pass 3 of the
same skill-route-discovery slice by adding `pass3_route_discovery_index`. The
index maps the active proposal IDs `p1_skill_route_discovery_index`,
`p2_skill_workflow_docs`, and `p3_skill_route_metadata_config` to the observed
`source_cited_domain_research`, `game_frontend_workflow`, and
`skill_ecosystem_state_handoff` profiles before activation. Each row carries
candidate source hashes, selected evidence item IDs, validation gates,
validation targets, replay commands, and only documentation, config, test, or
code_patch as allowed local lanes. Unsupported route pressure such as install,
provider runtime, runtime execution, profile writes, memory writes, external
harness execution, provider launch, remote execution, raw source URL export,
raw evidence URL export, raw target path export, and upstream body export
remains denied.

Source digest `github-growth-20260627T134310.685675Z` continues the active
pass 3 by adding `pass3_preflight_queue`. The queue joins the
`pass3_route_discovery_index` and `pass3_activation_handoff` surfaces so an
operator can see, before final-pass replay, whether the required
`source_cited_domain_research`, `game_frontend_workflow`, and
`skill_ecosystem_state_handoff` profiles are present, which bounded local
lanes are selected, which replay commands should be run, and which proposal IDs
remain blocked. It is still a discovery preflight only: allowed local lanes are
only documentation, config, test, or code_patch; runtime action, external skill
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
raw target path export, and upstream body export remain denied.

Source digest `github-growth-20260627T130311.159432Z` restarts pass 1 for the
same slice with the active proposal IDs
`proposal-skill-route-discovery-generic-zhengxi-views`,
`proposal-game-frontend-skill-profile-doc-test`, and
`proposal-skill-ecosystem-state-handoff-config-doc`. The local replay fixture
`skill_route_discovery_lane_20260627_pass1_window.json` treats zhengxi-views as
generic skill workflow evidence, Three.js Game Skills as
`game_frontend_workflow`, and COMPASS Skills as
`skill_ecosystem_state_handoff`. The controller-facing lesson is unchanged:
these profiles enter `skill_route_discovery` first, select only documentation,
config, test, or code_patch lanes, require local validation, and do not grant
runtime permissions. The state-handoff profile is evaluated through the same
route discovery queue and cannot bypass recomputed runtime gates, profile or
memory write denial, external skill activation denial, provider launch denial,
raw evidence URL hashing, or upstream body exclusion.

Source digest `github-growth-20260627T142310.634775Z` starts the active
skill-route-discovery window with COMPASS Skills, zhengxi-views, Three.js Game
Skills, and Qwen-AgentWorld evidence. The lane map now emits
`active_pass1_evidence_lane`, which keeps COMPASS-style state handoff,
source-cited zhengxi-views skill evidence, and Three.js/browser-game skill
evidence in bounded local documentation, config, test, or code_patch lanes with
local validation required. General-agent evidence such as Qwen-AgentWorld does
not inherit `skill_route_discovery` without skill workflow signals; it is
recorded as an adjacent `agent_harness_eval_required` row with no direct
runtime or code_patch route until a local agent-harness evaluation path is
established. The surface exports hashes and selected IDs only, and denies
runtime action, external skill or agent activation, external harness execution,
provider launch, remote execution, raw source URL export, raw evidence URL
export, target path export, and upstream body export.

Source digest `github-growth-20260627T202729.517326Z` replays the active pass-1
shape for the current wake. The registry now preserves caller-provided source
digest metadata from frozen evidence items, and the harness lane summary
surfaces the active pass-1 digest/status without exporting raw evidence URLs or
the full upstream body. Older fixtures that do not carry digest metadata keep
the previous fallback digest only for compatibility; current operator replay
should prefer the carried digest when present.

Source digest `github-growth-20260627T170310.779794Z` advances pass 3 of the
same skill-route-discovery slice with a current local validation lane. The lane
map now emits `pass3_local_validation_lane`, keyed to
`p1-skill-route-discovery-index`, `p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff`. It treats zhengxi-views as generic skill
workflow evidence, Three.js Game Skills as `game_frontend_workflow`, and
COMPASS Skills as `skill_ecosystem_state_handoff`. Each row selects only a
bounded local lane, records source hashes and selected evidence item IDs,
downgrades install/runtime/provider pressure, and carries uncertainty when
repository details were not inspected. Runtime action, upstream skill
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
raw target path export, and upstream body export remain denied.

Source digest `github-growth-20260627T194729.481658Z` keeps pass 3 active and
turns the same lane into an operator replay contract. Each pass-3 row now
exposes a `bounded_lane_contract` that proves the selected lane is one of
documentation, config, test, or code_patch and records any removed install,
runtime, or provider pressure. The lane also emits
`operator_replay_contract`, a compact supervisor handoff with proposal IDs,
selected bounded lanes, hashed replay commands, rollback artifact/ref
requirements, and the next replay action. This contract is not an activation
grant: local validation is still required before final-pass promotion, and
runtime action, upstream skill activation, external harness execution, provider
launch, remote execution, profile writes, memory writes, raw source URL export,
raw evidence URL export, raw target path export, raw replay command export, and
upstream body export remain denied.

Source digest `github-growth-20260627T210729.503389Z` keeps pass 3 active with
`pass3_current_wake_acceptance_packet`. The packet binds the current proposal
IDs `p1-skill-route-discovery-index`, `p2-skill-route-discovery-docs`, and
`p3-agent-harness-eval-fixtures` into one supervisor-visible acceptance check.
The skill rows for zhengxi-views, Three.js Game Skills, and COMPASS Skills
must keep `skill_route_discovery`, body-free evidence IDs, local validation,
and only documentation, config, test, or code_patch lanes. Adjacent
Qwen-AgentWorld-style general-agent evidence remains
`agent_harness_eval_required` with `skill_route_discovery_inherited: false`;
it may be evaluated through documentation, test, or code_patch fixtures, but it
does not receive direct runtime, direct code_patch implementation, external
harness execution, provider launch, remote execution, profile writes, memory
writes, raw source URL export, raw evidence URL export, raw replay command
export, raw target path export, or upstream body export.

Source digest `github-growth-20260627T222729.506372Z` keeps pass 3 active for
the current proposal IDs `p1-skill-route-discovery-matrix`,
`p2-skill-route-documentation`, and `p3-agent-harness-eval-fixtures` by adding
`pass3_active_window_review_packet`. The packet is an operator review surface:
zhengxi-views remains `generic_skill_workflow`, Three.js Game Skills remains
`game_frontend_workflow`, and COMPASS Skills remains
`skill_ecosystem_state_handoff`; each skill row must enter
`skill_route_discovery_first`, expose only documentation, config, test, or
code_patch lanes, and require local validation before final-pass continuation.
Qwen-AgentWorld-style general-agent evidence remains adjacent
`agent_harness_eval_required` with `skill_route_discovery_inherited: false` and
no direct runtime or direct code_patch implementation route. Replay commands,
source URLs, evidence URLs, target paths, and upstream bodies remain unexported
or hashed, while runtime action, external skill or agent activation, external
harness execution, provider launch, remote execution, profile writes, and
memory writes remain denied.

Source digest `github-growth-20260627T184730.160071Z` completes the current
pass-4 window over COMPASS Skills, zhengxi-views, Three.js Game Skills, and
Qwen-AgentWorld. The final handoff keeps the three skill workflow records in
`pass4_local_lane_validation` and `pass4_completion_handoff` with selected
local lanes limited to documentation, config, test, or code_patch. Adjacent
general-agent evidence such as Qwen-AgentWorld is represented as an
`agent_harness_eval_required` row, not as inherited skill-route evidence. It
may name later documentation, test, or code_patch evaluation lanes only after a
local agent-harness eval route is established; direct runtime action, direct
code_patch activation, external agent activation, external harness execution,
provider launch, remote execution, raw source URL export, raw evidence URL
export, target path export, and upstream body export remain denied.

The bounded evidence reviewed for these runs is:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/ACN1987/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/LeanEntropy/threejs-phaser-game-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/pretinhuu1-boop/threejs-game-skills`
- `https://github.com/wisdomedeki761/threejs-game-skills`
- `https://github.com/xiaoguomeiyitian/threejs-game-skills`

No upstream code, install scripts, prompts, or skill bodies were adopted.

The 2026-06-18T21:52Z wake rechecked the same public repository class and kept
the lesson narrow. FableCodex describes Codex workflow gates, COMPASS Skills
describes local skills for clarification, task memory, and collaboration
profiles, and Three.js Game Skills describes a domain director with specialist
skills and verification helpers. Those are useful routing shapes, but the local
artifact remains documentation and fixture coverage only. The evidence does not
grant permission to install, execute, scaffold, profile, generate assets, or
activate any upstream skill package.

## Route Matrix

| Observed repository | Evidence shape | Candidate lanes | Local lesson | Activation boundary |
| --- | --- | --- | --- | --- |
| `baskduf/FableCodex` | Codex workflow package with evidence gates, inspection, ledgers, and verification habits. | documentation, test, code patch | Treat workflow skills as process-contract evidence that can become local docs, regression checks, or bounded verification behavior. | Keep disabled until a local test or controller path proves the specific gate. |
| `dongshuyan/compass-skills` | Multi-skill system for clarification, repo-local task memory, and collaboration profile state. | documentation, config, test, code patch | Treat skill ecosystems as routing topology evidence: entry points, durable state, and ambiguity gates can inform local route metadata. | Do not create local memory/profile behavior from repository presence alone. |
| `lyra81604/zhengxi-views` | Source-cited domain research agent skill with public-view evidence and investment-research framing. | documentation, config, test, code patch | Treat source-cited domain skills as evidence for local citation and advice-boundary validation. | Do not import upstream datasets, generate financial advice, launch providers, or treat repository claims as decision support. |
| `majidmanzarpour/threejs-game-skills` | Domain director routes specialist game, asset, debug, QA, and release skills with bundled helper materials. | documentation, config, test, code patch | Treat domain directors as evidence for explicit route orchestration and validation ledgers. | Do not run bundled scaffolds, installers, browser checks, or asset generators without a separate local capability path. |
| `LeanEntropy/threejs-phaser-game-skills` | Fork-lineage game-skill bundle adds Phaser/game-engine wording to the Three.js browser-game route shape. | documentation, config, test, code patch | Treat Phaser or game-engine skills as the same local `game_frontend_workflow` validation profile. | Do not amplify fork presence into installation, execution, scaffolding, provider launch, or external skill activation. |

## Route Discovery Catalog

The reusable lesson is a category map, not a source import. A future digest may
observe more skill repositories than the three above, but each observation must
be translated through one of these local routes before proposal synthesis uses
it:

| Category | Recognition hints | Allowed local outputs | Required validation | Rejected shortcut |
| --- | --- | --- | --- | --- |
| Workflow-gate package | Evidence gates, review ledgers, inspection habits, verification routines, Codex or agent workflow language. | documentation, test, code_patch | Show the local gate in docs or a focused regression before changing runtime behavior. | Installing the upstream workflow or treating its README as proof the local controller already behaves that way. |
| State and alignment skill system | Task memory, collaboration profile, clarification gate, repo-local task graph, route metadata, skill ecosystem map. | documentation, config, test, code_patch | Keep state body-free unless a later local design explicitly models storage, retention, correction, and privacy boundaries. | Creating profile or memory behavior from repository presence alone. |
| Source-cited domain research skill | Traceable or cited source corpus, domain research framing, investment or other advisory wording, QA/source-grounding claims. | documentation, config, test, code_patch | Validate citation provenance and advice disclaimers locally before any domain-specific behavior changes. | Importing upstream datasets, generating advice, launching providers, or treating public views as verified local knowledge. |
| Domain director or specialist bundle | Director skill, specialist skills, scaffold, packaged helpers, QA scripts, asset or browser validation workflow. | documentation, config, test, code_patch | Validate only the local orchestration or boundary being changed; treat bundled scaffolds and helpers as evidence to inspect. | Running installer, scaffold, browser checker, asset generator, credential probe, or helper script during discovery. |

Catalog entries are additive only when they preserve the same bounded outputs:
documentation, config, test, or code_patch. Any proposed lane outside that set
is recorded as rejected or downgraded evidence, never as an activation request.
The local harness now emits `route_hint_lane_policy` beside the lane map so an
operator can see the exact bounded contract before activation: allowed local
lanes, selected local lanes, rejected lane names, downgrade/rejection counts,
and whether review is required. This policy surface is body-free and keeps
runtime action, external skill activation, external harness execution, provider
launch, remote execution, raw source URL export, and upstream body export
denied.

Source digest `github-growth-20260624T155904.194675Z` continues the pass-2
skill-route-discovery window across COMPASS Skills, zhengxi-views, and
Omnigent-style MCP/tool-route movement. The reusable local lesson is that a
bounded lane queue should be replayable from the operator surface itself. The
pass replay queue and pass-2 handoff now carry a `local_artifact_review` packet
per selected or queued lane with the artifact kind, changed-file target hashes,
review requirements, and the same denials for runtime action, upstream skill
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw target path export, and upstream body export. This makes
the selected `test` lane and queued `config` lane auditable before activation
without importing upstream skill bodies or executing external projects.

Pass-2 lane maps also emit `privacy_review_panel`, a body-free operator surface
for skill-route evidence that touches state/profile handoff, private-context
export, provider launch, or advisory/domain research boundaries. COMPASS-style
state handoff rows remain in the selected local config lane while requiring
`privacy-leakage-human-review`; source-cited domain research rows remain in the
selected local test lane while denying private-context export and provider
runtime launch. The panel carries candidate source hashes, route profiles,
selected local lanes, review reason codes, and validation gates only. It does
not export raw source URLs, raw evidence URLs, raw target paths, upstream
bodies, or sensitive values, and it does not authorize profile writes, memory
writes, external skill activation, external harness execution, provider launch,
remote execution, or runtime action.

Lane maps also emit `bounded_route_profile_matrix`, a compact profile-to-lane
view for pass-2 review. The matrix maps observed `generic_skill_workflow`,
`game_frontend_workflow`, and `skill_ecosystem_state_handoff` evidence to only
the bounded documentation, config, test, or code_patch lanes, then records the
selected local lane, validation target, replay command, candidate source hashes,
and activation boundary for each profile. It is classification metadata only:
runtime action, external skill activation, external harness execution, provider
launch, remote execution, raw source URL export, raw evidence URL export, raw
target path export, and upstream body export remain denied.

Provider/runtime-control passes follow the same rule. If a skill workflow item
mentions provider setup, runtime launch, model commands, harnesses, or recovery
workflow, the route may still choose only documentation, config, test, or
code_patch. The resulting lane map must keep `local_validation_required: true`,
`runtime_action: none`, `provider_runtime_launch_allowed: false`,
`external_harness_execution_allowed: false`, and `remote_execution_allowed:
false` until a separate local preflight proves the runtime path. FableCodex-style
mixed Codex/workflow evidence can expose
`agent_harness_eval_after_local_corroboration`, but that secondary path stays
blocked until the skill-route regression has passed.

The provider-runtime preflight now includes runner-state diagnostics for
Omnigent-style meta-harness failures where a harness disconnect and a mid-turn
buffered message leave tool callbacks without active turn context. That signal
maps to `provider_runner_turn_context_desync`: a blocker that emits only counts,
hashes, booleans, replay commands, and recovery hint codes. It does not export
session ids, runner logs, callback bodies, policy bodies, upstream issue bodies,
or raw source URLs, and it does not authorize provider launch. If policy handling
defaulted allow while turn context was missing, the diagnostic records
`policy_fail_open_risk` and requires fail-closed or self-heal/watchdog recovery
before replay.

## Classification Rules

Record a candidate as `skill_route_discovery` when the digest evidence shows a
public repository organized around reusable agent skills, directors, workflows,
or skill installation. The first local artifact should be body-free metadata:
name, source URL, short evidence summary, route hint, candidate lanes, validation
status, and disabled state.

Source URLs must be plain public GitHub repository URLs. The classifier rejects
local paths, non-HTTPS schemes, private hostnames, owner-only GitHub URLs, and
URLs carrying query strings, fragments, embedded credentials, or other
decorations. Discovery metadata is intended to be replayable public evidence,
not an intake path for private locations, tokens, or installable package bodies.

Allowed candidate lanes are exactly:

- documentation
- config
- test
- code_patch

Blocked discovery actions include install, enable, run, execute,
clone-and-run, and local deletion. Repository lifecycle events remain record
only: creation does not install a skill, and deletion does not delete a local
skill.

Fork or mirror evidence is lineage evidence, not independent activation
pressure. When a body-free repository summary carries `upstream_source_url`,
`forked_from_url`, or `parent_source_url`, summary classification groups the
candidate by the upstream public GitHub repository and records the related
public source URLs for audit. The duplicate fork does not increase
`candidate_count`, proposal lane count, activation lane candidate count, or the
readiness of a local proposal. This keeps a repeated public skill package from
amplifying one lesson merely because it appears under more than one repository
owner.

Repeated public activity around the same skill repository name can now affect
only local discovery selection and metadata. Repository trend, fork, and push
items that classify as `skill_workflow` are grouped by a body-free project key
before context truncation. When two or more selected activities point at the
same project, the selector gives that skill-route evidence a small bounded
confidence bump and `build_route_hint_lane_map` reports a
`route_activity_pressure` summary with hashed project keys, item IDs, event
kinds, allowed lanes, local validation requirement, and `runtime_action: none`.
This is intended for repeated COMPASS Skills-style trend, fork, and push
pressure: it can make documentation, config, test, or code_patch investigation
more likely to survive context budgeting, but it does not create install,
enable, clone, run, execute, deletion, provider launch, remote execution, or
external skill activation authority.

The local harness also exposes that movement as `activity_signal_panel`.
GitHub `PushEvent` values are normalized to `push` and interpreted only as
validation pressure for the four bounded local lanes. A COMPASS Skills-style
push can therefore produce documentation, config, test, and code_patch rows,
but every row keeps `runtime_action: none`, requires the normal local replay
commands, hashes source metadata, and denies external skill activation,
external harness execution, provider launch, remote execution, and raw upstream
body export. Push movement never means install, enable, execute, clone, profile
write, memory write, or deletion.

Low-detail pull request movement is visible in the same panel only as weak
supporting context until a separate local corroboration record exists. Generic
or untitled `PullRequestEvent` evidence, missing PR details, lifecycle-only
summaries, route hints, CI words, and candidate lane names are not enough to
make a lane activation-ready. The panel records
`generic_movement_policy: supporting_context_only_until_local_corroboration`,
`weak_generic_movement_count`, and row-level
`weak_generic_supporting_context_only: true` while the activation gate remains
`review_weak_evidence_before_activation`. When a focused fixture, local
validation command, artifact, or operator review note corroborates the generic
movement, the policy can become `locally_corroborated_generic_context`; even
then, the lane remains limited to documentation, config, test, or code_patch
and keeps external skill activation denied.

The harness also emits `generic_validation_prompt` for that state. It is an
operator-facing prompt, not a proposal proof: it lists the low-detail PR rows,
accepted local corroboration signal kinds, replay commands, and the current
activation decision while denying runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw evidence URL
export, source URL export, and upstream body export. This keeps Omnigent-style
generic PR movement useful as a validation target without treating an untitled
pull request as behavior-change evidence.

## Review Notes

The evidence is repository-level and README-level. That is enough to preserve a
route-discovery matrix and local fixture, but not enough to promote a candidate
to executable skill routing. A future code patch should cite a narrower local
failure, test gap, or inspected upstream detail before changing runtime behavior.

## Acceptance Criteria

`skill_route_discovery` is accepted only when it stays inside the discovery
lane. A valid local change must satisfy all of these criteria before it can be
treated as more than evidence:

- Provenance: cite only frozen digest evidence or derived item evidence already
  present in the run package; do not trust README claims as implementation
  parity.
- Scope: map the discovery route only to documentation, config, test, or
  code_patch work.
- Local tests: add or run validation sized to the local artifact being changed;
  repository popularity or external examples do not replace local tests.
- Rollback: record a rollback ref or artifact before self-modification and keep
  recovery explicit.
- Trust boundary: do not automatically import, install, enable, execute, clone,
  scaffold, or otherwise trust external skill code from discovery evidence.
- Privacy boundary: do not expose, print, upload, publish, or share tokens,
  credentials, secrets, private keys, private chats, PII, or personal data while
  evaluating skill repositories.

## Summary Fixture Lane

Synthetic repository summaries can now be classified into the same disabled
registry without requiring pre-shaped candidate metadata. This lane is
body-free: the classifier reads public source URL, name, short summary, topics,
event kind, and optional suggested lanes, then emits only disabled
`skill_route_discovery` records.

Summary classification may narrow or expand local validation work only across
the bounded lanes: documentation, config, test, and code_patch. Suggested lanes
such as install, execute, run, or runtime execution are ignored rather than
promoted into candidate lanes or requested actions. Non-skill repositories are
ignored, and URL validation still happens at registry build time.

Summary records can also carry body-free file layout evidence through
`observed_paths` and metadata filename evidence through `metadata_files`.
Recognized examples include `skills/.../SKILL.md`, `skills.sh.json`,
`.codex-plugin/plugin.json`, tests, validation scripts, templates, scaffold
directories, and QA checklists. Those names are classified into layout and
metadata signal tags and can select only the four bounded local lanes. The
classifier does not read upstream file bodies, clone repositories, install
plugins, run scripts, export source URLs into harness panels, or treat a
generic `AGENTS.md` file by itself as reusable skill-package evidence.

BioNeMo-style multi-skill repositories add one more body-free shape:
agent-native plugin marketplace catalogs such as `.agents/plugins/marketplace.json`
or `.claude-plugin/marketplace.json`. These are now classified as
`agent_plugin_marketplace` metadata and exposed through a
`plugin_marketplace_contract`. The contract is config-first and operator-visible:
catalog rows can justify local config, documentation, or test validation of the
route, but they still cannot install, activate, execute, launch providers, run
external harnesses, export upstream bodies, or promote a plugin from repository
presence alone.

## Issue Evidence Lane

Repository issues can refine the same disabled discovery candidate when they
carry an explicit `skill_route_discovery` hint and body-free title or summary
evidence about a skill or workflow route. Issue URLs are canonicalized back to
their repository for candidate grouping, while the original issue URL is kept as
deduplicated evidence.

Repeated issue evidence increments duplicate counts instead of creating another
candidate, requested action, or executable route. Issue-derived lanes remain
bounded to documentation, config, test, and code_patch; install, execute, run,
and other runtime lanes are ignored during classification.

Issue and repository evidence items also preserve a separate
`evidence_item_urls` list. Proposal lanes rendered from an item-derived registry
cite only those frozen item URLs, even when broader candidate metadata contains
extra URLs. Summary-only registries keep the older repository-level fallback
because they do not carry per-item provenance.

Item-derived registries also preserve selected digest `item_id` values in
`evidence_item_ids`. Duplicate evidence URLs are still counted as duplicates and
do not create extra candidates, URLs, lanes, or summaries, but their distinct
selected `item_id` values are retained so proposal review can trace a lane back
to the frozen digest selection set.

## Proposal Lane Map

The disabled discovery registry can now be rendered into a proposal-lane map.
This is the controller-facing form for local growth planning: each recognized
skill project can produce only documentation, config, test, or code_patch
proposal kinds, each with `runtime_action: none` and local validation required.
The lane map also carries `candidate_lane_inventory`, one compact row per
recognized or downgraded candidate, so an operator can inspect which bounded
local lanes came from each public skill repository before reading the expanded
proposal rows. Inventory rows repeat the activation boundary:
`local_validation_required: true`, `runtime_action: none`,
`external_skill_activation_allowed: false`, and
`activation_gate: local_validation_before_activation`.
Each lane also carries body-free uncertainty text and `uncertainty_reasons` so
review can distinguish repository-level trend evidence, sparse selected-item
evidence, fork or mirror amplification, and `missing_detail_risk` from locally
validated behavior. These fields are review metadata; they do not grant external
skill activation or replace the required local validation commands.
When the source registry was built from selected evidence items, each lane also
exports the preserved `evidence_item_ids`; these ids are provenance only and do
not add new evidence or actions.

The harness exposes that inventory as `candidate_lane_intake` before the
expanded lane matrix. This is an operator-facing candidate selection surface,
not an activation surface. Each row hashes the candidate name and source,
reports bounded local proposal kinds, route profiles, selected digest item IDs,
evidence URL hashes, downgraded lane pressure such as `install`, `execute`, or
`runtime_execution`, and rejection counts. A `ready` intake means every candidate
mapped cleanly to documentation, config, test, or code_patch lanes and the
activation gate is already open for local proposal work. A `review` intake means
the candidate inventory remains body-free and locally bounded but downgraded or
rejected upstream pressure must be reviewed before a supervisor selects a local
validation lane. The intake always keeps `runtime_action_allowed: false`,
`external_skill_activation_allowed: false`, `external_skill_code_allowed: false`,
and raw source or evidence URLs out of the harness result.

Each intake row also includes `recommended_local_lane_order`, a profile-specific
ordering of only the lanes already present for that candidate. FableCodex-style
workflow gates prefer replay/test or documented-gate work first; COMPASS-style
state handoff routes prefer config or documentation boundary metadata before
tests or code patches; Three.js-style game director routes prefer validation
and documentation before local code changes. The recommendation never adds a
lane, never overrides downgraded or rejected upstream pressure, and never
permits install, enable, run, execute, clone-and-run, scaffold, asset
generation, provider launch, profile writes, memory writes, or external skill
activation.

The harness also emits `term_route_review`, a compact body-free panel for the
literal route-trigger terms `agent`, `agents`, `codex`, `skill`, `skills`, and
`workflow`. Each row is keyed by hashed candidate and source identifiers,
reports the matched terms and already-bounded proposal kinds, and rechecks that
local validation is required, `runtime_action` is `none`, external skill
activation is false, and raw source, evidence, or upstream bodies are not
exported. This panel is diagnostic only: repository popularity or term matches
can explain why evidence entered skill-route discovery, but they do not add
lanes, cite new evidence URLs, or make install, enable, run, execute,
clone-and-run, scaffold, profile-write, provider-launch, or external skill
activation requests valid.

The harness now emits `mixed_local_lane_probe` for candidate rows that combine
Codex, skill or skills, and workflow terms, with agent or agents marking a full
mixed signal. The probe selects `skill_route_discovery` as the primary route
before any secondary harness evaluation, repeats only documentation, config,
test, and code_patch lanes, and marks
`agent_harness_eval_after_local_corroboration` as blocked until local
corroboration exists. It is still body-free: it exports selected item IDs,
hashed candidate/source identifiers, bounded lane order, route profiles, and
the same denials for runtime action, external skill activation, external agent
activation, external harness execution, provider launch, remote execution, raw
source URLs, raw evidence URLs, and upstream bodies.

Unsupported lane hints are downgraded by removing the unsupported lanes and
recording them in `downgraded_candidates`. Candidates that request install,
enable, run, execute, clone-and-run, local deletion, private/non-plain source
URLs, or other non-lane validation failures are recorded in
`rejected_candidates` and produce no proposal lanes.

This keeps the useful lesson from the reviewed repositories: public skill
ecosystems reveal reusable routing shapes, but upstream installers, scripts,
scaffolds, profile stores, and QA helpers are evidence to inspect, not actions
to perform during discovery.

## Current Pass-2 Checkpoint

For source digest `github-growth-20260707T003555.486083Z`, pass 2 treats
`lingbol088-spec/reverse-flow-skill` as a skill-workflow route signal because
its public shape includes a Codex/AI Agent skill directory, `SKILL.md`,
references, scripts, local sandbox and CTF framing, and staged reverse-analysis
workflow language. That evidence may enter only the bounded
`skill_route_discovery_first` path with documentation, config, test, or
code_patch lanes. Install examples, script examples, vulnerability-analysis
language, runtime execution, provider launch, external harness execution,
external skill activation, and remote execution remain route pressure only.

Adjacent general-agent project signals such as `InternScience/Agents-A1`,
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`, and
`shepherd-agents/shepherd` stay in `agent_harness_eval_required`. They do not
inherit `skill_route_discovery`, have no direct pre-eval documentation, test,
code_patch, runtime, provider, harness, or remote-execution lane, and can only
produce implementation pressure after a local `agent_harness_eval_lane` replay.
The pass-2 `operator_activation_checkpoint` records the ordered supervisor
handoff: controller recomputes route families, the bounded skill-route lane is
replayed, then adjacent agent-harness evaluation is replayed. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k "20260707_pass2_checkpoint or 20260706T215555_pass2_route_probe"`.

For source digest `github-growth-20260707T070834.246450Z`, the proposal route
map also emits `current_pass2_activation_checkpoint` directly from the frozen
evidence package. `lingbol088-spec/reverse-flow-skill` remains a Codex-oriented
skill route and selects the local test lane; `Pluviobyte/rnskill` remains a
generic skill-workflow route and selects the documentation lane. Both are
bounded to documentation, config, test, or code_patch and require local replay
before activation. `shepherd-agents/shepherd`, `Fundamental-Ava`, and
`Agents-A1` remain adjacent general-agent rows with no direct implementation
lanes before `agent_harness_eval_required`. The checkpoint is body-free: raw
source URLs, evidence URLs, replay commands, target paths, upstream bodies,
external skill activation, external harness execution, provider launch, remote
execution, promotion, push, and kernel restart are all disabled.

## Local Harness Lane

`skill_route_discovery_lane` is the local harness behavior for replaying frozen
skill-route evidence before activation. It accepts body-free evidence items,
repository summaries, or pre-shaped candidates, builds the disabled discovery
registry, and renders the proposal lane map through the same bounded lane
contract: documentation, config, test, and code_patch.

The harness output is metadata-only. It reports candidate counts, lane counts,
proposal kinds, downgrade/rejection counts, whether every lane keeps
`runtime_action: none`, whether every lane requires local validation, a
body-free `evidence_strength` summary, body-free uncertainty reasons, and an
`activation_gate` for the controller surface. Generic pull request or push clusters are
`weak_generic_upstream_movement` unless the fixture also carries a separate
body-free `local_corroboration` record. A route hint, CI word, test word, or
generic PR title inside the upstream evidence does not count as corroboration
by itself. Weak generic movement can support investigation, documentation, or
review notes, but it is not activation-ready merely because its candidate lanes
are otherwise bounded.
Clean evidence is
`ready_for_local_proposal_activation`; downgraded evidence is
`review_degraded_lane_before_activation`; rejected or empty evidence is
`blocked_before_activation`; weak generic upstream movement is
`review_weak_evidence_before_activation`; generic upstream movement with local
corroboration can become `ready_for_local_proposal_activation`. The gate always
keeps `external_skill_activation_allowed: false`; it can only permit local
proposal activation for clean or locally corroborated documentation, config,
test, or code_patch lanes. Raw source and evidence URLs are hashed rather than
exported. Requested activation actions such as install, enable, run, execute,
clone-and-run, or local deletion block the harness lane as rejected candidates
and do not execute.

The same local harness family now includes a metadata-only CI round-trip
diagnostic for mocked E2E runner lanes. When public harness evidence suggests a
CI prompt round-trip is hanging, the local fixture should classify that as
`ci_round_trip_hang` separately from `authentication_failure`. The diagnostic
records only the expected and observed failure families, prompt/completion
booleans, and body-free privacy flags; it must not export raw CI logs, command
strings, token names with values, credentials, or provider responses.

The harness also renders a `discovery_checklist` for operator review before
local activation. Each checklist row records the hashed source, capability,
allowed local lane, required tests, rollback note, runtime action, and external
activation flag. The row is intentionally bounded: source URLs are represented
as hashes, capability is `skill_route_discovery`, allowed local lane is one of
documentation, config, test, or code_patch, required tests include
`pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`, rollback
notes require a rollback ref and artifact before source changes, runtime action
remains `none`, and external skill activation remains false.

The same output includes an `evidence_lane_matrix` for source-by-source review.
Each row hashes the candidate name and source URL, lists only the bounded local
lanes derived from that source, records selected digest item IDs and hashed
evidence URLs, reports downgraded or rejected lane pressure, and keeps
`runtime_action: none`. This matrix is intended for cases such as COMPASS
Skills, Three.js Game Skills, and FableCodex where upstream repositories may
mention installers, scaffolds, plugins, credential probes, or execution helpers.
Those signals can justify local documentation, config, test, or code_patch
work, but the matrix keeps install, enable, run, execute, clone-and-run,
provider launch, remote execution, raw upstream body export, and external skill
activation denied before supervisor promotion.

The harness also emits `bounded_profile_lane_matrix`, a profile-by-profile
view derived from the validation lane plan. It compares required capability
window profiles with observed route profiles, records missing-profile
diagnostics, lists only available documentation, config, test, and code_patch
lanes, and preserves selected lane distinctions such as
`generic_skill_workflow`, `skill_ecosystem_state_handoff`,
`game_frontend_workflow`, `source_cited_domain_research`, and
`codex_workflow_gate`. This matrix is for local validation planning only: it
does not add lanes, export raw URLs, launch providers, execute upstream code, or
permit external skill activation.

Each checklist row and activation row also carries
`inspection_requirements`. This is the bounded local inspection contract for
mapping a public skill repository into work: selected digest item IDs or frozen
digest evidence, body-free repository summaries, source-lineage metadata, local
artifact targets, changed-file review, focused local validation, rollback
artifact, and review note. The same contract records blocked shortcuts:
installing upstream skills, running upstream skill code, clone-and-run behavior,
trusting a README as local implementation parity, or exporting raw upstream
bodies. The preactivation trust boundary rejects activation rows that omit or
weaken this inspection contract.

The harness now also emits a body-free `source_lineage` summary and carries a
compact lineage view into supervisor readiness. This records candidate source
counts, hashed candidate and related source URLs, duplicate summary counts,
evidence item ID counts, and whether fork or mirror lineage was collapsed. It
does not export raw source URLs or related source URLs. This keeps public
skill-pack evidence such as COMPASS Skills, Three.js Game Skills, or FableCodex
fork movement visible as lineage pressure while preserving the preactivation
rule: forked or domain-specific skill repositories can justify bounded local
documentation, config, test, or code_patch lanes, but they do not add install,
clone, run, scaffold, profile, asset-generation, provider-launch, or remote
execution authority.

For controller handoff, the harness also emits `activation_lanes`. These rows
group proposal lanes by local output kind and carry the required validation
command, candidate names, hashed candidate sources, readiness flag, blockers,
body-free recovery hint codes, runtime action, raw-source export denial, and
external activation flag. A lane is
`activation_ready: true` only when the overall gate is
`ready_for_local_proposal_activation`; weak generic evidence, downgraded lanes,
rejected candidates, unbounded lanes, missing validation, or requested runtime
action keep the row present but blocked. Blocked rows expose
`recovery_hint_codes` that point back to the harness recovery hints, so an
operator can see whether to add local corroboration, review downgraded lanes,
remove actionful metadata, or regenerate activation rows. This lets a
supervisor promote validated documentation, config, test, or code_patch work
without treating an external skill repository as an installable package.

Each activation row also carries a `local_artifact_contract`. This is a
body-free handoff target, not a write instruction from the upstream repository:
documentation lanes point at local route documentation, config lanes at local
proposal-policy code, test lanes at local route and harness tests, and
code_patch lanes at the local skill-routing or harness evaluator modules. The
pre-activation trust boundary rejects artifact targets that are URLs, absolute
paths, path traversal, non-local review surfaces, raw upstream bodies, or
external skill code. This gives a supervisor an operator-visible lane-to-file
contract before activation while preserving the rule that discovery never
imports, runs, or clones external skill packages.

The harness also emits an `implementation_intake_preflight` before supervisor
promotion. This preflight is the implementation-facing summary of the
activation rows: it reports `ready` only when the preactivation trust boundary
passed, every activation lane is ready, every proposal kind remains one of
documentation, config, test, or code_patch, and each lane still points at a
local artifact contract. It exports target paths only as hashes, requires
changed-file review and local validation, and keeps runtime action, external
skill activation, external skill code, and raw upstream bodies denied. A
blocked intake preflight means route discovery may remain useful evidence, but
it is not yet a local implementation lane.

Each activation row also carries a `provider_runtime_preflight` contract. This
does not launch a provider or execute a remote runner. It requires the local
`provider_runtime_preflight` and `provider_runtime_recovery_summary` replay
lanes before supervisor promotion, keeps diagnostics body-free, and records
`provider_runtime_launch_allowed: false` and `remote_execution_allowed: false`.
The pre-activation trust boundary rejects rows that omit this contract, weaken
the replay commands, export non-body-free diagnostics, or allow provider runtime
launch. This connects skill-route discovery to the provider/runtime control
slice: public skill evidence can become local documentation, config, test, or
code_patch work only after the same local provider diagnostic lane remains
replayable.

Activation rows also expose `provider_runtime_control`, a compact replay
handoff for the same contract. It records the provider/runtime controller
surface, replay commands, readiness decision, next safe action,
recovery hint count, recovery hint codes, and hashed hint codes without
exporting raw preflight inputs or diagnostics. A ready local artifact lane may
be replayed locally, but provider launch and remote execution remain denied; a
blocked lane keeps the same recovery hint codes visible for operator review and
points the operator toward resolving those hints before replaying provider
runtime preflight.
When the block came from a sampled provider/runtime replay, the same control
object uses `reason: provider_runtime_replay_not_ready`,
`provider_runtime_replay_blocked: true`, and a provider-replay-specific next
action so the operator can distinguish runtime diagnostic recovery from a
generic skill-route evidence or artifact blocker without seeing provider bodies.

The activation rows now also include a pre-activation local harness check. Before
promotion, the controller-visible validation set includes both the
`skill_route_discovery_lane` replay, the `agent_harness_eval_lane` replay, and
the proposal-interpretation smoke suite.
The latter is metadata-only and keeps `external_harness_execution_allowed:
false`; it exists to prove that a skill-route proposal lane can pass through the
same local harness evidence surface used for public agent-harness lessons before
activation. Checklist rows expose the same `preactivation_harness` value and
external-harness denial so an operator can distinguish local replay from remote
or upstream harness execution.

When a skill-route fixture carries `provider_runtime_preflight_samples`, the
local lane also samples the provider/runtime recovery summary before activation.
The sample is metadata-only: it exports preflight counts, status counts,
blocked failure modes, recovery hint codes and hashes, supervisor decision, and
replay commands, but not raw preflight inputs, diagnostics, source URLs, paths,
environment keys, credentials, provider bodies, or upstream skill bodies. A
blocked or degraded provider/runtime replay sample blocks local skill-route
promotion with `provider_runtime_replay_not_ready` until the recovery hints are
resolved and `provider_runtime_preflight` plus
`provider_runtime_recovery_summary` are replayed.
For a provider-runtime-control window that is still in pass 1, a passing sample
only means the current action can continue with body-free local replay evidence.
The `provider_runtime_sample_gate` may be `ready`, while
`capability_window_completion` remains `blocked` with
`continue_or_replay_before_completion` until the later passes record their
operator handoff and validation coverage. This prevents a harmless local
provider preflight sample from being mistaken for permission to launch a
provider, run an external harness, or mark the whole capability slice complete.

The harness also emits a top-level `provider_runtime_diagnostic_panel`. This is
the operator-visible replay summary for the provider/runtime control slice. It
counts ready and blocked activation lanes, checks that every lane still carries
the provider/runtime preflight contract, repeats the local replay commands,
hashes recovery hint codes, and records whether diagnostics remain body-free.
The panel never exports raw provider inputs, diagnostics, source URLs, target
paths, credentials, or upstream skill bodies. A ready panel means the local
replay commands are the next validation step before promotion; it does not
permit provider launch, remote execution, external skill activation, or
installation.

The harness also emits a `preactivation_trust_boundary` result. This is a
second, runtime-facing guard over the generated activation rows: it rechecks
that every lane remains one of documentation, config, test, or code_patch; that
runtime action is still `none`; that local validation and the pre-activation
harness replay are still required; and that external skill or harness execution
is still denied. A static registry entry is therefore not enough by itself to
make a lane activation-ready.

For supervisor handoff, the same output now includes `supervisor_readiness`.
This is a compact operator-visible decision derived from the activation gate,
activation lanes, recovery hints, and preactivation trust boundary. It reports
`ready_for_supervisor_promotion` only when every local lane is ready, all replay
commands are present, the trust boundary passed, runtime action remains denied,
and external skill or harness activation remains false. Downgraded evidence is
`review_before_supervisor_promotion`; rejected, empty, weak, or trust-boundary
failed evidence is `blocked_before_supervisor_promotion`. The summary carries
only lane counts, proposal kinds, recovery hint codes, and replay commands; it
does not export raw evidence URLs or upstream skill bodies, and it does not
request restart, remote activation, installation, cloning, or execution.

The harness also emits `validation_lane_gate`, a narrower operator checkpoint
for the active validation lane. It repeats the allowed local lanes
(`documentation`, `config`, `test`, and `code_patch`), selected local lanes,
required replay commands, artifact-proof readiness, trust-boundary state, and
supervisor decision. If any replay command, local artifact proof, trust boundary,
or activation-lane condition is missing, the gate reports blocked and keeps
`runtime_action: none`. It never permits external skill activation, external
harness execution, provider runtime launch, remote execution, raw evidence URL
export, or upstream body export.

The final local handoff view is `operator_handoff`. It is derived from
`implementation_intake_preflight`, `supervisor_readiness`, activation lanes, and
body-free source lineage. It groups ready local artifact lanes by proposal kind,
exports only target path hashes and source counts, repeats the required replay
commands, and carries recovery hint codes for blocked or degraded lanes. A ready
handoff means the supervisor may review local documentation, config, test, or
code_patch artifacts; it still denies runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw evidence
export, raw source URL export, and raw target path export. A blocked handoff
keeps the discovery useful as evidence but requires review or replay before any
local implementation lane is promoted.

The same lane also emits `operator_recovery_plan`, a compact replay decision for
blocked or degraded skill-route diagnostics. It converts recovery hints into
body-free recovery steps, stable hint-code hashes, local replay commands, and
the next safe action for an operator or supervisor. The plan never exports raw
evidence, source URLs, upstream bodies, target paths, credentials, provider
diagnostics, or command bodies, and it continues to deny runtime action,
external skill activation, external harness execution, provider launch, and
remote execution. A ready plan means local replay may continue; a blocked plan
means the recovery hints must be resolved before promotion.

Provider-runtime recovery plans also surface privacy-sensitive remediation as a
top-level gate. A usage-limit hint with credential-pool failover marks
`privacy_sensitive_recovery_present`, increments
`privacy_review_required_count`, keeps
`privacy_sensitive_auto_recovery_allowed` and
`credential_failover_allowed_without_review` false, and requires operator
review before retry. This keeps rate-limit recovery replayable without turning
credential labels, tokens, headers, reset values, or response bodies into
diagnostics. The scheduler-facing `supervisor_readiness` view repeats
`privacy_sensitive_recovery_present`, `privacy_review_required_count`,
`privacy_sensitive_auto_recovery_allowed`, and `operator_review_required` so a
supervisor can block promotion or require review without expanding nested
recovery steps.

Before that final handoff, the harness now emits `local_lane_intake`. This is
the operator-visible inventory of bounded local work inferred from external
skill evidence. It groups proposal rows by documentation, config, test, or
code_patch, exposes only hashed candidate names, hashed source URLs, hashed
local target paths, evidence item counts, inspection requirements, required
local validation commands, activation blockers, source-lineage counts, and the
discovery actions that stay blocked. It does not export raw URLs, raw target
paths, raw evidence, upstream skill bodies, or external code, and it keeps
install, enable, run, execute, clone-and-run, and deletion authority denied.
Empty or actionful evidence therefore produces no intake rows even when the
upstream repository looked like a useful skill package.

The harness also emits `route_triage_plan`, a body-free lane planning view for
operators. It converts external skill evidence into the four permitted local
lanes and records why each lane exists: documentation records route lessons and
acceptance criteria, config registers bounded policy or proposal mapping, tests
replay the route evidence locally, and code_patch changes only local
classifier, harness, or controller behavior. Each row carries hashed source
URLs, evidence item counts, uncertainty reasons, local artifact contracts,
inspection requirements, required validation commands, activation readiness, and
local artifact proof readiness. It does not export raw evidence, raw source
URLs, raw target paths, upstream skill bodies, or external code, and it keeps
runtime action and external skill activation denied. A ready triage plan means
the lane can be locally reviewed and validated; supervisor handoff can still be
blocked later when local artifact proof is missing.

The pass-2 lane output also includes `proposal_validation_lane_catalog`. This
catalog groups the current skill/workflow repository window by local proposal
lane before activation, so FableCodex, COMPASS Skills, zhengxi-views, and
Three.js game-skill evidence can be inspected as documentation, config, test,
and code_patch validation candidates without choosing a runtime route. Each row
contains only selected item IDs, hashed candidate names, hashed source URLs,
route profiles, unsupported-lane counts, activation blockers, and the local
validation requirement. Unsupported runtime-shaped suggestions are counted as
downgraded or blocked actions, while `runtime_action`, external skill
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw evidence URL export, and upstream body export remain
denied.

The discovery lane also emits a body-free `route_profile_catalog` and repeats
bounded `route_profiles` on proposal and triage rows. Current profiles include
`codex_workflow_gate` for FableCodex-style workflow gates,
`skill_ecosystem_state_handoff` for COMPASS-style state, memory, profile, and
handoff systems, `game_frontend_workflow` for Three.js or browser game director
skills, `source_cited_domain_research` for source-cited research skills with
citation and advice-boundary concerns, and `generic_skill_workflow` when the
evidence is too broad for a more specific profile. These profiles are triage metadata only: they count and group
local validation candidates, keep `runtime_action: none`, require local
validation, and do not create install, scaffold, asset-generation, browser-run,
profile-writing, upstream dataset import, advice generation, provider-launch,
remote-execution, or external skill activation authority.

The harness also emits `route_profile_review` before supervisor promotion. This
panel groups the proposal lanes by profile and records profile-specific
recognition signals, expected metadata, safe local tests, and rejection
conditions without exporting raw source URLs or upstream skill bodies. It is an
operator-facing inspection surface for deciding whether a route profile has
enough local evidence to become documentation, config, test, or code_patch work.

The current profile contracts are:

- `codex_workflow_gate`: FableCodex-style Codex workflow evidence. It expects
  selected digest item IDs, a body-free workflow summary, and a local gate or
  test target. It rejects upstream workflow installation, URL-based proposal
  citations, and README claims treated as local gate parity.
- `game_frontend_workflow`: Three.js game director and specialist-skill
  evidence. It recognizes browser-game, director, QA, screenshot, and canvas
  validation signals, but rejects upstream scaffolds, browser checkers,
  credential probes, provider launch, and asset generation without a separate
  local capability path.
- `skill_ecosystem_state_handoff`: COMPASS-style task clarification, memory,
  handoff, and profile systems. It expects a body-free ecosystem summary plus
  state-retention and privacy boundaries, and rejects profile or memory writes
  inferred only from repository presence.
- `source_cited_domain_research`: source-cited domain research skill evidence.
  It expects a body-free research summary, citation boundary, advice disclaimer
  boundary, and local evidence replay target. It rejects upstream dataset
  imports, financial or medical advice generation, provider launch, and private
  context export inferred only from repository presence.

A ready `route_profile_review` means the local route profile has an inspectable
contract for bounded local work. It still keeps `runtime_action: none`, requires
local validation, denies external skill activation, and does not import, run,
clone, install, scaffold, probe credentials, launch providers, or generate
assets, advice, or upstream datasets from the upstream repository.

The profile review also checks body-free metadata coverage for each profile
before activation review. A FableCodex-style workflow gate must show selected
digest item IDs, a body-free workflow summary, and a local gate or test target.
A Three.js game workflow must show a body-free game-skill summary, a local
frontend validation target, and an asset/provider boundary note. A
COMPASS-style state handoff route must show a body-free skill ecosystem
summary, state-retention and privacy boundary evidence, and any local memory or
profile target as metadata only. The panel exports counts and stable hashes for
evidence records and source references, but not raw evidence text, raw source
URLs, raw target paths, upstream skill bodies, or install commands. Missing
profile metadata changes the review panel to `review` with
`metadata_missing` diagnostics; it does not create install, enable, run,
profile-write, memory-write, scaffold, browser-run, asset-generation,
provider-launch, remote-execution, or external skill activation authority.

For COMPASS-style `skill_ecosystem_state_handoff` routes, profile review now
also emits `state_handoff_preflight`. This preflight is required before a
state/profile route can be ready: the local input must explicitly record that
retention policy is documented, privacy boundaries are documented, and any
local memory or profile target is metadata-only. Repository presence, README
claims, install instructions, or skill names never grant state, memory, or
profile write authority. If the explicit boundary is absent or claims upstream
presence grants writes, the profile review stays in `review` with
`state_handoff_preflight` diagnostics while keeping runtime action, external
skill activation, raw upstream body export, and private context export denied.

The profile review now also renders `local_lane_contracts` for each bounded
proposal kind present in the profile. These contracts expose only hashed local
artifact targets, target counts, required local artifact proof fields, and the
same runtime/external-skill denials. They are the operator-visible bridge from
profile evidence to local work: FableCodex-style workflow gates, COMPASS-style
state handoff systems, and Three.js-style director bundles can point reviewers
toward local documentation, config, test, or code_patch files, but the review
surface still withholds raw target paths and upstream bodies and requires
changed-file review, focused local validation, rollback artifact, and review
note proof before supervisor handoff.

Pass-3 replay also emits `preactivation_lane_selection`, a compact selector
that chooses one bounded local lane per ready route profile from the lanes
already present in the activation manifest. FableCodex-style workflow gates and
Three.js game director routes prefer the replay/test lane first, while
COMPASS-style state handoff routes prefer config metadata before documentation,
tests, or code patches. The selector never adds a lane, never selects a profile
whose metadata review or state-handoff preflight is not ready, and never selects
without local artifact proof. It exports only route profile names and bounded
lane names, keeps `runtime_action_allowed: false`, and continues to deny
external skill activation, external skill code, external harness execution,
provider launch, remote execution, raw source URLs, raw target paths, and
upstream bodies.

Pass-3 replay also emits `profile_validation_replay`, a per-profile local
checklist derived from `validation_lane_plan`. Each row names the route profile,
the selected bounded local lane, a local operator replay step, selected item-id
evidence refs, hashed candidate sources, required validation commands, and
provider-runtime replay commands. This makes the active pass directly
actionable without exposing upstream URLs or bodies: FableCodex-style workflow
gates and Three.js game skill routes map to
`replay_local_test_lane_for_workflow_or_game_route`, while COMPASS-style state
handoff maps to `review_local_config_lane_for_state_handoff`. The panel does
not add lanes, install skills, run upstream code, execute browser/game helpers,
write profiles, launch providers, perform remote execution, export raw evidence
URLs, export raw source URLs, export raw target paths, or export upstream
bodies.

The pass-3 handoff packet also carries `runner_harness_control_plane`, a
five-stage operator view over the same local artifacts: intake from
`pass_validation_replay_queue`, mid-flight state from `current_action` and
operator checkpoints, recovery from `profile_validation_proof`, replay from the
promotion runbook, and report state from `activation_proof_summary`. The
control plane records stage readiness, artifact-name hashes, replay command
hashes, provider-runtime replay command hashes, and a workflow fingerprint. It
does not export raw artifact paths, raw source URLs, raw evidence URLs, raw
target paths, or upstream bodies, and it keeps runtime action, external skill
activation, external harness execution, provider launch, and remote execution
disabled.

On final scheduled passes for this capability slice, the harness emits
`capability_window_completion`. This panel consumes the route profile review,
activation manifest, operator handoff, supervisor readiness, and
provider-runtime diagnostic panel, then reports whether the skill-route
discovery window is complete enough for supervisor handoff. It records the
theme, current and total pass counts, hashed anchoring proposals, hashed
evidence URLs, bounded proposal kinds, route profiles, required validation, and
provider-runtime replay commands. A ready completion panel means the four-pass
slice has an operator-visible local result; it does not grant runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw evidence URL export, raw source URL export, or upstream body
export.

Final passes may also declare `required_route_profiles` in the capability
window. When present, completion checks those required profiles against the
body-free profiles actually replayed in the local harness. A pass that cites or
anchors FableCodex, COMPASS Skills, and Three.js Game Skills can therefore
require `codex_workflow_gate`, `skill_ecosystem_state_handoff`, and
`game_frontend_workflow` before supervisor handoff. Missing profiles block only
the completion handoff; they do not grant install, enable, run, execute,
clone-and-run, profile-write, memory-write, scaffold, asset-generation,
provider-launch, remote-execution, raw evidence export, raw source URL export,
or upstream body export authority.

The completion report also includes `profile_validation_gate`, a final
profile-specific check before the report can be ready. FableCodex-style
`codex_workflow_gate` rows must still prove
`skill_route_discovery_first` with the secondary
`agent_harness_eval_after_local_corroboration` lane blocked; Three.js
`game_frontend_workflow` rows must be tied to the local test/frontend
validation lane; COMPASS `skill_ecosystem_state_handoff` rows must be tied to
the local config/state-boundary lane. The gate records only profile names,
bounded lane names, validation scopes, metadata readiness, local artifact proof
readiness, operator lane readiness, diagnostic hashes, and replay commands. It
does not export raw repository URLs or upstream bodies, install external
skills, run scaffolds or browser checkers, write profiles or memory, launch
providers, execute a secondary harness, or perform remote execution.

The same panel includes `completion_handoff`, a compact supervisor-facing
contract for the final slice state. It repeats the completion status and
decision, names a `supervisor_next_action`, records the
`activation_sequence_status`, records whether the final planned pass was
observed, lists selected item-id evidence refs, and carries any
completion blockers. Ready handoffs use
`handoff_completed_skill_route_slice_to_supervisor`; non-final clean passes use
`continue_capability_window_before_completion`; blocked final passes use
`replay_or_repair_before_supervisor_handoff`. The handoff remains body-free:
selected item IDs are allowed, while raw evidence URLs, source URLs, upstream
bodies, runtime action, external skill activation, provider launch, and remote
execution remain denied.

The completion handoff also carries `completion_recovery`, a body-free repair
selector for final-pass failures. It maps existing completion diagnostics to the
next bounded local action: continue the window when the planned pass is not
complete, repair missing required route profiles, repair local artifact proof,
replay provider-runtime preflight, repair profile metadata, or replay the
bounded skill-route lane. The selector records only bounded lane names, missing
route profile names, blocker hashes, hint codes, and replay commands. It does
not export raw evidence URLs, raw source URLs, raw target paths, or upstream
bodies, and it continues to deny runtime action, external skill activation,
external harness execution, provider launch, and remote execution.

Final-pass completion now also emits `activation_packet`, a body-free supervisor
replay packet derived from the activation manifest. The packet lists only
bounded local proposal kinds, route profiles, selected item-id evidence refs,
hashed candidate sources, hashed local target paths, local artifact proof
readiness, required validation commands, and provider-runtime replay commands.
Ready packets mark each row for bounded local review and replay; blocked
packets mark rows for repair before replay. The packet does not add lanes and
does not permit install, enable, run, execute, clone-and-run, profile-write,
memory-write, scaffold, asset generation, provider launch, remote execution,
raw evidence URL export, raw source URL export, raw target path export, or
upstream body export.

Pass-4 completion also emits `final_slice_closure`, a single body-free closure
decision for the supervisor. It gathers the required and observed route
profiles, selected item-id evidence refs, selected local lanes, profile replay
rows, activation manifest status, activation packet status, and recovery
decision into one panel. A complete FableCodex, COMPASS Skills, and Three.js
Game Skills window can therefore close with FableCodex and Three.js replaying
through the local test lane while COMPASS remains a local config lane. Blocked
closures point back to the bounded recovery selector instead of widening the
route. The panel does not add lanes, install skills, run upstream code, execute
browser/game helpers, write profiles, launch providers, perform remote
execution, export raw evidence URLs, export raw source URLs, export raw target
paths, or export upstream bodies.

Provider-runtime-control capability windows now also require a body-free
`provider_runtime_preflight_samples` replay before the completion panel can
continue. Missing samples produce `provider_runtime_preflight_sample_missing`
and route recovery to the local provider-runtime preflight and recovery-summary
commands. A ready sample is still metadata-only: it reports counts, statuses,
failure classes, hashes, and replay commands while denying provider launch,
remote execution, raw preflight input export, diagnostics export, and provider
value export. A degraded-only sample, such as a mock provider path using
placeholder auth, is ready for local replay but not ready for supervisor
promotion; the sample gate records `degraded_replay_only: true`,
`ready_for_supervisor_promotion: false`, and `success_claim_allowed: false` so
operators can replay recovery without mistaking a degraded provider diagnostic
for activation success. Blocked samples still stop completion as
`provider_runtime_replay_not_ready`. Skill-route-only windows keep the sample
optional so older discovery passes remain replayable unless a window explicitly
opts into provider-runtime control.

Before the final planned pass, the same panel reports `status: in_progress`
when all bounded lane surfaces are otherwise ready but the capability window has
not reached its planned completion count. That state carries
`capability_window_not_at_final_pass` as the only diagnostic and uses
`continue_capability_window_before_completion` as the decision, so supervisors
can keep the slice active without mistaking a healthy pass-3 replay for a
blocked route. It preserves the same documentation, config, test, and
code_patch lane bounds and the same denials for runtime action, external skill
activation, provider launch, remote execution, raw evidence URLs, raw source
URLs, and upstream bodies.

The completion panel also emits `next_pass_handoff` for pass-to-pass
continuity. This body-free handoff records the current pass, next pass,
remaining pass count, hashed candidate and source identifiers, selected item-id
evidence refs, observed route profiles, proposal kinds, and a
`recommended_local_lane_order` derived only from already bounded local lanes.
Clean non-final passes use `continue_bounded_lane_validation_next_pass` and
`continue_skill_route_discovery_window`; blocked passes use
`repair_current_pass_before_continuing`. The handoff is not an activation
surface: it repeats local validation requirements and denies runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw evidence URLs, raw source URLs, and upstream bodies.

The harness also emits `route_discovery_catalog`, an operator-visible catalog
that connects each observed route profile to the bounded local lane selected for
review. Catalog rows carry selected item IDs, hashed candidate sources,
allowed local lanes, the chosen local lane, required validation commands, and
provider-runtime replay commands. In `provider-runtime-control` windows the
catalog requires a body-free provider-runtime preflight sample before it can be
ready. The catalog is not a permission surface: it keeps runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw source URLs, raw target paths, and upstream bodies denied.

The evaluator also emits `validation_lane_plan`, a pass-to-pass operator panel
derived from the catalog. It turns each cataloged route profile into the next
bounded local validation lane, records the selected item IDs and hashed
candidate sources that justify the lane, and sets a local-only validation scope
such as `local_test_lane_only` or `local_config_lane_only`. Non-final passes use
`continue_bounded_local_validation_lane` so the supervisor can continue the
skill-route window with a concrete lane target instead of treating public skill
repositories as installable or executable workflows. The plan repeats the same
runtime, external activation, provider launch, remote execution, raw evidence
URL, raw source URL, raw target path, and upstream body denials.

For `source_kind: summaries`, the harness emits
`summary_signal_audit` before activation. This panel shows how many repository
summaries were accepted, ignored, or collapsed as duplicates, then lists only
hashed candidate names, hashed candidate sources, matched route terms, route
profiles, bounded proposal kinds, and hashed evidence URLs. A COMPASS-style
summary with agent, skill, skills, workflow, handoff, and validation signals is
therefore visible as a local `skill_ecosystem_state_handoff` lane candidate,
while a generic agent-runtime summary remains ignored by this route. The audit
does not export raw source URLs or upstream bodies and does not allow runtime
action, external skill activation, external harness execution, provider launch,
or remote execution.

For `skill_ecosystem_state_handoff` candidates, the proposal lane map also
emits `state_profile_boundary` on the candidate inventory row and each derived
local lane. This is a COMPASS-inspired metadata contract, not storage behavior:
retention policy and privacy boundary review are required before activation,
local targets remain metadata-only, and profile writes, memory writes, global
config writes, private-context export, and write authority from upstream
repository presence are denied. The deeper harness review remains
`skill_route_discovery_state_handoff_preflight`.

The same plan also groups selected profiles into `lane_validation_targets`.
These rows are the operator-visible workload for the next pass: each row names
one bounded local lane, the route profiles it covers, selected item IDs, hashed
candidate sources, required validation commands, and provider-runtime replay
commands. A COMPASS-style state-handoff route can therefore remain a local
config validation target while FableCodex-style workflow gates and Three.js game
skill routes share a local test validation target. The grouping does not add
lanes and does not authorize upstream install, clone, execution, scaffold
generation, provider launch, remote execution, raw source URL export, raw target
path export, or upstream body export.

The harness also emits `validation_work_queue`, which expands the selected
route-profile lanes into bounded local work items. Each row joins the selected
lane from `validation_lane_plan` with candidate-level route evidence from
`candidate_lane_intake`, then reports only hashed candidate identifiers, hashed
candidate sources, selected item IDs, hashed local artifact targets, replay
commands, and a supervisor replay step. For the current pass-3 profile set,
FableCodex and Three.js Game Skills become local `test` work items, while
COMPASS-style state handoff becomes a local `config` work item. The queue is
body-free and local-only: it cannot add lanes, export raw source URLs or target
paths, run upstream code, execute external harnesses, launch providers, or
activate external skill packages.

The plan also emits `next_validation_target`, a single bounded lane selected
from the grouped targets for the next scheduled pass. The selector prefers a
local `test` replay when workflow or game-skill route evidence is present, then
`config` for COMPASS-style state handoff, then documentation and code_patch.
This field is repeated through `profile_validation_replay`,
`validation_target_handoff`, and `next_pass_handoff` so a pass-1 or pass-2
supervisor does not have to infer the next local lane from raw upstream
repositories. It still exports only selected item IDs and candidate source
hashes, requires the focused local validation commands, and denies runtime
action, external skill activation, external skill code, external harness
execution, provider launch, remote execution, raw evidence URLs, raw source
URLs, raw target paths, and upstream bodies.

The harness also lifts that selected target into `current_action`, a compact
supervisor row for the current scheduled pass. It repeats the selected bounded
lane, validation scope, route profiles, selected item IDs, hashed candidate
sources, required replay commands, next pass, and supervisor next action without
exporting raw upstream URLs or bodies. A pass-3 skill-route window can therefore
show "continue with the local test lane next pass" directly at the top level
while preserving the same denials for runtime action, external skill
activation, external skill code, external harness execution, provider launch,
remote execution, raw evidence URLs, raw source URLs, raw target paths, and
upstream bodies.

When more than one bounded lane is ready, `current_action` also carries
`queued_validation_targets`. This keeps the first replay target compact while
making adjacent local work visible: for example, a pass-1 window can select the
FableCodex/Three.js-style local `test` lane and still show the COMPASS-style
state-handoff documentation or config lane as queued metadata, depending on
which local artifact proof is ready. Queued targets repeat only selected item
IDs, route profiles, hashed candidate sources, and the same denials; they are
not permission to install, enable, run, scaffold, write profiles, write memory,
export raw URLs, or execute upstream skill code.

The harness also emits `pass_validation_replay_queue`, a single replay packet
for the current pass. The first row is the selected `current_action` lane and
later rows are queued bounded lanes, so a pass-3 window can show the
FableCodex/Three.js local `test` replay before the COMPASS-style `config`
handoff without requiring operators to compare multiple panels. The packet
exports only selected item IDs, route profiles, candidate source hashes, local
validation commands, provider-runtime replay commands, and queue roles. It is
not an activation request: runtime action, external skill activation, external
skill code, external harness execution, provider launch, remote execution, raw
evidence URLs, raw source URLs, raw target paths, and upstream bodies remain
denied.

Each `pass_validation_replay_queue` row also carries a `queue_fingerprint`
derived from queue role, bounded lane, validation scope, route profiles,
selected item IDs, candidate source hashes, and the denied runtime/external
activation flags. The top-level `queue_fingerprints` list preserves the row
order for supervisor drift checks between pass handoffs. These fingerprints are
body-free replay identifiers only; they do not include raw source URLs, raw
target paths, replay command bodies, upstream skill bodies, or any authority to
install, enable, run, clone, scaffold, launch providers, or execute remote work.

Pass-1 windows use the same row. A COMPASS, Three.js Game Skills, and
FableCodex-style discovery window should expose the first concrete local replay
target as `current_action.selected_local_lane` instead of requiring the
supervisor to infer it from raw repository URLs or README claims. Mixed
Codex/workflow/skill evidence remains `skill_route_discovery_first`; secondary
agent-harness evaluation stays blocked until local corroboration.

For the 2026-06-21T11:12Z pass-1 window, the harness also emits
`pass1_validation_queue`. This queue maps anchoring proposals such as
`p1-skill-route-discovery-compass`, `p2-threejs-game-skill-docs`, and
`p3-codex-workflow-gate-config` to the selected bounded local lane already
chosen by the replay queue. COMPASS-style state handoff remains a local
documentation or config-boundary row, Three.js game/frontend evidence remains a
local test/frontend validation row, and FableCodex-style Codex workflow-gate
evidence remains a local test row that preserves
`skill_route_discovery_first`. Adjacent general-agent anchors such as
`p4-general-agent-harness-eval` and `trend:omnigent-ai/omnigent` are represented
as `agent_harness_eval_required` rows with
`skill_route_discovery_inherited: false`.

The queue is a replay surface, not an activation token. It cites selected
`item_id` values only, exports candidate/source metadata as hashes, and repeats
the denials for runtime action, external skill activation, external agent
activation, external harness execution, provider launch, remote execution, raw
evidence URL export, raw source URL export, raw target path export, and upstream
body export.

Pass-2 windows now also emit `pass2_handoff_packet`. This packet copies the
selected current-pass lane, queued bounded lanes, selected item IDs, candidate
source hashes, and mixed-route probe decision into one supervisor-readable
surface. For the current COMPASS/FableCodex/Three.js window, FableCodex-style
mixed Codex/agent/skill/workflow evidence keeps
`mixed_skill_workflow_primary_route: skill_route_discovery`, while
`agent_harness_eval_after_local_corroboration` remains blocked. The packet is
not a secondary-harness activation token: it denies runtime action, external
skill activation, external agent activation, external harness execution,
provider launch, remote execution, raw source URL export, raw evidence URL
export, raw target path export, and upstream body export.

The same packet now carries `bounded_activation_preview`, a pass-2 replay
surface for the selected current-pass lane and queued bounded lanes. It reports
only allowed local lanes, route profiles, selected-item citation mode, replay
commands, provider-runtime replay commands, activation-preview steps, and
blocker codes. The preview exists so the supervisor can replay the local `test`
lane and carry the queued `config` lane without re-reading the full nested
manifest. It does not add lanes, cite raw repository URLs, activate the
secondary harness, install skills, execute upstream code, launch providers,
perform remote execution, export raw target paths, or export upstream bodies.

The packet also carries `operator_checkpoint_list`, a compact pass-2 checklist
for the same rows. Each checkpoint names whether the supervisor should replay
the selected current-pass lane or carry a queued bounded lane forward, then
shows the bounded lane, validation scope, route profiles, selected-item citation
mode, evidence and source counts, queue fingerprint, replay commands, provider
preflight replay commands, readiness status, and blocker codes. The checklist
exists to make the next operator action visible without expanding raw upstream
evidence. It repeats that runtime action, external skill activation, external
agent activation, external harness execution, provider launch, remote
execution, raw source URL export, raw evidence URL export, raw target path
export, and upstream body export remain denied.

`pass2_handoff_packet` also emits `local_lane_acceptance_contract`. This is the
pass-2 acceptance surface for converting COMPASS-style state handoff evidence,
Three.js/game skill evidence, and FableCodex-style mixed Codex/workflow/skill
evidence into bounded local work. Each selected or queued row repeats the
bounded lane, validation scope, route profiles, queue fingerprint, replay
commands, and provider-runtime replay commands, then lists boolean acceptance
gates for bounded lane membership, local validation, `runtime_action: none`,
external skill denial, secondary harness denial, provider launch denial, remote
execution denial, and omission of raw evidence URLs, raw source URLs, raw target
paths, and upstream bodies. The contract also records that mixed
Codex/workflow/skill evidence preserves `skill_route_discovery` as the primary
route and keeps `agent_harness_eval_after_local_corroboration` blocked. A ready
contract is a local replay signal only; it does not install skills, execute
upstream code, launch a provider, execute the secondary harness, write remote
state, or export raw upstream evidence.

For `provider-runtime-control` windows the harness also emits
`current_action_provider_runtime_preflight`. This panel joins the selected
current action to provider-runtime replay state so pass-1 supervisors can see
the next safe recovery step without inspecting provider bodies. Missing
provider-runtime samples block with
`provider_runtime_preflight_sample_missing`; blocked samples carry only hashed
recovery hint codes; degraded samples are reviewable replay evidence but do not
allow success claims; passed samples mark the current action ready for the
bounded local lane. The panel repeats the provider-runtime preflight and
recovery-summary replay commands and keeps runtime action, external skill
activation, external harness execution, provider launch, remote execution, raw
preflight inputs, raw diagnostics, raw provider values, raw source URLs, raw
target paths, and upstream bodies denied.

Pass-2 `provider-runtime-control` windows also emit
`provider_runtime_promotion_checkpoint`. This checkpoint condenses the
provider-runtime sample gate, current-action preflight, and replay sample into a
single body-free supervisor row. A ready checkpoint means the selected bounded
local lane may continue after local provider-runtime replay; it is not provider
launch authority and it is not four-pass slice completion. Blocked checkpoints
route back to provider-runtime preflight and recovery-summary replay; degraded
checkpoints require operator review before any success claim. The row carries
only selected item counts, source hashes, readiness booleans, recovery hint
hashes, diagnostics hashes, and replay commands while denying runtime action,
external harness execution, provider launch, remote execution, raw preflight
inputs, raw diagnostics, raw provider values, raw source URLs, and upstream body
export.

The pass-4 skill-route lane map can also expose
`provider_runtime_completion_checkpoint` for a specific provider-runtime-control
digest. This is the lane-map completion companion to the generic harness
handoff: it joins the bounded skill-route handoff, route-boundary checklist, and
operator completion checklist into one supervisor-visible row. It carries only
status fields, selected lane names, counts, recovery hint codes and hashes, and
replay command hashes. It keeps runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw replay
commands, raw source URLs, raw evidence URLs, raw preflight inputs, raw provider
values, raw target paths, and upstream bodies denied.

`validation_readiness_summary` consumes that current-action provider-runtime
preflight before it reports a selected lane as replay-ready. In
`provider-runtime-control` windows, a missing or blocked preflight changes the
summary decision to `resolve_provider_runtime_preflight_before_replay`; a
degraded replay remains review-only; and only a ready or not-applicable
preflight can preserve `operator_can_replay_selected_bounded_validation_lane`.
The embedded `provider_runtime_preflight` row is body-free: it exposes status,
decision, next-action code, sample readiness booleans, replay commands,
recovery hint codes and hashes, and diagnostics while denying provider launch,
remote execution, raw preflight input export, raw diagnostics export, and raw
provider-value export.

The summary also carries `profile_validation_checklist`, a compact mirror of
the profile acceptance contract for the current pass. It marks each profile as
either `selected_current_pass_profile` or `queued_profile_for_later_pass`,
records the expected first local lane, validation scope, validation gate,
metadata requirements, and acceptance status, and repeats the local validation
commands. In the pass-2 skill-route window, FableCodex-style
`codex_workflow_gate` and Three.js-style `game_frontend_workflow` profiles can
be selected for the local test lane while COMPASS-style
`skill_ecosystem_state_handoff` remains queued for the local config lane. The
checklist is a replay aid only: it does not add lanes, install or activate
upstream skills, execute a secondary harness, launch providers, perform remote
execution, export raw evidence URLs, export raw source URLs, export raw target
paths, or export upstream bodies.

For pass-2 handoff specifically, `pass2_handoff_packet` also repeats the same
route-profile decision as `route_profile_acceptance_summary`. This summary gives
the supervisor the selected FableCodex-style `codex_workflow_gate` and
Three.js-style `game_frontend_workflow` rows in the local `test` lane, plus the
queued COMPASS-style `skill_ecosystem_state_handoff` row in the local `config`
lane, without expanding the nested readiness panel. The mixed
Codex/workflow/skill row must still report `skill_route_discovery_first`, and
the summary keeps the secondary harness lane blocked until local corroboration.
It is body-free and repeats that runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw evidence URL
export, raw source URL export, raw target path export, and upstream body export
remain denied.

The same pass-2 packet now includes `profile_lane_matrix`, a direct
profile-by-profile lane map derived from the acceptance contract. It records the
profile, selected bounded local lane, validation scope, validation gate, pass
role, accepted status, and lane-bounded boolean for generic skill workflows,
COMPASS-style state handoff, Three.js/game frontend workflows, and
FableCodex/Codex workflow gates. This matrix is the operator-visible bridge from
skill evidence to local replay lanes: every row must stay inside
documentation, config, test, or code_patch; every row keeps `runtime_action:
none`; and the matrix repeats denials for external skill activation, external
harness execution, provider launch, remote execution, raw evidence URL export,
raw source URL export, raw target path export, and upstream body export.

The same row now carries `recovery_replay_packet`, an operator replay packet for
the selected skill-route action. It translates provider-runtime recovery hint
codes into scoped replay steps such as adding a body-free sample, repairing
model-command config, reviewing a mock-auth placeholder, or resolving sampled
recovery hints before re-running the local preflight commands. The packet also
includes `operator_recovery_plan`, a compact replay plan with the packet status,
next action, sample route status, sanitized sample-plan decision, recovery step
codes and hashes, replay step names, and replay commands. The packet is not a
provider launch plan: it repeats selected item ID mode, candidate source hashes,
sample readiness booleans, replay commands, recovery code hashes, and denials
for runtime action, provider launch, remote execution, raw preflight inputs, raw
diagnostics, raw provider values, raw source URLs, raw target paths, and upstream
bodies. Blocked packets require repair before local replay; degraded packets are
replayable for local validation but remain review-only before any success claim.

On the final pass of a `provider-runtime-control` window,
`capability_window_completion` also emits `provider_runtime_completion_handoff`.
This packet joins the final slice status, provider-runtime sample gate,
activation packet readiness, and final closure readiness into a single
supervisor-visible decision. A ready packet means the pass-4 slice has a
body-free provider-runtime replay sample, the activation packet is ready, and
the local completion blockers are empty; blocked packets point back to the
provider-runtime sample gate or the local completion recovery lane. The packet
does not launch providers or activate upstream skills. It records only status
codes, counts, recovery hint codes and hashes, replay commands, final-pass
booleans, and the same denials for runtime action, external skill activation,
external skill code, external harness execution, provider launch, remote
execution, raw evidence URLs, raw source URLs, raw preflight inputs, raw
diagnostics, raw provider values, raw target paths, and upstream bodies.

Final provider-runtime diagnostics also include
`provider_runtime_operator_replay_workflow`. This is the flat operator checklist
for the same handoff: provider-runtime sample gate, provider-runtime recovery
summary, diagnostic panel, and completion handoff each get a status, decision,
readiness boolean, and recovery-code hashes. The workflow repeats the local
provider-runtime replay commands and the skill-route validation commands so a
supervisor can replay the path without expanding nested packets. It is a
diagnostic and recovery surface only: it does not grant runtime action, external
skill activation, external skill code execution, external harness execution,
provider launch, remote execution, raw evidence URL export, raw source URL
export, raw preflight input export, raw diagnostic export, raw provider value
export, raw target path export, or upstream body export.

The final `completion_report` carries
`provider_runtime_interpretation_panel` when the active theme is
`provider-runtime-control`. This panel is the expected interpretation of
provider/runtime wording found in skill-route evidence: diagnostics and
recovery hints only, followed by local provider-runtime replay and then bounded
documentation, config, test, or code_patch validation. It summarizes the
diagnostic panel, sample gate, recovery summary, and completion handoff as
status codes, readiness booleans, route-profile hashes, recovery hint codes,
and replay commands. It does not create a provider-runtime lane, launch a
provider, execute an external harness, activate upstream skills, perform remote
execution, export raw evidence URLs, export raw source URLs, export raw
preflight inputs, export raw diagnostics, export raw provider values, export raw
target paths, or export upstream bodies.

For final pass skill-route handoff, `capability_window_completion` also emits
`completion_report`. This is the compact operator summary to read before
traversing the nested activation packet, final closure, and provider-runtime
handoff objects. It records completion status, selected bounded lanes, selected
evidence reference hashes, missing route profiles, activation packet status,
final closure status, provider-runtime completion status, blocker hashes, and
replay commands. The report also includes `local_lane_closure`, a per-lane
closure summary derived from the validated activation packet. It reports
documentation, config, test, and code_patch readiness, selected profile
validation lanes, evidence reference hashes, source and target counts, local
artifact proof readiness, operator lane readiness, and activation blocker
hashes. A ready report means the completed slice can be handed to the
supervisor for local replay of documentation, config, test, or code_patch lanes
only. It does not expand evidence URLs, install or enable upstream skills,
execute external harnesses, launch providers, perform remote execution, export
raw source URLs, export raw target paths, or export upstream bodies.

The same report includes `activation_handoff`, a final supervisor replay
contract for pass-4 completion. It repeats the planned-window status, activation
packet status, final slice status, local lane closure status, provider-runtime
completion status, selected bounded lanes, ready and blocked lane counts, replay
step hashes, blocker hashes, required local validation, and provider-runtime
replay commands. A ready handoff says only that an external supervisor may
replay the already validated documentation, config, test, or code_patch lanes
after local validation. The kernel does not restart itself, launch providers,
perform remote execution, activate upstream skills, export raw evidence URLs,
export raw source URLs, export raw target paths, or export upstream bodies.

The report also emits `completion_audit`, a stable body-free fingerprint for
comparing pass-4 replay attempts. The fingerprint is derived from completion
status, bounded proposal kinds, selected local lanes, route profiles, selected
item-id hashes, per-lane readiness rows, replay-step hashes, and blocker hashes.
It is an audit key only: it does not add lanes, cite raw repository URLs, export
target paths, install or enable upstream skills, run external skill code,
launch providers, execute external harnesses, perform remote execution, restart
the kernel, or activate the completed slice without the existing supervisor
handoff.

The final report also includes `completion_replay_checklist`. This is the
operator-visible replay surface for closing a pass-4 skill-route slice: it
orders the profile validation gate, local lane closure, activation packet,
provider-runtime handoff, completion audit, and supervisor handoff into one
body-free checklist. A ready checklist means those surfaces are ready or not
applicable and the supervisor can replay the already bounded local lanes after
the local validation commands. A blocked checklist carries only hashed blocker
and step identifiers plus recovery hint codes. It does not add lanes, restart
the kernel, launch providers, execute external harnesses, perform remote
execution, export raw source or target paths, or activate upstream skill code.
The checklist now repeats `profile_lane_contracts`, one body-free row per route
profile, so operators can see that FableCodex-style workflow gates still start
with `skill_route_discovery_first`, Three.js-style game workflow evidence stays
on the local test lane, and COMPASS-style state handoff evidence stays on the
local config boundary lane. These rows repeat readiness booleans, gate names,
validation scopes, and replay commands only; they do not export raw source URLs
or grant profile writes, memory writes, provider launch, remote execution, or
upstream skill activation.

For domain-specific skill bundles such as Three.js game workflows, the harness
also emits `domain_validation_probe`. This panel is derived from the same
body-free validation lane plan and becomes ready only when the game/frontend
route profile maps to a local `test` lane with selected digest item evidence.
It lists the focused local replay commands and repeats that runtime action,
external skill activation, external skill code, upstream scaffold execution,
upstream browser checkers, asset generation, provider launch, remote execution,
raw source URLs, raw target paths, and upstream bodies remain denied. The probe
is an operator-visible pre-activation check for local test validation, not a
domain skill activation path.

`capability_window_completion` now repeats those grouped targets through
`validation_target_handoff` and repeats the per-profile replay checklist through
`profile_validation_replay`. This makes the next supervisor action visible from
the completion surface itself: a non-final pass can carry a local config target
for COMPASS-style state handoff and a local test target for FableCodex-style or
game-skill workflow evidence without requiring operators to infer the route from
raw upstream URLs. The handoff remains body-free and keeps the same denials for
runtime action, external skill activation, external harness execution, provider
launch, remote execution, raw evidence URLs, raw source URLs, raw target paths,
and upstream bodies.

`next_pass_handoff` also carries `next_pass_replay_packet`, a compact
supervisor replay row for the selected next validation target. The packet
copies the chosen bounded lane, selected `item_id` references, hashed candidate
sources, queued bounded lanes, replay commands, and completion blockers into
one place. It is intentionally not an activation token: runtime action,
external skill code, external skill activation, external harness execution,
provider launch, remote execution, raw evidence URL export, raw source URL
export, raw target path export, and upstream body export remain denied.

On pass 3 of a skill-route-discovery window, `pass3_handoff_packet` gives the
supervisor the active final-pass lane and any queued bounded lane in one
body-free packet. For the FableCodex, Three.js Game Skills, and COMPASS Skills
class, it keeps the selected local `test` lane and queued local `config` lane
visible together, preserves only selected `item_id` references and source
hashes, and repeats that mixed Codex/workflow/skill evidence stays
`skill_route_discovery` first while
`agent_harness_eval_after_local_corroboration` remains blocked. The packet does
not add lanes, install or enable upstream skills, run upstream code, activate
an external agent, execute a harness, launch a provider, perform remote
execution, export raw evidence URLs, export raw source URLs, export raw target
paths, or export upstream bodies.

The same packet now includes `final_pass_replay_checklist`, an operator-facing
recovery checklist for the final pass. It separates four checks: replay the
selected current-pass lane, carry queued bounded lanes, preserve the secondary
agent-harness block until local corroboration exists, and verify that the
handoff remains body-free. The checklist repeats only selected item counts,
bounded lane names, route profiles, replay commands, and denial flags. It does
not add proposal lanes, cite raw URLs, import upstream skill bodies, launch
providers, execute harnesses, or activate external skills.

The pass-3 packet also includes `operator_checkpoint_list`, a compact row list
for the same selected and queued lanes. This gives operators a direct checkpoint
view of the FableCodex/Three.js local test lane and the COMPASS config lane
without walking nested queue rows. Each checkpoint carries only the bounded lane,
route profiles, selected item counts, source counts, queue fingerprint, replay
commands, provider-runtime replay commands, blockers, and denial flags. It does
not export raw evidence URLs or source URLs, expose upstream bodies, run
providers, execute harnesses, or activate external skills.

On the first pass of a skill-route-discovery window, the harness also emits
`pass1_handoff_packet`. The packet joins the selected current-pass bounded lane,
queued bounded lanes, selected digest item IDs, hashed candidate sources, and
local replay commands into one supervisor-visible row. Omnigent-style general
agent framework evidence remains adjacent only: the packet reports
`adjacent_general_agent_project_eval` with `agent_harness_eval_required: true`,
`skill_route_discovery_inherited: false`, and allowed local lanes of
documentation, test, or code_patch. It does not add skill-route lanes, grant
runtime action, activate an external agent, run an external harness, launch a
provider, perform remote execution, export raw source URLs, or export upstream
bodies.

The current pass-1 replay fixture for digest
`github-growth-20260621T043207.872197Z` uses the carried proposal IDs
`p1-skill-route-discovery-compass`, `p2-threejs-skill-discovery-fixture`, and
`p3-fablecodex-skill-workflow-probe` as the only proposal evidence refs. It
selects the local `test` lane for mixed FableCodex/Three.js workflow evidence,
queues the COMPASS state-handoff evidence as a bounded documentation lane, and
keeps the FableCodex mirror source as hashed lineage pressure. The mixed probe
continues to report `skill_route_discovery` as the primary route while
`agent_harness_eval_after_local_corroboration` remains blocked. This fixture is
an activation-readiness replay surface for documentation, config, test, or
code_patch lanes only; it does not install, enable, run, clone, scaffold,
launch providers, activate external harnesses, write profiles or memory, export
raw GitHub URLs, or treat upstream skill bodies as local behavior.

Before supervisor promotion, the lane now emits
`activation_manifest` as a compact replay surface for bounded local work. The
manifest lists only the allowed local lane names, selected-item `evidence_refs`,
route profiles, candidate source hashes, local target path hashes, local
artifact proof readiness, required validation commands, provider-runtime replay
commands, recovery hint codes, and activation blockers. Its
`evidence_ref_mode` is `selected_item_ids_only`: public repository URLs remain
source evidence in the frozen package, not manifest citations. A ready manifest
means documentation, config, test, or code_patch lanes have enough local proof
to replay; it still denies runtime action, external skill activation, external
harness execution, provider launch, remote execution, raw evidence URLs, raw
source URLs, raw target paths, and raw upstream bodies.

The activation manifest also carries `activation_sequence`, an ordered
supervisor replay checklist derived from the same body-free fields. The sequence
requires source-lineage inspection, bounded local lane checks, local artifact
proof, focused local validation, provider-runtime preflight replay, and the
final operator handoff before it reports ready. Each step repeats the denials
for runtime action, external skill activation, external harness execution,
provider launch, remote execution, raw evidence export, raw source URL export,
raw target path export, and upstream body export. The sequence is a replay
surface only; it does not install, clone, execute, scaffold, generate assets, or
activate upstream skill code.

The validated activation packet now includes `operator_activation_lane`, a
compact supervisor queue derived from the manifest rows. It reports only bounded
local proposal kinds, route profiles, selected evidence counts, candidate source
hash counts, local target hash counts, proof readiness, and replay commands. A
ready operator lane means every listed documentation, config, test, or
code_patch row already has local artifact proof and the packet has no completion
diagnostics. A blocked operator lane points the supervisor back to local repair
before replay. It repeats the same denials for runtime action, external skill
activation, external skill code, external harness execution, provider launch,
remote execution, raw evidence URL export, raw source URL export, raw target
path export, and upstream body export.

Activation rows now distinguish bounded upstream evidence from proof that a
local artifact exists for the lane. A clean discovery lane can still be blocked
from supervisor handoff until it carries a body-free `local_artifact_proof` for
each proposal kind. That proof records only changed-file hashes, rollback
artifact hash, validation-command match, target-contract match, and a review-note
presence flag. It must not export raw upstream bodies, raw source URLs, secrets,
or external skill code, and it does not execute any upstream package. This keeps
repositories such as FableCodex, COMPASS Skills, and Three.js Game Skills useful
as route evidence while requiring an operator-visible local docs/config/test/code
artifact before promotion.

Use this lane when a digest proposes skill-route discovery work that should be
validated by the controller surface before a code, config, test, or
documentation proposal is applied:

```bash
pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane
pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane
pytest tests/test_harness_eval.py -q -k proposal_interpretation
pytest tests/test_harness_eval.py -q -k provider_runtime_preflight
pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary
```

The proposal-interpretation smoke suite is required because it checks the
controller-facing proposal gates that sit immediately after route discovery:
allowed local lanes, selected-item `evidence_refs` rather than URL citations,
and review-only classification for offensive-behavior or privacy-leakage
signals. Passing route discovery alone does not prove those proposal gates.

## Native Session Title Lane

The 2026-06-19 source digest carried Omnigent issue #851, where a native Claude
Code session launched first through a Skill or slash-command stayed untitled and
the sidebar fell back to the generic provider label `Claude Code`. The reusable
local lesson is not provider-specific UI behavior; it is a runner-harness
metadata invariant: a skill-first native session must preserve enough command,
skill, prompt, or launch context to seed a descriptive session title.

`native_skill_session_title` is the local replay lane for that invariant. It
accepts body-free fixture metadata for provider label, launch context,
transcript item kinds, and session title metadata. It passes only when a
skill/slash-command-first launch has context signals, the session title is
present, the title source is one of command, skill, prompt, launch_context, or
LLM summary, and the title does not fall back to a generic provider label.

The lane is metadata-only. It hashes title and provider labels, does not export
raw command text, prompt bodies, title strings, session IDs, or transcript
bodies, and does not launch a native provider. A blocked result should be fixed
by preserving launch context through the controller/session metadata path before
activation, then replayed with:

```bash
pytest tests/test_harness_eval.py -q -k native_skill_session_title
```

## Route-Hint Policy Preflight

Before proposal interpretation accepts any implementation lane,
`build_route_hint_lane_map` renders controller-owned route hints into bounded
proposal lanes, and `build_route_hint_policy_preflight` checks that map. For
`skill_route_discovery`, the only valid resolved lanes are still documentation,
config, test, and code_patch. Any extra lane such as runtime_execution,
install, enable, or follow_up_issue causes the preflight to fail before a
candidate can be normalized or accepted.

The lane map and preflight are intentionally metadata-only. They read selected
item `route_hints` and the controller policy table, then report selected hints,
configured hints, route-hint entries, proposal lanes, and diagnostics. They do
not read upstream skill bodies, install packages, expose secrets, execute
repository scripts, grant permissions, or add new evidence URLs. This makes
route-hint drift visible even when an LLM candidate would otherwise be rejected
later by the per-candidate lane check.

The proposal evidence package now also records a body-free route classification
beside each selected item. Public repositories that show reusable skills,
skill packs, director skills, workflow gates, workflow routing, plugins, or
tool integrations are classified as `skill_workflow` and may expose only the
bounded `skill_route_discovery` lanes: documentation, config, test, and
code_patch. General agent-project movement remains visible as
`general_agent_project` when it names agents or runtimes but lacks a skill or
workflow-specific route signal. That class does not inherit
`skill_route_discovery` lanes merely from repository popularity or generic
agent activity.

`build_route_hint_lane_map` summarizes those classifier rows through
`route_class_counts` and `route_classifier`. The rows carry item IDs, route
class, route hints, allowed local lanes, route profiles, and classifier reasons
only. Route profiles distinguish the local validation shape before activation:
FableCodex-style Codex workflow gates are `codex_workflow_gate`, COMPASS-style
state or profile handoff packages are `skill_ecosystem_state_handoff`, and
Three.js/domain game skill packages are `game_frontend_workflow`. These profiles
select review lanes and replay expectations, not upstream activation authority.
They do not export raw upstream bodies, add evidence URLs, grant permissions,
install packages, or request runtime action.

The map also checks selected item metadata for lane drift. If a pre-shaped
`route_classification` marks an item as `skill_workflow` but includes lanes
outside documentation, config, test, or code_patch, the unsupported lanes are
reported on the classifier row and the policy preflight fails before proposal
review. The `skill_route_local_lane_candidates` panel still shows the filtered
bounded lanes for audit, but marks that item `blocked_unsupported_lanes` and
sets the activation gate to `blocked_before_activation`. This prevents
malformed selected-item metadata from bypassing local validation by being
silently narrowed in the operator-facing panel.

The same route-hint map also emits `skill_route_local_lane_candidates`, a
bounded pre-activation panel derived directly from selected skill/workflow
items. FableCodex, COMPASS Skills, and Three.js Game Skills-style rows expose
only documentation, config, test, and code_patch as `local_lanes`, require local
validation, hash source URLs, and deny runtime action, external skill
activation, external agent activation, and upstream body export. Mixed
FableCodex-style rows keep the secondary harness lane blocked until local
corroboration, while general agent projects such as Omnigent do not appear in
this panel.

For general agent projects such as Omnigent-style agent frameworks or
meta-harnesses, the same lane map emits `general_agent_project_eval`. This is
an evaluation lane, not a skill-route lane: it records selected item IDs, hashed
source URLs, `agent_harness_eval_required`, allowed local lanes of
documentation, test, or code_patch, and replay commands for the local harness
and proposal tests. It keeps `skill_route_discovery_inherited: false`,
`local_validation_required: true`, `runtime_action: none`, raw source URL
export denied, and external agent activation denied. The 2026-06-21T08:32Z
pass-1 route window replays this split with FableCodex, COMPASS Skills, and
Three.js Game Skills in bounded skill-route lanes while Omnigent-style general
agent evidence remains gated behind harness evaluation. A general agent
framework can therefore justify local harness evaluation before a behavior
change, but cannot become a skill discovery candidate unless the selected
evidence also shows skill/workflow signals.

The same route-hint map now emits `skill_route_boundary_report`, a compact
operator summary of that split. Skill/workflow rows such as FableCodex,
COMPASS Skills, or Three.js Game Skills keep `primary_route:
skill_route_discovery` with only documentation, config, test, or code_patch
local lanes. General agent-project rows such as Omnigent or xuefeng-agent keep
`primary_route: agent_harness_eval_required` with documentation, test, or
code_patch evaluation lanes and `skill_route_discovery_inherited: false`.
Mixed skill/workflow rows keep
`agent_harness_eval_after_local_corroboration` blocked until local
corroboration exists. The report exports item IDs and source URL hashes only;
it does not add lanes, expose raw source URLs, export upstream bodies, run an
external harness, launch a provider, perform remote execution, activate an
external agent, or activate upstream skill code.

The skill-route proposal lane map now also emits `pass2_validation_handoff`.
This is the pass-2 operator surface for the active skill-route-discovery window:
COMPASS-style skill ecosystems, zhengxi-views-style source-cited domain skills,
and Three.js-style game frontend skills are converted into selected local
validation lanes before any activation. Each row keeps
`primary_route: skill_route_discovery`, exposes only documentation, config,
test, or code_patch as allowed local lanes, requires local validation, and
denies runtime action, upstream skill activation, external harness execution,
provider launch, remote execution, raw source URL export, target-path export,
and upstream body export. Adjacent general-agent projects remain outside this
handoff through `adjacent_general_agent_policy`: they require
`agent_harness_eval_required`, allow only documentation, test, or code_patch
evaluation lanes, and keep `skill_route_discovery_inherited: false` until a
local harness replay succeeds.

The route-hint map now also emits `route_activation_preflight`, a supervisor
gate that turns the split into an activation-readiness decision before local
work is selected. It lists skill-route rows, general-agent rows, bounded local
lanes, blockers, and replay commands without raw repository URLs or upstream
bodies. FableCodex, COMPASS Skills, and Three.js Game Skills-style evidence can
be ready only for documentation, config, test, or code_patch validation.
Omnigent-style general agent-project evidence remains
`agent_harness_eval_required` with documentation, test, or code_patch evaluation
lanes and `skill_route_discovery_inherited: false`. A ready preflight does not
install, enable, run, clone, scaffold, launch providers, execute an external
harness, activate an external agent, activate upstream skill code, perform
remote execution, or export raw source URLs.

For pass 3 handoff, the same map emits `skill_route_pass3_handoff`. This is a
body-free supervisor packet for the active skill-route-discovery window: skill
workflow repositories such as COMPASS Skills, zhengxi-views, and Three.js Game
Skills keep `primary_route: skill_route_discovery` with only documentation,
config, test, or code_patch lanes, while adjacent general agent projects such
as Omnigent keep `primary_route: agent_harness_eval_required` with
documentation, test, or code_patch evaluation lanes. The packet records selected
item IDs, route rows, lane limits, replay commands, and activation blockers
only. It requires local validation, exports no raw source URLs or upstream
bodies, performs no runtime action, and grants no external skill, agent,
harness, provider, or remote-execution activation.

The classifier treats negated skill language as boundary evidence rather than a
positive skill-route signal. Phrases such as `not skill discovery inheritance`
do not create `skill_route_discovery` unless the same selected item also names a
concrete skill artifact such as `SKILL.md`, `agent skill`, `skill package`, or a
skills directory. This keeps general agent/meta-harness evidence visible for
`agent_harness_eval` without inheriting skill lanes by accident.

The source-registry lane map also emits `adoption_manifest`, a body-free
operator handoff for public skill ecosystem evidence before any adoption
decision. The manifest records each candidate's route profiles, bounded local
lanes, selected validation lane, validation target, replay command, evidence
item IDs, and source hash. FableCodex-style workflow gates, COMPASS-style state
handoff packages, and Three.js/game frontend skill packages can be marked ready
only for local validation lanes: documentation, config, test, or code_patch.
The manifest keeps `runtime_action: none`, requires
`local_validation_required: true`, blocks install, execute, provider launch,
remote execution, upstream skill activation, raw source URL export, and upstream
body export, and remains blocked if a candidate is rejected, downgraded, lacks a
bounded lane, or misses required `skill_route_discovery_first` proof.

The same lane map now emits `validation_profile_coverage` for pass-3
source-registry review. It normalizes both route profiles and route signals into
one operator-visible checklist: `skill_term`, `mixed_skill_workflow_probe`,
`generic_skill_workflow`, `skill_ecosystem_state_handoff`,
`game_frontend_workflow`, and `codex_workflow_gate`. Each row reports candidate
names, source URL hashes, bounded local lanes, selected local lanes, and signal
basis only. A ready row still means local validation is required and only
documentation, config, test, or code_patch lanes are available; it does not
install, enable, execute, launch a provider, run an external harness, perform
remote execution, export raw source URLs, or export upstream bodies.

Mixed Codex/workflow/skill repositories now get an explicit local probe before
that split becomes ambiguous. When a selected item has skill-route evidence and
also mentions Codex, plugins, examples, tests, evals, replay, harness, or other
validation signals, `build_route_hint_lane_map` emits
`mixed_skill_workflow_probe` and marks the classifier row with
`route_probe_decision: skill_route_discovery_first`. This is the FableCodex
procedure for source digest `github-growth-20260620T175208.289414Z`: public
evidence showed a Codex workflow plugin with verification habits, examples,
tests/evals, and routing docs, so the local first lane is still
`skill_route_discovery`, not upstream plugin install and not automatic
agent-harness activation.

The probe is body-free and cites only selected item IDs plus source URL hashes.
Its secondary lane is
`agent_harness_eval_after_local_corroboration`, meaning harness evaluation can
be selected later when the proposal names a general agent-project claim or when
local fixtures prove a harness-specific gap. Until then, the allowed local
outputs remain documentation, config, test, and code_patch; runtime action,
external skill activation, external agent activation, raw source URL export,
upstream body export, install, enable, run, execute, clone-and-run, profile
write, and memory write remain denied.

The mixed probe now carries an explicit activation gate:
`local_skill_route_validation_before_secondary_harness_eval`. Candidate rows
mark the secondary lane as `blocked_until_local_corroboration` and expose a
recommended local lane order of test, documentation, config, then code_patch.
That order is advisory only and is filtered to the already allowed
skill-route lanes; it cannot add follow-up issue, runtime execution, install,
provider launch, remote execution, profile-write, memory-write, raw source URL
export, or upstream body export authority. The required validation commands
remain the local mixed-skill and route-hint lane-map tests.

The core disabled-registry lane map now exposes the same first-route decision
before downstream harness expansion. When body-free candidate metadata contains
mixed Codex, skill, and workflow terms, each candidate inventory row and
proposal-lane row records `route_probe_decision: skill_route_discovery_first`,
`primary_route: skill_route_discovery`,
`secondary_lane: agent_harness_eval_after_local_corroboration`, and
`secondary_lane_status: blocked_until_local_corroboration`. An explicit agent
term is recorded as `full_mixed_signal`, but it is no longer required for a
FableCodex-style Codex/skill/workflow repository to enter skill-route discovery
before any broader harness evaluation. The recommended lane order is filtered
to lanes already present on that candidate, and the allowed proposal kinds
remain only documentation, config, test, and code_patch.

The core lane map also emits a `route_validation_contract` on every candidate
inventory row and proposal-lane row. This contract is derived only from
body-free route profiles and already bounded lanes; it does not inspect
upstream skill bodies and it cannot add lanes. `codex_workflow_gate` rows use
`skill_route_discovery_first_before_workflow_gate`, `game_frontend_workflow`
rows use `local_frontend_validation_before_game_skill_activation`, and
`skill_ecosystem_state_handoff` rows use
`state_handoff_boundary_before_profile_or_memory_write`. Each row repeats
`local_validation_required: true`, `runtime_action: none`, denied external
skill activation, denied provider launch, denied remote execution, and denied
raw upstream body export before activation.

Each core candidate inventory row and proposal-lane row also carries
`handoff_metadata`. This is the bounded local handoff surface used before a
supervisor or later pass selects work: it records the selected local lane, any
queued local lanes, profile validation gates, required metadata, and the same
activation denials as the route validation contract. Candidate rows may queue
remaining documentation, config, test, or code_patch lanes; individual proposal
rows select only their own proposal kind and queue nothing. The handoff metadata
does not export raw upstream bodies, add evidence URLs, install or enable
external skills, run external harnesses, launch providers, or perform remote
execution.

The core lane map now also emits `local_lane_matrix`, a compact pre-activation
summary derived from the bounded candidate inventory. It gives controllers one
row per recognized skill repository with route profiles, allowed local lanes,
selected and queued lanes, validation gates, and whether a FableCodex-style
`codex_workflow_gate` has confirmed `skill_route_discovery_first`. The matrix
is ready only when every row has at least one bounded local lane and required
first-route proof is present. It does not add lanes, export raw source URLs or
upstream bodies, install or enable upstream skills, execute external harnesses,
launch providers, or perform remote execution.

Pass-1 lane maps also emit `local_activation_targets`, a body-free validation
target panel derived from the same candidate inventory. Each row records the
selected bounded local lane, queued local lanes, profile validation gates, a
local validation target, and the focused replay command an operator can run
before activation. FableCodex-style workflow evidence maps to a
`skill_route_first_probe_regression`, COMPASS-style state handoff maps to
`state_or_profile_boundary_metadata`, and Three.js/game frontend evidence maps
to `local_frontend_render_or_workflow_check`. The panel hashes candidate
sources and exports no raw evidence URLs or upstream bodies. It is an activation
target list, not an activation grant: runtime action, upstream skill activation,
external harness execution, provider launch, remote execution, profile writes,
memory writes, and source/body export remain denied.

Pass-1 lane maps now also emit `pass1_validation_matrix`, a compact replay
matrix derived only from `local_activation_targets`. It gives the supervisor one
row per bounded candidate with selected and queued local lanes, route profiles,
validation gates, replay command, selected item IDs, promotion proof hashes, and
activation blockers. The matrix is ready only when every row is ready for local
validation. It is not a new activation lane: runtime action, upstream skill
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw evidence URL export, raw target path export, and upstream
body export remain denied.

The same core lane map now exposes `next_validation_step`, a compact pass-2
handoff selector derived only from `local_activation_targets`. It chooses one
ready bounded replay target for the supervisor to run next, prioritizing
FableCodex-style `skill_route_discovery_first` regression checks before
game/frontend test lanes and COMPASS-style state boundary review. The selector
also lists ready and blocked candidate names so the scheduled loop can stop on
missing first-route proof instead of inferring readiness from individual rows.
The selected step now carries `promotion_proof`: a body-free checklist of
changed-file review, focused local validation, rollback artifact, and review
note evidence, plus hashed target paths for the chosen bounded lane. This lets
the supervisor see which proof must exist before promotion without exporting
raw target paths or treating the replay command as activation.
It does not add lanes or grant activation: runtime action, upstream skill
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw evidence URL export, raw target path export, and upstream
body export remain denied.

The lane map also emits `route_profile_handoff_queue`, an operator-visible
profile queue derived from `local_activation_targets`. Each observed profile
gets one body-free handoff row with its selected bounded local lane, validation
target, replay command, validation gates, selected evidence item IDs, hashed
candidate sources, first-route proof status, and activation blockers. This
makes FableCodex-style `codex_workflow_gate`, COMPASS-style
`skill_ecosystem_state_handoff`, and other skill-workflow validation profiles
visible before a pass is activated. The queue does not add lanes or grant
authority: runtime action, upstream skill activation, external harness
execution, provider launch, remote execution, raw source URL export, raw
evidence URL export, raw target path export, and upstream body export remain
denied.

Harness replay results now surface that same `local_lane_matrix` inside the
top-level `lane_map` summary. This is the pass-4 operator path for the active
COMPASS/FableCodex/Three.js window: a supervisor can inspect the bounded
profile rows, selected local lanes, queued lanes, and first-route proof before
opening the deeper completion report. The summary remains body-free and
classification-only; it does not authorize upstream skill activation, external
harness execution, provider launch, remote execution, profile writes, memory
writes, or raw upstream body export.

The local harness also summarizes those row contracts as
`profile_lane_acceptance_contract`. This profile-level panel is the pass-handoff
view: it lists the observed route profiles, allowed documentation/config/test/
code_patch lanes, each profile's preferred first validation lane, validation
scope, metadata requirements, and acceptance gates. FableCodex-style
`codex_workflow_gate` evidence must preserve `skill_route_discovery_first`
before workflow handling; Three.js `game_frontend_workflow` evidence starts in
the local test/frontend validation lane; COMPASS-style
`skill_ecosystem_state_handoff` evidence starts in the local config/state
boundary lane. The panel is ready only when profile review is ready, metadata
is complete, local validation remains required, runtime action is `none`, and
external skill activation, external harness execution, provider launch, remote
execution, raw source URL export, raw target path export, and upstream body
export remain denied. The pass-2 handoff packet embeds the same contract so the
operator can reject a pass before replaying selected or queued bounded lanes.

For pass-1 windows, `pass1_validation_queue` also carries the relevant trimmed
profile contract on each skill-route anchoring proposal row. This lets an
operator inspect the Three.js/game frontend validation gate, COMPASS state
handoff boundary, and FableCodex first-route proof directly beside the selected
bounded lane. These row-level contracts are replay metadata only: they do not
add lanes, do not change the selected local lane, and keep runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw source URL export, raw target path export, and upstream body
export denied.

`pass1_validation_queue` also summarizes those row contracts as
`profile_validation_lanes`. This is the operator-visible lane queue for the
active pass-1 profile set: COMPASS-style state handoff exposes the local config
or boundary-review lane, Three.js game/frontend evidence exposes the local test
or frontend-validation lane, and FableCodex-style workflow evidence exposes the
local test lane with `first_route_required` and `first_route_confirmed` before
any secondary harness path. The panel is derived only from already-bounded
profile contracts and selected item IDs; it does not add lanes, export raw
source URLs or upstream bodies, install or enable upstream skills, execute an
external harness, launch providers, write memory/profile state, or perform
remote execution.

`pass1_validation_queue` also emits `pass1_replay_lane_plan` for current
pass-1 windows. This is the compact supervisor replay order: first the selected
current-pass lane and then queued bounded profile lanes. Each row carries only
selected digest item IDs, candidate source hashes, validation gates, queue
fingerprints, and local replay commands. It does not export raw GitHub URLs,
raw target paths, upstream bodies, or sensitive values, and it continues to
deny runtime action, external skill activation, external harness execution,
provider launch, remote execution, profile writes, and memory writes. The
surface lets an operator validate COMPASS state-handoff, FableCodex
workflow-gate, and game/frontend workflow lanes without inferring replay order
from multiple panels.

Pass-3 handoff packets also emit `profile_activation_gates`. This is the final
pre-activation profile view for the active window: it maps each observed route
profile to its selected bounded local lane, queue role, selected item IDs,
hashed candidate sources, required local validation, and activation blockers.
Codex workflow rows must still prove
`route_probe_decision: skill_route_discovery_first`; game/frontend rows remain
local test validation; skill-ecosystem state handoff rows remain local config
validation. The gate is body-free and cannot add lanes, install upstream
skills, run external harnesses, launch providers, write profile or memory
state, perform remote execution, or export raw source URLs or upstream bodies.

The pass-3 gate now also carries the profile acceptance contract into each
activation row. A profile cannot be ready for final-pass replay unless its
contract status is ready, its profile-specific validation gate is visible, and
its metadata requirements remain satisfied. FableCodex-style workflow rows
therefore expose `skill_route_discovery_first_before_workflow_gate`; Three.js
game/frontend rows expose `local_frontend_validation_before_game_skill_activation`;
COMPASS-style state handoff rows expose
`state_handoff_boundary_before_profile_or_memory_write`. If any acceptance gate
fails, the handoff is blocked before activation while preserving only the
bounded documentation, config, test, or code_patch lanes.

Pass-3 handoff packets also include `profile_validation_proof`. This packet is
the focused-evidence-review lane for the active Compass/FableCodex/Three.js
window: each route profile must have one bounded selected local lane, selected
item IDs, hashed candidate sources, a matching local artifact proof, required
local replay commands, and a ready profile acceptance contract. Missing proof
or a failed acceptance contract blocks that profile before final activation.
The proof remains body-free and does not install upstream skills, execute
external harnesses, launch providers, write profile or memory state, perform
remote execution, or export raw source URLs, raw target paths, or upstream
bodies.

The same pass-3 packet now includes `activation_proof_summary`, a compact
operator handoff derived from `profile_validation_proof`. It collapses profile
readiness, selected bounded local lanes, blocker counts, local artifact proof
presence, acceptance-contract readiness, and hashed replay-command evidence
into one promotion-facing decision. This summary is intentionally not a new
lane and not an activation grant: it exports no raw source URLs, evidence URLs,
target paths, or upstream bodies, and it keeps runtime action, external skill
activation, external harness execution, provider launch, and remote execution
denied until the focused local replay has passed.

Pass-3 handoff packets now also include `promotion_runbook`, an ordered
supervisor replay gate derived from `operator_checkpoint_list`,
`profile_validation_proof`, and `activation_proof_summary`. The runbook keeps
the selected current-pass lane and queued bounded lanes in replay order, repeats
profile validation gates, hashes validation commands, and blocks promotion when
any proof surface is blocked. It remains body-free and cannot activate upstream
skills, execute external harnesses, launch providers, perform remote execution,
or export raw source URLs, evidence URLs, target paths, or upstream bodies.

The same pass-3 packet also includes `local_validation_probe`, a compact
activation-review probe for skill ecosystem route discovery. It maps the
COMPASS, FableCodex, and game/frontend route profiles to their bounded local
lanes, validation gates, selected item IDs, candidate source hashes, queue
fingerprints, required local validation commands, and provider replay commands.
FableCodex-style `codex_workflow_gate` rows must preserve
`skill_route_discovery_first`; game/frontend rows stay in local `test`
validation; COMPASS-style state handoff stays in the local `config` boundary.
The probe fails closed when the acceptance contract, local artifact proof,
first-route decision, or promotion runbook step is not ready. It repeats the
same denials for runtime action, external skill activation, external harness
execution, provider launch, remote execution, raw evidence URL export, raw
source URL export, raw target path export, and upstream body export.

Pass-4 completion reports include `final_route_handoff_manifest`, a compact
body-free route manifest for the external supervisor. It presents one row per
route profile with the selected bounded local lane, operator replay step,
profile gate, selected item IDs, hashed candidate sources, and completion
diagnostics. For the FableCodex, Three.js Game Skills, and COMPASS Skills
window, the manifest maps FableCodex-style workflow gates and game/frontend
skills to local `test` replay, while COMPASS-style state handoff maps to local
`config` review. The manifest is not an activation grant: runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw source URL export, raw target path export, and upstream body
export remain denied.

The same pass-4 report now emits `route_validation_lane_queue`. This is the
operator-visible queue for the completed slice: it restates the final route
profiles as bounded local validation lanes, reports the selected `config` or
`test` lane per profile, and carries the replay commands needed before any
supervisor promotion. For FableCodex-style Codex/workflow evidence, each queued
row also carries `workflow_gate`: `skill_route_discovery_first` must be
confirmed before the workflow gate is considered ready, and the queue blocks the
row if that first-route proof is missing. Game/frontend and state-handoff rows
stay in the same bounded local lane queue without gaining a secondary workflow
action. Repository activity freshness is included only as a non-authoritative
signal. A COMPASS-style `PushEvent` can mark
`push_event_freshness_signal: true`, but `push_event_authoritative` remains
false and the queue still denies install, activation, external harness
execution, provider launch, remote execution, raw source URL export, raw target
path export, and upstream body export.

Pass-4 completion also emits `secondary_harness_bridge`, the local handoff
between skill-route discovery and broader `agent_harness_eval_lane` checks.
This bridge is for mixed skill/workflow/general-agent signals such as
FableCodex plus Omnigent-style harness evidence: it records which route profile
would require a later agent-harness evaluation, confirms that
`skill_route_discovery` stayed first, and keeps the secondary lane
`blocked_until_local_corroboration`. The bridge is not activation authority.
It denies local eval activation, external harness execution, provider launch,
remote execution, raw source URL export, and upstream body export until a later
local agent-harness fixture maps the candidate claims to existing controller
invariants.

Pass-4 completion also emits `completion_consistency_guard`. This guard compares
the activation handoff, replay checklist, final route handoff manifest, route
validation lane queue, and secondary harness bridge before the completion report
can be marked ready.
The selected local lane set must match across those surfaces, ready and blocked
profile counts must match ready and blocked queue counts, all panel statuses
must be ready, and the handoff must remain external-supervisor controlled with
no kernel restart request. Diagnostics are reported only as hashes. The guard
does not add lanes or grant activation: runtime action, upstream skill
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw target path export, and upstream body export remain
denied.

The guard also emits `replay_contract`, a body-free command-alignment check for
the same final surfaces. The activation handoff, replay checklist, final route
handoff manifest, and route validation lane queue must all carry the
skill-route local replay command, while the secondary harness bridge must carry
both the skill-route replay command and the later `agent_harness_eval_lane`
command. The contract exports command hashes rather than raw commands and
blocks completion if a final surface drops the expected local replay path.

Pass-4 completion now also emits `current_window_evidence_gate`. This is the
operator-visible link between the upstream evidence window and local capability
closure: when the planned final pass declares required route profiles, the gate
checks that the observed route profiles cover that requirement, that selected
digest evidence refs are present, and that the source evidence is represented
only as URL hashes. This lets FableCodex-style skill/workflow evidence,
COMPASS-style skill ecosystem state handoff evidence, and Three.js workflow
evidence become a single local completion gate without importing upstream skill
code or exporting raw GitHub URLs. Omnigent-style generic movement remains
supporting context for a separate agent-harness route unless it carries concrete
route hints or local code matches. The gate can block the completion report, but
it does not grant runtime action, external skill activation, external harness
execution, provider launch, remote execution, raw evidence URL export, raw
source URL export, or upstream body export.

Pass-4 completion also emits `final_lane_policy_inventory`. This is the
operator-facing inventory for the completed skill-route slice: it repeats the
allowed local lane set, proposal kinds, selected local lanes, evidence-ref and
evidence-URL hash counts, profile rows, replay-command hashes, and whether a
later agent-harness evaluation remains blocked behind local corroboration. The
inventory is derived from `final_route_handoff_manifest`,
`route_validation_lane_queue`, and `secondary_harness_bridge`; it does not add
lanes, accept raw repository URLs, export upstream bodies, install upstream
skills, execute external harnesses, launch providers, perform remote execution,
or grant runtime action.

The lane map now also exposes `pass4_completion_handoff`, a compact final
operator checklist derived from `pass4_local_lane_validation`. It records the
required rollback ref and artifact contract, hashed replay commands, per-profile
inspection requirements, recovery hint codes, and the handoff mode
`external_supervisor_replay_without_kernel_restart`. The accepted skill-route
rows still map only to documentation, config, test, or code_patch lanes, and the
adjacent general-agent boundary remains
`agent_harness_eval_required` with `skill_route_discovery_inherited: false`.
This panel is a replay and recovery handoff only: runtime action remains
`none`, external skill activation and external harness execution remain false,
and raw source URLs, raw evidence URLs, raw target paths, and upstream bodies
are not exported.

Final-pass completion also exposes `pass4_operator_replay_manifest`, a
body-free replay packet derived from `pass4_completion_handoff`. It gives the
external supervisor one compact checklist for the selected local lanes: confirm
the rollback ref and artifact, replay the selected local lane commands from
`pass4_local_lane_validation`, compare changed files with hashed lane artifact
targets, record unmatched files as review notes or blockers, and keep activation
outside the kernel. The manifest records only candidate names, route profiles,
selected lane names, candidate source hashes, replay-command hashes, artifact
target hashes, recovery hint codes, and the adjacent general-agent boundary.
It does not export raw target paths, raw replay commands, raw source URLs, raw
evidence URLs, upstream bodies, install instructions, external harness
execution, provider launch, remote execution, or runtime action.

The `agent_harness_eval_lane` replay now carries a body-free
`claim_evaluation` matrix for this general-agent path. Each recognized public
record can contribute behavior claims such as multi-agent orchestration, policy
or sandbox control, provider configuration, conversation state, or local data
grounding. Claims that map to existing local controller or runner capabilities
name their focused validation commands; claims without a local capability remain
`unmapped_evidence_only`. The matrix does not export raw repository URLs or
upstream bodies, does not execute external projects, and does not grant external
agent activation. This is the intended lane for comparing Omnigent-style
meta-harness evidence with domain-agent evidence such as xuefeng-agent before
any local behavior change is proposed.

For final-pass skill-route windows that carry Omnigent-style policy or harness
execution pressure, the secondary bridge can now use `agent_harness_policy_eval`
as the pre-execution lane. That lane validates only local fixture, controller
replay, report-generation, mock-harness, or local-validation action plans, and
requires an earlier policy decision before each action is considered runnable.
ASK, DENY, review-required, missing, late, or unknown policy outcomes block
before execution; external harness execution, provider launch, remote execution,
credential access, and upstream agent activation remain forbidden action kinds.
The replay command is `pytest tests/test_harness_eval.py -q -k
agent_harness_policy_eval`, and reports hash action/policy ids while omitting
raw commands, provider config, credentials, policy bodies, source URLs, and
upstream bodies.

The same replay now emits `project_intake_probe` before local behavior adoption
is considered. This panel records five body-free shape categories for each
general-agent project: install shape, entrypoints, dependency boundaries, task
loop assumptions, and observable behaviors. Omnigent-style meta-harness evidence
can therefore be represented as Python/package or installer shape, CLI/server/
YAML-agent entrypoints, provider and sandbox boundaries, orchestrated session
loops, and observable policy or multi-agent supervision behavior. Domain-agent
evidence such as xuefeng-agent can be represented as web/API entrypoints,
database/provider/browser-session boundaries, conversational loop assumptions,
and source-citation or model-selection behavior. The probe hashes sources and
exports no raw install commands, upstream bodies, provider inputs, or project
code. `status: ready` only means the five shape categories are recorded for
local evaluation; install, import, external harness execution, provider launch,
remote execution, and external agent activation remain denied.

Activation readiness now depends on that matrix. If any recognized general-agent
claim is still `unmapped_evidence_only`, the harness reports
`failure_mode: unmapped_agent_claims` and
`activation_gate.decision: map_agent_claims_before_activation`. The bounded
documentation, test, or code_patch lanes remain visible for local work, but each
activation lane stays blocked with `runtime_action: none` until a later pass
either maps the claim to a local validation command or records it as evidence
that should not drive activation.

The blocked state now includes `claim_remediation_plan`. This operator-facing
panel turns each unmapped general-agent claim into a bounded local follow-up
row, currently preferring documentation or test work before code patches. The
plan repeats the activation blocker, required local replay command, and denied
runtime/external actions. For Omnigent-style meta-harness evidence, this means
generic movement can request local claim mapping, but it still cannot activate
an upstream agent, run an external harness, launch a provider, perform remote
execution, or export raw claim bodies.

The `agent_harness_eval_lane` replay also emits `activation_review`, a compact
operator-facing gate over the same evidence. It reports bounded activation lane
count, mapped and unmapped claim counts, project-intake probe status, weak or
generic evidence review need, safety-review note count, and the local validation
command required before promotion. A generic harness-eval record can remain
ready when it has no general-agent behavior claims to adopt; Omnigent-style
meta-harness claims must be mapped to local controller invariants first, and any
unmapped claim keeps local eval activation blocked. The review panel does not
grant external agent activation, external harness execution, provider launch,
remote execution, raw source URL export, raw evidence-body export, raw
claim-body export, or upstream body export.

Source digest `github-growth-20260627T174729.898501Z` starts a new pass-1
skill-route-discovery window over COMPASS Skills, zhengxi-views, Three.js Game
Skills, and Qwen-AgentWorld. The local harness now emits
`pass1_route_registry_handoff`, an operator-visible registry handoff derived
from the existing active pass-1 evidence lane and validation matrix. It reports
one bounded skill-route row per selected registry candidate, one profile row per
generic, game/frontend, or state-handoff route profile, and an adjacent
`agent_harness_eval_required` row for Qwen-AgentWorld-style general-agent
evidence. The handoff preserves only selected item IDs, route profiles, local
lane names, validation gates, and source hashes. It does not export raw GitHub
URLs or upstream bodies, and it denies runtime action, upstream skill
activation, external agent activation, external harness execution, provider
launch, and remote execution.

Source digest `github-growth-20260627T214729.514933Z` keeps the active pass-1
window on the same skill-route-discovery slice and adds
`active_window_route_lane_matrix`. This matrix maps active proposal IDs into one
row per bounded route: source-cited or generic skill repositories, game/frontend
skill repositories, and skill-ecosystem handoff repositories stay in
`skill_route_discovery` with only documentation, config, test, or code_patch as
local lanes. General-agent benchmark evidence such as Qwen-AgentWorld stays in
`agent_harness_eval_required` with documentation, test, or code_patch eval
lanes and `skill_route_discovery_inherited: false`. The matrix is body-free and
may expose proposal IDs, selected digest item IDs, source hashes, route profiles,
validation gates, and replay commands; it must not export raw source URLs,
upstream README bodies, provider inputs, target path bodies, or execution
requests. Trend summaries are non-adoption evidence: they can open a bounded
local validation lane, but they do not install, enable, run, or promote upstream
skill or agent code.

Source digest `github-growth-20260627T230729.530583Z` keeps pass 1 focused on
operator-visible activation candidates for the same bounded lane set. The
derived `active_window_activation_candidate_lane` summarizes the route matrix as
supervisor replay rows: generic/source-cited skill workflow evidence such as
zhengxi-views can become a documentation or test replay candidate, Three.js game
skill evidence can become a local test/code_patch candidate only after frontend
validation, and COMPASS-style state handoff evidence can become a config
candidate without profile or memory writes. Adjacent agent-harness evidence such
as Qwen-AgentWorld remains a blocked adjacent-eval row until the local
`agent_harness_eval_lane` is replayed. The activation candidate lane exports
proposal IDs, selected item IDs, route profiles, source hashes, validation
commands, and blockers; it does not export raw repository URLs, upstream bodies,
target paths, provider payloads, or execution requests.

Source digest `github-growth-20260627T232729.533390Z` advances pass 2 of the
same skill-route-discovery slice with active proposals
`p1-skill-route-discovery-generic`,
`p2-skill-route-discovery-game-frontend-profile`, and
`p3-skill-ecosystem-state-handoff`. The lane map now emits
`current_window_pass2_focused_review`, an operator-facing replay surface for
the focused-evidence-review gate. It maps zhengxi-views-style generic or
source-cited skill workflow evidence to a local test lane, Three.js game
frontend skill evidence to a local documentation lane, and COMPASS-style skill
ecosystem handoff evidence to a local test lane. The surface records selected
item IDs and hashes candidate sources and evidence URLs; it does not export raw
source URLs, raw evidence URLs, raw target paths, upstream bodies, install
requests, runtime action, external skill or agent activation, external harness
execution, provider launch, remote execution, profile writes, or memory writes.

Source digest `github-growth-20260627T234729.527065Z` advances pass 3 of the
same active proposal set by adding `pass3_active_proposal_acceptance_lane`.
This operator-visible surface binds generic skill workflow evidence to the
local `test` lane, game/frontend skill workflow evidence to the local
`documentation` lane, and skill ecosystem state handoff evidence to the local
`config` lane. The packet is an acceptance checkpoint for supervisor replay,
not activation authority: it requires selected item IDs or frozen fixtures,
body-free summaries, rollback evidence, focused local validation, and a review
note before pass-4 continuation. It hashes candidate sources and replay
commands, exports no raw GitHub URLs, raw evidence URLs, raw target paths,
commands, or upstream bodies, and keeps runtime action, external skill
activation, external harness execution, provider launch, remote execution,
profile writes, and memory writes denied.

Source digest `github-growth-20260628T000729.525285Z` completes pass 4 for the
active proposal IDs `p1-skill-route-discovery-generic`,
`p2-game-skill-workflow-profile`, and
`p3-skill-ecosystem-state-handoff`. The `active_pass4_completion_matrix` now
uses those proposal IDs directly, treats zhengxi-views-style generic skill
evidence and its stricter source-cited variant as the same bounded generic
route for completion, maps Three.js game skill evidence to the documentation
lane, and maps COMPASS-style state handoff evidence to the config lane. The
matrix remains a supervisor replay surface only: it reports selected item IDs,
route profiles, lane names, source hashes, replay-command hashes, validation
targets, and blockers. It does not export raw source URLs, raw evidence URLs,
raw target paths, replay commands, upstream bodies, install or provider lanes,
runtime action, external skill or agent activation, external harness execution,
provider launch, remote execution, profile writes, or memory writes.

Source digest `github-growth-20260628T002729.501775Z` starts the next pass-1
skill-route-discovery window with active proposals
`p1-skill-route-discovery-index`,
`p2-skill-route-discovery-test-fixtures`,
`p3-game-frontend-skill-profile`,
`p4-skill-ecosystem-state-handoff-profile`, and
`p5-agent-project-harness-eval-doc`. The lane map now emits
`current_pass1_route_discovery_index`, which binds the first four skill-route
proposals to documentation, test, documentation, and config lanes respectively.
COMPASS-style state handoff, zhengxi-views-style source-cited skill evidence,
and Three.js game/frontend skill evidence remain bounded to documentation,
config, test, or code_patch and require local validation before any later
activation. Qwen-AgentWorld-style general-agent evidence is recorded only as an
adjacent `agent_harness_eval_required` row for the fifth proposal; it does not
inherit `skill_route_discovery`, direct runtime authority, direct code_patch
authority, provider launch, external harness execution, or upstream activation.
The packet exposes selected item IDs and source hashes only, not raw source
URLs, evidence URLs, target paths, replay commands, or upstream bodies.

Source digest `github-growth-20260628T004729.566895Z` advances the same slice
to pass 2 with `current_window_pass2_route_lane_matrix`. The matrix keeps the
active skill-route proposals `p1-skill-route-discovery-index`,
`p2-skill-route-discovery-test-fixtures`, `p3-game-frontend-skill-profile`, and
`p4-skill-ecosystem-state-handoff-profile` as bounded local lanes while
recording `p5-agent-project-harness-eval-doc` as an adjacent
`agent_harness_eval_required` route. Nested `route_classification` metadata may
carry route hints, route profiles, and requested local lanes, but the
interpreter/controller boundary preserves only body-free metadata: selected item
IDs or frozen fixtures, route class, profile names, allowed documentation,
config, test, and code_patch lanes, validation gates, source hashes, and the
local-validation requirement. Unsupported install, provider_runtime, and
runtime_execution pressure is downgraded out of activation lanes. The matrix
does not export raw source URLs, raw evidence URLs, raw target paths, replay
command bodies, or upstream bodies, and it denies runtime action, external
skill or agent activation, external harness execution, provider launch, profile
writes, memory writes, and remote execution.

Source digest `github-growth-20260628T010729.693724Z` advances the window to
pass 3 with `current_window_pass3_validation_cases`. The packet turns the
active proposal set into operator-visible local validation cases:
`p1-skill-route-discovery-index` selects a documentation lane over the bounded
skill-route index, `p2-skill-route-discovery-test-fixtures` selects a test lane
for fixture replay, `p3-game-frontend-skill-profile` selects a documentation
lane for Three.js/browser-game workflow validation gates, and
`p4-skill-ecosystem-state-handoff-profile` selects a config lane for
COMPASS-style state handoff metadata. The packet keeps Qwen-AgentWorld-style
general-agent evidence in adjacent `agent_harness_eval_required` review under
`p5-agent-project-harness-eval-doc`; it does not inherit `skill_route_discovery`
or direct code patch/runtime authority. The pass-3 surface exposes selected
item IDs, route profiles, source hashes, validation gates, and replay-command
hashes only. Unsupported install, provider runtime, runtime execution, external
skill or agent activation, external harness execution, provider launch, profile
writes, memory writes, remote execution, raw source URL export, raw evidence URL
export, raw target path export, replay command export, and upstream body export
remain denied.

Source digest `github-growth-20260624T073355.748356Z` completes the
runner-harness-control pass for the carried FableCodex, COMPASS Skills, and
Three.js Game Skills route window. The pass-4 completion report now includes
`runner_harness_control_plane`, an operator-visible five-stage packet covering
intake, mid-flight state, recovery, replay, and report readiness. It derives
from existing body-free completion gates: current-window evidence coverage,
final slice closure, route validation lane queue, activation handoff, replay
checklist, final route manifest, secondary harness bridge, and consistency
guard. The packet hashes replay commands and artifact labels, records no raw
repository URLs, paths, command bodies, or upstream content, and keeps runtime
action, upstream skill activation, external harness execution, provider launch,
remote execution, profile writes, and memory writes denied. Its purpose is to
make the completed skill-route workflow replayable by a supervisor without
turning public skill repositories into executable local routes.

Source digest `github-growth-20260624T043356.363880Z` rechecked Omnigent as a
general-agent/meta-harness signal. The reusable lesson is not to adopt its
runner behavior, but to make harness-specific assumptions visible before local
activation: Omnigent's public PR review around per-turn ACP token accounting
distinguishes stream-specific behavior from another harness's accounting path
and treats local tests/e2e evidence as the gate. Locally, the
`agent_harness_eval_lane` replay now emits
`general_agent_route_review_queue`. The queue turns each mapped or unmapped
general-agent claim into a bounded local review row with a selected
documentation or test lane, required validation command, activation blockers,
and denied runtime/external actions. Unmapped claims such as local data
grounding remain blocked until a future pass maps them to a local validation
contract or records them as evidence-only; mapped Omnigent-style claims still
do not authorize upstream harness execution, provider launch, remote execution,
raw source URL export, or upstream body export.

## Evidence Citation And Uncertainty

When `skill_route_discovery` appears in a frozen proposal evidence package,
proposal examples and replay fixtures must cite only selected `item_id` values
in `evidence_refs`. They must not cite repository URLs, owner/repository names,
truncated item IDs, or evidence URLs invented by the candidate. The deterministic
review layer derives accepted evidence URLs from those frozen `item_id` values.

Focused replay checks for this route should assert both halves of the contract:
accepted candidates use only documentation, config, test, or code_patch lanes,
and every accepted `evidence_ref` is a selected `item_id` from the frozen
evidence package. URL strings such as `https://github.com/baskduf/FableCodex`
are valid source evidence in the package, but they are not valid proposal
citations.

Trend-only repository details are enough to select a bounded local lane, but not
enough to claim upstream implementation parity. When the selected evidence is
generic, README-level, sparse, or context-budget truncation reports
`missing_detail_risk`, proposal uncertainty must mention that missing detail
risk and narrow the claim to local validation.

Example accepted citation shape:

```json
{
  "proposal_id": "skill-route-doc-contract",
  "kind": "documentation",
  "evidence_refs": ["fablecodex-codex-skill-workflow"],
  "uncertainty": "Repository-level trend evidence leaves missing_detail_risk for specific upstream implementation details."
}
```

Example rejected citation shape:

```json
{
  "proposal_id": "skill-route-url-citation",
  "kind": "documentation",
  "evidence_refs": ["https://github.com/baskduf/FableCodex"],
  "uncertainty": "This cites a URL instead of a frozen item_id."
}
```

## Current Window Pass 4 Replay Gate

Source digest `github-growth-20260628T012729.510462Z` completes the current
skill-route-discovery slice with `current_window_pass4_supervisor_replay_gate`.
The gate binds active proposals `p1-skill-route-discovery-fixtures`,
`p2-skill-route-discovery-docs`, and `p3-agent-harness-eval-tests` to an
operator-visible replay contract.

COMPASS-style state handoff, zhengxi-views source-cited skill workflow, and
Three.js game skill evidence remain `skill_route_discovery` records with only
documentation, config, test, or code_patch lanes. The selected pass-4 lanes are
test and documentation; local validation remains required before any supervisor
promotion. Qwen-AgentWorld-style general-agent evidence is not promoted into a
direct implementation lane. It stays in `agent_harness_eval_required` with no
direct allowed lanes before a local agent-harness eval route establishes whether
documentation, test, or code_patch work is justified.

The replay gate exports selected item IDs, source hashes, route profiles,
bounded lane names, validation gates, and replay-command hashes only. It keeps
runtime action, external skill activation, external agent activation, external
harness execution, provider launch, remote execution, profile writes, memory
writes, raw evidence URLs, raw source URLs, target paths, replay commands, and
upstream bodies out of the pass-4 handoff.

## Current Window Pass 1 Discovery Intake

Source digest `github-growth-20260628T014729.582985Z` starts the next
skill-route-discovery pass with `current_window_pass1_discovery_intake_lane`.
The lane maps the active proposal IDs `p1-skill-route-discovery-catalog`,
`p2-skill-profile-routing-tests`, `p4-game-frontend-skill-eval-fixture`, and
`p5-skill-ecosystem-handoff-note` to bounded local skill-route work.

The focused evidence keeps the same route boundary. COMPASS-style skill
ecosystem evidence is a `skill_ecosystem_state_handoff` signal and may open
documentation, config, test, or code_patch lanes, but profile and memory writes
remain denied. zhengxi-views-style source-cited skill evidence is treated as
`source_cited_domain_research`; it can drive local citation/advice-boundary
validation, not provider launch or advice generation. Three.js game skill
evidence is `game_frontend_workflow`; it can drive local documentation or test
fixtures before any frontend code patch. Qwen-AgentWorld-style general-agent
evidence remains adjacent `agent_harness_eval_required`; it does not inherit
`skill_route_discovery`, direct runtime authority, or direct code_patch
authority before the agent-harness eval lane is replayed.

The intake lane exports proposal IDs, selected item IDs, route profiles, source
hashes, selected bounded lanes, validation gates, and replay-command hashes
only. It does not export raw source URLs, evidence URLs, target paths, replay
commands, upstream bodies, install requests, runtime action, external skill or
agent activation, external harness execution, provider launch, profile writes,
memory writes, or remote execution.

## Active Pass 1 Proposal Replay Lane

Source digest `github-growth-20260628T030729.514321Z` opens another pass-1
skill-route-discovery window with `active_pass1_proposal_replay_lane`. The lane
binds the active proposal IDs `p1-skill-route-discovery-docs-and-probe`,
`p2-skill-route-discovery-test-fixtures`, and
`p3-game-frontend-skill-profile-discovery` to operator-visible local replay
rows before any activation.

`p1-skill-route-discovery-docs-and-probe` selects the documentation lane and
must map current skill-route evidence into the documentation, config, test, and
code_patch lane boundary without adding new external URLs. `p2-skill-route-discovery-test-fixtures`
selects the test lane and must keep `skill_workflow` items with
`skill_route_discovery` hints inside those bounded lanes. `p3-game-frontend-skill-profile-discovery`
selects a documentation lane for the `game_frontend_workflow` profile and
records the validation concerns expected before activation: runnable examples,
visual assets, frontend testability, and local test or frontend validation.

The replay lane exports proposal IDs, selected digest item IDs, route profiles,
source hashes, selected local lanes, validation gates, and expected validation
concerns only. It keeps Qwen-AgentWorld-style general-agent evidence adjacent as
`agent_harness_eval_required` with no inherited `skill_route_discovery`,
runtime action, external skill or agent activation, external harness execution,
provider launch, profile writes, memory writes, remote execution, raw source
URLs, evidence URLs, target paths, or upstream bodies.

The same harness output now emits `active_pass1_activation_gate`, a compact
supervisor review packet derived from `active_pass1_proposal_replay_lane` and
`current_digest_pass1_validation_lane`. The gate is ready only when every
pass-1 skill-route row selects one of documentation, config, test, or
code_patch; adjacent general-agent rows remain behind `agent_harness_eval_required`;
and runtime action, provider launch, external skill or agent activation,
external harness execution, remote execution, raw source URLs, evidence URLs,
target paths, and upstream bodies remain disabled. The gate does not activate
anything itself; it records `external_supervisor_after_validation` as the
activation authority.

## Current Run Pass 2 Local Validation Lane

Source digest `github-growth-20260707T100834.719723Z` advances pass 2 with
`current_run_pass2_local_validation_lane`. The lane binds the current proposal
set to one operator-visible replay packet:
`p1-skill-route-discovery-reverse-flow` covers reverse-flow-skill style Codex
workflow-gate evidence and selects the local test lane, while
`p2-skill-route-discovery-rnskill` covers rnskill-style generic skill workflow
evidence and selects the documentation lane. Each skill row remains a local
validation candidate only and may use documentation, config, test, or
code_patch lanes after `skill_route_discovery` validation.

`p3-agent-harness-eval-shepherd` is recorded as an adjacent
`agent_harness_eval_required` row for Shepherd-style runtime substrate evidence.
General-agent project evidence without skill workflow signals does not inherit
`skill_route_discovery`, direct code_patch authority, runtime authority,
provider launch, external harness execution, or upstream agent activation. It
must first pass a local agent-harness evaluation lane before it can influence
implementation-oriented work.

The pass-2 packet exports selected item IDs, route profiles, source hashes,
validation gates, and replay-command hashes only. It does not export raw source
URLs, raw evidence URLs, target paths, replay commands, upstream bodies,
install requests, runtime action, external skill or agent activation, external
harness execution, provider launch, profile writes, memory writes, or remote
execution.

## Current Run Pass 3 Validation Lane

Source digest `github-growth-20260628T022729.498868Z` advances the active
skill-route-discovery slice to pass 3 with `current_run_pass3_validation_lane`.
The lane converts the current proposal set into an operator-visible validation
packet: `proposal_skill_route_discovery_catalog_001` selects a local test lane
for representative external skill-style metadata, and
`proposal_skill_profile_documentation_002` selects a documentation lane for
generic/source-cited skill workflows, Three.js game/frontend workflows, and
COMPASS-style state handoff profiles.

Qwen-AgentWorld-style general-agent project evidence is recorded only under
`proposal_agent_harness_eval_003` as `agent_harness_eval_required`. It does not
inherit `skill_route_discovery`, direct code_patch authority, runtime authority,
external harness execution, provider launch, remote execution, or upstream
agent activation before a local agent-harness eval route is replayed.

The pass-3 packet exports selected item IDs, route profiles, source hashes,
bounded lane names, validation gates, and replay-command hashes only. Unsupported
install, provider_runtime, and runtime_execution pressure is removed from local
proposal lanes. Raw source URLs, raw evidence URLs, target paths, replay
commands, upstream bodies, profile writes, and memory writes remain outside the
handoff.

## Current Run Pass 4 Completion Lane

Source digest `github-growth-20260628T024729.609046Z` completes the planned
pass-4 skill-route-discovery window with `current_run_pass4_completion_lane`.
The completion lane binds `proposal-skill-route-discovery-001` to the local
test lane, `proposal-skill-route-docs-002` to the local documentation lane, and
keeps `proposal-agent-harness-eval-003` in adjacent `agent_harness_eval_required`
until the local agent-harness evaluation route is replayed.

Skill-route rows may expose only documentation, config, test, or code_patch as
local lanes and must carry selected digest item IDs or frozen fixture evidence,
body-free summaries, rollback evidence, focused local validation, and a review
note. Qwen-AgentWorld-style general-agent evidence does not inherit
`skill_route_discovery`, direct code_patch authority, runtime authority,
external harness execution, provider launch, remote execution, or upstream agent
activation before that eval route is established.

## Active Window Pass 2 Validation Lane

Source digest `github-growth-20260628T072729.647518Z` advances the active
pass-2 skill-route-discovery window with `active_window_pass2_validation_lane`.
The lane maps `p1-skill-route-discovery-generic` to a local test lane for
generic, source-cited, and COMPASS-style state-handoff skill workflow evidence,
maps `p2-game-skill-profile` to a local documentation lane for
`game_frontend_workflow`, and keeps `p3-agent-harness-eval` as adjacent
`agent_harness_eval_required` evidence when the repository is a general-agent
project without skill workflow route hints.

This surface is a local validation route, not activation authority. Skill rows
may expose only documentation, config, test, or code_patch as bounded lanes.
The adjacent general-agent row may expose only documentation, test, or
code_patch as evaluation lanes after the agent-harness eval route is replayed.
Runtime action, upstream skill or agent activation, external harness execution,
provider launch, profile writes, memory writes, remote execution, raw source
URLs, raw evidence URLs, target paths, and upstream bodies remain denied.

## Active Pass 3 Activation Candidate Lane

Source digest `github-growth-20260628T034729.532203Z` advances the active
skill-route-discovery window to pass 3 with
`active_pass3_activation_candidate_lane`. The lane binds
`proposal-skill-route-discovery-aggregate-001` to a local test lane for
representative external skill-style repository metadata,
`proposal-game-frontend-skill-profile-002` to a documentation lane for
Three.js/browser-game workflow interpretation, and
`proposal-skill-state-handoff-003` to a config lane for COMPASS-style handoff
metadata.

This surface is an activation-candidate review packet, not activation
authority. Skill rows may expose only documentation, config, test, or
code_patch lanes after local validation. Public repository names, popularity,
fork lineage, or game/frontend terminology do not add install, provider
runtime, runtime execution, external harness execution, profile writes, memory
writes, or upstream skill activation. Qwen-AgentWorld-style general-agent
evidence remains adjacent as `agent_harness_eval_required` and cannot inherit
`skill_route_discovery` until a separate local harness-eval route is replayed.

The packet exports proposal IDs, selected item IDs, route profiles, source
hashes, bounded lane names, validation gates, and replay-command hashes only.
It does not export raw source URLs, raw evidence URLs, target paths, replay
commands, upstream bodies, secrets, imported state, or runtime permissions.

## Current Pass 4 Local Probe

Source digest `github-growth-20260628T040729.561092Z` completes the planned
skill-route-discovery slice with
`skill_route_discovery_current_pass4_local_probe`. The probe maps
`p1-skill-route-discovery-zhengxi-views` to the
`source_cited_domain_research` test lane and
`p3-game-skill-route-threejs` to the `game_frontend_workflow` test lane. Both
rows carry local artifact proofs, selected proposal IDs, source hashes, and
validation commands only.

`p2-agent-harness-qwen-agentworld` stays adjacent as
`agent_harness_eval_required`. It can be represented as documentation, test, or
code_patch evaluation evidence after the local harness-eval route is replayed,
but it does not inherit `skill_route_discovery`, runtime authority, provider
launch, external harness execution, remote execution, upstream agent activation,
or external skill activation.

The pass-4 probe exports no raw source URLs, evidence URLs, target paths,
replay-command bodies, or upstream bodies. It is an operator-visible completion
handoff for bounded local validation, not an install, execution, restart,
promotion, or external activation request.

## Focused Pass 2 Route Classification Lanes

Source digest `github-growth-20260628T044729.594506Z` advances a new pass-2
window over COMPASS Skills, zhengxi-views, and Three.js Game Skills evidence.
The local harness fixture
`skill_route_discovery_pass2_focused_route_classification_lanes.json` treats
nested `route_classification` metadata as compact route evidence only:
`generic_skill_workflow`, `skill_ecosystem_state_handoff`, and
`game_frontend_workflow` profiles are preserved, while lanes remain bounded to
documentation, config, test, and code_patch.

Unsupported pressure such as provider runtime, install, and runtime execution
does not become an activation lane. The pass-2 handoff may expose selected item
IDs, profile names, source hashes, bounded local lanes, validation gates, and
the next-pass handoff. It must not export raw source URLs, raw evidence URLs,
target paths, replay-command bodies, upstream bodies, or grant runtime action,
external skill activation, external harness execution, provider launch, profile
writes, memory writes, remote execution, install, or scaffold execution.

## Focused Pass 3 Profile Proof Checklist

Source digest `github-growth-20260628T050729.790102Z` advances pass 3 of the
same skill-route-discovery slice by making each operator-visible validation row
carry `profile_validation_requirements`. These requirements are derived from
the local route-profile contracts, not from upstream skill bodies. They state
what local validation must prove before activation:

- `generic_skill_workflow` must prove frozen digest or fixture evidence
  classifies a skill workflow without upstream activation.
- `source_cited_domain_research` must prove citation traceability and advice
  boundaries before any domain skill activation.
- `game_frontend_workflow` must prove local frontend or test validation covers a
  runnable game workflow and asset/provider boundaries.
- `skill_ecosystem_state_handoff` must prove state handoff metadata remains
  local config without profile or memory writes.

The active pass keeps the same bounded lane boundary: skill-route evidence may
select only documentation, config, test, or code_patch lanes, and every selected
lane keeps `local_validation_required: true`. COMPASS-style state handoff,
zhengxi-views-style source-cited skill workflow, and Three.js browser-game skill
evidence remain local validation candidates only. General-agent projects without
skill workflow signals remain adjacent `agent_harness_eval_required` evidence
and do not inherit `skill_route_discovery`, direct code_patch authority, runtime
action, provider launch, external harness execution, remote execution, or
upstream agent activation.

## Current Pass 3 Discovery Validation Packet

Source digest `github-growth-20260628T130729.680353Z` adds
`skill_route_discovery_current_active_pass3_discovery_validation_packet` for
the active zhengxi-views, Qwen-AgentWorld, and Three.js Game Skills window. The
packet keeps zhengxi-views in the `source_cited_domain_research` test lane and
Three.js Game Skills in the `game_frontend_workflow` test lane. Both rows may
lead only to docs, config, tests, or code_patch work after local validation.

Qwen-AgentWorld is deliberately represented as adjacent
`agent_harness_eval_required` evidence, not as skill-route evidence. It can
queue docs, tests, or code_patch outputs only after the local agent-harness eval
route is established. The packet exports candidate names, selected item IDs,
route profiles, validation targets, source hashes, and replay-command hashes;
it does not export raw source URLs, raw evidence URLs, target paths, replay
commands, upstream bodies, provider config, runtime authority, external harness
execution, remote execution, or upstream activation.

## Current Pass 4 Completion Lane

Source digest `github-growth-20260628T120729.553038Z` completes the current
skill-route-discovery window by adding
`skill_route_discovery_current_pass_completion_lane` inside the existing
rollback-aware `completion_workflow`. The lane is keyed to the active proposal
IDs `p1-skill-route-discovery-general`,
`p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff`.

The completion lane converts the current evidence into bounded local replay
work only: generic or source-cited skill workflow evidence selects a local test
lane, Three.js/browser-game skill evidence selects a documentation lane for
non-network game frontend workflow acceptance criteria, and COMPASS-style state
handoff evidence selects a config lane for metadata-only validation. Each row
now carries an operator replay step and a local pytest replay command for the
selected bounded lane, while the top-level replay bundle groups those commands
by proposal ID. Each row requires selected digest item IDs or a frozen fixture,
body-free repository summary evidence, rollback ref and artifact evidence,
focused local validation, changed-file review, and a review note.

This surface is not an activation grant. It exports proposal IDs, route
profiles, source hashes, selected item IDs, bounded lane names, validation
gates, validation task names, and local validation replay commands only.
Runtime action, upstream skill
activation, upstream agent activation, external harness execution, provider
launch, profile writes, memory writes, remote execution, raw source URLs, raw
evidence URLs, raw target paths, and upstream bodies remain denied.

## Current Run Pass 1 Activation Readiness

Source digest `github-growth-20260628T070730.472651Z` adds
`current_run_pass1_activation_readiness` for the active pass-1
`skill-route-discovery` window. The panel binds the carried proposal IDs
`proposal-skill-route-discovery-generic-001`,
`proposal-game-skill-route-profile-002`, and
`proposal-skill-ecosystem-handoff-003` to route profiles and selected local
lanes before any activation handoff.

The current readiness split is deliberately local: zhengxi-views-style
source-cited skill workflow evidence selects the test lane, Three.js game skill
director evidence selects the documentation lane until frontend validation
exists, and COMPASS-style skill ecosystem handoff evidence selects the config
lane for metadata-only state/profile boundaries. Each row must carry selected
item IDs or frozen fixture evidence, source hashes, bounded lane names, and a
profile validation gate.

The panel is not a skill, agent, harness, provider, profile, memory, or remote
activation grant. Runtime action, upstream skill activation, external harness
execution, provider launch, profile writes, memory writes, raw source URLs, raw
evidence URLs, target paths, and upstream bodies remain outside the exported
operator surface.

## Current Active Pass 2 Skill Route Matrix

Source digest `github-growth-20260628T060729.568458Z` advances pass 2 of the
active `skill-route-discovery` slice with
`current_active_pass2_skill_route_validation_matrix`. The matrix binds the
active proposals `p1-skill-route-discovery-general`,
`p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff` to one operator-visible local validation
surface before activation.

The matrix treats zhengxi-views-style generic or source-cited skill workflow
evidence as a local test lane, Three.js game/frontend skill evidence as a local
test lane that must prove no runtime action is emitted before validation, and
COMPASS-style skill ecosystem handoff evidence as a local config lane for
metadata-only state handoff interpretation. Each row may expose only
documentation, config, test, or code_patch as local lanes and must carry
selected item IDs or frozen fixture evidence plus route-profile validation
gates.

Unsupported install, provider runtime, runtime execution, external harness
execution, upstream skill activation, provider launch, profile writes, memory
writes, remote execution, raw source URLs, raw evidence URLs, target paths,
replay-command bodies, and upstream bodies remain outside the handoff.

## Current Run Pass 2 Batch Validation Lane

Source digest `github-growth-20260628T084729.600885Z` advances pass 2 with
`skill_route_discovery_current_pass2_validation_lane` exposed directly from the
local harness output. The lane binds `p1-skill-route-discovery-batch` to the
three required skill-route profiles for this wake:
`generic_skill_workflow`, `game_frontend_workflow`, and
`skill_ecosystem_state_handoff`. Pass-2 readiness now requires all three
profiles to be present before the packet can report `ready`.

Qwen-AgentWorld-style benchmark evidence and Looper-style loop-control
evidence are carried as adjacent `agent_harness_eval_required` rows only. They
may use documentation, test, or code_patch evaluation lanes after the local
harness-eval route is replayed, but they do not inherit `skill_route_discovery`,
runtime authority, direct controller changes, provider launch, external harness
execution, remote execution, or upstream agent activation.

The packet exports selected item IDs, route profiles, source hashes, bounded
lane names, validation gates, and eval-only adjacent rows. It does not export
raw source URLs, raw evidence URLs, local target paths, replay-command bodies,
upstream bodies, profile writes, memory writes, install requests, or runtime
actions.

The same lane now includes
`proposal_acceptance_contract`, an active pass-2 proposal surface for
`p1-skill-route-discovery-zviews`,
`p2-skill-route-discovery-game-frontend`, and
`p3-skill-ecosystem-state-handoff`. The contract records each proposal's
selected bounded lane, route profile, validation gates, and denial gates for
runtime action, upstream skill activation, external harness execution, provider
launch, remote execution, raw URLs, raw replay commands, target paths, and
upstream bodies. Adjacent Qwen-AgentWorld or Looper-style evidence remains in
`agent_harness_eval_required` rows and cannot inherit skill-route authority.

## Current Active Pass 3 Local Activation Proof

Source digest `github-growth-20260628T062729.695489Z` advances pass 3 of the
same active slice with `current_active_pass3_local_activation_proof_lane`. The
lane reuses the pass-2 matrix proposal IDs:
`p1-skill-route-discovery-general`, `p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff`.

The pass-3 surface is an operator-visible proof checklist before pass-4
handoff, not an activation grant. Generic or source-cited skill workflow
evidence must carry a focused local test or fixture proving classification
without runtime permission. Three.js game/frontend workflow evidence must carry
a frontend validation boundary test or profile note before any scaffold,
provider, asset, or runtime path can be considered. COMPASS-style state handoff
evidence must carry a metadata-only config check proving profile and memory
writes remain denied.

Rows export proposal IDs, selected digest item IDs, source hashes, bounded lane
names, validation gates, proof artifact names, and profile validation
requirements only. Runtime action, upstream skill or agent activation, external
harness execution, provider launch, profile writes, memory writes, remote
execution, raw source URLs, raw evidence URLs, target paths, replay-command
bodies, and upstream bodies remain denied.

## Current Pass 4 Route Discovery Validation Fix

Source digest `github-growth-20260628T064730.025611Z` completes the planned
pass-4 `skill-route-discovery` window with
`current_pass4_route_discovery_validation_fix`. The packet keeps the three
current proposals separate for operator replay:
`p1-skill-route-discovery-index` validates generic or source-cited skill
workflow evidence through the local test lane,
`p2-game-frontend-skill-doc-lane` documents the game/frontend workflow lane,
and `p3-skill-ecosystem-handoff-config` validates COMPASS-style state handoff
metadata through the local config lane.

Game/frontend skill candidates may enter documentation, config, test, or
code_patch lanes only after local validation covers assets, UI behavior,
frontend testability, and provider or scaffold boundaries. Skill ecosystem
state handoff candidates may enter the same bounded lanes only as local
metadata or validation work; profile writes and memory writes remain denied
until a separate privacy and state boundary is validated. Generic or
source-cited skill workflow evidence stays body-free and must cite selected
digest item IDs or frozen fixture evidence rather than raw repository URLs.

The pass-4 validation-fix packet exports proposal IDs, route profiles, selected
item IDs, source hashes, bounded lane names, validation gates, and replay-command
hashes only. Unsupported install, provider runtime, runtime execution, external
harness execution, upstream skill activation, provider launch, profile writes,
memory writes, remote execution, raw source URLs, raw evidence URLs, target
paths, replay-command bodies, and upstream bodies remain outside the handoff.

## Current Pass 3 Route Validation Lane

Source digest `github-growth-20260628T074730.300165Z` advances pass 3 of the
active `skill-route-discovery` slice with
`current_pass3_route_validation_lane`. The lane is derived from the existing
local activation-proof surface and rekeys the current proposal IDs:
`p1-skill-route-discovery-generic`, `p2-threejs-game-skill-routing`, and
`p3-skill-ecosystem-state-handoff`.

The generic skill workflow row validates that agent/skill repository metadata
maps only to documentation, config, test, or code_patch work. The Three.js game
skill row selects the local test lane for `game_frontend_workflow` and keeps
runtime execution, scaffold execution, provider launch, asset generation, and
external skill activation denied until local frontend or test validation exists.
The skill ecosystem state handoff row records the expected input/output
boundary: inputs are profile or state-handoff metadata, privacy boundary notes,
and selected digest item IDs or frozen fixture evidence; outputs are metadata-
only config or documentation lanes plus explicit profile-write and memory-write
denial.

This pass-3 lane is an operator replay surface, not activation authority. It
exports proposal IDs, selected item IDs, route profiles, source hashes, bounded
lane names, validation gates, validation tasks, and body-free IO contracts only.
Runtime action, upstream skill activation, external harness execution, provider
launch, profile writes, memory writes, remote execution, raw source URLs, raw
evidence URLs, target paths, replay-command bodies, and upstream bodies remain
outside the handoff.

## Active Pass 3 Acceptance Gates

Source digest `github-growth-20260628T090729.682480Z` continues pass 3 by
making `pass3_active_proposal_acceptance_lane` expose an explicit local
acceptance contract for the active proposals
`p1-skill-route-discovery-generic`,
`p2-game-frontend-skill-workflow`, and
`p3-skill-ecosystem-state-handoff`.

Each row now reports body-free acceptance gates for bounded lane membership,
selected evidence presence, validation gate presence, local validation, denied
runtime action, denied external skill or harness execution, denied provider
runtime launch, denied remote execution, and omission of raw source, evidence,
target path, upstream body, and replay-command content. Failed gates become row
activation blockers before final-pass handoff.

This preserves the current interpretation of COMPASS Skills, zhengxi-views,
and Three.js Game Skills as local validation candidates only. Qwen-AgentWorld
or Looper-style general-agent evidence without skill workflow signals remains
outside this route and must continue through an `agent_harness_eval_required`
lane before it can influence implementation work.

## Active Pass 4 Operator Activation Packet

Source digest `github-growth-20260628T092729.663882Z` completes the current
`skill-route-discovery` window by adding
`active_pass4_operator_activation_packet` to the proposal lane map. The packet
is derived from `active_pass4_completion_matrix`; it does not accept separate
upstream evidence or add new lane names.

The packet gives supervisors one operator-visible closure decision for
`p1-skill-route-discovery-generic`, `p2-game-skill-workflow-profile`, and
`p3-skill-ecosystem-state-handoff`. It reports proposal IDs, selected bounded
lanes, covered route profiles, selected evidence item IDs, replay-command
hashes, rollback requirements, and replay requirements. Documentation, config,
test, and code_patch remain the only local lanes, with
`local_validation_required: true`.

Runtime execution, installation, provider launch, external skill activation,
external harness execution, profile writes, memory writes, remote execution,
raw source URLs, raw evidence URLs, target paths, replay-command bodies, and
upstream bodies remain denied. A ready packet means the external supervisor may
replay the validated local lanes and record completion; it is not a kernel
restart or upstream skill activation path.

## Current Pass 1 Focused Proposal Aliases

Source digest `github-growth-20260628T094729.579910Z` starts the next pass-1
window over zhengxi-views, Three.js Game Skills, and COMPASS Skills. The local
validation cases now carry alias IDs for the active proposal names
`p1_skill_route_discovery_generic_views`, `p2_game_frontend_skill_profile`, and
`p3_skill_ecosystem_state_handoff` while preserving the existing stable case
IDs used by older fixtures.

The aliases are controller replay metadata only. They do not add lane names or
runtime authority. zhengxi-views remains a source-cited or generic skill
workflow validation case, Three.js Game Skills remains a game/frontend workflow
case, and COMPASS Skills remains a state-handoff config case. Each row may map
only to documentation, config, test, or code_patch lanes, requires local
validation before activation, and continues to deny install, provider runtime,
runtime execution, external skill activation, external harness execution,
profile writes, memory writes, remote execution, raw source URL export, raw
target path export, and upstream body export.

## Current Active Pass 2 Proposal Lane

Source digest `github-growth-20260628T100729.595957Z` advances the same
skill-route-discovery slice with `current_active_pass2_proposal_lane`. The lane
uses the active proposal aliases
`p1_skill_route_discovery_generic_views`,
`p2_game_frontend_skill_profile`, and
`p3_skill_ecosystem_state_handoff`, while preserving the hyphenated proposal
IDs carried by the focused evidence window.

The lane maps zhengxi-views-style source-cited skill workflow evidence to a
local test lane for citation and advice-boundary validation, Three.js
game/frontend skill evidence to a documentation lane for the game workflow
validation checklist, and COMPASS-style state handoff evidence to a config lane
for metadata-only handoff boundaries. Qwen-AgentWorld-style general-agent
evidence remains adjacent as `agent_harness_eval_required`; it does not inherit
skill-route lanes or implementation authority.

This pass-2 surface exports proposal IDs, aliases, selected item IDs, source
hashes, bounded lane names, validation gates, and replay-command hashes only.
Runtime action, install, upstream skill or agent activation, external harness
execution, provider launch, profile writes, memory writes, remote execution, raw
source URLs, raw evidence URLs, target paths, replay-command bodies, and
upstream bodies remain denied.

The same wake now emits `current_active_pass2_activation_contract` beside the
proposal lane. The contract is an operator-visible acceptance checklist for the
three active pass-2 profiles, derived from the sanitized proposal lane and the
skill-route validation matrix. It does not add evidence, lanes, commands, or
activation authority.

The contract binds `p1_skill_route_discovery_generic_views` to the local test
lane for generic or source-cited skill workflow evidence, binds
`p2_game_frontend_skill_profile` to a game/frontend acceptance gate requiring
local UI, render, or workflow validation before any behavior change, and binds
`p3_skill_ecosystem_state_handoff` to config metadata only. State, profile, and
memory writes stay denied for the handoff profile. Game scaffold, install,
provider launch, external skill activation, external harness execution, remote
execution, raw evidence URL export, raw upstream body export, and replay-command
body export remain denied for every row.

## Current Run Pass 3 Acceptance Lane

Source digest `github-growth-20260628T102729.741495Z` advances pass 3 by adding
`current_run_pass3_acceptance_lane` as an operator-visible gate derived from the
existing `current_run_pass3_validation_lane`. The new surface does not add
evidence or new local lanes. It checks that the current pass-3 validation rows
are ready, use only documentation, config, test, or code_patch lanes, carry
selected evidence and validation gates, require local validation, and deny
runtime action, upstream skill activation, external harness execution, provider
launch, remote execution, raw source URL export, raw evidence URL export, target
path export, upstream body export, and raw replay-command export.

Adjacent Qwen-AgentWorld-style general-agent evidence remains accepted only as
`agent_harness_eval_required`. It can queue documentation, test, or code_patch
evaluation work after local harness evaluation, but it does not inherit
`skill_route_discovery`, direct runtime authority, direct code_patch selection,
external agent activation, external harness execution, provider launch, or
remote execution.

## Current Window Pass 4 Route Completion Lane

Source digest `github-growth-20260628T104729.721650Z` completes the planned
skill-route-discovery slice with
`current_window_pass4_route_completion_lane`. The lane makes the active proposal
aliases operator-visible as separate rows:
`p1_skill_route_discovery_generic_views`,
`p2_game_frontend_skill_profile`, and
`p3_skill_ecosystem_state_handoff`.

The completion packet treats zhengxi-views-style generic or source-cited skill
workflow evidence as a local test lane, Three.js game/frontend skill evidence
as a local test lane, and COMPASS-style state handoff evidence as a local config
lane. Each row must carry selected digest item IDs or frozen fixture evidence,
profile validation gates, bounded local lanes, and a hashed replay command.

Discovery remains non-executing and non-activating. Documentation, config, test,
and code_patch are the only skill-route lanes. Adjacent Qwen-AgentWorld or
Looper-style general-agent evidence stays in `agent_harness_eval_required` and
does not inherit skill-route authority, direct code_patch selection, external
harness execution, provider launch, remote execution, profile writes, memory
writes, raw source URL export, raw target path export, raw replay command
export, or upstream body export.

## Current Window Pass 4 Activation Validation Manifest

Source digest `github-growth-20260628T132729.593996Z` completes the active
pass-4 window by carrying profile-specific validation proof rows into
`local_activation_targets`, `pass1_validation_matrix`, and
`next_validation_step`. The manifest keeps zhengxi-views-style generic or
source-cited skill evidence, Three.js game/frontend skill evidence, and
COMPASS-style state handoff evidence inside the same bounded local lanes:
documentation, config, test, or code_patch.

Each manifest row records the route profile, validation gate, proof expected
before activation, selected local lane, selected item IDs, and a hashed replay
command. It does not schedule runtime action and does not grant external skill
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
raw target path export, raw upstream body export, or raw replay command export.
Literal replay commands remain present only on the established local replay
surfaces for operator execution; the manifest itself is hash-only.

## Current Digest Pass 1 Validation Lane

Source digest `github-growth-20260628T134729.588648Z` starts the next pass-1
window with `current_digest_pass1_validation_lane`. The lane binds the active
proposal IDs `p1-skill-route-discovery-generic`,
`p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff` to the current digest's bounded local
validation work.

The lane keeps zhengxi-views-style generic or source-cited skill evidence in a
local test lane, Three.js game/frontend workflow evidence in a documentation
lane until local frontend fixture validation exists, and COMPASS-style state
handoff evidence in a config lane that records uncertainty instead of creating
memory or profile behavior. Each row exports selected digest item IDs, route
profiles, bounded lane names, validation gates, validation task text, source
hashes, and replay-command hashes only.

Adjacent Qwen-AgentWorld or Looper-style general-agent evidence is carried only
as `agent_harness_eval_required`. It does not inherit `skill_route_discovery`,
direct runtime authority, direct code_patch selection, provider launch,
external harness execution, remote execution, profile writes, memory writes,
raw source URL export, raw evidence URL export, raw target path export, replay
command bodies, or upstream body export.

## Current Digest Pass 1 Active Proposal Aliases

Source digest `github-growth-20260628T110729.847216Z` starts a new pass-1
window over the same skill-route-discovery slice. The
`current_pass_validation_cases` surface now recognizes the active proposal IDs
`p1-skill-route-discovery-generic`, `p2-game-skill-workflow-routing`, and
`p3-skill-state-handoff-validation` as aliases for the stable local validation
case rows.

The active fixture maps zhengxi-views to the source-cited/generic skill route
test lane, Three.js Game Skills to the game/frontend documentation lane, and
COMPASS Skills to the state-handoff config lane. These aliases are replay
metadata only; they do not add install, runtime execution, provider launch,
external skill activation, external harness execution, remote execution, profile
writes, memory writes, raw URL export, target path export, or upstream body
export. Qwen-AgentWorld-style adjacent general-agent evidence remains in
`agent_harness_eval_required` and does not inherit `skill_route_discovery`.

## Current Pass 3 Proposal Lane Contract

Source digest `github-growth-20260628T114729.691889Z` continues the active
pass-3 skill-route-discovery window with
`proposal_lane_activation_contract` inside `pass3_handoff_packet`. The contract
binds the carried proposal IDs `p1-skill-route-discovery-generic`,
`p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-state-handoff` to the already accepted route-profile lanes
before activation: generic zhengxi-views-style skill evidence maps to a local
documentation lane, Three.js game/frontend skill evidence maps to a local test
lane, and COMPASS-style state handoff evidence maps to a local config lane.

This is a controller replay contract, not an activation grant. Each row must
stay inside documentation, config, test, or code_patch; require local
validation; cite selected item IDs; and expose only source hashes, route
profiles, validation gates, and replay metadata. Adjacent Qwen-AgentWorld-style
general-agent evidence stays in `blocked_adjacent_proposal_ids` and cannot
inherit `skill_route_discovery`. Runtime action, external skill or agent
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw evidence URL export, target path export, and upstream
body export remain denied.

## Current Digest Pass 2 Local Validation Lane

Source digest `github-growth-20260628T140729.531143Z` advances pass 2 of the
active skill-route-discovery slice with
`current_digest_pass2_local_validation_lane`. The lane is keyed to the active
proposal IDs `p1-skill-route-discovery-compass-handoff`,
`p2-threejs-game-skill-routing-profile`, and
`p3-generic-skill-workflow-discovery-fixture`.

The lane interprets COMPASS-style skill ecosystem handoff evidence as a local
test lane for documentation/config/test/patchable route metadata boundaries,
Three.js game/frontend skill evidence as a local documentation lane for route
profile handling before scaffold or runtime use, and generic agent-skill
workflow evidence as a local test lane that keeps `runtime_action` set to
`none`. Each row must carry selected digest item IDs or frozen fixture evidence,
bounded lane inventory, route-profile validation gates, source hashes, and
hashed replay commands only.

This is a validation handoff, not an activation path. Install, runtime
execution, provider runtime, external skill activation, external harness
execution, provider launch, remote execution, profile writes, memory writes,
raw source URLs, raw evidence URLs, target paths, replay-command bodies, and
upstream bodies remain denied. Adjacent Qwen-AgentWorld or Looper-style
general-agent evidence stays in `agent_harness_eval_required` and does not
inherit skill-route implementation authority.

## Current Digest Pass 3 Local Validation Lane

Source digest `github-growth-20260628T142729.611973Z` advances pass 3 of the
same skill-route-discovery slice with a focused local harness fixture:
`skill_route_discovery_current_digest_pass3_local_validation_lane.json`. The
fixture binds `p1-skill-route-discovery-views`,
`p2-threejs-game-skill-profile`, and `p3-skill-ecosystem-state-handoff` to the
operator-visible `pass3_handoff_packet.route_profile_lane_contract` and
`proposal_lane_activation_contract`.

The lane treats zhengxi-views-style generic skill workflow evidence as a local
documentation lane, Three.js game/frontend skill evidence as a local test lane,
and COMPASS-style state handoff evidence as a local config lane. Each row must
remain inside documentation, config, test, or code_patch; require local
validation; and deny runtime action, upstream skill activation, external
harness execution, provider launch, remote execution, profile writes, memory
writes, raw source URL export, raw evidence URL export, target path export, and
upstream body export.

Qwen-AgentWorld remains adjacent as `agent_harness_eval_required`; it does not
inherit `skill_route_discovery` or direct implementation authority from the
skill-route lane.

## Current Digest Pass 4 Completion Handoff

Source digest `github-growth-20260628T144729.539313Z` completes the active
four-pass `skill-route-discovery` window with
`current_digest_pass4_completion_handoff`. The handoff binds the current
proposal IDs `p1-skill-route-discovery-generic`,
`p2-game-frontend-skill-profile`, and `p3-skill-ecosystem-handoff` to the
bounded route profiles already validated across the slice.

The packet treats zhengxi-views-style generic skill workflow evidence as a
local test lane, Three.js game/frontend skill evidence as a documentation lane
until local frontend validation exists, and COMPASS-style skill ecosystem
handoff evidence as a local test lane for metadata-only state boundaries. It
exports selected item IDs, source hashes, route profiles, bounded lane names,
validation gates, and replay-command hashes only.

This is a supervisor replay handoff, not runtime activation. Install, runtime
execution, provider runtime, external skill activation, external harness
execution, provider launch, profile writes, memory writes, remote execution,
raw source URL export, raw evidence URL export, raw target path export, replay
command export, and upstream body export remain denied.

## Current Source Digest Pass 1 Route Discovery Validation

Source digest `github-growth-20260628T150729.645832Z` starts the next
skill-route-discovery pass with the existing
`current_digest_pass1_validation_lane`, keyed to the active proposal IDs
`p1-skill-route-discovery-index`, `p2-game-frontend-skill-profile`, and
`p3-skill-ecosystem-handoff-profile`.

The lane converts the carried COMPASS Skills, zhengxi-views, and Three.js Game
Skills repository metadata into bounded local validation candidates only.
Source-cited or generic skill evidence selects the local test lane, Three.js
game/frontend workflow evidence selects a documentation lane until local
frontend validation exists, and COMPASS-style ecosystem handoff evidence selects
a metadata-only config lane. Candidate evidence refs remain selected item IDs,
and Qwen-AgentWorld-style general-agent evidence is kept adjacent as
`agent_harness_eval_required` without inheriting skill-route lanes.

Documentation, config, test, and code_patch remain the only local lanes.
Install, runtime execution, provider runtime, upstream skill activation,
external harness execution, provider launch, profile writes, memory writes,
remote execution, raw source URL export, raw evidence URL export, target path
export, replay-command export, and upstream body export remain denied.

Source digest `github-growth-20260628T162729.568714Z` keeps the same pass-1
lane active under the controller proposal IDs
`proposal_skill_route_discovery_index`, `proposal_game_frontend_skill_profile`,
and `proposal_skill_state_handoff_profile`. The local operator surface maps
zhengxi-views-style skill route evidence to a test lane, Three.js
game/frontend workflow evidence to a documentation lane, and COMPASS-style
state handoff evidence to a config lane. These rows are local validation
candidates only: `local_validation_required` remains true, unsupported
provider/runtime/install pressure is stripped from allowed lanes, and adjacent
Qwen-AgentWorld-style general-agent evidence stays in
`agent_harness_eval_required` instead of inheriting skill-route authority.

Source digest `github-growth-20260628T170729.576248Z` advances pass 3 by adding
`route_confidence_report` to `pass3_route_discovery_index` and
`pass3_preflight_queue`. The report is not an upstream popularity score and not
an activation grant. It is a local readiness summary for the active proposal
rows: each row must have candidate evidence, a route profile, selected item IDs
or frozen fixture evidence, a validation gate, and a selected lane bounded to
documentation, config, test, or code_patch. Complete rows are marked
`bounded_local_ready`; incomplete rows are marked `needs_local_corroboration`
and keep the preflight blocked. Runtime action, install, upstream skill
activation, external harness execution, provider launch, remote execution, raw
source URL export, raw evidence URL export, target path export, replay-command
export, and upstream body export remain denied.

## Current Digest Pass 4 Completion Checklist

Source digest `github-growth-20260628T160729.676966Z` completes the planned
skill-route-discovery window with an operator-visible profile validation
checklist on the pass-4 completion handoff and replay manifest. The checklist
is generated from local route profiles only; it does not read upstream bodies,
export raw source URLs, add lane names, or grant activation authority.

Generic skill workflow rows must confirm skill terms, route hints, selected
item IDs or frozen fixture evidence, and a bounded local lane. Source-cited
domain research rows add citation, advice-boundary, private-context, and
provider-launch checks. Game/frontend workflow rows add local frontend or
render validation before any patch work and keep scaffold, asset-generation,
and browser-run pressure denied. Skill ecosystem state-handoff rows add
metadata-only, privacy-boundary, profile-write, and memory-write checks.

The completion packet remains a supervisor replay artifact. Documentation,
config, test, and code_patch are still the only local lanes. Installation,
runtime execution, provider runtime, upstream skill activation, external
harness execution, provider launch, profile writes, memory writes, remote
execution, raw source URL export, raw evidence URL export, target path export,
replay-command export, and upstream body export remain denied.

## Current Digest Pass 4 Local-Kernel Handoff

Source digest `github-growth-20260628T172729.584826Z` completes the current
four-pass skill-route-discovery window by adding
`skill_route_discovery_local_kernel_handoff` to the completion packet. This is a
compact supervisor-facing summary derived from the existing completion report,
activation lane contract, runner control plane, consistency guard, recovery
packet, and profile completion check.

The handoff names only bounded local lanes and route profiles. In the current
digest, generic skill workflow evidence can select the documentation lane,
Three.js game/frontend workflow evidence can select the test lane, and
COMPASS-style state handoff evidence can select the config lane. Adjacent
Qwen-AgentWorld or Looper-style general-agent evidence remains visible only as
`agent_harness_eval_required`; it does not inherit skill-route lanes.

This packet is a local-kernel completion report for an external supervisor, not
a restart or activation command. It records replay-stage readiness, recovery
hint codes, validation-command hashes, and adjacent-agent counts without raw
source URLs, replay command bodies, target paths, or upstream bodies. Runtime
action, install, upstream skill or agent activation, external harness execution,
provider launch, profile writes, memory writes, and remote execution remain
denied.

## Current Digest Pass 1 Local Lane Activation

Source digest `github-growth-20260628T174729.552272Z` starts a new pass-1
skill-route-discovery window with the active proposal IDs
`p1-skill-route-discovery-generic`, `p2-threejs-game-skill-routing`, and
`p3-skill-ecosystem-state-handoff`.

The local lane map treats zhengxi-views-style agent/skill workflow signals as a
generic local test lane, Three.js Game Skills as a game/frontend documentation
lane, and COMPASS Skills as a metadata-only state-handoff config lane. Adjacent
Qwen-AgentWorld evidence remains `agent_harness_eval_required` under
`p4-agent-harness-eval`; it does not inherit `skill_route_discovery` lanes.

The pass-1 surface exports selected item IDs, source hashes, route profiles,
bounded lane names, validation gates, and replay-command hashes only.
Documentation, config, test, and code_patch remain the only local skill-route
lanes. Install, runtime execution, provider runtime, upstream skill activation,
external harness execution, provider launch, profile writes, memory writes,
remote execution, raw source URL export, raw evidence URL export, target path
export, replay-command export, and upstream body export remain denied.

## Active Window Pass 2 Local Lane Acceptance Contract

Source digest `github-growth-20260628T180729.573966Z` advances pass 2 of the
same skill-route-discovery slice by embedding
`local_lane_acceptance_contract` inside
`active_window_pass2_validation_lane`. The contract is derived from the
already-sanitized validation rows for zhengxi-views, Three.js Game Skills,
COMPASS Skills, and adjacent Qwen-AgentWorld evidence. It does not add new
evidence, read upstream bodies, or change allowed lanes.

The contract turns selected and queued pass-2 rows into explicit acceptance
gates before any later handoff. Skill-route rows must have a ready validation
row, selected evidence item IDs, route validation gates, a selected lane and
queued lanes bounded to documentation, config, test, or code_patch, local
validation required, and `runtime_action: none`. Three.js game/frontend rows
therefore remain documentation-first until local frontend or render validation
justifies further patch work. Adjacent Qwen-AgentWorld-style general-agent
evidence remains `agent_harness_eval_required` and must not inherit
`skill_route_discovery`, direct runtime routing, or direct code_patch
selection.

The acceptance contract remains an operator-visible validation surface, not an
activation grant. Install, runtime execution, provider runtime, upstream skill
or agent activation, external harness execution, provider launch, profile
writes, memory writes, remote execution, raw source URL export, raw evidence
URL export, target path export, replay-command export, and upstream body export
remain denied.

Source digest `github-growth-20260703T211924.184160Z` extends the pass-2
secondary harness surface with
`local_harness_fixture_intake_queue`. The queue is emitted inside
`pass2_secondary_harness_checklist` and repeated through the pass-2 handoff so
an operator can see the next bounded local work item for adjacent general-agent
projects such as Agent Apprenticeship or Qwen-AgentWorld. These rows do not
inherit `skill_route_discovery`: each requires a declared local
`agent_harness_eval_lane` fixture with fixture path, expected behavior,
expected output, pass/fail signal, rollback artifact, and non-secret config
before any implementation patch is considered. The queue exports source hashes
and route reason codes only; runtime action, external harness execution,
provider launch, remote execution, raw source URLs, and upstream bodies remain
denied.

Source digest `github-growth-20260703T223922.916308Z` keeps that pass-2 queue
as the operator-visible handoff for the active skill-route-discovery slice. The
Codex-oriented `reverse-flow-skill` evidence is accepted only as
`skill_route_discovery_first` for the `codex_workflow_gate` profile and maps to
bounded local documentation, config, test, or code_patch lanes with the test
lane selected for validation. The generic `zhengxi-views` skill workflow item
maps to the documentation lane for local interpretation work. General
agent-project evidence from Agent Apprenticeship and Qwen-AgentWorld remains
adjacent `agent_harness_eval_required` material: it must declare a local
`agent_harness_eval_lane` fixture before any documentation, test, or code patch
implementation is selected from that popularity signal. Runtime action,
external skill or agent activation, external harness execution, provider
launch, remote execution, raw source URLs, and upstream bodies remain denied.

## Current Digest Pass 3 Focused Validation Packet

Source digest `github-growth-20260628T182729.632246Z` advances pass 3 with
`current_digest_pass3_focused_validation_packet`, keyed to the active proposal
IDs `p1-skill-route-discovery-index`,
`p2-skill-ecosystem-handoff-doc`, and
`p3-game-frontend-skill-validation`.

The packet converts zhengxi-views-style source-cited skill evidence,
COMPASS-style skill ecosystem state handoff evidence, and Three.js game
frontend workflow evidence into local validation rows only. Each row must have
selected digest item IDs, route profile validation gates, acceptance gates, and
a lane bounded to documentation, config, test, or code_patch. Unsupported
provider_runtime, runtime_execution, and install pressure is stripped before
this packet and is not allowed to appear as a route.

State handoff remains metadata-only until local validation succeeds: profile
writes, memory writes, privacy-sensitive exports, and permission changes stay
denied. Game frontend workflow evidence can request local frontend validation,
but it does not permit scaffold execution, asset generation, provider launch,
browser runtime control, or upstream skill activation. Adjacent
Qwen-AgentWorld-style general-agent evidence stays in
`agent_harness_eval_required` and does not inherit `skill_route_discovery`,
direct runtime authority, or direct code_patch selection.

Source digest `github-growth-20260628T210729.710960Z` reuses the same packet
for the current pass-3 capability window. The active rows are
`p1-skill-route-discovery-matrix` and `p3-skill-profile-documentation`, with
adjacent `p2-agent-harness-eval-fixtures` rows held outside
`skill_route_discovery`.

The matrix row accepts generic skill workflow, Three.js game frontend workflow,
and COMPASS-style skill ecosystem state handoff profiles only when their
selected lane is one of documentation, config, test, or code_patch and local
validation remains required. The documentation row may describe that mapping,
but it is still a bounded local lane, not a skill install, upstream activation,
provider launch, scaffold execution, profile write, memory write, or remote
execution grant. Qwen-AgentWorld and looper-style general-agent projects remain
`agent_harness_eval_required` until a local harness evaluation route exists.

## Current Digest Pass 4 Activation Prerequisites

Source digest `github-growth-20260628T184729.576873Z` completes the active
skill-route-discovery window with an operator-visible
`activation_prerequisite_lane` embedded in the current digest pass-4 completion
handoff. The lane converts the focused zhengxi-views, Three.js Game Skills, and
COMPASS Skills rows into explicit prerequisites before supervisor replay:
focused evidence review, selected item IDs or frozen fixture evidence, profile
validation checklist completion, bounded local validation, rollback artifact
coverage, and confirmation that external activation remains denied.

This lane is derived from local completion rows only. It does not read upstream
bodies, export raw source URLs, export raw replay commands, expose target paths,
install upstream skills, execute scaffolds, launch providers, write profiles,
write memory, restart the kernel, or grant remote execution. zhengxi-views-style
source-cited skill evidence remains a local validation candidate, Three.js game
workflow evidence remains behind frontend validation before code changes, and
COMPASS-style handoff evidence remains metadata-only unless a later local
validation surface explicitly permits a narrower behavior.

## Current Digest Pass 1 Route Discovery Index

Source digest `github-growth-20260628T190729.559090Z` opens the next pass-1
skill-route-discovery window with the active proposal IDs
`p1-skill-route-discovery-index`, `p2-skill-route-fixture-tests`, and
`p3-game-frontend-skill-profile`, while keeping
`p4-agent-harness-eval-fixtures` and `p5-skill-ecosystem-state-handoff` visible
as anchoring context.

The local lane interprets the carried COMPASS Skills, zhengxi-views, and
Three.js Game Skills evidence as a bounded route-discovery index first. The
index and fixture-test proposals may cover all recognized skill-route profiles
to confirm that public skill repositories classify only into documentation,
config, test, or code_patch lanes. The game/frontend proposal narrows to
`game_frontend_workflow` and records config metadata only until local frontend
or render validation justifies patch work.

Unsupported pressure from the evidence, including install, provider_runtime,
runtime_execution, scaffold execution, provider launch, external skill
activation, external harness execution, remote execution, profile writes,
memory writes, raw source URL export, raw evidence URL export, target path
export, replay-command export, and upstream body export remains denied.
Adjacent Qwen-AgentWorld-style general-agent evidence stays in
`agent_harness_eval_required` and does not inherit `skill_route_discovery`.

## Current Digest Pass 2 Focused Review Lane

Source digest `github-growth-20260628T192730.399337Z` advances pass 2 with a
focused evidence review lane under `current_digest_pass2_local_validation_lane`.
The lane binds the active proposal IDs `p1-skill-route-discovery-generic`,
`p2-agent-harness-eval-qwen-agentworld`, and
`p3-game-frontend-skill-route` without requiring the supervisor to infer the
current pass from older COMPASS/state-handoff aliases.

The focused lane treats zhengxi-views-style public `SKILL.md` workflow evidence
as a local test lane, Three.js game/frontend workflow evidence as a local
documentation lane, and Qwen-AgentWorld-style general-agent project evidence as
`agent_harness_eval_required`. The general-agent row must collect install
shape, entrypoints, dependency boundaries, task-loop assumptions, observable
behaviors, and evaluation dimensions before any runtime, controller, or
tool-routing implementation route can be considered.

This is still a validation surface, not activation. Documentation, config,
test, and code_patch remain the only skill-route lanes. Qwen-AgentWorld does
not inherit `skill_route_discovery`, direct runtime authority, or direct
code_patch selection. Install, runtime execution, provider runtime, upstream
skill or agent activation, external harness execution, provider launch, remote
execution, profile writes, memory writes, raw source URL export, raw evidence
URL export, target path export, replay-command export, and upstream body export
remain denied.

## Current Source Digest Pass 3 Route Readiness Index

Source digest `github-growth-20260628T194729.590017Z` advances pass 3 of the
active skill-route-discovery slice with
`current_pass3_route_readiness_index` in the proposal lane map. The index is an
operator-facing summary derived from existing route classification and the
pass-3 handoff. It distinguishes skill-route rows that are ready for bounded
local validation from adjacent general-agent rows that are still blocked behind
`agent_harness_eval_required`.

The current carried skill evidence from COMPASS Skills, zhengxi-views, and
Three.js Game Skills can be summarized as ready only for documentation, config,
test, or code_patch lanes, with selected item IDs as the evidence reference
scope. Qwen-AgentWorld-style general-agent project evidence stays adjacent:
it may expose only the documentation/test/code_patch harness-evaluation lane
inventory, does not inherit `skill_route_discovery`, and cannot receive direct
runtime, controller, or code_patch authority before a local harness evaluation
result exists.

The readiness index is not activation. Runtime action, upstream skill or agent
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
and upstream body export remain denied.

## Current Digest Pass 4 Skill Route Completion Lane

Source digest `github-growth-20260628T200729.682703Z` completes the active
skill-route-discovery window with the existing
`current_digest_pass4_completion_handoff` surface specialized to the current
proposal IDs `p1-skill-route-discovery-index`,
`p2-skill-profile-documentation`, and adjacent `p3-agent-harness-eval`.

The lane converts COMPASS Skills, zhengxi-views, and Three.js Game Skills into
bounded local route rows only. The route index row selects the local test lane,
and the profile documentation row selects the local documentation lane. Both
rows must keep selected item IDs or frozen fixture evidence, route-profile
validation gates, downgraded unsupported lane pressure, replay-command hashes,
and `local_validation_required: true`.

Qwen-AgentWorld-style general-agent evidence remains adjacent as
`agent_harness_eval_required`: it may collect documentation/test/code_patch
evidence only after a local harness-eval path exists, and it does not inherit
`skill_route_discovery` or direct runtime/controller/code_patch authority.
Install, runtime execution, provider runtime, upstream skill or agent
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
target path export, replay-command export, and upstream body export remain
denied.

Source digest `github-growth-20260629T000729.615262Z` completes the fourth
skill-route-discovery pass with
`skill_route_discovery_current_digest_pass4_completion_lane` inside the
local-kernel handoff. The lane binds the active proposal set
`p1-skill-route-discovery-compass`, `p2-generic-skill-workflow-docs`, and
`p3-agent-harness-eval-qwen-agentworld` to one replayable operator surface.

The COMPASS-style state handoff signal maps to the local config lane only after
the state-handoff boundary says retention policy, privacy boundary, metadata-only
local target, and no upstream-presence write authority are all explicit.
zhengxi-views-style generic skill workflow evidence maps to documentation, and
Three.js game skill workflow evidence maps to the local test lane. Unsupported
pressure such as install, runtime execution, and provider runtime is treated as
rejected lane pressure rather than activation authority.

Qwen-AgentWorld remains adjacent general-agent evidence. Its local route is
`agent_harness_eval_required` with the allowed harness-evaluation lanes
documentation, test, and code_patch; it does not inherit `skill_route_discovery`
and cannot create runtime behavior, external harness execution, provider launch,
remote execution, profile writes, memory writes, or direct implementation work
before harness evidence exists. The handoff exports the source digest, counts,
selected lanes, hashes, and denial booleans only; raw source URLs, raw evidence
URLs, target paths, replay command bodies, and upstream bodies remain omitted.

Source digest `github-growth-20260628T204729.558875Z` continues pass 2 with
`current_digest_pass2_active_slice_review_lane`. This nested lane binds the
active anchoring proposals `p1-skill-route-discovery-index`,
`p2-skill-profile-docs`, and `p3-agent-harness-eval-fixtures` to the same
bounded local route evidence before pass 3. The index row covers generic skill
workflow, Three.js game/frontend workflow, and COMPASS-style skill ecosystem
state handoff together in the local test lane. The profile-docs row exposes the
same route profiles as documentation/config/test/code_patch candidates only
after local validation. Adjacent Qwen-AgentWorld or Looper-style general-agent
evidence remains `agent_harness_eval_required`; it does not inherit
`skill_route_discovery`, direct runtime authority, direct code_patch authority,
external harness execution, provider launch, or remote execution.

Source digest `github-growth-20260629T233904.362379Z` completes pass 4 of the
current `skill-route-discovery` window with a digest-specific final closure
fixture and replay surface. The completion handoff names the current proposals
directly: `p1-skill-route-discovery-compass`,
`p2-generic-skill-route-coverage-zhengxi`, and
`p3-agent-harness-eval-qwen-agentworld`.

COMPASS-style skill ecosystem evidence maps to the local test lane for
metadata-only state-handoff validation. zhengxi-views-style Agent Skill
workflow evidence maps to the documentation lane. A third local test row keeps
the skill-workflow versus general-agent boundary explicit. Qwen-AgentWorld and
looper remain adjacent general-agent projects: Qwen is the final-closure
`agent_harness_eval_required` boundary and looper is the pass-4 handoff
adjacent loop-runner eval row. Neither inherits `skill_route_discovery` or
direct runtime/code_patch authority before local harness evaluation.

The current digest pass-4 surfaces are body-free and supervisor-facing. They
export proposal IDs, selected item IDs, lane names, route profiles, hashes, and
denial booleans only. Raw source URLs, raw evidence URLs, replay command
bodies, target paths, upstream bodies, install, provider runtime, runtime
execution, profile writes, memory writes, remote execution, external skill
activation, external agent activation, and external harness execution remain
denied.

## Final Route Closure Manifest

The pass-4 local-kernel handoff now includes
`final_route_closure_manifest`. It is the operator-visible closure surface for a
completed skill-route-discovery capability window: skill-route evidence can close
only when the proposal completion summary, current digest completion lane, final
pass marker, and replay stages are all ready.

The manifest emits two route decisions when the window also contains general
agent evidence. `skill_route_discovery` rows may activate only bounded local
documentation, config, test, or code_patch lanes after local validation.
`agent_harness_eval_required` rows remain gated and explicitly do not inherit
`skill_route_discovery`; they can proceed only through the separate
`agent_harness_eval_lane` replay before any runtime, controller, provider, or
implementation behavior is considered.

The manifest is body-free. It exports source digest, route profiles, selected
local lanes, stage counts, replay stage names, validation command hashes, and
denial booleans. It does not export raw source URLs, evidence URLs, target paths,
replay command bodies, upstream bodies, or any profile or memory write authority.

## 2026-07-02 Pass-4 Current Completion Handoff

Source digest `github-growth-20260702T094715.832381Z` now has an explicit
`current_digest_pass4_completion_handoff` branch instead of falling through to a
generic older handoff. The current window closes only the zhengxi-views
RepositoryTrend as a bounded `skill_route_discovery` local test lane, with
allowed lanes limited to documentation, config, test, and code_patch.

Qwen-AgentWorld, Fundamental-Ava, and looper-style general-agent project trends
remain adjacent `agent_harness_eval_required` rows. They do not inherit
`skill_route_discovery`, direct code_patch and runtime routes stay disabled, and
local agent-harness evaluation is required before any implementation route.
Workflow-usecase fork clusters without route hints are recorded as weak
workflow popularity pressure for documentation or test follow-up only; they do
not count as independent implementation evidence.

The handoff remains body-free and operator replayable: it records selected item
IDs, proposal IDs, lane names, route profiles, checklist status, and denial
booleans while omitting raw source URLs, evidence URLs, replay command bodies,
target paths, and upstream repository bodies.

## 2026-06-30 Pass-4 Profile Closure

Source digest `github-growth-20260630T005904.395870Z` completes the current
skill-route-discovery slice with an evidence-derived pass-4 profile contract.
The completion lane no longer requires a game/frontend skill profile when the
current digest contains only COMPASS-style state handoff plus zhengxi-views-style
generic/source-cited skill workflow evidence. Required profiles are derived from
the skill-route candidates present in the digest, while unsupported install,
provider runtime, runtime execution, profile write, memory write, remote
execution, and external activation pressure remains denied.

The operator-visible completion packet uses the current proposal IDs:
`p1-skill-route-discovery-zhengxi-views` for the bounded zhengxi skill-route test
lane, `p2-agent-harness-eval-suite` for Qwen-AgentWorld and looper as adjacent
`agent_harness_eval_required` evidence, and `p3-agent-trend-routing-doc` for the
documentation lane that explains skill-route versus harness-eval routing.

## 2026-06-30 Pass-3 Empty-Hint General-Agent Boundary

Source digest `github-growth-20260630T024714.466980Z` advances pass 3 by
preserving explicit empty `route_hints` from general-agent trend evidence instead
of defaulting them into `skill_route_discovery`. zhengxi-views-style agent plus
skill evidence remains a bounded local skill-route test lane, limited to
documentation, config, test, or code_patch.

Qwen-AgentWorld and looper-style general-agent projects without route hints are
operator-visible only as `agent_harness_eval_required` rows. Empty route hints do
not authorize scheduler, runner, loop, runtime, provider, external harness, or
direct code_patch changes. They must first pass local agent harness evaluation,
and the pass-3 surface exports only body-free hashes, lane names, proposal IDs,
and denial booleans.

## 2026-06-30 Pass-2 Acceptance Gates

Source digest `github-growth-20260630T050714.525014Z` keeps the pass-2
skill-route and general-agent split operator-visible before activation. The
`proposal_acceptance_contract` now summarizes accepted skill-route lanes,
unsupported upstream lane pressure removed during local bounding, and aggregate
acceptance gates for local validation, no runtime action, denied external
activation, and omitted raw upstream material.

Adjacent Qwen-AgentWorld-style general-agent evidence is summarized in a
separate `adjacent_agent_harness_gate`: it remains
`agent_harness_eval_required`, does not inherit `skill_route_discovery`, and
requires the local `agent_harness_eval_lane` replay before implementation,
runtime, provider, controller, or remote-execution changes are considered.

## 2026-06-30 Pass-4 Operator Activation Queue

The pass-4 `runner_harness_control_plane` now carries an
`operator_activation_queue` summary derived from the validated activation
packet. The replay stage is ready only when the final route handoff manifest,
route validation lane queue, activation packet, and operator activation lane are
all ready.

The queue gives the supervisor one body-free place to inspect lane count, ready
and blocked counts, proposal kinds, route profiles, activation packet status,
and the bounded next action. It still exports only local lane metadata and denial
booleans: runtime action, external skill code, external harness execution,
provider launch, remote execution, raw evidence URLs, raw source URLs, target
paths, and upstream bodies remain unavailable from this surface.

## 2026-06-30 Pass-3 Current Evaluation Lane

Source digest `github-growth-20260630T080714.700772Z` continues pass 3 with
the current active proposal IDs. `p1_skill_route_discovery_probe_zhengxi_views`
is the only skill-route implementation candidate and maps zhengxi-views to the
local test lane after stripping unsupported `provider_runtime` evidence. It may
select only documentation, config, test, or code_patch, and it keeps local
validation required before activation.

`p2_agent_harness_eval_gate_for_general_agent_projects` is the aggregate local
gate for Qwen-AgentWorld, open-reverselab, and looper. Each adjacent row remains
`agent_harness_eval_required`; trend summaries alone do not grant direct
documentation, test, code_patch, runtime, external harness, provider launch,
remote execution, profile-write, memory-write, raw URL export, replay-command
export, target-path export, or upstream-body export authority.
`p3_document_route_policy_for_trend_only_inputs` is documentation-only guidance
for that boundary, not an activation route.

Source digest `github-growth-20260630T052714.485930Z` keeps the active
`skill-route-discovery` slice in pass 3 with current proposal names instead of
older aliases. zhengxi-views is treated as public Agent Skill workflow evidence
and maps to `proposal-skill-route-discovery-zhengxi-views` in the local test
lane. That row may select only documentation, config, test, or code_patch and
keeps local validation required before any activation.

Qwen-AgentWorld, open-reverselab, and looper are represented by
`proposal-agent-harness-eval-trending-agent-projects` as adjacent general-agent
evidence. They remain in `agent_harness_eval_required`: they do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, remote execution, profile writes,
memory writes, raw source URL export, replay-command export, target-path export,
or upstream body export. `proposal-route-classification-docs` is carried as the
operator-visible documentation route for this distinction.

## 2026-06-30 Pass-4 Current Slice Closure

Source digest `github-growth-20260630T054715.044236Z` completes the current
skill-route-discovery slice with digest-specific pass-4 handoff and final
closure rows. zhengxi-views is the only skill-route candidate in this digest,
so required route profiles are derived from its present generic and
source-cited workflow evidence rather than older COMPASS/state-handoff aliases.
It maps to a bounded local test lane for
`p1-skill-route-discovery-zhengxi-views` and a bounded documentation lane for
`p3-route-hint-policy-documentation`.

Qwen-AgentWorld, open-reverselab, and looper remain adjacent
`p2-agent-harness-eval-suite` rows. The pass-4 operator completion checklist
marks replay, rollback artifact coverage, focused local validation, route
boundary separation, and the agent-harness gate as explicit supervisor-visible
conditions. It does not grant runtime action, external skill or agent
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw URL export, replay-command export,
target-path export, or upstream body export.

## 2026-07-01 Pass-2 Local Validation Lane

Source digest `github-growth-20260701T143923.018624Z` continues pass 2 by
making the active lane replayable for the current proposal IDs.
`p1-skill-route-discovery-validation` maps the zhengxi-views Agent Skill signal
to the local test lane, and `p3-agent-harness-docs` records the route policy as
documentation. Both rows may use only documentation, config, test, or
code_patch lanes, and both keep `runtime_action: none`.

Qwen-AgentWorld, Fundamental-Ava, and open-reverselab stay adjacent
`p2-agent-harness-eval-fixtures` rows until a local agent harness evaluation
passes. They do not inherit `skill_route_discovery`, direct runtime routing,
direct code_patch authority, external harness execution, provider launch,
remote execution, raw source URL export, raw evidence URL export, or upstream
body export. The open-reverselab anchor is also recorded as
`p4-open-reverselab-safety-aware-harness-case` with review influence only at
the offensive-behavior boundary.

## 2026-07-01 Pass-4 Skill Route Completion Boundary

Source digest `github-growth-20260701T190302.389615Z` completes the current
skill-route-discovery window with an operator-visible pass-4 handoff. The
zhengxi-views signal is the only `skill_route_discovery` candidate and remains
bounded to documentation, config, test, or code_patch lanes; this pass selects
the local test lane plus a documentation boundary row.

| Evidence shape | Route | Allowed local lanes before eval | Activation boundary |
| --- | --- | --- | --- |
| zhengxi-views-style Agent Skill workflow with generic and source-cited profiles | `skill_route_discovery` | documentation, config, test, code_patch | local validation and rollback evidence required before supervisor replay |
| Qwen-AgentWorld, Fundamental-Ava, or looper-style general Python agent project without skill workflow hints | `agent_harness_eval_required` | none until harness eval; documentation, test, code_patch only after eval | does not inherit `skill_route_discovery`, direct runtime routing, or direct code_patch authority |

The handoff records Qwen-AgentWorld, Fundamental-Ava, and looper as adjacent
general-agent rows under `p2-agent-harness-eval-general-python-agents`. They
remain gated until a local agent harness evaluation exists, with runtime action,
external agent activation, external harness execution, provider launch, remote
execution, raw URL export, replay-command export, target-path export, and
upstream-body export denied.

## 2026-07-02 Pass-3 Adjacent Harness Matrix

Source digest `github-growth-20260702T080714.759237Z` advances pass 3 of the
active `skill-route-discovery` slice by making adjacent general-agent gates
operator-visible as an `adjacent_agent_harness_eval_matrix` inside
`current_digest_pass3_activation_review_lane`. The zhengxi-views row remains a
bounded `skill_route_discovery` test lane, while BioNeMo-style skill catalog
evidence may inform only bounded documentation/config/test/code_patch work.
Qwen-AgentWorld and Fundamental-Ava are listed as separate
`agent_harness_eval_required` matrix rows with implementation lanes disabled
until a local harness evaluation result exists.

The matrix is body-free: it exports project names, item ids, proposal ids, lane
state, and denial flags, but no raw source URLs, evidence URLs, replay commands,
target paths, upstream bodies, provider launch, remote execution, profile
writes, memory writes, external skill activation, or external harness
execution.

## Current Digest 20260702T084714 Pass 1

The `github-growth-20260702T084714.820443Z` pass-1 lane is exposed through
`current_digest_pass1_validation_lane`. It binds the active proposal IDs to a
single zhengxi-views skill-route validation row and three adjacent generic-agent
rows. zhengxi-views maps to `skill_route_discovery` with only documentation,
config, test, and code_patch lanes, and keeps local validation required before
activation.

Qwen-AgentWorld, Fundamental-Ava, and looper remain
`agent_harness_eval_required` rows. Empty `allowed_lanes` in their source
fixture is not a no-action signal; it means no implementation lane is enabled
until a local harness-evaluation result frames documentation, test, or code_patch
work. The lane exports hashes and bounded route metadata only, not raw source
URLs, replay commands, upstream bodies, provider launches, external harness
execution, or restart authority.

## Current Digest 20260702T092714 Pass 3

The `github-growth-20260702T092714.857659Z` pass-3 activation review lane is
now exposed through `current_digest_pass3_activation_review_lane`. It keeps
zhengxi-views as the only `skill_route_discovery` row because the public
repository presents a concrete skill package shape: `SKILL.md`, `skill.yml`,
references, evals, scripts, source-citation boundaries, and non-investment
advice limits. That row selects only the local test lane inside the bounded
documentation, config, test, or code_patch envelope.

Qwen-AgentWorld, Fundamental-Ava, and looper remain a single adjacent
`agent_harness_eval_required` row plus an operator-visible matrix. They do not
inherit `skill_route_discovery`; their direct lanes before harness evaluation
are empty, and only documentation, test, or code_patch can be considered after a
local harness result exists.

Workflow-usecase evidence remains a documentation-only route boundary in this
pass. A workflow-only trend without an explicit skill-route hint does not adopt
runtime workflows, launch providers, execute external harnesses, or enable
remote execution. It stays behind `agent_harness_eval_required` until local
evaluation creates a bounded follow-up lane.

## Current Digest 20260702T100715 Pass 1

The `github-growth-20260702T100715.355760Z` pass-1 lane is exposed through
`current_digest_pass1_validation_lane` for the carried proposal IDs. The
zhengxi-views RepositoryTrend is the only direct `skill_route_discovery` row:
its public Agent Skill shape (`SKILL.md`, `skill.yml`, references, scripts,
evals, source-citation boundaries, and non-investment-advice limits) maps to the
local test lane inside the bounded documentation, config, test, and code_patch
envelope.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`agent_harness_eval_required` rows. Their general-agent or review-gated loop
topics do not inherit `skill_route_discovery`; direct runtime and direct
code_patch routes stay disabled until a local agent harness evaluation produces
a bounded follow-up lane. The self-model was read for this pass and left
unchanged because it is descriptive policy context rather than an executable
route source.

## Current Digest 20260702T104714 Pass 3

The `github-growth-20260702T104714.732349Z` pass-3 activation review lane is
now exposed through `current_digest_pass3_activation_review_lane`. The current
zhengxi-views evidence remains a `skill_route_discovery` test row because the
public repository presents a concrete skill package shape: `SKILL.md`,
`skill.yml`, references, scripts, evals, source-citation boundaries, and
non-investment-advice limits. The only allowed local lanes are documentation,
config, test, and code_patch, with the pass selecting test before activation
review.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`agent_harness_eval_required` rows. They do not inherit `skill_route_discovery`,
and direct runtime or code_patch routes stay disabled until a local harness
evaluation produces a bounded documentation, test, or code_patch follow-up.
Workflow-usecase repository trends without explicit skill-route signals are
recorded as documentation triage only; they stay behind the same harness-eval
boundary and do not authorize runtime workflow adoption, provider launch,
external harness execution, or remote execution.

## Current Digest 20260702T134626 Pass 4

The `github-growth-20260702T134626.866283Z` pass-4 completion handoff is now a
digest-specific supervisor surface. The zhengxi-views evidence is treated as a
public Agent Skill package shape: `SKILL.md`, `skill.yml`, references, scripts,
evals, source-citation boundaries, and non-investment-advice limits. It maps to
`p1-skill-route-discovery-zhengxi-views` in the local test lane, while
`p3-document-agent-growth-routing-policy` records the policy distinction as a
documentation lane. Both remain inside the documentation, config, test, and
code_patch envelope, and both keep local validation required.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent general-agent
project rows under `p2-agent-harness-eval-fixtures`. They do not inherit
`skill_route_discovery`, and their direct lanes before agent-harness evaluation
are empty. Only documentation, test, or code_patch can be selected after local
`agent_harness_eval_required` evidence exists. The handoff and final closure
export proposal IDs, selected item IDs, lane names, route profiles, hashes, and
denial booleans only; raw source URLs, evidence URLs, replay commands, target
paths, upstream bodies, provider launch, external harness execution, remote
execution, profile writes, memory writes, external skill activation, and
external agent activation remain denied.

## Current Digest 20260702T193118 Pass 4

The `github-growth-20260702T193118.749598Z` pass-4 completion handoff closes
the active skill-route-discovery slice through
`current_digest_pass4_completion_handoff`. The zhengxi-views trend remains the
only direct `skill_route_discovery` candidate because the digest carries both
agent and skill signals plus repository-shape evidence such as `SKILL.md`,
`skill.yml`, references, validation scripts, evals, source-citation workflow,
and explicit local validation framing. It maps to
`p1-skill-route-discovery-zhengxi-views` in the local test lane and may select
only documentation, config, test, or code_patch.

Qwen-AgentWorld, Fundamental-Ava, and looper are represented under
`p2-agent-harness-eval-general-agent-projects` as adjacent general-agent rows.
They remain `agent_harness_eval_required`: no direct runtime route, direct
code_patch route, external harness execution, provider launch, remote
execution, or skill-route inheritance is granted before a local harness
evaluation creates a bounded documentation, test, or code_patch follow-up.

Workflow-themed repositories without explicit skill-route signals, including
Awesome-Blender-Seedance-Workflow-Usecases, are recorded by
`p3-agent-harness-docs-for-workflow-repos` as documentation and harness-eval
boundary evidence only. A workflow topic match alone does not authorize direct
workflow adoption, provider launch, external harness execution, or remote
execution. The handoff remains body-free and exports proposal IDs, selected
item IDs, lane names, route profiles, hashes, and denial booleans rather than
raw source URLs, evidence URLs, replay commands, target paths, or upstream
bodies.

## Current Digest 20260702T214709 Pass 2

The `github-growth-20260702T214709.510460Z` pass-2 lane now has an explicit
current-window replay surface. The zhengxi-views RepositoryTrend is the only
direct `skill_route_discovery` candidate because it carries both agent and
skill signals plus repository-shape evidence such as `SKILL.md`, `skill.yml`,
references, scripts, evals, source-citation workflow, and advice-boundary
metadata. It maps to `p1_skill_route_discovery_zhengxi_views` in the local test
lane and to `p3_document_agent_trend_routing_contract` in the documentation
lane. Both rows remain bounded to documentation, config, test, or code_patch.

Qwen-AgentWorld, Fundamental-Ava, and looper are kept as adjacent general-agent
rows under `p2_agent_harness_eval_general_projects`. They do not inherit
`skill_route_discovery`; direct runtime and direct code_patch routes stay
disabled until a local `agent_harness_eval_required` result exists. The pass-2
surface is body-free and denies provider launch, external harness execution,
remote execution, external skill or agent activation, raw source URL export,
replay-command export, target-path export, and upstream-body export.

## Current Digest 20260702T222121 Pass 3

The `github-growth-20260702T222121.903294Z` pass-3 activation review lane now
has an explicit current-window replay surface. The zhengxi-views trend remains
the only direct `skill_route_discovery` candidate because the digest carries
explicit skill-route evidence: `SKILL.md`, `skill.yml`, references, scripts,
evals, source-citation workflow language, and local validation framing. It maps
to `p1-skill-route-discovery-zhengxi-views` in the local test lane, bounded to
documentation, config, test, or code_patch.

Qwen-AgentWorld, Fundamental-Ava, and looper are grouped separately under
`p2_agent_harness_eval_general_agent_projects` as adjacent general-agent
evidence. They do not inherit `skill_route_discovery`, and direct runtime or
direct code_patch routes stay disabled until local agent-harness evaluation
creates a bounded follow-up lane. The workflow-only Seedance usecase repository
is split into `p3-workflow-agent-eval-seedance` as documentation triage behind
the same harness boundary. Workflow keywords alone do not authorize runtime
workflow adoption, provider launch, external harness execution, remote
execution, raw URL export, replay-command export, target-path export, or
upstream-body export.

## Current Digest 20260702T224121 Pass 4

The `github-growth-20260702T224121.812742Z` final pass closes the current
skill-route-discovery slice with an operator recovery packet. zhengxi-views is
the only direct `skill_route_discovery` candidate: its public Agent Skill shape
includes `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation
workflow language, and advice-boundary metadata. It maps to the local test lane,
with a documentation row recording the route policy; the allowed lane envelope
remains documentation, config, test, and code_patch.

Qwen-AgentWorld and Fundamental-Ava are kept as separate adjacent
`agent_harness_eval_required` rows for
`p2_agent_harness_eval_qwen_agentworld` and
`p3_agent_harness_eval_fundamental_ava`. They do not inherit
`skill_route_discovery`; direct lanes before harness evaluation are empty, and
only documentation, test, or code_patch may be selected after a local harness
result exists. The operator packet requires a rollback ref, rollback artifact,
focused validation, and replay hashes, while denying runtime action, external
skill or agent activation, external harness execution, provider launch, remote
execution, raw URL export, replay-command export, target-path export, and
upstream-body export.

## Current Digest 20260702T230121 Provider Runtime Pass 1

The `github-growth-20260702T230121.760789Z` pass-1 provider-runtime-control
fixture keeps the same evidence split but makes the replay path explicit for
this wake. zhengxi-views is the only direct `skill_route_discovery` row because
the public repository exposes `SKILL.md`, `skill.yml`, references, evals,
scripts, source-citation workflow language, and advice-boundary metadata. It
may still select only documentation, config, test, or code_patch lanes.

Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent
`agent_harness_eval_required` evidence. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority, or
provider launch permission before local harness evaluation exists. The new
fixture adds a dry-run provider/runtime sample with Windows runner metadata so
the supervisor can replay body-free diagnostics, recovery hints, and preflight
status locally. It exports no raw source URLs, raw evidence URLs, provider
inputs, command bodies, diagnostics bodies, upstream bodies, or runtime actions,
and it keeps provider launch and remote execution denied.

## Current Digest 20260702T234121 Provider Runtime Pass 3

The `github-growth-20260702T234121.739101Z` pass-3 provider-runtime-control
surface adds `provider_runtime_control_pass3_operator_recovery_workflow`. The
workflow is derived from the existing current-action preflight, promotion
checkpoint, activation packet, validation readiness summary, and adjacent
general-agent boundary. It gives the scheduler one top-level pass-3 recovery
sequence before the final pass: replay provider-runtime preflight hashes,
confirm the promotion checkpoint, inspect the selected bounded validation lane,
and keep Qwen-AgentWorld, Fundamental-Ava, and looper behind
`agent_harness_eval_required`.

The workflow treats zhengxi-views as the only direct `skill_route_discovery`
candidate because its public repository shape includes `SKILL.md`, `skill.yml`,
references, evals, scripts, source-cited workflow language, and advice-boundary
metadata. Provider/runtime wording from that evidence remains diagnostic-only:
the pass exports command hashes, selected item IDs, source hashes, lane names,
counts, and denial booleans, not raw source URLs, evidence URLs, replay command
bodies, provider inputs, provider values, diagnostics bodies, target paths, or
upstream bodies. Provider runtime launch, external harness execution, remote
execution, supervisor promotion, and external skill or agent activation remain
denied.

## Current Digest 20260703T000121 Reverse-Flow Probe

The `github-growth-20260703T000121.763879Z` final provider-runtime-control pass
adds a local replay probe for reverse-flow-style skill/workflow signals. The
public evidence reviewed for this run was a fork-heavy `reverse-flow-skill`
cluster with Codex/AI-agent skill packaging, `skills/reverse-flow/SKILL.md`,
scripts, and local CTF/crackme/sandbox reverse-analysis workflow language.

The local fixture selects only `reverse-flow-skill-primary-package` into the
proposal context budget. Fork rows are preserved as truncated pressure, not
direct implementation evidence, so accepted proposals may cite only selected
item IDs and may map only to documentation, config, test, or code_patch lanes.
The selected lane for the replay probe is `test`; local validation remains
required, runtime action is `none`, and external skill activation, provider
launch, external harness execution, remote execution, raw URL export, and
upstream-body export remain denied.

## Current Digest 20260703T002121 Pass 1

The `github-growth-20260703T002121.806126Z` pass-1 lane turns the
reverse-flow cluster into an explicit route-classifier surface. The
baojunxiong, lingbol088-spec, and minxiang0101 reverse-flow-skill repositories
are treated as public Codex/AI Agent skill package evidence because their
body-free summaries expose a `skills/reverse-flow/SKILL.md` package shape,
scripts, and local sandbox/CTF/crackme workflow framing. They may select only
documentation, config, test, or code_patch local lanes. Unsupported pressure
from the upstream workflow, such as install or runtime/provider execution, is
not exported from the pass-1 lane.

The same lane carries zhengxi-views as source-cited Agent Skill evidence for a
documentation interpretation row: `skill_route_discovery` discovers local route
shape only. It does not authorize runtime action, external skill activation,
provider launch, external harness execution, remote execution, or final scope by
itself; controller policy and focused local validation still choose gates before
activation review. Qwen-AgentWorld, Fundamental-Ava, and workflow-only Seedance
usecase evidence remain adjacent `agent_harness_eval_required` rows with direct
lanes empty before local harness evaluation.

## Current Digest 20260703T004121 Pass 2

The `github-growth-20260703T004121.758638Z` pass-2 lane promotes the
reverse-flow cluster from generic skill evidence into a Codex workflow gate.
When a repository trend item carries agent, Codex, skill, and workflow signals,
the local route must expose `skill_route_discovery_first` before any secondary
agent-harness interpretation. The Codex row may still select only
documentation, config, test, or code_patch lanes, with `test` as the focused
local validation lane for this pass.

The same pass keeps zhengxi-views in the generic skill workflow documentation
lane because it has agent and skill evidence but not a Codex workflow gate.
Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under the pass-2 harness fixture proposal:
they do not inherit `skill_route_discovery`, direct runtime routing, direct
code_patch authority, provider launch, external harness execution, or remote
execution before local harness evaluation succeeds.

## Current Digest 20260703T010121 Pass 3

The `github-growth-20260703T010121.773810Z` pass-3 lane makes the reverse-flow
cluster operator-visible as a metadata-only candidate registry before final
activation review. The public evidence reviewed for this pass was a
reverse-flow-skill repository shape with a Codex/AI Agent skill package,
`skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF/crackme workflow
framing, and fork pressure, plus the carried zhengxi-views source-cited skill
item.

The registry fixture stores only item IDs, source digest, proposal IDs, route
profiles, bounded lane names, selected lane, fork-lineage role, public activity
counts, and body-free summary hashes. It must not store raw source URLs,
evidence URLs, upstream README text, command bodies, target paths, or upstream
bodies. A registry row is ready only when its item ID is already present in
candidate intake, its route profiles have passed local profile review, its
selected lane is one of documentation, config, test, or code_patch, and
`consumed_by` is `skill_route_discovery_lane`.

Reverse-flow-style Codex/workflow skill evidence still reports
`skill_route_discovery` first and may select only documentation, config, test,
or code_patch. Fork rows are lineage pressure rather than independent
implementation authority. Runtime action, upstream install, external skill
activation, provider launch, external harness execution, remote execution, raw
URL export, and upstream body export remain denied.

## Current Digest 20260703T021735 Pass 4

The `github-growth-20260703T021735.773118Z` final pass exposes a concrete
completion handoff for the reverse-flow skill-route window. The dukehao and
lingbol088-spec reverse-flow-skill rows are treated as Codex workflow skill
evidence because the body-free summaries carry Agent/Codex skill packaging,
`skills/reverse-flow/SKILL.md`, scripts, and local sandbox/CTF/crackme workflow
framing. The completion row keeps `codex_workflow_gate` in the test lane and
records `skill_route_discovery_first` before any secondary workflow or harness
interpretation.

The same handoff keeps zhengxi-views in generic skill-workflow documentation
triage, while Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows. Those
general-agent rows do not inherit `skill_route_discovery`; their direct lanes
before harness evaluation are empty, and only documentation, test, or
code_patch can be considered after local harness evidence exists. The operator
recovery packet requires rollback metadata and focused validation, and exports
hashes plus lane names rather than raw source URLs, replay commands, upstream
bodies, provider inputs, target paths, or activation authority.

## Current Digest 20260703T023735 Pass 1

The `github-growth-20260703T023735.914741Z` pass-1 lane reopens the
skill-route-discovery slice for current skill, Codex, and workflow signals.
The lingbol088-spec reverse-flow-skill item is treated as Codex workflow skill
evidence because the body-free summary carries Agent/Codex skill packaging,
`skills/reverse-flow/SKILL.md`, references, scripts, and local sandbox workflow
framing. It maps to the local test lane only inside the documentation, config,
test, and code_patch envelope. The zhengxi-views item remains a generic and
source-cited skill-workflow documentation row with the same bounded lane set.

Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows. They do not
inherit `skill_route_discovery`; direct runtime, direct code_patch, provider
launch, external harness execution, remote execution, raw URL export, replay
command export, and upstream-body export remain disabled until local
agent-harness evaluation produces a bounded documentation, test, or code_patch
follow-up lane.

## Current Digest 20260703T025735 Pass 2

The `github-growth-20260703T025735.929695Z` pass-2 lane binds the active
skill-route-discovery slice to `current_digest_pass2_local_validation_lane`.
The two skill-workflow examples remain local validation candidates only:
lingbol088-spec reverse-flow-skill supplies Codex workflow gate evidence for
`p2-skill-route-discovery-local-test`, and zhengxi-views supplies generic plus
source-cited skill-workflow evidence for `p1-skill-route-discovery-index`.
Both rows may select only documentation, config, test, or code_patch lanes;
`skill_route_discovery_first` is required for the reverse-flow Codex gate before
any secondary agent-harness interpretation.

Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-fixture`. They do not inherit `skill_route_discovery`,
and direct runtime or direct code_patch lanes remain disabled until local
harness evaluation exists. The pass-2 controller surfaces expose focused review,
operator replay, acceptance, and supervisor handoff status while denying
runtime action, upstream skill activation, external harness execution, provider
launch, remote execution, raw source URL export, replay-command export,
target-path export, and upstream-body export.

## Current Digest 20260703T034049 Pass 4

The `github-growth-20260703T034049.949785Z` final pass completes the active
skill-route-discovery window with a current proposal handoff. The
lingbol088-spec reverse-flow-skill item remains a Codex workflow-gate evidence
row because its public shape carries Agent/Codex skill packaging,
`skills/reverse-flow/SKILL.md`, references, scripts, and local sandbox/CTF
workflow framing. It maps to `p1-skill-route-discovery-codex-workflow` in the
local test lane and must record `skill_route_discovery_first` before any
secondary workflow or harness interpretation.

The generic skill workflow proposal
`p2-generic-skill-workflow-routing` is evidence-item interpretation only:
reverse-flow-skill and zhengxi-views may select documentation, config, test, or
code_patch after local validation, but they do not grant install, runtime
execution, provider launch, external skill activation, or raw upstream export.
Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and Fundamental-Ava
stay in `agent_harness_eval_required` under `p3-agent-harness-eval-fixtures`.
They do not inherit `skill_route_discovery`; direct lanes before harness
evaluation are empty, and only documentation, test, or code_patch may be
considered after local harness evidence exists. The pass-4 recovery packet
requires rollback metadata plus focused validation and leaves replay, promotion,
restart, and activation to the configured supervisor.

## Current Digest 20260703T044050 Pass 3

The `github-growth-20260703T044050.250851Z` pass-3 lane binds the active
skill-route-discovery slice to `current_digest_pass3_route_to_validation_lane`.
zhengxi-views is the source-cited skill workflow validation row for
`p1-skill-route-discovery-zhengxi-views`; reverse-flow-skill is the Codex
workflow-gate row for `p2-codex-skill-workflow-gate-reverse-flow`. Both rows
select the local test lane before activation. The reverse-flow row keeps
code_patch as a queued bounded lane, but only after `skill_route_discovery_first`
is proven by focused local validation.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld`. They do not inherit
`skill_route_discovery`, direct runtime, direct code_patch, provider launch,
external harness execution, or remote execution. The pass-3 surface exports
selected item IDs, proposal IDs, route profiles, lane names, source hashes, and
replay command hashes rather than raw source URLs, replay commands, target
paths, provider inputs, upstream bodies, or activation authority.

## Current Digest 20260703T050050 Pass 4

The `github-growth-20260703T050050.256364Z` final pass closes the active
skill-route-discovery slice through `current_digest_pass4_completion_handoff`.
The handoff maps reverse-flow-skill and zhengxi-views through
`p1-skill-route-discovery-lane`, selecting only bounded local lanes:
documentation, config, test, or code_patch. The current selected lane is test,
and runtime action remains `none`.

The mixed agent, Codex, and skill signal from reverse-flow-skill is also exposed
through `p2-codex-workflow-gate-coverage`. That row must record
`skill_route_discovery_first` before any secondary workflow, implementation, or
runtime interpretation. Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-eval-fixtures`; they
do not inherit `skill_route_discovery`, have no direct lanes before harness
evaluation, and may only move to documentation, test, or code_patch after local
harness evidence exists.

The pass-4 operator recovery packet requires rollback metadata and focused local
validation. It exports body-free proposal IDs, route profiles, lane names,
selected item IDs, source hashes, and replay command hashes while denying raw
source URL export, raw replay command export, upstream body export, external
skill activation, external agent activation, external harness execution,
provider runtime launch, remote execution, profile writes, and memory writes.

## Current Digest 20260703T100051 Pass 3

The `github-growth-20260703T100051.113454Z` pass-3 lane adds an operator-facing
validation packet for the active skill-route-discovery window. The
reverse-flow-skill and zhengxi-views rows are grouped under
`p1-skill-route-discovery-fixture` as local test-lane evidence only. The grouped
row must preserve the Codex workflow `skill_route_discovery_first` gate and the
source-cited/advice-boundary validation gate, and it may resolve only to
documentation, config, test, or code_patch.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3-agent-harness-smoke-tests`. The
operator packet also names `p2-agent-harness-eval-contract` so the documentation
contract and smoke-test route are visible before any general-agent
implementation lane can open. General-agent direct lanes before harness
evaluation are empty; after a local harness result, only documentation, test, or
code_patch may be considered. The pass-3 packet exports hashes and lane names,
not raw source URLs, replay commands, target paths, provider inputs, upstream
bodies, external activation, provider launch, remote execution, profile writes,
or memory writes.

## Current Digest 20260703T193923 Pass 1

The `github-growth-20260703T193923.799406Z` pass-1 lane adds a focused
reverse-flow validation surface for the active `skill-route-discovery` window.
`p1_reverse_flow_skill_discovery` groups TaoDevil and lingbol088-spec
reverse-flow-skill evidence as Codex workflow-gate rows. The selected local lane
is test, and the row must prove `skill_route_discovery_first` before any
documentation, config, test, or code_patch work can be considered for local
adoption.

`p2_generic_skill_workflow_probe` keeps zhengxi-views in the documentation lane
as a generic skill-workflow intake checklist. `p3_agent_harness_eval_baseline`
keeps agent-apprenticeship as adjacent `agent_harness_eval_required` evidence:
it does not inherit `skill_route_discovery`, has no direct runtime or code_patch
lane before local harness evaluation, and may only produce documentation, test,
or code_patch work after local harness evidence exists.

The pass-1 fixture exports body-free proposal IDs, selected item IDs, route
profiles, lane names, source hashes, and replay command hashes. It denies raw
source URL export, upstream body export, external skill activation, external
agent activation, external harness execution, provider runtime launch, remote
execution, profile writes, memory writes, and runtime action.

## Current Digest 20260704T000924 Pass 1

The `github-growth-20260704T000924.757419Z` pass-1 lane exposes the current
skill-route-discovery window through `current_digest_pass1_validation_lane`.
`proposal-skill-route-discovery-001` groups reverse-flow-skill and zhengxi-views
as explicit skill workflow evidence. The selected local lane is test, with
documentation, config, test, and code_patch as the only allowed local lanes.

`proposal-route-hint-policy-fixture-004` records the same evidence as a config
policy fixture so route hints remain bounded before activation. Qwen-AgentWorld
and Fundamental-Ava stay under `proposal-agent-harness-eval-002` as adjacent
`agent_harness_eval_required` rows. The workflow-only Seedance usecase item
stays under `proposal-workflow-usecase-classifier-003` and must pass local agent
harness evaluation before any documentation, test, or code_patch follow-up lane
can be selected.

The operator validation lane is replayable but not an activation route. It
exports proposal IDs, selected item IDs, route profiles, lane names, source
hashes, and replay command hashes while denying raw source URLs, raw replay
commands, upstream bodies, external skill activation, external agent activation,
external harness execution, provider runtime launch, remote execution, profile
writes, memory writes, and runtime action.

## Current Digest 20260704T200436 Pass 4

The `github-growth-20260704T200436.445375Z` pass-4 fixture closes the active
skill-route-discovery slice through the local-kernel completion handoff. The
selected skill evidence remains bounded to three local route profiles:
`codex_workflow_gate`, `generic_skill_workflow`, and
`source_cited_domain_research`.

`lingbol088-spec/reverse-flow-skill` is treated as a Codex workflow-gate skill
candidate. It can select only the local test lane after
`skill_route_discovery_first`; its install examples, runtime wording, and
reverse-engineering workflow remain diagnostic evidence, not activation
authority.

`lyra81604/zhengxi-views` remains a generic, source-cited skill workflow
candidate. Its fund-data and advice-boundary pressure is useful route evidence
for documentation or test follow-up, but trend metadata alone is insufficient
to run providers, fetch data, or produce investment-advice behavior.

`QwenLM/Qwen-AgentWorld` and the workflow-usecase cluster remain adjacent
`agent_harness_eval_required` pressure. They do not inherit
`skill_route_discovery` lanes, and the final closure manifest keeps external
skill activation, external agent activation, external harness execution,
provider launch, remote execution, profile writes, memory writes, raw replay
commands, raw source URLs, and upstream bodies denied.

Replay the current completion check with:
`python -m pytest tests/test_harness_eval.py -q -k 20260704T200436`.

## Current Digest 20260705T064819 Pass 4

The `github-growth-20260705T064819.468069Z` pass-4 fixture completes the
active skill-route-discovery slice through
`current_digest_pass4_completion_handoff`. The final handoff maps
`lingbol088-spec/reverse-flow-skill` to
`p1_reverse_flow_skill_route_discovery` in the local test lane and keeps its
install, script, reverse-workflow, and runtime pressure diagnostic only.

`NVIDIA-BioNeMo/bionemo-agent-toolkit` maps to
`p2_bionemo_skill_workflow_discovery` in the documentation lane. It is treated
as skill/workflow route evidence, not as an installable toolkit or provider
registration. The accepted lanes remain only documentation, config, test, or
code_patch, with local validation required before any controller recomputation
can choose final scope.

`QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under `p3_agent_harness_eval_queue`. They do
not inherit `skill_route_discovery`, direct runtime routing, direct code_patch
authority, external harness execution, provider launch, or remote execution
before bounded local harness evaluation exists.

The handoff is record-only for an external supervisor. It exports proposal IDs,
selected item IDs, route profiles, lane names, source hashes, and replay command
hashes while denying raw source URL export, raw replay command export, upstream
body export, external skill activation, external agent activation, external
harness execution, provider runtime launch, remote execution, profile writes,
memory writes, and runtime action. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T064819`.

## Current Digest 20260705T040819 Pass 4

The `github-growth-20260705T040819.295202Z` pass-4 fixture completes the
active skill-route-discovery slice through `current_digest_pass4_completion_handoff`.
`lingbol088-spec/reverse-flow-skill` remains a Codex workflow-gate skill
candidate and must prove `skill_route_discovery_first` before any workflow or
harness follow-up. Its install and runtime pressure is downgraded to
diagnostic evidence only.

`NVIDIA-BioNeMo/bionemo-agent-toolkit` is treated as generic agent-plus-skills
workflow evidence. It routes through `skill_route_discovery` and may open only
bounded local documentation, config, test, or code_patch lanes; the current
operator-visible lane is `code_patch` because this pass implements the local
normalization behavior.

`QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows. They do not inherit skill-route lanes, have
no direct lanes before harness evaluation, and may only produce documentation,
test, or code_patch follow-up after local harness evidence exists.

The handoff is record-only for an external supervisor. It exports body-free
proposal IDs, selected item IDs, route profiles, lane names, source hashes, and
replay command hashes while denying raw source URL export, raw replay command
export, upstream body export, external skill activation, external agent
activation, external harness execution, provider runtime launch, remote
execution, profile writes, memory writes, and runtime action. Replay with
`python -m pytest tests/test_skill_routing.py -q -k 20260705T040819`.

## Current Digest 20260705T052819 Pass 4

The `github-growth-20260705T052819.665146Z` pass-4 fixture completes the
active skill-route-discovery slice through
`current_digest_pass4_completion_handoff`. `lingbol088-spec/reverse-flow-skill`
maps to `p1-skill-route-discovery-reverse-flow` in the local test lane. It must
prove `skill_route_discovery_first`; upstream install, script, reverse workflow,
and runtime pressure remain diagnostic and do not activate external code.

`NVIDIA-BioNeMo/bionemo-agent-toolkit` maps to
`p2-skill-route-discovery-bionemo` in the documentation lane. Its skills CLI,
plugin marketplace, catalog, and domain workflow language are useful route
evidence, but the accepted local mapping is still only documentation, config,
test, or code_patch after focused validation.

`QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava` remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-general-agent-projects`. They do not inherit
`skill_route_discovery`, direct runtime routing, direct code_patch authority,
external harness execution, provider launch, or remote execution before bounded
local harness evaluation exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T052819`.

## Current Digest 20260704T035308 Pass 4

The `github-growth-20260704T035308.799236Z` pass-4 handoff completes the active
skill-route-discovery slice as a supervisor-visible local validation record.
The reverse-flow-skill evidence is a Codex workflow-gate row under
`p1-skill-route-discovery-codex-workflow`: it must expose
`skill_route_discovery_first`, select the local test lane, and stay within
documentation, config, test, or code_patch. The upstream install and runtime
pressure remains diagnostic and does not grant activation authority.

The zhengxi-views evidence remains under
`p2-generic-skill-route-discovery-doc` as a generic source-cited skill workflow
documentation lane. Link-Start reverse-flow fork evidence is retained only as
corroborating skill-route context; the pass-4 row uses the direct
lingbol088-spec source for the Codex workflow gate.

Awesome-Blender-Seedance-Workflow-Usecases, Qwen-AgentWorld, and
Fundamental-Ava remain adjacent `agent_harness_eval_required` rows under
`p3-agent-harness-eval-fixtures`. They do not inherit
`skill_route_discovery`, have no direct local lanes before harness evaluation,
and may only produce documentation, test, or code_patch follow-up after bounded
local harness evidence exists.

The handoff is record-only for an external supervisor. It exports body-free
proposal IDs, selected item IDs, route profiles, lane names, source hashes, and
replay command hashes while denying raw source URL export, raw replay command
export, upstream body export, external skill activation, external agent
activation, external harness execution, provider runtime launch, remote
execution, profile writes, memory writes, and runtime action.

## Current Digest 20260704T170435 Pass 3

The `github-growth-20260704T170435.079487Z` pass-3 lane specializes
`current_digest_pass3_route_to_validation_lane` for the active skill-route
window. It maps `zhengxi-views` to `p1-skill-route-discovery-zviews` in the
local test lane because its public evidence shows a skill package with
`SKILL.md`, `skill.yml`, references, evals, scripts, source-cited research
workflow language, and an advice boundary.

`reverse-flow-skill` maps to `p2-codex-skill-workflow-gate` in the local test
lane and must preserve `skill_route_discovery_first` before any Codex workflow
gate is treated as a local behavior candidate. Its install and runtime pressure
is retained only as downgraded unsupported-lane evidence.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-trending-projects`. They do not inherit
`skill_route_discovery`, have no direct lanes before local harness evaluation,
and may only produce documentation, test, or code_patch follow-up after bounded
agent-harness evidence exists.

The operator packet is body-free and record-only: it exports proposal IDs,
selected item IDs, route profiles, lane names, source hashes, and replay command
hashes while denying raw source URLs, raw replay commands, upstream bodies,
external skill activation, external agent activation, external harness
execution, provider runtime launch, remote execution, profile writes, memory
writes, and runtime action. Replay with
`python -m pytest tests/test_skill_routing.py -q -k 20260704T170435`.

## Current Digest 20260704T061309 Pass 3

The `github-growth-20260704T061309.969283Z` pass-3 operator lane exposes the
active skill-route-discovery window through
`current_source_digest_pass3_operator_lane`. `zhengxi-views` is selected through
its source-cited skill workflow profile and maps to a local test lane with both
generic workflow validation and source-citation/advice-boundary validation.

`reverse-flow-skill` is selected as Codex workflow-gate evidence under
`p2-codex-workflow-gate-reverse-flow-skill`. It must pass
`skill_route_discovery_first_before_workflow_gate` before any workflow or
controller change is considered, and its install or runtime pressure remains
diagnostic only.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-qwen-agentworld`. They do not inherit skill-route lanes,
cannot open direct runtime or code_patch routes before local harness evaluation,
and may only produce documentation, tests, or code_patch after bounded harness
evidence exists.

The packet is body-free and operator-visible: it exports proposal IDs, selected
item IDs, route profiles, lane names, source hashes, and replay command hashes
while denying raw source URL export, raw replay command export, upstream body
export, external skill activation, external agent activation, external harness
execution, provider runtime launch, remote execution, profile writes, memory
writes, and runtime action.

## Current Digest 20260704T065309 Pass 1

The `github-growth-20260704T065309.891207Z` pass-1 lane specializes
`current_digest_pass1_validation_lane` to the active proposal IDs.
`reverse-flow-skill` maps to
`p1_skill_route_discovery_for_codex_reverse_flow` in the local test lane. It
must preserve `skill_route_discovery_first` before any secondary Codex workflow,
install, runtime, provider, external skill activation, or remote execution path
is considered.

`zhengxi-views` maps to `p2_generic_skill_workflow_route_probe` in the
documentation lane. The local validation path records only selected evidence
item IDs and body-free route metadata, then maps skill workflow evidence into
documentation, config, test, or code_patch candidates after focused local
validation.

Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under
`p3_agent_harness_eval_for_agentworld`. They do not inherit
`skill_route_discovery`, have no direct local lanes before bounded harness
evaluation, and cannot become direct code_patch, runtime, provider, external
harness, or remote-execution candidates from trend evidence alone. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260704T065309`.

## Current Digest 20260704T063309 Pass 4

The `github-growth-20260704T063309.450936Z` final pass closes the active
skill-route-discovery window through `current_digest_pass4_completion_handoff`.
The pass binds `p1_reverse_flow_skill_route_discovery`,
`p2_zhengxi_views_skill_probe`, and `p3_agentworld_harness_eval` to a
supervisor-visible replay record.

The reverse-flow-skill signal includes the direct `lingbol088-spec` repository
and the observed `iunclear` fork. The local fixture records the fork with
`forked_from_url`, so registry construction collapses both items into one
reverse-flow lineage candidate. That row selects the local test lane, keeps
`skill_route_discovery_first`, treats install and runtime pressure as diagnostic
only, and does not create a separate activation candidate for fork activity.

The zhengxi-views row remains a documentation lane for generic source-cited
skill workflow criteria. Qwen-AgentWorld and Fundamental-Ava remain adjacent
`agent_harness_eval_required` rows under `p3_agentworld_harness_eval`; they do
not inherit skill-route lanes and have no direct runtime or code_patch lane
before bounded local harness evaluation.

The handoff is record-only for an external supervisor. It exports body-free
proposal IDs, selected item IDs, route profiles, lane names, source hashes, and
replay command hashes while denying raw source URL export, raw replay command
export, upstream body export, external skill activation, external agent
activation, external harness execution, provider runtime launch, remote
execution, profile writes, memory writes, and runtime action.

## Current Digest 20260705T050821 Pass 3

The `github-growth-20260705T050821.175166Z` pass-3 lane specializes
`current_digest_pass3_route_to_validation_lane` for the active skill route
discovery window. It turns the carried reverse-flow and BioNeMo evidence into
operator-visible local validation rows before any activation path.

`lingbol088-spec/reverse-flow-skill` and the carried
`LLLL2266/reverse-flow-skill` fork-lineage signal collapse into one
reverse-flow candidate. The row maps to
`p1_reverse_flow_skill_route_discovery` in the local test lane, records both
selected evidence item IDs, preserves `skill_route_discovery_first`, and treats
install, execute, and runtime pressure as downgraded diagnostics rather than
as implementation evidence.

`NVIDIA-BioNeMo/bionemo-agent-toolkit` maps to
`p3_bionemo_skill_route_probe` in the local test lane as generic agent-toolkit
skill workflow evidence. The same skill evidence also feeds
`p2_skill_workflow_documentation_lane`, which is the documentation decision
path for public repositories that mention skills, routes, plugins, catalogs,
or workflows but still require local validation before documentation, config,
test, or code_patch work.

Qwen-AgentWorld, Fundamental-Ava, and
Awesome-Blender-Seedance-Workflow-Usecases remain adjacent
`agent_harness_eval_required` rows under
`p3-agent-harness-eval-for-general-agent-trends`. They do not inherit
skill-route lanes, cannot open direct runtime or code_patch routes before local
harness evaluation, and may only produce documentation, tests, or code_patch
after bounded harness evidence exists.

The lane exports proposal IDs, selected evidence item IDs, route profiles,
lane names, source hashes, and replay command hashes. It denies raw source URL
export, raw evidence URL export, raw replay command export, upstream body
export, external skill activation, external agent activation, external harness
execution, provider runtime launch, remote execution, profile writes, memory
writes, and runtime action. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260705T050821`.

## Current Digest 20260706T151555 Pass 2

The pass-2 validation packet now exposes `route_priority_policy` and
`route_validation_queue` for mixed reverse-flow plus general-agent evidence.
The queue is body-free priority metadata: explicit `skill_route_discovery`
rows validate first through documentation, config, test, or code_patch lanes;
adjacent general-agent projects with no skill-route hint remain queued behind
`agent_harness_eval_required` and have no direct implementation lane before
bounded harness evaluation.

For the current window, `lingbol088-spec/reverse-flow-skill` is the priority-0
skill route and selects the local test lane. Shepherd, Agents-A1,
Qwen-AgentWorld, and Fundamental-Ava are priority-10 agent-harness rows. The
packet keeps runtime action, external skill activation, external harness
execution, provider launch, remote execution, raw source URL export, and
upstream body export disabled for every queued row. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k current_digest_pass2_prioritizes_route_hints`.

## Source Digest 20260706T231555 Pass 2

The pass-2 lane adds `skill_route_discovery_repository_lane_probe` as a
body-free pre-activation surface for repository metadata. The probe is meant
for evidence shaped like `lingbol088-spec/reverse-flow-skill`: public Codex or
AI Agent skill packages with `skills/.../SKILL.md`, references, scripts, local
sandbox framing, install/run examples, and workflow language.

The probe maps those signals only into the bounded local lanes:
documentation, config, test, and code_patch. Existing route-profile preference
still chooses the local test lane for Codex workflow-gate evidence. Install,
run, execute, provider runtime, or remote execution pressure is recorded as
stripped diagnostic pressure and never becomes a lane. Ambiguous repositories
that merely mention Codex, workflow, or developer skill without a skill package
signal are reported as ignored rows instead of inheriting skill-route lanes.

The output exports source hashes, route profiles, matched terms, layout and
metadata signal names, selected local lanes, and diagnostic pressure. It denies
runtime action, external skill activation, external harness execution, provider
runtime launch, remote execution, raw source URL export, evidence URL export,
and upstream body export. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k repository_lane_probe`.

## Source Digest 20260707T030834 Pass 2

The `github-growth-20260707T030834.667753Z` pass-2 window keeps
`lingbol088-spec/reverse-flow-skill` in `skill_route_discovery` and routes the
adjacent general-agent and workflow-topic repositories through
`agent_harness_eval_lane`. The harness lane now exposes an explicit
`implementation_readiness_contract.promotion_gate` for the general-agent side
of the split.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`,
`shepherd-agents/shepherd`, and
`Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` must show complete
project-shape probes, mapped local claims, bounded follow-up lanes, and passing
per-project result rows before documentation, test, or code_patch follow-up is
promoted. The gate is still local and body-free: direct behavior adoption,
pre-eval implementation patches, runtime action, external harness execution,
provider launch, remote execution, raw source URLs, and upstream bodies remain
disabled. Replay with:
`python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or 20260707T030834"`.

## Source Digest 20260707T054834 Pass 2

The `github-growth-20260707T054834.215350Z` pass-2 lane exposes
`skill_route_discovery_current_digest_pass2_skill_workflow_route_discovery` for
paired skill workflow evidence. `lingbol088-spec/reverse-flow-skill` remains a
Codex workflow-gate row and must preserve both `codex_workflow_gate` and
`generic_skill_workflow` profiles before selecting the local test lane.
`Pluviobyte/rnskill` remains a generic skill workflow row and selects the
documentation lane. Both rows may expose only documentation, config, test, or
code_patch lanes; install, enable, run, plugin marketplace, provider, runtime,
external skill activation, and remote-execution wording is diagnostic pressure
only.

Agents-A1, Fundamental-Ava, and Shepherd remain adjacent
`agent_harness_eval_required` rows. They do not inherit `skill_route_discovery`,
open no direct implementation lane before bounded harness evaluation, and may
only produce documentation, test, or code_patch follow-up after local harness
evidence exists. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T054834`.

## Source Digest 20260707T102834 Pass 3

The `github-growth-20260707T102834.622372Z` pass-3 lane exposes
`skill_route_discovery_current_digest_20260707T102834_pass3_validation_lane`
for the active reverse-flow, rnskill, and general-agent project window.

`lingbol088-spec/reverse-flow-skill` remains the Codex workflow-gate skill row.
It selects the local test lane, preserves `skill_route_discovery_first`, and
keeps install, run, script, provider, runtime, and external harness wording as
diagnostic pressure only. `Pluviobyte/rnskill` remains the generic
`SKILL.md`-style workflow collection and is replayed through bounded
documentation/config validation metadata before any activation path.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows.
They do not inherit skill-route lanes, expose no direct implementation lane
before local harness evaluation, and may only produce documentation, test, or
code_patch follow-up after bounded agent-harness evidence exists.

The lane is body-free and operator-visible. It exports proposal IDs, selected
item IDs, lane names, route profiles, source hashes, and validation command
hashes while denying raw source URL export, raw evidence URL export, replay
command export, upstream body export, external skill or agent activation,
external harness execution, provider launch, remote execution, profile writes,
memory writes, and runtime action. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T102834`.

## Source Digest 20260707T164109 Pass 3

The `github-growth-20260707T164109.440819Z` pass-3 lane exposes
`skill_route_discovery_current_digest_20260707T164109_pass3_validation_lane`
and its
`skill_route_discovery_current_digest_20260707T164109_pass3_activation_review_packet`.
This is a validation-before-activation surface for the active reverse-flow and
rnskill proposals, not authority to install, run, or activate upstream skills.

`lingbol088-spec/reverse-flow-skill` maps to the bounded local test lane as a
Codex workflow-gate skill-route row. `Pluviobyte/rnskill` maps to the bounded
documentation lane as generic skill-workflow evidence. Both rows preserve only
documentation, config, test, and code_patch as local outputs. Requested
implementation scope and validation-gate wording from proposal evidence are
ignored and recomputed by controller code as `local_validation_candidate` with
focused local validation.

`InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and
`shepherd-agents/shepherd` remain adjacent `agent_harness_eval_required` rows.
They inherit no skill-route lane, expose no direct pre-eval implementation
lane, and may only proceed to documentation, test, or code_patch after local
agent-harness evidence exists.

The lane is body-free: it exports selected item IDs, proposal IDs, lane names,
route profiles, source hashes, and validation command hashes while denying raw
source URLs, raw evidence URLs, replay commands, upstream bodies, external
skill or agent activation, external harness execution, provider launch, memory
writes, remote execution, and runtime action. Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T164109`.

## Source Digest 20260707T170109 Pass 4

The `github-growth-20260707T170109.447884Z` pass-4 handoff exposes
`skill_route_discovery_current_digest_20260707T170109_pass4_completion_handoff`
as the completion surface for the skill-route policy lane. It binds
`p1-skill-route-discovery-fixture`,
`p2-agent-harness-eval-shepherd`, and
`p4-route-hint-policy-regression` to local validation metadata only.

`hdz717/reverse-flow-skill` and `lingbol088-spec/reverse-flow-skill` map to
bounded local test rows under `skill_route_discovery`; `Pluviobyte/rnskill`
maps to the bounded documentation row. All skill rows allow only
documentation, config, test, or code_patch lanes and keep `runtime_action` as
`none`.

`InternScience/Agents-A1`, `shepherd-agents/shepherd`, and
`shepherd-agents/shepherd` PR #33 remain `agent_harness_eval_required` rows.
They have no direct local lanes before bounded harness evaluation and may only
produce documentation, test, or code_patch follow-up after evaluation.

The route-hint policy regression records that `skill_route_discovery` maps only
to documentation, config, test, or code_patch and `agent_harness_eval` maps
only to documentation, test, or code_patch. Route hints are not permission
grants and do not authorize runtime action, external skill activation, external
harness execution, provider launch, remote execution, promotion, or restart.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k 20260707T170109`.

## Source Digest 20260707T182110 Pass 4 Completion

The `github-growth-20260707T182110.051391Z` final pass uses the reusable
`skill_route_discovery_active_pass4_operator_activation_packet` rather than a
new standalone fixture. The packet now includes
`skill_route_discovery_active_pass4_operator_review_dossier`, a body-free
operator review surface derived from the pass-4 completion matrix.

The reviewed evidence keeps `Pluviobyte/rnskill` as a generic SKILL.md
collection, `lingbol088-spec/reverse-flow-skill` as a Codex workflow-gate skill
route, and `shepherd-agents/shepherd` as adjacent general-agent runtime
substrate evidence. Skill rows may complete only through documentation, config,
test, or code_patch lanes with `local_validation_required` preserved. Adjacent
general-agent rows remain in `agent_harness_eval_required`, inherit no
skill-route lane, and expose no direct implementation lane before local harness
evaluation.

The dossier records selected lane summaries, selected evidence counts, hashed
replay command counts, rollback ref/artifact requirements, adjacent
agent-harness queue state, and explicit activation denials. It exports no raw
source URLs, evidence URLs, replay commands, target paths, or upstream bodies,
and grants no runtime action, external skill activation, external harness
execution, provider launch, remote execution, promotion, or restart authority.
Replay with:
`python -m pytest tests/test_skill_routing.py -q -k active_pass4_operator_activation_packet`.

## 20260708T090635 Pass-2 Lane

The `github-growth-20260708T090635.452817Z` skill-route-discovery pass-2
window reuses the reverse-flow/rnskill pass-2 lane family and emits
`skill_route_discovery_current_digest_20260708T090635_pass2_validation_lane`.
The lane keeps `lingbol088-spec/reverse-flow-skill` as
`skill_route_discovery_first` in the local `test` lane, maps
`Pluviobyte/rnskill` to the `generic_skill_workflow` documentation lane, and
queues Shepherd, Hy3, and the Blender/Seedance workflow-usecase repository only
as `agent_harness_eval_required`.

The lane exports selected item ids, route profiles, lane names, hashes, and
operator decisions only. It does not export upstream bodies, source URLs,
target paths, raw replay commands, or activation authority, and it keeps
external skill activation, external harness execution, provider launch, memory
writes, and remote execution denied. Replay with
`python -m pytest tests/test_skill_routing.py -q -k 20260708T090635`.
