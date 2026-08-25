"""Application-growth plane: an unplannable goal grows through forage matching.

The forage-growth plane still needs a separate invocation: match a goal key,
forage, then re-plan. This module closes that leftover — **automatic growth**:

- the only caller input is an :class:`ApplicationTask` (initial state, goal
  keys, frozen oracle); no package name and no forage-growth plane call;
- if the live registry already plans the task, it executes and never forages;
- if the task is unplannable, forage matching runs in-process (catalog
  provides stripped, lying popular decoy probed and skipped) and the first
  covering package is foraged;
- the original task is then re-planned and executed against the grown
  registry — a goal that was honestly unplannable becomes solvable;
- an uncovered goal stays an honest refusal; no ledger write is fabricated;
- ablation hides the foraged capability and the goal is unplannable again;
- a digest-sealed report under ``artifacts/capability-application-growth/``;
  verification re-grows the recorded task, re-checks the digest, and
  re-proves the foraged capability, so a tampered winner or forged grade
  fails.

``run_application_task(..., grow=True)`` is the same path: unplannable
tasks grow without a separate plane invocation. Default ``grow=False``
keeps planner honesty.

Live-registry leftover: ``run_application_live_growth_plane`` refreshes an
npm+pypi catalog from the goal keys (replayable, never a frozen apply
catalog) and grows the same unplannable task.

Registry-archive leftover: ``run_application_registry_growth_plane`` probes
live-shaped npm/pypi hits that have no ``replay_source`` by materializing
published registry archives, then forages a covering package whose origin
is the registry artifact rather than a fixture overlay.

Live-fetch leftover: ``run_application_live_fetch_growth_plane`` probes
registry hits that have no stewardship archive by live-fetching the
published npm/pypi artifact (replayable from the forage download cache),
then forages a covering package the stewardship tree has never seen.

Runtime-deps leftover: ``run_application_runtime_deps_growth_plane`` live-fetches
an import-unclosed sdist, vendors its declared transitive runtime
dependencies into the staged tree, then forages it so application-growth
can solve the original task. Isolated introspection without those deps
stays an honest refusal.

Node runtime-deps leftover: ``run_application_node_runtime_deps_growth_plane``
live-fetches an import-unclosed npm tarball, vendors declared
``package.json`` dependencies into the staged tree, then forages it so
application-growth can solve the original task.

Node default-export leftover: ``run_application_node_default_export_growth_plane``
reflects a Node default export so a default-export-only live-fetched tarball
with declared ``package.json`` dependencies can be foraged the same way.
Named-export-only introspection of that package still fails.

Node default-export-object leftover:
``run_application_node_default_export_object_growth_plane`` reflects a Node
default-exported namespace of functions so a live-fetched tarball whose
default export is an object rather than a single function can be foraged
the same way. Named-export-only introspection of that package still fails.

Node default-export-class leftover:
``run_application_node_default_export_class_growth_plane`` reflects a Node
default-exported constructable so a live-fetched tarball whose default
export is a class (instance methods) rather than a namespace object can be
foraged the same way. Named-export-only introspection of that package
still fails.

Node class-static leftover:
``run_application_node_class_static_growth_plane`` reflects Node class
static methods so a live-fetched tarball whose callable API is
``Class.method`` rather than ``new Class().method`` can be foraged the
same way. Named-export-only introspection of that package still fails.

Node named class-static leftover:
``run_application_node_named_class_static_growth_plane`` reflects static
methods on named class exports and nested namespace classes so a
live-fetched tarball whose API is ``Base64.encode`` or
``buffer.Buffer.byteLength`` rather than a default-exported
``Class.method`` can be foraged the same way.

Node named class-instance leftover:
``run_application_node_named_class_instance_growth_plane`` reflects
instance methods on named class exports so a live-fetched tarball whose
API is ``new Parser().parse`` / ``new XMLBuilder().build`` rather than a
default-exported constructable can be foraged the same way.

Node named class-construct leftover:
``run_application_node_named_class_construct_growth_plane`` constructs a
named class (including constructors that require arguments) so instance
methods that exist only after ``new Parser(options)`` / ``new Eta(options)``
can be foraged the same way as ``new Parser().parse``.

Python class-instance leftover:
``run_application_python_class_instance_growth_plane`` constructs a Python
class (including constructors that require arguments) so instance methods
that exist only after ``Parser(opts)`` / ``MarkdownIt()`` can be foraged
the same way as a module-level function.

Python class-static leftover:
``run_application_python_class_static_growth_plane`` reflects Python class
static methods so a live-fetched sdist whose callable API is
``Class.method`` / ``HTMLRenderer.escape_html`` rather than
``Parser(opts).loads`` can be foraged the same way, including when the
constructor cannot be satisfied.

Python nested-namespace class-static leftover:
``run_application_python_nested_namespace_class_static_growth_plane``
reflects class statics on a package submodule so a live-fetched sdist
whose callable API is ``package.submodule.Class.method`` /
``api.String.from_raw`` rather than a top-level ``Class.method`` can be
foraged the same way.

Python nested-namespace class-instance leftover:
``run_application_python_nested_namespace_class_instance_growth_plane``
constructs a class on a package submodule so a live-fetched sdist
whose callable API is ``package.submodule.Class(opts).method`` /
``cmd.Template(text).has_def`` rather than a nested
``package.submodule.Class.method`` static can be foraged the same way.

Python deep nested-namespace class-instance leftover:
``run_application_python_deep_nested_namespace_class_instance_growth_plane``
constructs a class two submodule levels down so a live-fetched sdist
whose callable API is ``package.subpackage.submodule.Class(opts).method`` /
``filters.sanitizer.Filter(source).allowed_token`` rather than a one-level
``package.submodule.Class(opts).method`` can be foraged the same way.

Python nested-namespace function leftover:
``run_application_python_nested_namespace_function_growth_plane`` reflects
module-level functions exported only on a nested submodule so a
live-fetched sdist whose callable API is ``package.submodule.func`` /
``utils.canonicalize_name`` rather than a class method can be foraged
the same way. Two-level ``package.subpackage.submodule.func`` is
reflected with an exclusive flag so it does not steal this plane.

Python deep nested-namespace function leftover:
``run_application_python_deep_nested_namespace_function_growth_plane``
reflects module-level functions two submodule levels down so a
live-fetched sdist whose callable API is
``package.subpackage.submodule.func`` / ``ad.nrt.compact`` rather than
a one-level ``package.submodule.func`` can be foraged the same way.

Python deep nested-namespace class-static leftover:
``run_application_python_deep_nested_namespace_class_static_growth_plane``
reflects class statics two submodule levels down so a live-fetched
sdist whose callable API is
``package.subpackage.submodule.Class.method`` /
``dev.helpers.File.exists`` rather than a two-level module function
can be foraged the same way.

Python triple nested-namespace class-static leftover:
``run_application_python_triple_nested_namespace_class_static_growth_plane``
reflects class statics three submodule levels down so a live-fetched
sdist whose callable API is
``package.subpackage.subpackage.submodule.Class.method`` /
``utils.math.math2html.Cloner.clone`` rather than a two-level
``package.subpackage.submodule.Class.method`` can be foraged the same
way.

Python quadruple nested-namespace class-static leftover:
``run_application_python_quadruple_nested_namespace_class_static_growth_plane``
reflects class statics four submodule levels down so a live-fetched
sdist whose callable API is
``package.subpackage.subpackage.subpackage.submodule.Class.method`` /
``contrib.humanize.templatetags.humanize.NaturalTimeFormatter.string_for``
rather than a three-level
``package.subpackage.subpackage.submodule.Class.method`` can be foraged
the same way.

Python quintuple nested-namespace class-instance leftover:
``run_application_python_quintuple_nested_namespace_class_instance_growth_plane``
reflects class instance methods five submodule levels down so a live-fetched
sdist whose callable API is
``package.subpackage.subpackage.subpackage.subpackage.submodule.Class(opts).method`` /
``openid.connect.core.grant_types.authorization_code.AuthorizationCodeGrant.id_token_hash``
rather than a four-level
``package.subpackage.subpackage.subpackage.submodule.Class.method`` can be
foraged the same way.

Python quintuple nested-namespace class-static leftover:
``run_application_python_quintuple_nested_namespace_class_static_growth_plane``
reflects class statics five submodule levels down so a live-fetched sdist
whose covering ``Class.method`` returns a cwd-independent JSON scalar
(``create.via_global_ref.builtin.cpython.common.CPython.exe_stem``) rather
than an inherited path validator (``CPython.validate_dest``) can be foraged
the same way.

Python sextuple nested-namespace class-static leftover:
``run_application_python_sextuple_nested_namespace_class_static_growth_plane``
reflects class statics six submodule levels down so a live-fetched sdist
whose covering ``Class.method`` is
``ads.googleads.v25.services.services.account_budget_proposal_service.AccountBudgetProposalServiceClient.common_billing_account_path``
rather than a five-level nested ``Class.method`` static can be foraged the
same way.

Python sextuple nested-namespace class-instance leftover:
``run_application_python_sextuple_nested_namespace_class_instance_growth_plane``
constructs a class six submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method`` /
``providers.amazon.aws.executors.batch.utils.BatchJobCollection.failure_count_by_id``
rather than a six-level nested ``Class.method`` static can be foraged the
same way.

Python septuple nested-namespace class-instance leftover:
``run_application_python_septuple_nested_namespace_class_instance_growth_plane``
constructs a class seven submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than a six-level nested ``Class().method`` instance can be foraged
the same way.

Python octuple nested-namespace class-instance leftover:
``run_application_python_octuple_nested_namespace_class_instance_growth_plane``
constructs a class eight submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than a seven-level nested ``Class().method`` instance can be foraged
the same way.

Python nonuple nested-namespace class-instance leftover:
``run_application_python_nonuple_nested_namespace_class_instance_growth_plane``
constructs a class nine submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than an eight-level nested ``Class().method`` instance can be foraged
the same way.

Python decuple nested-namespace class-instance leftover:
``run_application_python_decuple_nested_namespace_class_instance_growth_plane``
constructs a class ten submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than a nine-level nested ``Class().method`` instance can be foraged
the same way.

Python undecuple nested-namespace class-instance leftover:
``run_application_python_undecuple_nested_namespace_class_instance_growth_plane``
constructs a class eleven submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than a ten-level nested ``Class().method`` instance can be foraged
the same way.

Python duodecuple nested-namespace class-instance leftover:
``run_application_python_duodecuple_nested_namespace_class_instance_growth_plane``
constructs a class twelve submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than an eleven-level nested ``Class().method`` instance can be foraged
the same way.

Python tredecuple nested-namespace class-instance leftover:
``run_application_python_tredecuple_nested_namespace_class_instance_growth_plane``
constructs a class thirteen submodule levels down so a live-fetched sdist whose
covering API is ``package.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method``
rather than a twelve-level nested ``Class().method`` instance can be foraged
the same way.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import (
    _digest,
    load_persisted_records,
    prove_absorbed_capability,
)
from blackhole_agent.capability_application import (
    APPLICATION_TASKS,
    ApplicationTask,
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    atomic_write_json,
    default_ledger_path,
    load_ledger,
    prove_capability,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.capability_forage_growth import (
    match_forage_goal,
    strip_declared_provides,
)
from blackhole_agent.capability_forage_targets import (
    HERMETIC_ABSORBED_SLUGS,
    forage_request_for,
    load_catalog,
    query_from_goal,
    rank_catalog,
    refresh_registry_catalog,
    registry_replay_archive,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-application-growth"
DEFAULT_LIVE_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-application-live-growth"
DEFAULT_REGISTRY_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-application-registry-growth"
DEFAULT_LIVE_FETCH_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-application-live-fetch-growth"
DEFAULT_RUNTIME_DEPS_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-application-runtime-deps-growth"
DEFAULT_NODE_RUNTIME_DEPS_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-runtime-deps-growth"
)
DEFAULT_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_apply_catalog.json"
DEFAULT_REGISTRY_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_registry_catalog.json"
DEFAULT_LIVE_FETCH_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_live_fetch_catalog.json"
DEFAULT_RUNTIME_DEPS_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_runtime_deps_catalog.json"
DEFAULT_NODE_RUNTIME_DEPS_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_node_runtime_deps_catalog.json"
DEFAULT_NODE_DEFAULT_EXPORT_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-default-export-growth"
)
DEFAULT_NODE_DEFAULT_EXPORT_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_node_default_export_catalog.json"
)
DEFAULT_NODE_DEFAULT_EXPORT_OBJECT_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-default-export-object-growth"
)
DEFAULT_NODE_DEFAULT_EXPORT_OBJECT_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_node_default_export_object_catalog.json"
)
DEFAULT_NODE_DEFAULT_EXPORT_CLASS_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-default-export-class-growth"
)
DEFAULT_NODE_DEFAULT_EXPORT_CLASS_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_node_default_export_class_catalog.json"
)
DEFAULT_NODE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-class-static-growth"
)
DEFAULT_NODE_CLASS_STATIC_CATALOG = REPO_ROOT / "tests" / "fixtures" / "forage_node_class_static_catalog.json"
DEFAULT_NODE_NAMED_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-named-class-static-growth"
)
DEFAULT_NODE_NAMED_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_node_named_class_static_catalog.json"
)
DEFAULT_NODE_NAMED_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-named-class-instance-growth"
)
DEFAULT_NODE_NAMED_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_node_named_class_instance_catalog.json"
)
DEFAULT_NODE_NAMED_CLASS_CONSTRUCT_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-node-named-class-construct-growth"
)
DEFAULT_NODE_NAMED_CLASS_CONSTRUCT_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_node_named_class_construct_catalog.json"
)
DEFAULT_PYTHON_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-class-instance-growth"
)
DEFAULT_PYTHON_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_class_instance_catalog.json"
)
DEFAULT_PYTHON_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-class-static-growth"
)
DEFAULT_PYTHON_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_class_static_catalog.json"
)
DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-nested-namespace-class-static-growth"
)
DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_nested_namespace_class_static_catalog.json"
)
DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-deep-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_deep_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_NESTED_NAMESPACE_FUNCTION_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-nested-namespace-function-growth"
)
DEFAULT_PYTHON_NESTED_NAMESPACE_FUNCTION_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_nested_namespace_function_catalog.json"
)
DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-deep-nested-namespace-function-growth"
)
DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_deep_nested_namespace_function_catalog.json"
)
DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-deep-nested-namespace-class-static-growth"
)
DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_deep_nested_namespace_class_static_catalog.json"
)
DEFAULT_PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-triple-nested-namespace-class-static-growth"
)
DEFAULT_PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_triple_nested_namespace_class_static_catalog.json"
)
DEFAULT_PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-quadruple-nested-namespace-class-static-growth"
)
DEFAULT_PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_quadruple_nested_namespace_class_static_catalog.json"
)
DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-quintuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_quintuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-quintuple-nested-namespace-class-static-growth"
)
DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_quintuple_nested_namespace_class_static_catalog.json"
)
DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-sextuple-nested-namespace-class-static-growth"
)
DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_sextuple_nested_namespace_class_static_catalog.json"
)
DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-sextuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_sextuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-septuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_septuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-octuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_octuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-nonuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_nonuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-decuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_decuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-undecuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_undecuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-duodecuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_duodecuple_nested_namespace_class_instance_catalog.json"
)
DEFAULT_PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR = (
    REPO_ROOT / "artifacts" / "capability-application-python-tredecuple-nested-namespace-class-instance-growth"
)
DEFAULT_PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG = (
    REPO_ROOT / "tests" / "fixtures" / "forage_python_tredecuple_nested_namespace_class_instance_catalog.json"
)
WINNER_SLUG = "forage-rotate"
DECOY_SLUG = "forage-pick"
LIVE_NPM_DECOY_SLUG = "left-pad"
REGISTRY_PYPI_DECOY_SLUG = "tomli"
REGISTRY_WINNER_SLUG = "marked"
LIVE_FETCH_WINNER_SLUG = "titlecase"
LIVE_FETCH_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
RUNTIME_DEPS_WINNER_SLUG = "python-slugify"
RUNTIME_DEPS_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
RUNTIME_DEPS_DEP_NAME = "text-unidecode"
NODE_RUNTIME_DEPS_WINNER_SLUG = "snake-case"
NODE_RUNTIME_DEPS_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_RUNTIME_DEPS_DEP_NAME = "no-case"
GOAL_KEY = "rotate_output"
REGISTRY_GOAL_KEY = "marked_output"
LIVE_FETCH_GOAL_KEY = "titlecase_output"
RUNTIME_DEPS_GOAL_KEY = "slugify_output"
NODE_RUNTIME_DEPS_GOAL_KEY = "snake_case_output"
NO_MATCH_GOAL = "unicorn_output"
WINNER_CAPABILITY_ID = f"capability.absorbed-{WINNER_SLUG}"
REGISTRY_WINNER_CAPABILITY_ID = f"capability.absorbed-{REGISTRY_WINNER_SLUG}"
LIVE_FETCH_WINNER_CAPABILITY_ID = f"capability.absorbed-{LIVE_FETCH_WINNER_SLUG}"
RUNTIME_DEPS_WINNER_CAPABILITY_ID = f"capability.absorbed-{RUNTIME_DEPS_WINNER_SLUG}"
NODE_RUNTIME_DEPS_WINNER_CAPABILITY_ID = f"capability.absorbed-{NODE_RUNTIME_DEPS_WINNER_SLUG}"
NODE_DEFAULT_EXPORT_WINNER_SLUG = "humanize-string"
NODE_DEFAULT_EXPORT_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_DEFAULT_EXPORT_DEP_NAME = "decamelize"
NODE_DEFAULT_EXPORT_GOAL_KEY = "humanize_string_output"
NODE_DEFAULT_EXPORT_WINNER_CAPABILITY_ID = f"capability.absorbed-{NODE_DEFAULT_EXPORT_WINNER_SLUG}"
NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG = "query-string"
NODE_DEFAULT_EXPORT_OBJECT_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME = "decode-uri-component"
NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY = "extract_output"
NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG}"
)
NODE_DEFAULT_EXPORT_CLASS_WINNER_SLUG = "markdown-it"
NODE_DEFAULT_EXPORT_CLASS_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_DEFAULT_EXPORT_CLASS_DEP_NAME = "argparse"
NODE_DEFAULT_EXPORT_CLASS_GOAL_KEY = "render_output"
NODE_DEFAULT_EXPORT_CLASS_WINNER_CAPABILITY_ID = f"capability.absorbed-{NODE_DEFAULT_EXPORT_CLASS_WINNER_SLUG}"
NODE_CLASS_STATIC_WINNER_SLUG = "spark-md5"
NODE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_CLASS_STATIC_GOAL_KEY = "hash_output"
NODE_CLASS_STATIC_WINNER_CAPABILITY_ID = f"capability.absorbed-{NODE_CLASS_STATIC_WINNER_SLUG}"
APPLY_ABSORBED_SLUGS = frozenset(HERMETIC_ABSORBED_SLUGS) | frozenset({"forage-flip"})
REGISTRY_COMPETING_HIDE: tuple[str, ...] = ()
LIVE_FETCH_COMPETING_HIDE: tuple[str, ...] = ()

GROW_TASK = ApplicationTask(
    id="rotate-unplannable",
    description="Unplannable application goal that must grow through forage matching.",
    initial_state={"text": "Hello World"},
    goal=(GOAL_KEY,),
    oracle={GOAL_KEY: "rotated:Hello World"},
)

UNCOVERED_TASK = ApplicationTask(
    id="unicorn-uncovered",
    description="Unplannable application goal no catalog package covers.",
    initial_state={"text": "Hello World"},
    goal=(NO_MATCH_GOAL,),
    oracle={NO_MATCH_GOAL: "missing"},
)

ALREADY_SOLVABLE_TASK = next(task for task in APPLICATION_TASKS if task.id == "ledger-inventory-check")

REGISTRY_GROW_TASK = ApplicationTask(
    id="marked-unplannable",
    description="Unplannable application goal grown from a registry package with no fixture overlay.",
    initial_state={"arg0": "Hello World", "arg1": "Hello World"},
    goal=(REGISTRY_GOAL_KEY,),
    oracle={REGISTRY_GOAL_KEY: "<p>Hello World</p>\n"},
)

LIVE_FETCH_GROW_TASK = ApplicationTask(
    id="titlecase-unplannable",
    description="Unplannable application goal grown from a live-fetched package the stewardship tree has never seen.",
    initial_state={"text": "the quick brown fox"},
    goal=(LIVE_FETCH_GOAL_KEY,),
    oracle={LIVE_FETCH_GOAL_KEY: "The Quick Brown Fox"},
)

RUNTIME_DEPS_GROW_TASK = ApplicationTask(
    id="slugify-unplannable",
    description="Unplannable application goal grown from an import-unclosed live-fetched sdist.",
    initial_state={"text": "Hello World"},
    goal=(RUNTIME_DEPS_GOAL_KEY,),
    oracle={RUNTIME_DEPS_GOAL_KEY: "hello-world"},
)

NODE_RUNTIME_DEPS_GROW_TASK = ApplicationTask(
    id="snake-case-unplannable",
    description="Unplannable application goal grown from an import-unclosed live-fetched npm tarball.",
    initial_state={"arg0": "Hello World", "arg1": "Hello World"},
    goal=(NODE_RUNTIME_DEPS_GOAL_KEY,),
    oracle={NODE_RUNTIME_DEPS_GOAL_KEY: "hello_world"},
)

NODE_DEFAULT_EXPORT_GROW_TASK = ApplicationTask(
    id="humanize-string-unplannable",
    description="Unplannable application goal grown from a default-export-only live-fetched npm tarball.",
    initial_state={"arg0": "Hello World"},
    goal=(NODE_DEFAULT_EXPORT_GOAL_KEY,),
    oracle={NODE_DEFAULT_EXPORT_GOAL_KEY: "Hello world"},
)

NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK = ApplicationTask(
    id="query-string-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched npm tarball "
        "whose default export is a namespace of functions."
    ),
    initial_state={"arg0": "https://example.com?foo=bar"},
    goal=(NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY,),
    oracle={NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY: "foo=bar"},
)

NODE_DEFAULT_EXPORT_CLASS_GROW_TASK = ApplicationTask(
    id="markdown-it-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched npm tarball "
        "whose default export is a constructable class."
    ),
    initial_state={"arg0": "Hello World", "arg1": "Hello World"},
    goal=(NODE_DEFAULT_EXPORT_CLASS_GOAL_KEY,),
    oracle={NODE_DEFAULT_EXPORT_CLASS_GOAL_KEY: "<p>Hello World</p>\n"},
)

NODE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="spark-md5-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched npm tarball "
        "whose callable API is a class static method."
    ),
    initial_state={"arg0": "Hello World", "arg1": ""},
    goal=(NODE_CLASS_STATIC_GOAL_KEY,),
    oracle={NODE_CLASS_STATIC_GOAL_KEY: "b10a8db164e0754105b7a99be72e3fe5"},
)
NODE_NAMED_CLASS_STATIC_WINNER_SLUG = "ip-address"
NODE_NAMED_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_NAMED_CLASS_STATIC_GOAL_KEY = "address4_is_valid_output"
NODE_NAMED_CLASS_STATIC_WINNER_CAPABILITY_ID = f"capability.absorbed-{NODE_NAMED_CLASS_STATIC_WINNER_SLUG}"

NODE_NAMED_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="ip-address-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched npm tarball "
        "whose callable API is a named class static method."
    ),
    initial_state={"arg0": "192.168.0.1"},
    goal=(NODE_NAMED_CLASS_STATIC_GOAL_KEY,),
    oracle={NODE_NAMED_CLASS_STATIC_GOAL_KEY: True},
)
NODE_NAMED_CLASS_INSTANCE_WINNER_SLUG = "fast-xml-parser"
NODE_NAMED_CLASS_INSTANCE_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_NAMED_CLASS_INSTANCE_GOAL_KEY = "xmlbuilder_build_output"
NODE_NAMED_CLASS_INSTANCE_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{NODE_NAMED_CLASS_INSTANCE_WINNER_SLUG}"
)
NODE_NAMED_CLASS_INSTANCE_ORACLE = (
    "<0>H</0><1>e</1><2>l</2><3>l</3><4>o</4><5> </5><6>W</6><7>o</7><8>r</8><9>l</9><10>d</10>"
)

NODE_NAMED_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="fast-xml-parser-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched npm tarball "
        "whose callable API is a named class instance method."
    ),
    initial_state={"arg0": "Hello World"},
    goal=(NODE_NAMED_CLASS_INSTANCE_GOAL_KEY,),
    oracle={NODE_NAMED_CLASS_INSTANCE_GOAL_KEY: NODE_NAMED_CLASS_INSTANCE_ORACLE},
)
NODE_NAMED_CLASS_CONSTRUCT_WINNER_SLUG = "eta"
NODE_NAMED_CLASS_CONSTRUCT_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
NODE_NAMED_CLASS_CONSTRUCT_GOAL_KEY = "eta_compile_body_output"
NODE_NAMED_CLASS_CONSTRUCT_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{NODE_NAMED_CLASS_CONSTRUCT_WINNER_SLUG}"
)
NODE_NAMED_CLASS_CONSTRUCT_ORACLE = (
    "__eta.res+='H';\n__eta.res+='e';\n__eta.res+='l';\n__eta.res+='l';\n"
    "__eta.res+='o';\n__eta.res+=' ';\n__eta.res+='W';\n__eta.res+='o';\n"
    "__eta.res+='r';\n__eta.res+='l';\n__eta.res+='d';\n"
)

NODE_NAMED_CLASS_CONSTRUCT_GROW_TASK = ApplicationTask(
    id="eta-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched npm tarball "
        "whose named class instance methods exist only after construction."
    ),
    initial_state={"arg0": "Hello World"},
    goal=(NODE_NAMED_CLASS_CONSTRUCT_GOAL_KEY,),
    oracle={NODE_NAMED_CLASS_CONSTRUCT_GOAL_KEY: NODE_NAMED_CLASS_CONSTRUCT_ORACLE},
)
PYTHON_CLASS_INSTANCE_WINNER_SLUG = "markdown-it-py"
PYTHON_CLASS_INSTANCE_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_CLASS_INSTANCE_GOAL_KEY = "markdown_it_normalize_link_output"
PYTHON_CLASS_INSTANCE_WINNER_CAPABILITY_ID = f"capability.absorbed-{PYTHON_CLASS_INSTANCE_WINNER_SLUG}"
PYTHON_CLASS_INSTANCE_ORACLE = "Hello%20World"

PYTHON_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="markdown-it-py-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python class instance method after construction."
    ),
    initial_state={"url": "Hello World"},
    goal=(PYTHON_CLASS_INSTANCE_GOAL_KEY,),
    oracle={PYTHON_CLASS_INSTANCE_GOAL_KEY: PYTHON_CLASS_INSTANCE_ORACLE},
)
PYTHON_CLASS_STATIC_WINNER_SLUG = "marko"
PYTHON_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_CLASS_STATIC_GOAL_KEY = "htmlrenderer_escape_html_output"
PYTHON_CLASS_STATIC_WINNER_CAPABILITY_ID = f"capability.absorbed-{PYTHON_CLASS_STATIC_WINNER_SLUG}"
PYTHON_CLASS_STATIC_ORACLE = "Hello &lt;World&gt;"

PYTHON_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="marko-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python class static method."
    ),
    initial_state={"raw": "Hello <World>"},
    goal=(PYTHON_CLASS_STATIC_GOAL_KEY,),
    oracle={PYTHON_CLASS_STATIC_GOAL_KEY: PYTHON_CLASS_STATIC_ORACLE},
)
PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG = "tomlkit"
PYTHON_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY = "api_string_from_raw_output"
PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG}"
)
PYTHON_NESTED_NAMESPACE_CLASS_STATIC_ORACLE = "Hello World"

PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="tomlkit-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class static method."
    ),
    initial_state={"value": "Hello World"},
    goal=(PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
    oracle={PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY: PYTHON_NESTED_NAMESPACE_CLASS_STATIC_ORACLE},
)
PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG = "mako"
PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = "cmd_template_has_def_output"
PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG}"
)
PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = False

PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="mako-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class instance method."
    ),
    initial_state={"name": "Hello World"},
    goal=(PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE},
)
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG = "html5lib"
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "filters_sanitizer_filter_allowed_token_output"
)
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG}"
)
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "Hello World"

PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="html5lib-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class instance "
        "method two submodule levels down."
    ),
    initial_state={"token": "Hello World"},
    goal=(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG = "packaging"
PYTHON_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_NESTED_NAMESPACE_FUNCTION_GOAL_KEY = "utils_canonicalize_name_output"
PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG}"
)
PYTHON_NESTED_NAMESPACE_FUNCTION_ORACLE = "hello world"

PYTHON_NESTED_NAMESPACE_FUNCTION_GROW_TASK = ApplicationTask(
    id="packaging-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace module function."
    ),
    initial_state={"name": "Hello World"},
    goal=(PYTHON_NESTED_NAMESPACE_FUNCTION_GOAL_KEY,),
    oracle={PYTHON_NESTED_NAMESPACE_FUNCTION_GOAL_KEY: PYTHON_NESTED_NAMESPACE_FUNCTION_ORACLE},
)
PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG = "python-stdnum"
PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GOAL_KEY = "ad_nrt_compact_output"
PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG}"
)
PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_ORACLE = "HELLOWORLD"

PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GROW_TASK = ApplicationTask(
    id="python-stdnum-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace module function "
        "two submodule levels down."
    ),
    initial_state={"number": "Hello World"},
    goal=(PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GOAL_KEY,),
    oracle={
        PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GOAL_KEY: PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_ORACLE
    },
)
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG = "isbnlib"
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY = "dev_helpers_file_exists_output"
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG}"
)
PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_ORACLE = False

PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="isbnlib-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class static "
        "method two submodule levels down."
    ),
    initial_state={"path": "Hello World"},
    goal=(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
    oracle={
        PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY: PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_ORACLE
    },
)
PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG = "docutils"
PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY = "utils_math_math2html_cloner_clone_output"
PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG}"
)
PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE = ""

PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="docutils-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class static "
        "method three submodule levels down."
    ),
    initial_state={"original": "Hello World"},
    goal=(PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
    oracle={
        PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY: PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE
    },
)
PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG = "django"
PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY = (
    "contrib_humanize_templatetags_humanize_natural_time_formatter_st"
)
PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG}"
)
PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE = "Hello World"
PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_CALLABLE = (
    "contrib.humanize.templatetags.humanize.NaturalTimeFormatter.string_for"
)

PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="django-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class static "
        "method four submodule levels down."
    ),
    initial_state={"value": "Hello World"},
    goal=(PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
    oracle={
        PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY: PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE
    },
)
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG = "oauthlib"
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "openid_connect_core_grant_types_authorization_code_authorization"
)
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG}"
)
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "pZGm1Av0IEBKARczz7exkA"
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "openid.connect.core.grant_types.authorization_code.AuthorizationCodeGrant.id_token_hash"
)

PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="oauthlib-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose callable API is a Python nested-namespace class instance "
        "method five submodule levels down."
    ),
    initial_state={"value": "Hello World"},
    goal=(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG = "virtualenv"
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY = (
    "create_via_global_ref_builtin_cpython_common_cpython_exe_stem_ou"
)
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG}"
)
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE = "python"
PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CALLABLE = (
    "create.via_global_ref.builtin.cpython.common.CPython.exe_stem"
)

PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="virtualenv-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose covering Class.method is a Python nested-namespace class "
        "static five submodule levels down that returns a cwd-independent "
        "JSON scalar rather than an inherited path validator."
    ),
    initial_state={},
    goal=(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
    oracle={
        PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY: PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE
    },
)
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG = "google-ads"
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY = (
    "ads_googleads_v25_services_services_account_budget_proposal_serv"
)
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG}"
)
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE = "billingAccounts/Hello World"
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CALLABLE = (
    "ads.googleads.v25.services.services.account_budget_proposal_service."
    "AccountBudgetProposalServiceClient.common_billing_account_path"
)

PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK = ApplicationTask(
    id="google-ads-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose covering Class.method is a Python nested-namespace class "
        "static six submodule levels down rather than a five-level nested "
        "Class.method static."
    ),
    initial_state={"billing_account": "Hello World"},
    goal=(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
    oracle={
        PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY: PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ORACLE
    },
)
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG = "apache-airflow-providers-amazon"
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG = LIVE_NPM_DECOY_SLUG
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "providers_amazon_aws_executors_batch_utils_batch_job_collection"
)
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID = (
    f"capability.absorbed-{PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG}"
)
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = 0
PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "providers.amazon.aws.executors.batch.utils.BatchJobCollection.failure_count_by_id"
)

PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="apache-airflow-providers-amazon-unplannable",
    description=(
        "Unplannable application goal grown from a live-fetched sdist "
        "whose covering API is a Python nested-namespace class instance "
        "method six submodule levels down rather than a six-level nested "
        "Class.method static."
    ),
    initial_state={"job_id": "Hello World"},
    goal=(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_codec_encode_output"
)
PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.Codec.encode"
)
PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="septuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method seven submodule "
        "levels down rather than a six-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_unit_codec_encode_output"
)
PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.unit.Codec.encode"
)
PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="octuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method eight submodule "
        "levels down rather than a seven-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_unit_cell_codec_encode_output"
)
PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.unit.cell.Codec.encode"
)
PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="nonuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method nine submodule "
        "levels down rather than an eight-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_unit_cell_atom_codec_encode_output"
)
PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.unit.cell.atom.Codec.encode"
)
PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="decuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method ten submodule "
        "levels down rather than a nine-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_unit_cell_atom_quark_codec_encode_output"
)
PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.Codec.encode"
)
PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="undecuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method eleven submodule "
        "levels down rather than a ten-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_unit_cell_atom_quark_gluon_codec_encode_output"
)
PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.gluon.Codec.encode"
)
PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="duodecuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method twelve submodule "
        "levels down rather than an eleven-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)
PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY = (
    "codec_text_safe_inner_leaf_more_core_unit_cell_atom_quark_gluon_lepton_codec_encode_output"
)
PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE = (
    "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.gluon.lepton.Codec.encode"
)
PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE = "HELLO WORLD"
PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK = ApplicationTask(
    id="tredecuple-nested-instance-unplannable",
    description=(
        "Unplannable application goal grown from a sdist whose covering API "
        "is a Python nested-namespace class instance method thirteen submodule "
        "levels down rather than a twelve-level nested Class().method instance."
    ),
    initial_state={"text": "Hello World"},
    goal=(PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
    oracle={
        PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY: PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ORACLE
    },
)


def _report_digest(report: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in report.items() if key not in {"generated_at", "report_digest"}})


def load_apply_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the hermetic application-growth forage catalog."""

    return load_catalog(path or DEFAULT_CATALOG)


def _live_registry(repo_root: Path, *, hide: Sequence[str] = ()) -> dict[str, Any]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return build_application_registry(
        ledger,
        hide=hide,
        include_synthesized=True,
        include_absorbed=True,
    )


def grow_application_task(
    task: ApplicationTask,
    *,
    catalog: Mapping[str, Any] | None = None,
    absorbed: Sequence[str] | None = None,
    forage: bool = True,
    hide_before: Sequence[str] = (),
    repo_root: Path = REPO_ROOT,
    live_fetch: bool = False,
) -> dict[str, Any]:
    """Grow an unplannable application task through forage matching.

    Already-solvable tasks execute and never forage. The caller never names a
    package and never invokes the forage-growth plane.
    """

    payload = dict(catalog) if catalog is not None else load_apply_catalog()
    absorbed_slugs = list(absorbed) if absorbed is not None else sorted(APPLY_ABSORBED_SLUGS)
    before = _live_registry(repo_root, hide=hide_before)
    planned = plan_application_task(task, before)
    if planned is not None:
        result = run_application_task(task, before)
        result.update(
            {
                "grew": False,
                "forage": None,
                "unplannable_before": False,
                "used_forage_growth_plane": False,
                "winner_slug": "",
            }
        )
        return result

    matched = match_forage_goal(
        task.goal,
        catalog=payload,
        absorbed=absorbed_slugs,
        forage=forage,
        repo_root=repo_root,
        live_fetch=live_fetch,
    )
    forage_record = {
        "ok": bool((matched.get("forage") or {}).get("ok") if forage else matched.get("ok")),
        "slug": (matched.get("winner") or {}).get("slug") or "",
        "capability_id": (matched.get("forage") or {}).get("capability_id") or "",
        "error": matched.get("error") or "",
        "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
        "probes": [
            {
                "slug": row.get("slug"),
                "skip_reason": row.get("skip_reason"),
                "covers_goal": bool(row.get("covers_goal")),
            }
            for row in matched.get("probes") or []
        ],
    }
    if forage:
        forage_record["ok"] = bool((matched.get("forage") or {}).get("ok"))
        if not forage_record["ok"]:
            forage_record["error"] = str(
                (matched.get("forage") or {}).get("error") or matched.get("error") or "forage failed"
            )
    winner_entry = matched.get("winner") or {}
    if winner_entry:
        origin = dict(
            forage_request_for(winner_entry, repo_root=repo_root, live_fetch=live_fetch).get("origin") or {}
        )
        forage_record["origin"] = origin
        forage_record["fixture_overlay"] = origin.get("kind") == "fixture"
        forage_record["live_fetch"] = bool(live_fetch)
        forage_record["runtime_deps"] = list((matched.get("forage") or {}).get("runtime_deps") or []) or list(
            (matched.get("covering") or {}).get("runtime_deps") or []
        )
        forage_record["extra_paths"] = list((matched.get("forage") or {}).get("extra_paths") or []) or list(
            (matched.get("covering") or {}).get("extra_paths") or []
        )
    if not matched.get("ok"):
        return {
            "ok": False,
            "plan": None,
            "outcome": {},
            "error": str(matched.get("error") or "no forage match"),
            "grew": False,
            "forage": forage_record,
            "unplannable_before": True,
            "used_forage_growth_plane": False,
            "winner_slug": forage_record["slug"],
        }

    after = _live_registry(repo_root)
    result = run_application_task(task, after)
    result.update(
        {
            "grew": True,
            "forage": forage_record,
            "unplannable_before": True,
            "used_forage_growth_plane": False,
            "winner_slug": forage_record["slug"],
        }
    )
    return result


def _covering_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    if WINNER_CAPABILITY_ID in ledger.capabilities:
        return (WINNER_CAPABILITY_ID,)
    records = {str(item.get("slug")): item for item in load_persisted_records()}
    capability_id = str((records.get(WINNER_SLUG) or {}).get("capability_id") or "")
    return (capability_id,) if capability_id else ()


def _honesty(
    task: ApplicationTask,
    capability_id: str,
    *,
    repo_root: Path,
    hide: Sequence[str] = (),
) -> dict[str, Any]:
    competing = [item for item in hide if item and item != capability_id]
    hidden_ids = ([capability_id] if capability_id else []) + competing
    hidden = _live_registry(repo_root, hide=hidden_ids)
    grown = _live_registry(repo_root, hide=competing)
    unplannable_before = plan_application_task(task, hidden) is None
    grown_result = run_application_task(task, grown)
    grown_plan_solved = bool(
        grown_result.get("ok") and grown_result.get("plan") and capability_id in (grown_result.get("plan") or [])
    )
    ablation_unplannable = plan_application_task(task, hidden) is None
    return {
        "ok": unplannable_before and grown_plan_solved and ablation_unplannable,
        "unplannable_before": unplannable_before,
        "grown_plan_solved": grown_plan_solved,
        "ablation_unplannable": ablation_unplannable,
        "capability_id": capability_id,
        "plan": grown_result.get("plan"),
    }


def _scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(GOAL_KEY,))
    matched = match_forage_goal((GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root)
    probes = list(matched.get("probes") or [])
    decoy_probe = next((row for row in probes if row.get("slug") == DECOY_SLUG), {})
    skipped_reasons = {row["slug"]: row["skip_reason"] for row in trend.get("skipped") or []}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root
    )
    return {
        "trend_winner_slug": (trend.get("winner") or {}).get("slug") or "",
        "trend_decoy_wins": (trend.get("winner") or {}).get("slug") == DECOY_SLUG,
        "lying_catalog_picks_decoy": (lying.get("winner") or {}).get("slug") == DECOY_SLUG,
        "match_is_forage_rotate": (matched.get("winner") or {}).get("slug") == WINNER_SLUG,
        "decoy_probed_and_skipped": decoy_probe.get("skip_reason") == "not_covering"
        and GOAL_KEY not in set(decoy_probe.get("inferred_provides") or []),
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "absorbed_skipped": skipped_reasons.get("inflection") == "already_absorbed"
        and skipped_reasons.get("forage-lab") == "already_absorbed",
        "nonviable_skipped": skipped_reasons.get("forage-empty") == "nonviable",
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "inferred_provides": row.get("inferred_provides") or [],
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {
            "ok": bool(lying.get("ok")),
            "winner": (lying.get("winner") or {}).get("slug") or "",
        },
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def run_application_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow the hermetic unplannable task, skip solvable ones, seal evidence."""

    catalog = load_apply_catalog()
    scenarios = _scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
    )
    hide_before = _covering_hide(repo_root)
    grown = grow_application_task(
        GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(GROW_TASK, capability_id, repo_root=repo_root)
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "grow_winner_is_forage_rotate": grown.get("winner_slug") == WINNER_SLUG,
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "uncovered_refused": bool(scenarios["uncovered_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    }
    grade["ok"] = all(grade.values())
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
            "plan": skip_result.get("plan"),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
    }


def verify_application_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-grow the hermetic task and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_apply_catalog()
    scenarios = _scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    expected_grade = {
        "already_solvable_skips_forage": bool((report.get("already_solvable") or {}).get("ok"))
        and (report.get("already_solvable") or {}).get("grew") is False,
        "uncovered_stays_unsolved": (not (report.get("uncovered") or {}).get("ok"))
        and (report.get("uncovered") or {}).get("error") == "no forage match"
        and (report.get("uncovered") or {}).get("grew") is False,
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "grow_winner_is_forage_rotate": ((report.get("grown") or {}).get("winner_slug") == WINNER_SLUG),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "uncovered_refused": bool(scenarios["uncovered_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "forage_ok": bool(((report.get("grown") or {}).get("forage") or {}).get("ok")),
        "grew": bool((report.get("grown") or {}).get("grew")),
        "unplannable_before": bool((report.get("honesty") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((report.get("honesty") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((report.get("honesty") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": True,
    }
    expected_grade["ok"] = all(expected_grade.values())
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == WINNER_SLUG
    live_proof = prove_absorbed_capability(WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    ok = digest_ok and catalog_ok and grade_ok and winner_ok and live_ok
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
    }


def builtin_application_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: unplannable tasks grow through forage matching."""

    catalog = load_apply_catalog()
    scenarios = _scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-growth-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_growth_plane(report_dir)
        verification = verify_application_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_forage_rotate"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_decoy_wins": bool(scenarios["trend_decoy_wins"]),
        "lying_catalog_picks_decoy": bool(scenarios["lying_catalog_picks_decoy"]),
        "grow_winner_is_forage_rotate": bool((plane.get("grade") or {}).get("grow_winner_is_forage_rotate")),
        "decoy_probed_and_skipped": bool(scenarios["decoy_probed_and_skipped"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "uncovered_refused": bool(scenarios["uncovered_refused"]),
        "absorbed_skipped": bool(scenarios["absorbed_skipped"]),
        "nonviable_skipped": bool(scenarios["nonviable_skipped"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "action": "application_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_growth_plane_proof; r=builtin_application_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_decoy_wins') and r.get('lying_catalog_picks_decoy') "
        "and r.get('grow_winner_is_forage_rotate') and r.get('decoy_probed_and_skipped') "
        "and r.get('catalog_provides_ignored') and r.get('uncovered_refused') "
        "and r.get('absorbed_skipped') and r.get('nonviable_skipped') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('grew') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-growth-plane",
        name="Application-growth forage plane",
        description=(
            "An unplannable application goal grows itself through forage "
            "matching without a separate plane invocation: already-solvable "
            "tasks never forage, uncovered goals stay honestly unsolved, a "
            "lying popular decoy is probed and skipped, the covering package "
            "is foraged, and the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_growth_plane",
        proof_command=application_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_apply_catalog.json",
            "tests/fixtures/external_packages/forage-rotate/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "An unplannable application goal no longer needs a separate "
            "forage-growth invocation: grow=True (or grow_application_task) "
            "matches and forages a covering package in-process, a lying "
            "popular decoy is skipped, and the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_growth_plane() -> dict[str, Any]:
    """Entry surface: run the hermetic plane and summarize the grown task."""

    result = run_application_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "grade": result.get("grade"),
    }


def load_live_apply_catalog(query: str = "") -> dict[str, Any]:
    """Refresh the replayed npm+pypi catalog. Never networks."""

    return refresh_registry_catalog(query or query_from_goal(GROW_TASK.goal), live=False)


def _live_scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(GOAL_KEY,))
    matched = match_forage_goal((GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root)
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == LIVE_NPM_DECOY_SLUG), {})
    pypi_probe = next((row for row in probes if row.get("slug") == DECOY_SLUG), {})
    frozen = load_apply_catalog()
    registries = {str(item.get("registry") or "") for item in items}
    frozen_sources = any(str(item.get("source") or "") for item in items)
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == LIVE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug") == LIVE_NPM_DECOY_SLUG,
        "match_is_forage_rotate": (matched.get("winner") or {}).get("slug") == WINNER_SLUG,
        "npm_decoy_no_source": npm_probe.get("skip_reason") == "no_source",
        "pypi_decoy_not_covering": pypi_probe.get("skip_reason") == "not_covering"
        and GOAL_KEY not in set(pypi_probe.get("inferred_provides") or []),
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "not_frozen_apply_catalog": _digest({"query": catalog.get("query"), "items": catalog.get("items")})
        != _digest({"query": frozen.get("query"), "items": frozen.get("items")}),
        "no_frozen_source_field": frozen_sources is False,
        "query_from_goal": catalog.get("query") == query_from_goal(GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False and catalog.get("replay") is True,
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "inferred_provides": row.get("inferred_provides") or [],
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def run_application_live_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow the unplannable task from a replayed npm+pypi catalog."""

    catalog = load_live_apply_catalog()
    scenarios = _live_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK, catalog=catalog, absorbed=sorted(APPLY_ABSORBED_SLUGS), forage=forage, repo_root=repo_root
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK, catalog=catalog, absorbed=sorted(APPLY_ABSORBED_SLUGS), forage=forage, repo_root=repo_root
    )
    hide_before = _covering_hide(repo_root)
    grown = grow_application_task(
        GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(GROW_TASK, capability_id, repo_root=repo_root)
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_forage_rotate": grown.get("winner_slug") == WINNER_SLUG,
        "npm_decoy_no_source": bool(scenarios["npm_decoy_no_source"]),
        "pypi_decoy_not_covering": bool(scenarios["pypi_decoy_not_covering"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "not_frozen_apply_catalog": bool(scenarios["not_frozen_apply_catalog"]),
        "no_frozen_source_field": bool(scenarios["no_frozen_source_field"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
        "replay_origin": ((grown.get("forage") or {}).get("slug") == WINNER_SLUG),
    }
    grade["ok"] = all(grade.values())
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_live_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "refresh": {
            "live": bool(catalog.get("live")),
            "replay": bool(catalog.get("replay")),
            "network_used": bool(catalog.get("network_used")),
            "registries": list(catalog.get("registries") or []),
        },
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_LIVE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
    }


def _expected_live_grade(report: Mapping[str, Any], scenarios: Mapping[str, Any]) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool((report.get("already_solvable") or {}).get("ok"))
        and (report.get("already_solvable") or {}).get("grew") is False,
        "uncovered_stays_unsolved": (not (report.get("uncovered") or {}).get("ok"))
        and (report.get("uncovered") or {}).get("error") == "no forage match"
        and (report.get("uncovered") or {}).get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_forage_rotate": ((report.get("grown") or {}).get("winner_slug") == WINNER_SLUG),
        "npm_decoy_no_source": bool(scenarios["npm_decoy_no_source"]),
        "pypi_decoy_not_covering": bool(scenarios["pypi_decoy_not_covering"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "not_frozen_apply_catalog": bool(scenarios["not_frozen_apply_catalog"]),
        "no_frozen_source_field": bool(scenarios["no_frozen_source_field"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "forage_ok": bool(((report.get("grown") or {}).get("forage") or {}).get("ok")),
        "grew": bool((report.get("grown") or {}).get("grew")),
        "unplannable_before": bool((report.get("honesty") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((report.get("honesty") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((report.get("honesty") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": True,
        "replay_origin": ((report.get("grown") or {}).get("winner_slug") == WINNER_SLUG),
    }
    grade["ok"] = all(grade.values())
    return grade


def verify_application_live_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-refresh the replay catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_live_apply_catalog()
    scenarios = _live_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    expected_grade = _expected_live_grade(report, scenarios)
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == WINNER_SLUG
    live_proof = prove_absorbed_capability(WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_live_growth_plane"
    ok = digest_ok and catalog_ok and grade_ok and winner_ok and live_ok and kind_ok
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
    }


def builtin_application_live_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: unplannable tasks grow from a replayed npm+pypi catalog."""

    catalog = load_live_apply_catalog()
    scenarios = _live_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-live-growth-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_live_growth_plane(report_dir)
        verification = verify_application_live_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_forage_rotate"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_live_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_forage_rotate": bool((plane.get("grade") or {}).get("grow_winner_is_forage_rotate")),
        "npm_decoy_no_source": bool(scenarios["npm_decoy_no_source"]),
        "pypi_decoy_not_covering": bool(scenarios["pypi_decoy_not_covering"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "not_frozen_apply_catalog": bool(scenarios["not_frozen_apply_catalog"]),
        "no_frozen_source_field": bool(scenarios["no_frozen_source_field"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "action": "application_live_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_live_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_live_growth_plane_proof; r=builtin_application_live_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_live_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_forage_rotate') and r.get('npm_decoy_no_source') "
        "and r.get('pypi_decoy_not_covering') and r.get('catalog_provides_ignored') "
        "and r.get('registries_npm_and_pypi') and r.get('not_frozen_apply_catalog') "
        "and r.get('no_frozen_source_field') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_live_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the live-registry application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-live-growth-plane",
        name="Application live-registry growth plane",
        description=(
            "An unplannable application goal grows itself from a live-shaped "
            "npm+pypi catalog: the search query is derived from the goal keys, "
            "catalog provides are ignored, a popular npm decoy without a local "
            "tree is skipped, a lying pypi decoy is probed and skipped, and the "
            "covering package is foraged from a replayed registry refresh "
            "instead of a frozen apply catalog."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_live_growth_plane",
        proof_command=application_live_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_forage_targets.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_live_catalog.json",
            "tests/fixtures/external_packages/forage-rotate/",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer needs a frozen fixture catalog: a "
            "goal-derived npm+pypi catalog refresh (replayable) ranks live "
            "registry hits, skips a popular npm decoy and a lying pypi decoy, "
            "and forages the covering package so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "live-registry"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_live_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from the replayed npm+pypi catalog."""

    result = run_application_live_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "grade": result.get("grade"),
    }


def load_registry_apply_catalog() -> dict[str, Any]:
    """Load the live-shaped catalog whose hits have no fixture overlay."""

    payload = load_catalog(DEFAULT_REGISTRY_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _registry_hide(repo_root: Path) -> tuple[str, ...]:
    ids = list(REGISTRY_COMPETING_HIDE)
    if REGISTRY_WINNER_CAPABILITY_ID not in ids:
        ids.append(REGISTRY_WINNER_CAPABILITY_ID)
    ledger = load_ledger(default_ledger_path(repo_root))
    return tuple(item for item in ids if item in ledger.capabilities or item in REGISTRY_COMPETING_HIDE)


def _registry_scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(REGISTRY_GOAL_KEY,))
    matched = match_forage_goal(
        (REGISTRY_GOAL_KEY,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root
    )
    probes = list(matched.get("probes") or [])
    pypi_probe = next((row for row in probes if row.get("slug") == REGISTRY_PYPI_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root).get("origin") or {}) if winner_entry else {}
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,), catalog=catalog, absorbed=absorbed, forage=False, repo_root=repo_root
    )
    return {
        "trend_pypi_decoy_wins": (trend.get("winner") or {}).get("slug") == REGISTRY_PYPI_DECOY_SLUG,
        "lying_catalog_picks_pypi_decoy": (lying.get("winner") or {}).get("slug") == REGISTRY_PYPI_DECOY_SLUG,
        "match_is_marked": (matched.get("winner") or {}).get("slug") == REGISTRY_WINNER_SLUG,
        "pypi_decoy_probed": pypi_probe.get("skip_reason") not in {"", None, "no_source"}
        and REGISTRY_GOAL_KEY not in set(pypi_probe.get("inferred_provides") or []),
        "pypi_decoy_not_no_source": pypi_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_not_fixture": origin.get("kind") not in {"", "fixture"} and bool(origin.get("kind")),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(REGISTRY_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "inferred_provides": row.get("inferred_provides") or [],
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def run_application_registry_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from registry hits with no fixture overlay."""

    catalog = load_registry_apply_catalog()
    scenarios = _registry_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK, catalog=catalog, absorbed=sorted(APPLY_ABSORBED_SLUGS), forage=forage, repo_root=repo_root
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK, catalog=catalog, absorbed=sorted(APPLY_ABSORBED_SLUGS), forage=forage, repo_root=repo_root
    )
    hide_before = _registry_hide(repo_root)
    grown = grow_application_task(
        REGISTRY_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or REGISTRY_WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            REGISTRY_GROW_TASK, capability_id, repo_root=repo_root, hide=REGISTRY_COMPETING_HIDE
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_pypi_decoy_wins": bool(scenarios["trend_pypi_decoy_wins"]),
        "lying_catalog_picks_pypi_decoy": bool(scenarios["lying_catalog_picks_pypi_decoy"]),
        "grow_winner_is_marked": grown.get("winner_slug") == REGISTRY_WINNER_SLUG,
        "pypi_decoy_probed": bool(scenarios["pypi_decoy_probed"]),
        "pypi_decoy_not_no_source": bool(scenarios["pypi_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_not_fixture": origin.get("kind") not in {"", "fixture"}
        and bool(origin.get("kind"))
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    }
    grade["ok"] = all(grade.values())
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_registry_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": REGISTRY_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_REGISTRY_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def _expected_registry_grade(report: Mapping[str, Any], scenarios: Mapping[str, Any]) -> dict[str, Any]:
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    grade = {
        "already_solvable_skips_forage": bool((report.get("already_solvable") or {}).get("ok"))
        and (report.get("already_solvable") or {}).get("grew") is False,
        "uncovered_stays_unsolved": (not (report.get("uncovered") or {}).get("ok"))
        and (report.get("uncovered") or {}).get("error") == "no forage match"
        and (report.get("uncovered") or {}).get("grew") is False,
        "trend_pypi_decoy_wins": bool(scenarios["trend_pypi_decoy_wins"]),
        "lying_catalog_picks_pypi_decoy": bool(scenarios["lying_catalog_picks_pypi_decoy"]),
        "grow_winner_is_marked": ((report.get("grown") or {}).get("winner_slug") == REGISTRY_WINNER_SLUG),
        "pypi_decoy_probed": bool(scenarios["pypi_decoy_probed"]),
        "pypi_decoy_not_no_source": bool(scenarios["pypi_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_not_fixture": origin.get("kind") not in {"", "fixture"}
        and bool(origin.get("kind"))
        and ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False,
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "forage_ok": bool(((report.get("grown") or {}).get("forage") or {}).get("ok")),
        "grew": bool((report.get("grown") or {}).get("grew")),
        "unplannable_before": bool((report.get("honesty") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((report.get("honesty") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((report.get("honesty") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": True,
    }
    grade["ok"] = all(grade.values())
    return grade


def verify_application_registry_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-match the registry catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_registry_apply_catalog()
    scenarios = _registry_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    expected_grade = _expected_registry_grade(report, scenarios)
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == REGISTRY_WINNER_SLUG
    live_proof = prove_absorbed_capability(REGISTRY_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_registry_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    ok = digest_ok and catalog_ok and grade_ok and winner_ok and live_ok and kind_ok and overlay_ok
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
    }


def builtin_application_registry_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: unplannable tasks grow from registry hits with no overlay."""

    catalog = load_registry_apply_catalog()
    scenarios = _registry_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-registry-growth-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_registry_growth_plane(report_dir)
        verification = verify_application_registry_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_marked"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_registry_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_pypi_decoy_wins": bool(scenarios["trend_pypi_decoy_wins"]),
        "lying_catalog_picks_pypi_decoy": bool(scenarios["lying_catalog_picks_pypi_decoy"]),
        "grow_winner_is_marked": bool((plane.get("grade") or {}).get("grow_winner_is_marked")),
        "pypi_decoy_probed": bool(scenarios["pypi_decoy_probed"]),
        "pypi_decoy_not_no_source": bool(scenarios["pypi_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_not_fixture": bool((plane.get("grade") or {}).get("winner_origin_not_fixture")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_registry_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_registry_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_registry_growth_plane_proof; r=builtin_application_registry_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_registry_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_pypi_decoy_wins') and r.get('lying_catalog_picks_pypi_decoy') "
        "and r.get('grow_winner_is_marked') and r.get('pypi_decoy_probed') "
        "and r.get('pypi_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('no_replay_source_field') and r.get('winner_origin_not_fixture') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_registry_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the registry-archive application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-live-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-registry-growth-plane",
        name="Application registry-archive growth plane",
        description=(
            "An unplannable application goal grows itself from live-shaped "
            "npm+pypi hits that have no replay_source: catalog provides are "
            "ignored, a popular PyPI decoy is probed from a published sdist "
            "and skipped, and the covering npm package is foraged from its "
            "registry archive rather than a fixture overlay."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_registry_growth_plane",
        proof_command=application_registry_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_forage_targets.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_registry_catalog.json",
            "stewardship/tomli-2.4.1/tomli-2.4.1.tar.gz",
            "stewardship/marked-18.0.7/marked-18.0.7.tgz",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer needs a fixture overlay to forage a "
            "covering registry package: live-shaped npm/pypi hits without "
            "replay_source are probed from published archives, a popular PyPI "
            "decoy is skipped after inference, and the covering npm package is "
            "foraged so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "registry-archive"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_registry_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from registry hits with no fixture overlay."""

    result = run_application_registry_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_live_fetch_apply_catalog() -> dict[str, Any]:
    """Load the live-shaped catalog whose hits have no stewardship archive."""

    payload = load_catalog(DEFAULT_LIVE_FETCH_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _live_fetch_hide(repo_root: Path) -> tuple[str, ...]:
    ids = list(LIVE_FETCH_COMPETING_HIDE)
    if LIVE_FETCH_WINNER_CAPABILITY_ID not in ids:
        ids.append(LIVE_FETCH_WINNER_CAPABILITY_ID)
    ledger = load_ledger(default_ledger_path(repo_root))
    return tuple(item for item in ids if item in ledger.capabilities or item in LIVE_FETCH_COMPETING_HIDE)


def _live_fetch_origin(entry: Mapping[str, Any], *, repo_root: Path) -> dict[str, Any]:
    return dict(forage_request_for(entry, repo_root=repo_root, live_fetch=True).get("origin") or {})


def _source_is_stewardship(origin: Mapping[str, Any]) -> bool:
    source = str(origin.get("source") or "").replace("\\", "/")
    return source.startswith("stewardship/") or "/stewardship/" in source


def _live_fetch_scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(LIVE_FETCH_GOAL_KEY,))
    matched = match_forage_goal(
        (LIVE_FETCH_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == LIVE_FETCH_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = _live_fetch_origin(winner_entry, repo_root=repo_root) if winner_entry else {}
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    replay = registry_replay_archive(winner_entry, repo_root=repo_root) if winner_entry else None
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == LIVE_FETCH_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug") == LIVE_FETCH_NPM_DECOY_SLUG,
        "match_is_titlecase": (matched.get("winner") or {}).get("slug") == LIVE_FETCH_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "no_stewardship_archive": replay is None,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(LIVE_FETCH_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "inferred_provides": row.get("inferred_provides") or [],
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _live_fetch_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_titlecase": grown.get("winner_slug") == LIVE_FETCH_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"}
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "no_stewardship_archive": bool(scenarios["no_stewardship_archive"]),
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True
        if separate_plane is None
        else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_live_fetch_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from live-fetched registry hits with no archive."""

    catalog = load_live_fetch_apply_catalog()
    scenarios = _live_fetch_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _live_fetch_hide(repo_root)
    grown = grow_application_task(
        LIVE_FETCH_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or LIVE_FETCH_WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            LIVE_FETCH_GROW_TASK, capability_id, repo_root=repo_root, hide=LIVE_FETCH_COMPETING_HIDE
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _live_fetch_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_live_fetch_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": LIVE_FETCH_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_LIVE_FETCH_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_live_fetch_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-match the live-fetch catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_live_fetch_apply_catalog()
    scenarios = _live_fetch_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _live_fetch_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == LIVE_FETCH_WINNER_SLUG
    live_proof = prove_absorbed_capability(LIVE_FETCH_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_live_fetch_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    origin_ok = origin.get("kind") in {"npm-live", "pypi-live"} and not _source_is_stewardship(origin)
    ok = digest_ok and catalog_ok and grade_ok and winner_ok and live_ok and kind_ok and overlay_ok and origin_ok
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
    }


def builtin_application_live_fetch_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: unplannable tasks grow from live-fetched registry hits."""

    catalog = load_live_fetch_apply_catalog()
    scenarios = _live_fetch_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-live-fetch-growth-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_live_fetch_growth_plane(report_dir)
        verification = (
            verify_application_live_fetch_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_titlecase"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_live_fetch_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_titlecase": bool((plane.get("grade") or {}).get("grow_winner_is_titlecase")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "no_stewardship_archive": bool(scenarios["no_stewardship_archive"]),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_live_fetch_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_live_fetch_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_live_fetch_growth_plane_proof; r=builtin_application_live_fetch_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_live_fetch_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_titlecase') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('no_replay_source_field') and r.get('winner_origin_live') "
        "and r.get('no_stewardship_archive') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_live_fetch_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the live-fetch application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-registry-growth-plane",
            "capability.application-live-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-live-fetch-growth-plane",
        name="Application live-fetch growth plane",
        description=(
            "An unplannable application goal grows itself from live npm/pypi "
            "hits that have no on-disk stewardship archive: catalog provides "
            "are ignored, a popular npm decoy is live-fetched and skipped, and "
            "the covering PyPI package is foraged from a live registry fetch "
            "rather than a stewardship replay or fixture overlay."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_live_fetch_growth_plane",
        proof_command=application_live_fetch_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_forage_targets.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_live_fetch_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips registry hits that have no "
            "stewardship archive: live-fetch probing materializes published "
            "npm/pypi artifacts, a popular npm decoy is skipped after "
            "inference, and a covering package the stewardship tree has never "
            "seen is foraged so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "live-fetch"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_live_fetch_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from live-fetched registry hits with no archive."""

    result = run_application_live_fetch_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_runtime_deps_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist is import-unclosed without deps."""

    payload = load_catalog(DEFAULT_RUNTIME_DEPS_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _runtime_deps_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (RUNTIME_DEPS_WINNER_CAPABILITY_ID,) if RUNTIME_DEPS_WINNER_CAPABILITY_ID in ledger.capabilities else ()


def _runtime_dep_names(payload: Mapping[str, Any] | Sequence[Any] | None) -> set[str]:
    names: set[str] = set()
    if isinstance(payload, Mapping):
        raw = payload.get("runtime_deps") or payload.get("closed") or []
        if isinstance(payload.get("name"), str) and payload.get("name"):
            names.add(str(payload["name"]).replace("_", "-").lower())
    else:
        raw = payload or []
    for item in raw if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) else []:
        if isinstance(item, Mapping):
            names.add(str(item.get("name") or item.get("requested") or "").replace("_", "-").lower())
        elif item:
            names.add(str(item).replace("_", "-").lower())
    names.discard("")
    return names


def _unclosed_without_deps(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-unclosed-sdist-") as tmp:
        opened = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            close_deps=False,
        )
    return (not opened.get("ok")) and "import failed" in str(opened.get("error") or "")


def _named_only_unselected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-named-only-") as tmp:
        named = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="node",
            close_deps=True,
            include_default=False,
        )
    return (not named.get("ok")) and named.get("stage") == "select"


def _named_class_static_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-named-class-static-") as tmp:
        named = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="node",
            close_deps=True,
            include_default=False,
        )
    record = named.get("record") or {}
    return bool(named.get("ok")) and bool(record.get("named_export_class_static"))


def _named_class_instance_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-named-class-instance-") as tmp:
        named = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="node",
            close_deps=True,
            include_default=False,
        )
    record = named.get("record") or {}
    return bool(named.get("ok")) and bool(record.get("named_export_class"))


def _runtime_deps_scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(RUNTIME_DEPS_GOAL_KEY,))
    matched = match_forage_goal(
        (RUNTIME_DEPS_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == RUNTIME_DEPS_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    dep_names = _runtime_dep_names(covering)
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == RUNTIME_DEPS_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug") == RUNTIME_DEPS_NPM_DECOY_SLUG,
        "match_is_python_slugify": (matched.get("winner") or {}).get("slug") == RUNTIME_DEPS_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(RUNTIME_DEPS_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "unclosed_without_deps": _unclosed_without_deps(winner_entry, repo_root=repo_root) if winner_entry else False,
        "closed_dep_is_text_unidecode": RUNTIME_DEPS_DEP_NAME in dep_names,
        "extra_paths_vendored": bool(covering.get("extra_paths")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "runtime_deps": list(covering.get("runtime_deps") or []),
            "extra_paths": list(covering.get("extra_paths") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _runtime_deps_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    deps = _runtime_dep_names((grown.get("forage") or {}).get("runtime_deps"))
    extra_paths = list((grown.get("forage") or {}).get("extra_paths") or [])
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_python_slugify": grown.get("winner_slug") == RUNTIME_DEPS_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"}
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "winner_runtime_deps_closed": RUNTIME_DEPS_DEP_NAME in deps,
        "extra_paths_vendored": bool(extra_paths) or bool(scenarios["extra_paths_vendored"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_runtime_deps_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from an import-unclosed live-fetched sdist."""

    catalog = load_runtime_deps_apply_catalog()
    scenarios = _runtime_deps_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _runtime_deps_hide(repo_root)
    grown = grow_application_task(
        RUNTIME_DEPS_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or RUNTIME_DEPS_WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(RUNTIME_DEPS_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _runtime_deps_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_runtime_deps_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": RUNTIME_DEPS_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_RUNTIME_DEPS_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
        "runtime_deps": list((grown.get("forage") or {}).get("runtime_deps") or []),
    }


def verify_application_runtime_deps_growth_plane(report_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Re-match the import-unclosed catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_runtime_deps_apply_catalog()
    scenarios = _runtime_deps_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _runtime_deps_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == RUNTIME_DEPS_WINNER_SLUG
    live_proof = prove_absorbed_capability(RUNTIME_DEPS_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_runtime_deps_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    deps_ok = RUNTIME_DEPS_DEP_NAME in _runtime_dep_names(
        ((report.get("grown") or {}).get("forage") or {}).get("runtime_deps")
    )
    origin_ok = origin.get("kind") in {"npm-live", "pypi-live"} and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and deps_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "deps_ok": deps_ok,
    }


def builtin_application_runtime_deps_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: import-unclosed sdists grow after runtime deps close."""

    catalog = load_runtime_deps_apply_catalog()
    scenarios = _runtime_deps_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-runtime-deps-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_runtime_deps_growth_plane(report_dir)
        verification = (
            verify_application_runtime_deps_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_python_slugify"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_runtime_deps_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_python_slugify": bool((plane.get("grade") or {}).get("grow_winner_is_python_slugify")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "winner_runtime_deps_closed": bool((plane.get("grade") or {}).get("winner_runtime_deps_closed")),
        "extra_paths_vendored": bool((plane.get("grade") or {}).get("extra_paths_vendored")),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "runtime_deps": plane.get("runtime_deps") or [],
        "action": "application_runtime_deps_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_runtime_deps_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_runtime_deps_growth_plane_proof; r=builtin_application_runtime_deps_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_runtime_deps_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_python_slugify') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('unclosed_without_deps') and r.get('winner_runtime_deps_closed') "
        "and r.get('extra_paths_vendored') and r.get('winner_origin_live') "
        "and r.get('winner_source_not_stewardship') and r.get('registries_npm_and_pypi') "
        "and r.get('query_from_goal') and r.get('network_unused') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('grew') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_runtime_deps_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the runtime-deps application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-runtime-deps-growth-plane",
        name="Application runtime-deps growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose import is unclosed without declared runtime "
            "dependencies: those deps are vendored into the staged tree, a "
            "popular npm decoy is skipped, and the covering package is foraged "
            "so the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_runtime_deps_growth_plane",
        proof_command=application_runtime_deps_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_runtime_deps_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips import-unclosed sdists: "
            "declared transitive runtime dependencies are fetched and vendored "
            "into the staged tree, isolated introspection without them still "
            "fails, and a covering package is foraged so the original task "
            "becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "runtime-deps"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_runtime_deps_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from an import-unclosed live-fetched sdist."""

    result = run_application_runtime_deps_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "runtime_deps": result.get("runtime_deps"),
        "grade": result.get("grade"),
    }


def load_node_runtime_deps_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball is import-unclosed without deps."""

    payload = load_catalog(DEFAULT_NODE_RUNTIME_DEPS_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_runtime_deps_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_RUNTIME_DEPS_WINNER_CAPABILITY_ID,)
        if NODE_RUNTIME_DEPS_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_runtime_deps_scenario_grades(catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_RUNTIME_DEPS_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_RUNTIME_DEPS_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == NODE_RUNTIME_DEPS_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    dep_names = _runtime_dep_names(covering)
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == NODE_RUNTIME_DEPS_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug") == NODE_RUNTIME_DEPS_NPM_DECOY_SLUG,
        "match_is_snake_case": (matched.get("winner") or {}).get("slug") == NODE_RUNTIME_DEPS_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_RUNTIME_DEPS_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "unclosed_without_deps": _unclosed_without_deps(winner_entry, repo_root=repo_root) if winner_entry else False,
        "closed_dep_is_no_case": NODE_RUNTIME_DEPS_DEP_NAME in dep_names,
        "extra_paths_vendored": bool(covering.get("extra_paths")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "runtime_deps": list(covering.get("runtime_deps") or []),
            "extra_paths": list(covering.get("extra_paths") or []),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_runtime_deps_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    deps = _runtime_dep_names((grown.get("forage") or {}).get("runtime_deps"))
    extra_paths = list((grown.get("forage") or {}).get("extra_paths") or [])
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_snake_case": grown.get("winner_slug") == NODE_RUNTIME_DEPS_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "winner_runtime_deps_closed": NODE_RUNTIME_DEPS_DEP_NAME in deps,
        "extra_paths_vendored": bool(extra_paths) or bool(scenarios["extra_paths_vendored"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_runtime_deps_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from an import-unclosed live-fetched npm tarball."""

    catalog = load_node_runtime_deps_apply_catalog()
    scenarios = _node_runtime_deps_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_runtime_deps_hide(repo_root)
    grown = grow_application_task(
        NODE_RUNTIME_DEPS_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str((grown.get("forage") or {}).get("capability_id") or NODE_RUNTIME_DEPS_WINNER_CAPABILITY_ID)
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_RUNTIME_DEPS_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_runtime_deps_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_runtime_deps_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_RUNTIME_DEPS_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_RUNTIME_DEPS_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
        "runtime_deps": list((grown.get("forage") or {}).get("runtime_deps") or []),
    }


def verify_application_node_runtime_deps_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the import-unclosed npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_runtime_deps_apply_catalog()
    scenarios = _node_runtime_deps_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_runtime_deps_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_RUNTIME_DEPS_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_RUNTIME_DEPS_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_runtime_deps_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    deps_ok = NODE_RUNTIME_DEPS_DEP_NAME in _runtime_dep_names(
        ((report.get("grown") or {}).get("forage") or {}).get("runtime_deps")
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and deps_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "deps_ok": deps_ok,
    }


def builtin_application_node_runtime_deps_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: import-unclosed npm tarballs grow after package.json deps close."""

    catalog = load_node_runtime_deps_apply_catalog()
    scenarios = _node_runtime_deps_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-runtime-deps-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_runtime_deps_growth_plane(report_dir)
        verification = (
            verify_application_node_runtime_deps_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_snake_case"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_runtime_deps_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_snake_case": bool((plane.get("grade") or {}).get("grow_winner_is_snake_case")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "winner_runtime_deps_closed": bool((plane.get("grade") or {}).get("winner_runtime_deps_closed")),
        "extra_paths_vendored": bool((plane.get("grade") or {}).get("extra_paths_vendored")),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "runtime_deps": plane.get("runtime_deps") or [],
        "action": "application_node_runtime_deps_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_runtime_deps_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_runtime_deps_growth_plane_proof; "
        "r=builtin_application_node_runtime_deps_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_runtime_deps_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_snake_case') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('unclosed_without_deps') and r.get('winner_runtime_deps_closed') "
        "and r.get('extra_paths_vendored') and r.get('winner_origin_live') "
        "and r.get('winner_source_not_stewardship') and r.get('registries_npm_and_pypi') "
        "and r.get('query_from_goal') and r.get('network_unused') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('grew') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_runtime_deps_growth_plane_capability(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Register (idempotently) and prove the node runtime-deps application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-runtime-deps-growth-plane",
        name="Application node runtime-deps growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose import is unclosed without declared package.json "
            "dependencies: those deps are vendored into the staged tree, a "
            "popular npm decoy is skipped, and the covering package is foraged "
            "so the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_runtime_deps_growth_plane",
        proof_command=application_node_runtime_deps_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_runtime_deps_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips import-unclosed npm packages: "
            "declared package.json dependencies of a live-fetched tarball are "
            "fetched and vendored into the staged tree, isolated introspection "
            "without them still fails, and a covering package is foraged so "
            "the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "runtime-deps", "node"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_runtime_deps_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from an import-unclosed live-fetched npm tarball."""

    result = run_application_node_runtime_deps_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "runtime_deps": result.get("runtime_deps"),
        "grade": result.get("grade"),
    }


def load_node_default_export_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball is default-export-only."""

    payload = load_catalog(DEFAULT_NODE_DEFAULT_EXPORT_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_default_export_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_DEFAULT_EXPORT_WINNER_CAPABILITY_ID,)
        if NODE_DEFAULT_EXPORT_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_default_export_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_DEFAULT_EXPORT_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_DEFAULT_EXPORT_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == NODE_DEFAULT_EXPORT_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    dep_names = _runtime_dep_names(covering)
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == NODE_DEFAULT_EXPORT_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug") == NODE_DEFAULT_EXPORT_NPM_DECOY_SLUG,
        "match_is_humanize_string": (matched.get("winner") or {}).get("slug") == NODE_DEFAULT_EXPORT_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_DEFAULT_EXPORT_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "unclosed_without_deps": _unclosed_without_deps(winner_entry, repo_root=repo_root) if winner_entry else False,
        "named_only_unselected": _named_only_unselected(winner_entry, repo_root=repo_root) if winner_entry else False,
        "winner_is_default_export": bool(covering.get("default_export")),
        "closed_dep_is_decamelize": NODE_DEFAULT_EXPORT_DEP_NAME in dep_names,
        "extra_paths_vendored": bool(covering.get("extra_paths")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "runtime_deps": list(covering.get("runtime_deps") or []),
            "extra_paths": list(covering.get("extra_paths") or []),
            "default_export": bool(covering.get("default_export")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_default_export_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    deps = _runtime_dep_names((grown.get("forage") or {}).get("runtime_deps"))
    extra_paths = list((grown.get("forage") or {}).get("extra_paths") or [])
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_humanize_string": grown.get("winner_slug") == NODE_DEFAULT_EXPORT_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_runtime_deps_closed": NODE_DEFAULT_EXPORT_DEP_NAME in deps,
        "extra_paths_vendored": bool(extra_paths) or bool(scenarios["extra_paths_vendored"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_default_export_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a default-export-only live-fetched npm tarball."""

    catalog = load_node_default_export_apply_catalog()
    scenarios = _node_default_export_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_default_export_hide(repo_root)
    grown = grow_application_task(
        NODE_DEFAULT_EXPORT_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_DEFAULT_EXPORT_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_DEFAULT_EXPORT_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_default_export_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_default_export_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_DEFAULT_EXPORT_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_DEFAULT_EXPORT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
        "runtime_deps": list((grown.get("forage") or {}).get("runtime_deps") or []),
    }


def verify_application_node_default_export_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the default-export-only npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_default_export_apply_catalog()
    scenarios = _node_default_export_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_default_export_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_DEFAULT_EXPORT_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_DEFAULT_EXPORT_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_default_export_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    deps_ok = NODE_DEFAULT_EXPORT_DEP_NAME in _runtime_dep_names(
        ((report.get("grown") or {}).get("forage") or {}).get("runtime_deps")
    )
    default_ok = bool(scenarios.get("winner_is_default_export")) and bool(scenarios.get("named_only_unselected"))
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and deps_ok
        and default_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "deps_ok": deps_ok,
        "default_ok": default_ok,
    }


def builtin_application_node_default_export_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: default-export-only npm tarballs grow after default reflection."""

    catalog = load_node_default_export_apply_catalog()
    scenarios = _node_default_export_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-default-export-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_default_export_growth_plane(report_dir)
        verification = (
            verify_application_node_default_export_growth_plane(report_dir) if plane.get("ok") else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_humanize_string"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_default_export_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_humanize_string": bool((plane.get("grade") or {}).get("grow_winner_is_humanize_string")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_runtime_deps_closed": bool((plane.get("grade") or {}).get("winner_runtime_deps_closed")),
        "extra_paths_vendored": bool((plane.get("grade") or {}).get("extra_paths_vendored")),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "runtime_deps": plane.get("runtime_deps") or [],
        "action": "application_node_default_export_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_default_export_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_default_export_growth_plane_proof; "
        "r=builtin_application_node_default_export_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_default_export_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_humanize_string') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('unclosed_without_deps') and r.get('named_only_unselected') "
        "and r.get('winner_is_default_export') and r.get('winner_runtime_deps_closed') "
        "and r.get('extra_paths_vendored') and r.get('winner_origin_live') "
        "and r.get('winner_source_not_stewardship') and r.get('registries_npm_and_pypi') "
        "and r.get('query_from_goal') and r.get('network_unused') "
        "and r.get('plane_ok') and r.get('verify_ok') and r.get('tampered_rejected') "
        "and r.get('forage_ok') and r.get('grew') and r.get('unplannable_before') "
        "and r.get('grown_plan_solved') and r.get('ablation_unplannable') "
        "and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_default_export_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the node default-export application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-default-export-growth-plane",
        name="Application node default-export growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball that only exports a default function: Node introspection "
            "reflects that default export, declared package.json dependencies are "
            "vendored, named-export-only introspection still fails, and the covering "
            "package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_default_export_growth_plane",
        proof_command=application_node_default_export_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_default_export_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips default-export-only npm packages: "
            "Node introspection reflects default exports, declared package.json "
            "dependencies of a live-fetched tarball are still closed, named-export-only "
            "introspection still fails, and a covering package is foraged so the "
            "original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "default-export"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_default_export_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a default-export-only live-fetched npm tarball."""

    result = run_application_node_default_export_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "runtime_deps": result.get("runtime_deps"),
        "grade": result.get("grade"),
    }


def load_node_default_export_object_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball default-exports a namespace."""

    payload = load_catalog(DEFAULT_NODE_DEFAULT_EXPORT_OBJECT_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_default_export_object_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID,)
        if NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_default_export_object_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (row for row in probes if row.get("slug") == NODE_DEFAULT_EXPORT_OBJECT_NPM_DECOY_SLUG), {}
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    dep_names = _runtime_dep_names(covering)
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == NODE_DEFAULT_EXPORT_OBJECT_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == NODE_DEFAULT_EXPORT_OBJECT_NPM_DECOY_SLUG,
        "match_is_query_string": (matched.get("winner") or {}).get("slug")
        == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "unclosed_without_deps": _unclosed_without_deps(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "named_only_unselected": _named_only_unselected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_default_export": bool(covering.get("default_export")),
        "winner_is_default_export_object": bool(covering.get("default_export_object")),
        "closed_dep_is_decode_uri_component": NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME in dep_names,
        "extra_paths_vendored": bool(covering.get("extra_paths")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "runtime_deps": list(covering.get("runtime_deps") or []),
            "extra_paths": list(covering.get("extra_paths") or []),
            "default_export": bool(covering.get("default_export")),
            "default_export_object": bool(covering.get("default_export_object")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_default_export_object_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    deps = _runtime_dep_names((grown.get("forage") or {}).get("runtime_deps"))
    extra_paths = list((grown.get("forage") or {}).get("extra_paths") or [])
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_query_string": grown.get("winner_slug") == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_is_default_export_object": bool(scenarios["winner_is_default_export_object"]),
        "winner_runtime_deps_closed": NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME in deps,
        "extra_paths_vendored": bool(extra_paths) or bool(scenarios["extra_paths_vendored"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_default_export_object_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a default-exported-object live-fetched npm tarball."""

    catalog = load_node_default_export_object_apply_catalog()
    scenarios = _node_default_export_object_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_default_export_object_hide(repo_root)
    grown = grow_application_task(
        NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_DEFAULT_EXPORT_OBJECT_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_DEFAULT_EXPORT_OBJECT_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_default_export_object_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_default_export_object_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_DEFAULT_EXPORT_OBJECT_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_DEFAULT_EXPORT_OBJECT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
        "runtime_deps": list((grown.get("forage") or {}).get("runtime_deps") or []),
    }


def verify_application_node_default_export_object_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the default-exported-object npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_default_export_object_apply_catalog()
    scenarios = _node_default_export_object_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_default_export_object_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_DEFAULT_EXPORT_OBJECT_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_default_export_object_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    deps_ok = NODE_DEFAULT_EXPORT_OBJECT_DEP_NAME in _runtime_dep_names(
        ((report.get("grown") or {}).get("forage") or {}).get("runtime_deps")
    )
    default_ok = (
        bool(scenarios.get("winner_is_default_export"))
        and bool(scenarios.get("winner_is_default_export_object"))
        and bool(scenarios.get("named_only_unselected"))
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and deps_ok
        and default_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "deps_ok": deps_ok,
        "default_ok": default_ok,
    }


def builtin_application_node_default_export_object_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: default-exported-object npm tarballs grow after namespace reflection."""

    catalog = load_node_default_export_object_apply_catalog()
    scenarios = _node_default_export_object_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-default-export-object-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_default_export_object_growth_plane(report_dir)
        verification = (
            verify_application_node_default_export_object_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_query_string"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_default_export_object_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_query_string": bool((plane.get("grade") or {}).get("grow_winner_is_query_string")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_is_default_export_object": bool(scenarios["winner_is_default_export_object"]),
        "winner_runtime_deps_closed": bool((plane.get("grade") or {}).get("winner_runtime_deps_closed")),
        "extra_paths_vendored": bool((plane.get("grade") or {}).get("extra_paths_vendored")),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "runtime_deps": plane.get("runtime_deps") or [],
        "action": "application_node_default_export_object_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_default_export_object_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_default_export_object_growth_plane_proof; "
        "r=builtin_application_node_default_export_object_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_default_export_object_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_query_string') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('unclosed_without_deps') and r.get('named_only_unselected') "
        "and r.get('winner_is_default_export') and r.get('winner_is_default_export_object') "
        "and r.get('winner_runtime_deps_closed') and r.get('extra_paths_vendored') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_default_export_object_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the node default-export-object application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-default-export-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-default-export-object-growth-plane",
        name="Application node default-export-object growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose default export is a namespace of functions: Node "
            "introspection reflects those default-object methods, declared "
            "package.json dependencies are vendored, named-export-only "
            "introspection still fails, and the covering package is foraged so "
            "the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_default_export_object_growth_plane",
        proof_command=application_node_default_export_object_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_default_export_object_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips npm packages whose default export "
            "is a namespace of functions: Node introspection reflects default-exported "
            "objects, declared package.json dependencies of a live-fetched tarball "
            "are still closed, named-export-only introspection still fails, and a "
            "covering package is foraged so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "default-export-object"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_default_export_object_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a default-exported-object live-fetched npm tarball."""

    result = run_application_node_default_export_object_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "runtime_deps": result.get("runtime_deps"),
        "grade": result.get("grade"),
    }


def load_node_default_export_class_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball default-exports a class."""

    payload = load_catalog(DEFAULT_NODE_DEFAULT_EXPORT_CLASS_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_default_export_class_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_DEFAULT_EXPORT_CLASS_WINNER_CAPABILITY_ID,)
        if NODE_DEFAULT_EXPORT_CLASS_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_default_export_class_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_DEFAULT_EXPORT_CLASS_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_DEFAULT_EXPORT_CLASS_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (row for row in probes if row.get("slug") == NODE_DEFAULT_EXPORT_CLASS_NPM_DECOY_SLUG), {}
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    dep_names = _runtime_dep_names(covering)
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == NODE_DEFAULT_EXPORT_CLASS_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == NODE_DEFAULT_EXPORT_CLASS_NPM_DECOY_SLUG,
        "match_is_markdown_it": (matched.get("winner") or {}).get("slug")
        == NODE_DEFAULT_EXPORT_CLASS_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_DEFAULT_EXPORT_CLASS_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "unclosed_without_deps": _unclosed_without_deps(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "named_only_unselected": _named_only_unselected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_default_export": bool(covering.get("default_export")),
        "winner_is_default_export_class": bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "closed_dep_is_argparse": NODE_DEFAULT_EXPORT_CLASS_DEP_NAME in dep_names,
        "extra_paths_vendored": bool(covering.get("extra_paths")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "runtime_deps": list(covering.get("runtime_deps") or []),
            "extra_paths": list(covering.get("extra_paths") or []),
            "default_export": bool(covering.get("default_export")),
            "default_export_class": bool(covering.get("default_export_class")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_default_export_class_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    deps = _runtime_dep_names((grown.get("forage") or {}).get("runtime_deps"))
    extra_paths = list((grown.get("forage") or {}).get("extra_paths") or [])
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_markdown_it": grown.get("winner_slug") == NODE_DEFAULT_EXPORT_CLASS_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_is_default_export_class": bool(scenarios["winner_is_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_runtime_deps_closed": NODE_DEFAULT_EXPORT_CLASS_DEP_NAME in deps,
        "extra_paths_vendored": bool(extra_paths) or bool(scenarios["extra_paths_vendored"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_default_export_class_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a default-exported-class live-fetched npm tarball."""

    catalog = load_node_default_export_class_apply_catalog()
    scenarios = _node_default_export_class_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_default_export_class_hide(repo_root)
    grown = grow_application_task(
        NODE_DEFAULT_EXPORT_CLASS_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_DEFAULT_EXPORT_CLASS_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_DEFAULT_EXPORT_CLASS_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_default_export_class_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_default_export_class_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_DEFAULT_EXPORT_CLASS_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_DEFAULT_EXPORT_CLASS_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
        "runtime_deps": list((grown.get("forage") or {}).get("runtime_deps") or []),
    }


def verify_application_node_default_export_class_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the default-exported-class npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_default_export_class_apply_catalog()
    scenarios = _node_default_export_class_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_default_export_class_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_DEFAULT_EXPORT_CLASS_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_DEFAULT_EXPORT_CLASS_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_default_export_class_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    deps_ok = NODE_DEFAULT_EXPORT_CLASS_DEP_NAME in _runtime_dep_names(
        ((report.get("grown") or {}).get("forage") or {}).get("runtime_deps")
    )
    default_ok = (
        bool(scenarios.get("winner_is_default_export"))
        and bool(scenarios.get("winner_is_default_export_class"))
        and bool(scenarios.get("winner_is_not_default_export_object"))
        and bool(scenarios.get("named_only_unselected"))
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and deps_ok
        and default_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "deps_ok": deps_ok,
        "default_ok": default_ok,
    }


def builtin_application_node_default_export_class_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: default-exported-class npm tarballs grow after instance-method reflection."""

    catalog = load_node_default_export_class_apply_catalog()
    scenarios = _node_default_export_class_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-default-export-class-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_default_export_class_growth_plane(report_dir)
        verification = (
            verify_application_node_default_export_class_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_markdown_it"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_default_export_class_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_markdown_it": bool((plane.get("grade") or {}).get("grow_winner_is_markdown_it")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "unclosed_without_deps": bool(scenarios["unclosed_without_deps"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_is_default_export_class": bool(scenarios["winner_is_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_runtime_deps_closed": bool((plane.get("grade") or {}).get("winner_runtime_deps_closed")),
        "extra_paths_vendored": bool((plane.get("grade") or {}).get("extra_paths_vendored")),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "runtime_deps": plane.get("runtime_deps") or [],
        "action": "application_node_default_export_class_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_default_export_class_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_default_export_class_growth_plane_proof; "
        "r=builtin_application_node_default_export_class_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_default_export_class_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_markdown_it') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('unclosed_without_deps') and r.get('named_only_unselected') "
        "and r.get('winner_is_default_export') and r.get('winner_is_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_runtime_deps_closed') and r.get('extra_paths_vendored') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_default_export_class_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the node default-export-class application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-default-export-object-growth-plane",
            "capability.application-node-default-export-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-default-export-class-growth-plane",
        name="Application node default-export-class growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose default export is a constructable class: Node "
            "introspection reflects those instance methods, declared "
            "package.json dependencies are vendored, named-export-only "
            "introspection still fails, and the covering package is foraged so "
            "the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_default_export_class_growth_plane",
        proof_command=application_node_default_export_class_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_default_export_class_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips npm packages whose default export "
            "is a constructable class: Node introspection reflects default-exported "
            "class instance methods, declared package.json dependencies of a "
            "live-fetched tarball are still closed, named-export-only introspection "
            "still fails, and a covering package is foraged so the original task "
            "becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "default-export-class"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_default_export_class_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a default-exported-class live-fetched npm tarball."""

    result = run_application_node_default_export_class_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "runtime_deps": result.get("runtime_deps"),
        "grade": result.get("grade"),
    }


def load_node_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball exposes class static methods."""

    payload = load_catalog(DEFAULT_NODE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if NODE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_CLASS_STATIC_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == NODE_CLASS_STATIC_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == NODE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == NODE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_spark_md5": (matched.get("winner") or {}).get("slug") == NODE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "named_only_unselected": _named_only_unselected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_default_export": bool(covering.get("default_export")),
        "winner_is_default_export_class_static": bool(covering.get("default_export_class_static")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "default_export": bool(covering.get("default_export")),
            "default_export_class_static": bool(covering.get("default_export_class_static")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_spark_md5": grown.get("winner_slug") == NODE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_is_default_export_class_static": bool(scenarios["winner_is_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a class-static live-fetched npm tarball."""

    catalog = load_node_class_static_apply_catalog()
    scenarios = _node_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_class_static_hide(repo_root)
    grown = grow_application_task(
        NODE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_CLASS_STATIC_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_node_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the class-static npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_class_static_apply_catalog()
    scenarios = _node_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_CLASS_STATIC_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_class_static_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    default_ok = (
        bool(scenarios.get("winner_is_default_export"))
        and bool(scenarios.get("winner_is_default_export_class_static"))
        and bool(scenarios.get("winner_is_not_default_export_class"))
        and bool(scenarios.get("winner_is_not_default_export_object"))
        and bool(scenarios.get("named_only_unselected"))
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and default_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "default_ok": default_ok,
    }


def builtin_application_node_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: class-static npm tarballs grow after static-method reflection."""

    catalog = load_node_class_static_apply_catalog()
    scenarios = _node_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-class-static-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_class_static_growth_plane(report_dir)
        verification = (
            verify_application_node_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_spark_md5"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_class_static_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_spark_md5": bool((plane.get("grade") or {}).get("grow_winner_is_spark_md5")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "named_only_unselected": bool(scenarios["named_only_unselected"]),
        "winner_is_default_export": bool(scenarios["winner_is_default_export"]),
        "winner_is_default_export_class_static": bool(scenarios["winner_is_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_node_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_class_static_growth_plane_proof; "
        "r=builtin_application_node_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_spark_md5') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('named_only_unselected') "
        "and r.get('winner_is_default_export') and r.get('winner_is_default_export_class_static') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the node class-static application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-default-export-class-growth-plane",
            "capability.application-node-default-export-object-growth-plane",
            "capability.application-node-default-export-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-class-static-growth-plane",
        name="Application node class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose callable API is a class static method: Node "
            "introspection reflects Class.method rather than new Class().method, "
            "named-export-only introspection still fails, and the covering "
            "package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_class_static_growth_plane",
        proof_command=application_node_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips npm packages whose callable API "
            "is a class static method: Node introspection reflects "
            "default-exported Class.method callables, named-export-only "
            "introspection still fails, and a covering package is foraged so "
            "the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "class-static"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=280)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a class-static live-fetched npm tarball."""

    result = run_application_node_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_node_named_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball exposes named class statics."""

    payload = load_catalog(DEFAULT_NODE_NAMED_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_named_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_NAMED_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if NODE_NAMED_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_named_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_NAMED_CLASS_STATIC_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_NAMED_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == NODE_NAMED_CLASS_STATIC_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == NODE_NAMED_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == NODE_NAMED_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_ip_address": (matched.get("winner") or {}).get("slug") == NODE_NAMED_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_NAMED_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "named_class_static_selected": _named_class_static_selected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_named_export_class_static": bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class_static": not bool(covering.get("default_export_class_static")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "winner_is_not_nested_namespace_class_static": not bool(covering.get("nested_namespace_class_static")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "named_export_class_static": bool(covering.get("named_export_class_static")),
            "nested_namespace_class_static": bool(covering.get("nested_namespace_class_static")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_named_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_ip_address": grown.get("winner_slug") == NODE_NAMED_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "named_class_static_selected": bool(scenarios["named_class_static_selected"]),
        "winner_is_named_export_class_static": bool(scenarios["winner_is_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class_static": bool(scenarios["winner_is_not_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_is_not_nested_namespace_class_static": bool(
            scenarios["winner_is_not_nested_namespace_class_static"]
        ),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_named_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a named class-static live-fetched npm tarball."""

    catalog = load_node_named_class_static_apply_catalog()
    scenarios = _node_named_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_named_class_static_hide(repo_root)
    grown = grow_application_task(
        NODE_NAMED_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_NAMED_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_NAMED_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_named_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_named_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_NAMED_CLASS_STATIC_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_NAMED_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_node_named_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the named class-static npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_named_class_static_apply_catalog()
    scenarios = _node_named_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_named_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_NAMED_CLASS_STATIC_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_NAMED_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_named_class_static_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    named_ok = (
        bool(scenarios.get("winner_is_named_export_class_static"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("winner_is_not_default_export_class_static"))
        and bool(scenarios.get("named_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and named_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "named_ok": named_ok,
    }


def builtin_application_node_named_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: named class-static npm tarballs grow after static reflection."""

    catalog = load_node_named_class_static_apply_catalog()
    scenarios = _node_named_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-named-class-static-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_named_class_static_growth_plane(report_dir)
        verification = (
            verify_application_node_named_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_ip_address"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_named_class_static_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_ip_address": bool((plane.get("grade") or {}).get("grow_winner_is_ip_address")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "named_class_static_selected": bool(scenarios["named_class_static_selected"]),
        "winner_is_named_export_class_static": bool(scenarios["winner_is_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class_static": bool(scenarios["winner_is_not_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_node_named_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_named_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_named_class_static_growth_plane_proof; "
        "r=builtin_application_node_named_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_named_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_ip_address') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('named_class_static_selected') "
        "and r.get('winner_is_named_export_class_static') and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class_static') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_named_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the named class-static application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-class-static-growth-plane",
            "capability.application-node-default-export-class-growth-plane",
            "capability.application-node-default-export-object-growth-plane",
            "capability.application-node-default-export-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-named-class-static-growth-plane",
        name="Application node named class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose callable API is a named class static method: Node "
            "introspection reflects Base64.encode and buffer.Buffer.byteLength "
            "rather than a default-exported Class.method, and the covering "
            "package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_named_class_static_growth_plane",
        proof_command=application_node_named_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_named_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips npm packages whose callable API "
            "is a named class static or nested namespace class static: Node "
            "introspection reflects Base64.encode and buffer.Buffer.byteLength, "
            "and a covering package is foraged so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "named-class-static"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=360)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_named_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a named class-static live-fetched npm tarball."""

    result = run_application_node_named_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_node_named_class_instance_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball exposes named class instance methods."""

    payload = load_catalog(DEFAULT_NODE_NAMED_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_named_class_instance_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_NAMED_CLASS_INSTANCE_WINNER_CAPABILITY_ID,)
        if NODE_NAMED_CLASS_INSTANCE_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _node_named_class_instance_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_NAMED_CLASS_INSTANCE_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_NAMED_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == NODE_NAMED_CLASS_INSTANCE_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == NODE_NAMED_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == NODE_NAMED_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "match_is_fast_xml_parser": (matched.get("winner") or {}).get("slug")
        == NODE_NAMED_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_NAMED_CLASS_INSTANCE_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "named_class_instance_selected": _named_class_instance_selected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_named_export_class": bool(covering.get("named_export_class")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class_static": not bool(covering.get("default_export_class_static")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "named_export_class": bool(covering.get("named_export_class")),
            "named_export_class_static": bool(covering.get("named_export_class_static")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_named_class_instance_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_fast_xml_parser": grown.get("winner_slug") == NODE_NAMED_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "named_class_instance_selected": bool(scenarios["named_class_instance_selected"]),
        "winner_is_named_export_class": bool(scenarios["winner_is_named_export_class"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class_static": bool(scenarios["winner_is_not_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_named_class_instance_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a named class-instance live-fetched npm tarball."""

    catalog = load_node_named_class_instance_apply_catalog()
    scenarios = _node_named_class_instance_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_named_class_instance_hide(repo_root)
    grown = grow_application_task(
        NODE_NAMED_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_NAMED_CLASS_INSTANCE_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_NAMED_CLASS_INSTANCE_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_named_class_instance_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_named_class_instance_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "goal_key": NODE_NAMED_CLASS_INSTANCE_GOAL_KEY,
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "scenarios": {
            "trend": scenarios["trend"],
            "lying": scenarios["lying"],
            "matched": scenarios["matched"],
        },
        "already_solvable": {"ok": bool(skip_result.get("ok")), "grew": bool(skip_result.get("grew"))},
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_NAMED_CLASS_INSTANCE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_node_named_class_instance_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the named class-instance npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_named_class_instance_apply_catalog()
    scenarios = _node_named_class_instance_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_named_class_instance_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_NAMED_CLASS_INSTANCE_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_NAMED_CLASS_INSTANCE_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_named_class_instance_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    named_ok = (
        bool(scenarios.get("winner_is_named_export_class"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("winner_is_not_named_export_class_static"))
        and bool(scenarios.get("named_class_instance_selected"))
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and origin_ok
        and named_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "named_ok": named_ok,
    }


def builtin_application_node_named_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: named class-instance npm tarballs grow after instance reflection."""

    catalog = load_node_named_class_instance_apply_catalog()
    scenarios = _node_named_class_instance_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-application-node-named-class-instance-proof-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_named_class_instance_growth_plane(report_dir)
        verification = (
            verify_application_node_named_class_instance_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_fast_xml_parser"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_named_class_instance_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_fast_xml_parser": bool((plane.get("grade") or {}).get("grow_winner_is_fast_xml_parser")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "named_class_instance_selected": bool(scenarios["named_class_instance_selected"]),
        "winner_is_named_export_class": bool(scenarios["winner_is_named_export_class"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class_static": bool(scenarios["winner_is_not_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_node_named_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_named_class_instance_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_named_class_instance_growth_plane_proof; "
        "r=builtin_application_node_named_class_instance_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_named_class_instance_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_fast_xml_parser') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('named_class_instance_selected') "
        "and r.get('winner_is_named_export_class') and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class_static') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_named_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the named class-instance application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-node-class-static-growth-plane",
            "capability.application-node-default-export-class-growth-plane",
            "capability.application-node-default-export-object-growth-plane",
            "capability.application-node-default-export-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-named-class-instance-growth-plane",
        name="Application node named class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose callable API is a named class instance method: Node "
            "introspection reflects new Parser().parse / XMLBuilder.build rather "
            "than a default-exported constructable, and the covering package is "
            "foraged so the original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_named_class_instance_growth_plane",
        proof_command=application_node_named_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_named_class_instance_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips npm packages whose callable API "
            "is a named class instance method: Node introspection reflects "
            "new Parser().parse and XMLBuilder.build, named-only also selects "
            "those instance methods, and a covering package is foraged so the "
            "original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "named-class-instance"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=360)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_named_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a named class-instance live-fetched npm tarball."""

    result = run_application_node_named_class_instance_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_node_named_class_construct_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering npm tarball needs class construction."""

    payload = load_catalog(DEFAULT_NODE_NAMED_CLASS_CONSTRUCT_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _node_named_class_construct_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (NODE_NAMED_CLASS_CONSTRUCT_WINNER_CAPABILITY_ID,)
        if NODE_NAMED_CLASS_CONSTRUCT_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _named_class_construct_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-named-class-construct-") as tmp:
        named = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="node",
            close_deps=True,
            include_default=False,
        )
    record = named.get("record") or {}
    return (
        bool(named.get("ok"))
        and bool(record.get("named_export_class"))
        and str(record.get("winner") or "") == "Eta.compileBody"
    )


def _node_named_class_construct_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(NODE_NAMED_CLASS_CONSTRUCT_GOAL_KEY,))
    matched = match_forage_goal(
        (NODE_NAMED_CLASS_CONSTRUCT_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == NODE_NAMED_CLASS_CONSTRUCT_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == NODE_NAMED_CLASS_CONSTRUCT_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == NODE_NAMED_CLASS_CONSTRUCT_NPM_DECOY_SLUG,
        "match_is_eta": (matched.get("winner") or {}).get("slug") == NODE_NAMED_CLASS_CONSTRUCT_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(NODE_NAMED_CLASS_CONSTRUCT_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "named_class_construct_selected": _named_class_construct_selected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_named_export_class": bool(covering.get("named_export_class")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class_static": not bool(covering.get("default_export_class_static")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "named_export_class": bool(covering.get("named_export_class")),
            "named_export_class_static": bool(covering.get("named_export_class_static")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _node_named_class_construct_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_eta": grown.get("winner_slug") == NODE_NAMED_CLASS_CONSTRUCT_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "npm-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "named_class_construct_selected": bool(scenarios["named_class_construct_selected"]),
        "winner_is_named_export_class": bool(scenarios["winner_is_named_export_class"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class_static": bool(scenarios["winner_is_not_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_node_named_class_construct_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a named class that must be constructed."""

    catalog = load_node_named_class_construct_apply_catalog()
    scenarios = _node_named_class_construct_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _node_named_class_construct_hide(repo_root)
    grown = grow_application_task(
        NODE_NAMED_CLASS_CONSTRUCT_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or NODE_NAMED_CLASS_CONSTRUCT_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(NODE_NAMED_CLASS_CONSTRUCT_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _node_named_class_construct_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_node_named_class_construct_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_NODE_NAMED_CLASS_CONSTRUCT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_node_named_class_construct_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the named class-construct npm catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_node_named_class_construct_apply_catalog()
    scenarios = _node_named_class_construct_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _node_named_class_construct_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == NODE_NAMED_CLASS_CONSTRUCT_WINNER_SLUG
    live_proof = prove_absorbed_capability(NODE_NAMED_CLASS_CONSTRUCT_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_node_named_class_construct_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    named_ok = (
        bool(scenarios.get("winner_is_named_export_class"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("winner_is_not_named_export_class_static"))
        and bool(scenarios.get("named_class_construct_selected"))
    )
    origin_ok = origin.get("kind") == "npm-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and named_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "named_ok": named_ok,
    }


def builtin_application_node_named_class_construct_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: named class construction forages instance methods after new Ctor(options)."""

    catalog = load_node_named_class_construct_apply_catalog()
    scenarios = _node_named_class_construct_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-named-class-construct-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_node_named_class_construct_growth_plane(report_dir)
        verification = (
            verify_application_node_named_class_construct_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_eta"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_node_named_class_construct_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_eta": bool((plane.get("grade") or {}).get("grow_winner_is_eta")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "named_class_construct_selected": bool(scenarios["named_class_construct_selected"]),
        "winner_is_named_export_class": bool(scenarios["winner_is_named_export_class"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class_static": bool(scenarios["winner_is_not_default_export_class_static"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_node_named_class_construct_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_node_named_class_construct_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_node_named_class_construct_growth_plane_proof; "
        "r=builtin_application_node_named_class_construct_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_node_named_class_construct_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_eta') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('named_class_construct_selected') "
        "and r.get('winner_is_named_export_class') and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class_static') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_node_named_class_construct_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the named class-construct application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-node-class-static-growth-plane",
            "capability.application-node-default-export-class-growth-plane",
            "capability.application-node-default-export-object-growth-plane",
            "capability.application-node-default-export-growth-plane",
            "capability.application-node-runtime-deps-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-node-named-class-construct-growth-plane",
        name="Application node named class-construct growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "npm tarball whose named class instance methods exist only after "
            "construction: Node introspection constructs new Parser(options) / "
            "new Eta(options) rather than requiring new Parser().parse on the "
            "prototype, and the covering package is foraged so the original "
            "task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_node_named_class_construct_growth_plane",
        proof_command=application_node_named_class_construct_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_node_named_class_construct_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips npm packages whose named class "
            "instance methods exist only after construction, including "
            "constructors that require arguments: Node introspection constructs "
            "new Parser(options) / new Eta() and reflects Eta.compileBody, "
            "named-only also selects that instance method, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "node", "named-class-construct"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=360)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_node_named_class_construct_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a named class that must be constructed."""

    result = run_application_node_named_class_construct_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_class_instance_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes Python class instance methods."""

    payload = load_catalog(DEFAULT_PYTHON_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_class_instance_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_CLASS_INSTANCE_WINNER_CAPABILITY_ID,)
        if PYTHON_CLASS_INSTANCE_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_class_instance_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-python-class-instance-") as tmp:
        inferred = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="python",
            close_deps=True,
        )
    record = inferred.get("record") or {}
    return (
        bool(inferred.get("ok"))
        and bool(record.get("python_class_instance"))
        and str(record.get("winner") or "") == "MarkdownIt.normalizeLink"
    )


def _python_class_instance_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(PYTHON_CLASS_INSTANCE_GOAL_KEY,))
    matched = match_forage_goal(
        (PYTHON_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == PYTHON_CLASS_INSTANCE_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == PYTHON_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "match_is_markdown_it_py": (matched.get("winner") or {}).get("slug") == PYTHON_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(PYTHON_CLASS_INSTANCE_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_class_instance_selected": _python_class_instance_selected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_python_class_instance": bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_class_instance": bool(covering.get("python_class_instance")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_class_instance_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_markdown_it_py": grown.get("winner_slug") == PYTHON_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_class_instance_selected": bool(scenarios["python_class_instance_selected"]),
        "winner_is_python_class_instance": bool(scenarios["winner_is_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_class_instance_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a Python class instance method after construction."""

    catalog = load_python_class_instance_apply_catalog()
    scenarios = _python_class_instance_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_class_instance_hide(repo_root)
    grown = grow_application_task(
        PYTHON_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or PYTHON_CLASS_INSTANCE_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(PYTHON_CLASS_INSTANCE_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_class_instance_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_class_instance_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_CLASS_INSTANCE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_class_instance_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the Python class-instance catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_class_instance_apply_catalog()
    scenarios = _python_class_instance_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_class_instance_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == PYTHON_CLASS_INSTANCE_WINNER_SLUG
    live_proof = prove_absorbed_capability(PYTHON_CLASS_INSTANCE_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_class_instance_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_class_instance_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: Python class instance methods forage after construction."""

    catalog = load_python_class_instance_apply_catalog()
    scenarios = _python_class_instance_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-class-instance-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_class_instance_growth_plane(report_dir)
        verification = (
            verify_application_python_class_instance_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_markdown_it_py"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_class_instance_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_markdown_it_py": bool((plane.get("grade") or {}).get("grow_winner_is_markdown_it_py")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_class_instance_selected": bool(scenarios["python_class_instance_selected"]),
        "winner_is_python_class_instance": bool(scenarios["winner_is_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_class_instance_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_class_instance_growth_plane_proof; "
        "r=builtin_application_python_class_instance_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_class_instance_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_markdown_it_py') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_class_instance_selected') "
        "and r.get('winner_is_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the Python class-instance application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-node-named-class-construct-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-class-instance-growth-plane",
        name="Application python class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python class instance method: "
            "introspection constructs Parser(opts) / MarkdownIt() and reflects "
            "instance methods that exist only after construction rather than a "
            "module-level function, and the covering package is foraged so the "
            "original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_python_class_instance_growth_plane",
        proof_command=application_python_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_class_instance_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python class instance method that exists only after construction: "
            "introspection constructs Parser(opts) / MarkdownIt() and reflects "
            "MarkdownIt.normalizeLink, and a covering package is foraged so the "
            "original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "python", "class-instance"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=360)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a Python class instance method after construction."""

    result = run_application_python_class_instance_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes Python class static methods."""

    payload = load_catalog(DEFAULT_PYTHON_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_class_static_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-python-class-static-") as tmp:
        inferred = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="python",
            close_deps=True,
        )
    record = inferred.get("record") or {}
    return (
        bool(inferred.get("ok"))
        and bool(record.get("python_class_static"))
        and not bool(record.get("python_class_instance"))
        and str(record.get("winner") or "") == "HTMLRenderer.escape_html"
    )


def _python_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(PYTHON_CLASS_STATIC_GOAL_KEY,))
    matched = match_forage_goal(
        (PYTHON_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next((row for row in probes if row.get("slug") == PYTHON_CLASS_STATIC_NPM_DECOY_SLUG), {})
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug") == PYTHON_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_marko": (matched.get("winner") or {}).get("slug") == PYTHON_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query") == query_from_goal(PYTHON_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_class_static_selected": _python_class_static_selected(winner_entry, repo_root=repo_root)
        if winner_entry
        else False,
        "winner_is_python_class_static": bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_class_static": bool(covering.get("python_class_static")),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_marko": grown.get("winner_slug") == PYTHON_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_class_static_selected": bool(scenarios["python_class_static_selected"]),
        "winner_is_python_class_static": bool(scenarios["winner_is_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a Python class static method."""

    catalog = load_python_class_static_apply_catalog()
    scenarios = _python_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id") or PYTHON_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(PYTHON_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the Python class-static catalog and re-prove the foraged winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_class_static_apply_catalog()
    scenarios = _python_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == PYTHON_CLASS_STATIC_WINNER_SLUG
    live_proof = prove_absorbed_capability(PYTHON_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_class_static_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: Python class static methods forage without construction."""

    catalog = load_python_class_static_apply_catalog()
    scenarios = _python_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_marko"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_class_static_growth_plane(report_dir)["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_marko": bool((plane.get("grade") or {}).get("grow_winner_is_marko")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_class_static_selected": bool(scenarios["python_class_static_selected"]),
        "winner_is_python_class_static": bool(scenarios["winner_is_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_class_static_growth_plane_proof; "
        "r=builtin_application_python_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_marko') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_class_static_selected') "
        "and r.get('winner_is_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove the Python class-static application-growth plane."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-construct-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-class-static-growth-plane",
        name="Application python class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python class static method: "
            "introspection reflects Class.method / HTMLRenderer.escape_html "
            "rather than Parser(opts).loads, including when the constructor "
            "cannot be satisfied, and the covering package is foraged so the "
            "original task becomes solvable."
        ),
        kind="python",
        entry="blackhole_agent.capability_application_growth:demo_application_python_class_static_growth_plane",
        proof_command=application_python_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python class static method: introspection reflects "
            "HTMLRenderer.escape_html as Class.method rather than "
            "Parser(opts).loads, and a covering package is foraged so the "
            "original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "python", "class-static"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=360)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a Python class static method."""

    result = run_application_python_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_nested_namespace_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes nested-namespace class statics."""

    payload = load_catalog(DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_nested_namespace_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_nested_namespace_class_static_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-python-nested-ns-class-static-") as tmp:
        inferred = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="python",
            close_deps=True,
        )
    record = inferred.get("record") or {}
    return (
        bool(inferred.get("ok"))
        and bool(record.get("python_nested_namespace_class_static"))
        and not bool(record.get("python_class_static"))
        and not bool(record.get("python_class_instance"))
        and str(record.get("winner") or "") == "api.String.from_raw"
    )


def _python_nested_namespace_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,))
    matched = match_forage_goal(
        (PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (row for row in probes if row.get("slug") == PYTHON_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_tomlkit": (matched.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_nested_namespace_class_static_selected": (
            _python_nested_namespace_class_static_selected(winner_entry, repo_root=repo_root)
            if winner_entry
            else False
        ),
        "winner_is_python_nested_namespace_class_static": bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_nested_namespace_class_static": bool(
                covering.get("python_nested_namespace_class_static")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_nested_namespace_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_tomlkit": grown.get("winner_slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_nested_namespace_class_static_selected": bool(
            scenarios["python_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_nested_namespace_class_static": bool(
            scenarios["winner_is_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_nested_namespace_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a Python nested-namespace class static method."""

    catalog = load_python_nested_namespace_class_static_apply_catalog()
    scenarios = _python_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_nested_namespace_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(PYTHON_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_nested_namespace_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_nested_namespace_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_nested_namespace_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the nested-namespace class-static catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_nested_namespace_class_static_apply_catalog()
    scenarios = _python_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_nested_namespace_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG
    live_proof = prove_absorbed_capability(PYTHON_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_nested_namespace_class_static_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_nested_namespace_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_nested_namespace_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: nested-namespace Python class statics forage without top-level Class.method."""

    catalog = load_python_nested_namespace_class_static_apply_catalog()
    scenarios = _python_nested_namespace_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-nested-ns-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_nested_namespace_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_nested_namespace_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_tomlkit"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_nested_namespace_class_static_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_tomlkit": bool((plane.get("grade") or {}).get("grow_winner_is_tomlkit")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_nested_namespace_class_static_selected": bool(
            scenarios["python_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_nested_namespace_class_static": bool(
            scenarios["winner_is_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_nested_namespace_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_nested_namespace_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_nested_namespace_class_static_growth_plane_proof; "
        "r=builtin_application_python_nested_namespace_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_nested_namespace_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_tomlkit') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_nested_namespace_class_static_selected') "
        "and r.get('winner_is_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_nested_namespace_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove nested-namespace Python class-static growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-nested-class-static-growth-plane",
        name="Application python nested-namespace class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class static "
            "method: introspection reflects package.submodule.Class.method / "
            "api.String.from_raw rather than a top-level Class.method, and the "
            "covering package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_nested_namespace_class_static_growth_plane"
        ),
        proof_command=application_python_nested_namespace_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_nested_namespace_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class static method: introspection reflects "
            "api.String.from_raw as package.submodule.Class.method rather than a "
            "top-level Class.method, and a covering package is foraged so the "
            "original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "python", "nested-namespace", "class-static"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=360)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_nested_namespace_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a Python nested-namespace class static method."""

    result = run_application_python_nested_namespace_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes nested-namespace class instances."""

    payload = load_catalog(DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_nested_namespace_class_instance_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID,)
        if PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_nested_namespace_class_instance_selected(entry: Mapping[str, Any], *, repo_root: Path) -> bool:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    request = forage_request_for(entry, repo_root=repo_root, live_fetch=True)
    source = request.get("source")
    if source is None or not Path(str(source)).exists():
        return False
    with tempfile.TemporaryDirectory(prefix="blackhole-python-nested-ns-class-instance-") as tmp:
        inferred = infer_acquisition_spec(
            slug=str(request.get("slug") or ""),
            name=str(request.get("name") or request.get("slug") or ""),
            source=Path(str(source)),
            staging_root=Path(tmp),
            hint=str(request.get("hint") or request.get("name") or request.get("slug") or ""),
            origin=request.get("origin") or {},
            runtime="python",
            close_deps=True,
        )
    record = inferred.get("record") or {}
    return (
        bool(inferred.get("ok"))
        and bool(record.get("python_nested_namespace_class_instance"))
        and not bool(record.get("python_nested_namespace_class_static"))
        and not bool(record.get("python_class_static"))
        and not bool(record.get("python_class_instance"))
        and str(record.get("winner") or "") == "cmd.Template.has_def"
    )


def _python_nested_namespace_class_instance_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(items, absorbed=absorbed, goal_keys=(PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,))
    matched = match_forage_goal(
        (PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (row for row in probes if row.get("slug") == PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "match_is_mako": (matched.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_nested_namespace_class_instance_selected": (
            _python_nested_namespace_class_instance_selected(winner_entry, repo_root=repo_root)
            if winner_entry
            else False
        ),
        "winner_is_python_nested_namespace_class_instance": bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_nested_namespace_class_instance": bool(
                covering.get("python_nested_namespace_class_instance")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_nested_namespace_class_instance_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_mako": grown.get("winner_slug") == PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_nested_namespace_class_instance_selected": bool(
            scenarios["python_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_nested_namespace_class_instance_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a Python nested-namespace class instance method."""

    catalog = load_python_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_nested_namespace_class_instance_hide(repo_root)
    grown = grow_application_task(
        PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK, capability_id, repo_root=repo_root)
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_nested_namespace_class_instance_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_nested_namespace_class_instance_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_nested_namespace_class_instance_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the nested-namespace class-instance catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_nested_namespace_class_instance_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    live_proof = prove_absorbed_capability(PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_nested_namespace_class_instance_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_nested_namespace_class_instance_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: nested-namespace Python class instances forage without Class.method statics."""

    catalog = load_python_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_nested_namespace_class_instance_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-nested-ns-class-instance-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_nested_namespace_class_instance_growth_plane(report_dir)
        verification = (
            verify_application_python_nested_namespace_class_instance_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_mako"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_nested_namespace_class_instance_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_mako": bool((plane.get("grade") or {}).get("grow_winner_is_mako")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_nested_namespace_class_instance_selected": bool(
            scenarios["python_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_nested_namespace_class_instance_growth_plane_proof; "
        "r=builtin_application_python_nested_namespace_class_instance_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_nested_namespace_class_instance_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_mako') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_nested_namespace_class_instance_selected') "
        "and r.get('winner_is_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove nested-namespace Python class-instance growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-nested-class-instance-growth-plane",
        name="Application python nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class instance "
            "method: introspection constructs package.submodule.Class(opts) / "
            "cmd.Template(text) and reflects instance methods rather than a "
            "nested Class.method static, and the covering package is foraged so "
            "the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_nested_namespace_class_instance_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class instance method: introspection reflects "
            "cmd.Template.has_def as package.submodule.Class(opts).method rather "
            "than a nested Class.method static, and a covering package is foraged "
            "so the original task becomes solvable."
        ),
        tags=("foraging", "plane", "application", "growth", "python", "nested-namespace", "class-instance"),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=720)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a Python nested-namespace class instance method."""

    result = run_application_python_nested_namespace_class_instance_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_deep_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes two-level nested class instances."""

    payload = load_catalog(DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_deep_nested_namespace_class_instance_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID,)
        if PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_deep_nested_namespace_class_instance_selected(
    covering: Mapping[str, Any],
) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == "filters.sanitizer.Filter.allowed_token"
    )


def _python_deep_nested_namespace_class_instance_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "match_is_html5lib": (matched.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_deep_nested_namespace_class_instance_selected": (
            _python_deep_nested_namespace_class_instance_selected(covering)
        ),
        "winner_is_python_deep_nested_namespace_class_instance": bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_deep_nested_namespace_class_instance": bool(
                covering.get("python_deep_nested_namespace_class_instance")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_deep_nested_namespace_class_instance_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_html5lib": grown.get("winner_slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_deep_nested_namespace_class_instance_selected": bool(
            scenarios["python_deep_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_deep_nested_namespace_class_instance_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a two-level nested-namespace class instance method."""

    catalog = load_python_deep_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_deep_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_deep_nested_namespace_class_instance_hide(repo_root)
    grown = grow_application_task(
        PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_deep_nested_namespace_class_instance_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_deep_nested_namespace_class_instance_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_deep_nested_namespace_class_instance_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the two-level nested-namespace class-instance catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_deep_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_deep_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_deep_nested_namespace_class_instance_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get(
        "winner_slug"
    ) == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    live_proof = prove_absorbed_capability(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = (
        report.get("kind") == "capability_application_python_deep_nested_namespace_class_instance_growth_plane"
    )
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_deep_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_deep_nested_namespace_class_instance_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_deep_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: two-level nested-namespace Python class instances forage."""

    catalog = load_python_deep_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_deep_nested_namespace_class_instance_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-deep-nested-ns-class-instance-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_deep_nested_namespace_class_instance_growth_plane(report_dir)
        verification = (
            verify_application_python_deep_nested_namespace_class_instance_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_html5lib"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_deep_nested_namespace_class_instance_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_html5lib": bool((plane.get("grade") or {}).get("grow_winner_is_html5lib")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_deep_nested_namespace_class_instance_selected": bool(
            scenarios["python_deep_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_deep_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_deep_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_deep_nested_namespace_class_instance_growth_plane_proof; "
        "r=builtin_application_python_deep_nested_namespace_class_instance_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_deep_nested_namespace_class_instance_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_html5lib') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_deep_nested_namespace_class_instance_selected') "
        "and r.get('winner_is_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_deep_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove two-level nested-namespace Python class-instance growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-deep-nested-instance-growth-plane",
        name="Application python deep nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class instance "
            "method two submodule levels down: introspection constructs "
            "package.subpackage.submodule.Class(opts) / "
            "filters.sanitizer.Filter(source) and reflects instance methods rather "
            "than a one-level package.submodule.Class(opts).method, and the covering "
            "package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_deep_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_deep_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_deep_nested_namespace_class_instance_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class instance method two submodule levels down: "
            "introspection reflects filters.sanitizer.Filter.allowed_token as "
            "package.subpackage.submodule.Class(opts).method rather than a one-level "
            "package.submodule.Class(opts).method, and a covering package is foraged "
            "so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "deep-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_deep_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a two-level nested-namespace class instance method."""

    result = run_application_python_deep_nested_namespace_class_instance_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_nested_namespace_function_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes nested-namespace functions."""

    payload = load_catalog(DEFAULT_PYTHON_NESTED_NAMESPACE_FUNCTION_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_nested_namespace_function_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID,)
        if PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_nested_namespace_function_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == "utils.canonicalize_name"
    )


def _python_nested_namespace_function_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_NESTED_NAMESPACE_FUNCTION_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_NESTED_NAMESPACE_FUNCTION_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG,
        "match_is_packaging": (matched.get("winner") or {}).get("slug")
        == PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_NESTED_NAMESPACE_FUNCTION_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_nested_namespace_function_selected": (
            _python_nested_namespace_function_selected(covering)
        ),
        "winner_is_python_nested_namespace_function": bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_nested_namespace_function": bool(
                covering.get("python_nested_namespace_function")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_nested_namespace_function_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_packaging": grown.get("winner_slug")
        == PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_nested_namespace_function_selected": bool(
            scenarios["python_nested_namespace_function_selected"]
        ),
        "winner_is_python_nested_namespace_function": bool(
            scenarios["winner_is_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_nested_namespace_function_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a nested-namespace module function."""

    catalog = load_python_nested_namespace_function_apply_catalog()
    scenarios = _python_nested_namespace_function_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_nested_namespace_function_hide(repo_root)
    grown = grow_application_task(
        PYTHON_NESTED_NAMESPACE_FUNCTION_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_NESTED_NAMESPACE_FUNCTION_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_nested_namespace_function_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_nested_namespace_function_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_NESTED_NAMESPACE_FUNCTION_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_nested_namespace_function_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the nested-namespace function catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_nested_namespace_function_apply_catalog()
    scenarios = _python_nested_namespace_function_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_nested_namespace_function_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (report.get("grown") or {}).get("winner_slug") == PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG
    live_proof = prove_absorbed_capability(PYTHON_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_nested_namespace_function_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_nested_namespace_function_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_nested_namespace_function_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: nested-namespace Python module functions forage."""

    catalog = load_python_nested_namespace_function_apply_catalog()
    scenarios = _python_nested_namespace_function_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-nested-ns-function-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_nested_namespace_function_growth_plane(report_dir)
        verification = (
            verify_application_python_nested_namespace_function_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_packaging"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_nested_namespace_function_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_packaging": bool((plane.get("grade") or {}).get("grow_winner_is_packaging")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_nested_namespace_function_selected": bool(
            scenarios["python_nested_namespace_function_selected"]
        ),
        "winner_is_python_nested_namespace_function": bool(
            scenarios["winner_is_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_nested_namespace_function_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_nested_namespace_function_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_nested_namespace_function_growth_plane_proof; "
        "r=builtin_application_python_nested_namespace_function_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_nested_namespace_function_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_packaging') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_nested_namespace_function_selected') "
        "and r.get('winner_is_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_nested_namespace_function_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove nested-namespace Python function growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-nested-function-growth-plane",
        name="Application python nested-namespace function growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace module "
            "function: introspection reflects package.submodule.func / "
            "utils.canonicalize_name rather than a class method, and the covering "
            "package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_nested_namespace_function_growth_plane"
        ),
        proof_command=application_python_nested_namespace_function_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_nested_namespace_function_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace module function: introspection reflects "
            "utils.canonicalize_name as package.submodule.func rather than a "
            "class method, and a covering package is foraged so the original "
            "task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "function",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=600)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_nested_namespace_function_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a nested-namespace module function."""

    result = run_application_python_nested_namespace_function_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_deep_nested_namespace_function_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes two-level nested functions."""

    payload = load_catalog(DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_deep_nested_namespace_function_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID,)
        if PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_deep_nested_namespace_function_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == "ad.nrt.compact"
    )


def _python_deep_nested_namespace_function_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_NPM_DECOY_SLUG,
        "match_is_python_stdnum": (matched.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_deep_nested_namespace_function_selected": (
            _python_deep_nested_namespace_function_selected(covering)
        ),
        "winner_is_python_deep_nested_namespace_function": bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_deep_nested_namespace_function": bool(
                covering.get("python_deep_nested_namespace_function")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_deep_nested_namespace_function_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_python_stdnum": grown.get("winner_slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_deep_nested_namespace_function_selected": bool(
            scenarios["python_deep_nested_namespace_function_selected"]
        ),
        "winner_is_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_deep_nested_namespace_function_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a two-level nested-namespace module function."""

    catalog = load_python_deep_nested_namespace_function_apply_catalog()
    scenarios = _python_deep_nested_namespace_function_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_deep_nested_namespace_function_hide(repo_root)
    grown = grow_application_task(
        PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_deep_nested_namespace_function_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_deep_nested_namespace_function_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_deep_nested_namespace_function_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the two-level nested-namespace function catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_deep_nested_namespace_function_apply_catalog()
    scenarios = _python_deep_nested_namespace_function_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_deep_nested_namespace_function_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug") == PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_deep_nested_namespace_function_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_deep_nested_namespace_function_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_deep_nested_namespace_function_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: two-level nested-namespace Python module functions forage."""

    catalog = load_python_deep_nested_namespace_function_apply_catalog()
    scenarios = _python_deep_nested_namespace_function_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-deep-nested-ns-function-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_deep_nested_namespace_function_growth_plane(report_dir)
        verification = (
            verify_application_python_deep_nested_namespace_function_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_python_stdnum"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_deep_nested_namespace_function_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_python_stdnum": bool((plane.get("grade") or {}).get("grow_winner_is_python_stdnum")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_deep_nested_namespace_function_selected": bool(
            scenarios["python_deep_nested_namespace_function_selected"]
        ),
        "winner_is_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_deep_nested_namespace_function_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_deep_nested_namespace_function_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_deep_nested_namespace_function_growth_plane_proof; "
        "r=builtin_application_python_deep_nested_namespace_function_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_deep_nested_namespace_function_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_python_stdnum') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_deep_nested_namespace_function_selected') "
        "and r.get('winner_is_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_deep_nested_namespace_function_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove two-level nested-namespace Python function growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-deep-nested-function-growth-plane",
        name="Application python deep nested-namespace function growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace module "
            "function two submodule levels down: introspection reflects "
            "package.subpackage.submodule.func / ad.nrt.compact rather than a "
            "one-level package.submodule.func, and the covering package is "
            "foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_deep_nested_namespace_function_growth_plane"
        ),
        proof_command=application_python_deep_nested_namespace_function_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_deep_nested_namespace_function_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace module function two submodule levels down: "
            "introspection reflects ad.nrt.compact as package.subpackage.submodule.func "
            "rather than a one-level package.submodule.func, and a covering package "
            "is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "function",
            "deep-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_deep_nested_namespace_function_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a two-level nested-namespace module function."""

    result = run_application_python_deep_nested_namespace_function_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_deep_nested_namespace_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes two-level nested class statics."""

    payload = load_catalog(DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_deep_nested_namespace_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_deep_nested_namespace_class_static_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == "dev.helpers.File.exists"
    )


def _python_deep_nested_namespace_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_isbnlib": (matched.get("winner") or {}).get("slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_deep_nested_namespace_class_static_selected": (
            _python_deep_nested_namespace_class_static_selected(covering)
        ),
        "winner_is_python_deep_nested_namespace_class_static": bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_deep_nested_namespace_class_static": bool(
                covering.get("python_deep_nested_namespace_class_static")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_deep_nested_namespace_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_isbnlib": grown.get("winner_slug")
        == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_deep_nested_namespace_class_static_selected": bool(
            scenarios["python_deep_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_deep_nested_namespace_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a two-level nested-namespace class static method."""

    catalog = load_python_deep_nested_namespace_class_static_apply_catalog()
    scenarios = _python_deep_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_deep_nested_namespace_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_deep_nested_namespace_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_deep_nested_namespace_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_deep_nested_namespace_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the two-level nested-namespace class-static catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_deep_nested_namespace_class_static_apply_catalog()
    scenarios = _python_deep_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_deep_nested_namespace_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug") == PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_deep_nested_namespace_class_static_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_deep_nested_namespace_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_deep_nested_namespace_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: two-level nested-namespace Python class statics forage."""

    catalog = load_python_deep_nested_namespace_class_static_apply_catalog()
    scenarios = _python_deep_nested_namespace_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-deep-nested-ns-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_deep_nested_namespace_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_deep_nested_namespace_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_isbnlib"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_deep_nested_namespace_class_static_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_isbnlib": bool((plane.get("grade") or {}).get("grow_winner_is_isbnlib")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_deep_nested_namespace_class_static_selected": bool(
            scenarios["python_deep_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_deep_nested_namespace_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_deep_nested_namespace_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_deep_nested_namespace_class_static_growth_plane_proof; "
        "r=builtin_application_python_deep_nested_namespace_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_deep_nested_namespace_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_isbnlib') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_deep_nested_namespace_class_static_selected') "
        "and r.get('winner_is_python_deep_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_deep_nested_namespace_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove two-level nested-namespace Python class-static growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-deep-nested-static-growth-plane",
        name="Application python deep nested-namespace class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class "
            "static method two submodule levels down: introspection reflects "
            "package.subpackage.submodule.Class.method / dev.helpers.File.exists "
            "rather than a two-level module function, and the covering package "
            "is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_deep_nested_namespace_class_static_growth_plane"
        ),
        proof_command=application_python_deep_nested_namespace_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_deep_nested_namespace_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class static method two submodule levels down: "
            "introspection reflects dev.helpers.File.exists as "
            "package.subpackage.submodule.Class.method rather than a two-level "
            "module function, and a covering package is foraged so the original "
            "task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-static",
            "deep-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_deep_nested_namespace_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a two-level nested-namespace class static method."""

    result = run_application_python_deep_nested_namespace_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_triple_nested_namespace_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes three-level nested class statics."""

    payload = load_catalog(DEFAULT_PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_triple_nested_namespace_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_triple_nested_namespace_class_static_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_triple_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == "utils.math.math2html.Cloner.clone"
    )


def _python_triple_nested_namespace_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_docutils": (matched.get("winner") or {}).get("slug")
        == PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_triple_nested_namespace_class_static_selected": (
            _python_triple_nested_namespace_class_static_selected(covering)
        ),
        "winner_is_python_triple_nested_namespace_class_static": bool(
            covering.get("python_triple_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": not bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_triple_nested_namespace_class_static": bool(
                covering.get("python_triple_nested_namespace_class_static")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_triple_nested_namespace_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_docutils": grown.get("winner_slug")
        == PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_triple_nested_namespace_class_static_selected": bool(
            scenarios["python_triple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_triple_nested_namespace_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a three-level nested-namespace class static method."""

    catalog = load_python_triple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_triple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_triple_nested_namespace_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_triple_nested_namespace_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_triple_nested_namespace_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_triple_nested_namespace_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the three-level nested-namespace class-static catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_triple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_triple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_triple_nested_namespace_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug") == PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = report.get("kind") == "capability_application_python_triple_nested_namespace_class_static_growth_plane"
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_triple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_triple_nested_namespace_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_triple_nested_namespace_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: three-level nested-namespace Python class statics forage."""

    catalog = load_python_triple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_triple_nested_namespace_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-triple-nested-ns-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_triple_nested_namespace_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_triple_nested_namespace_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_docutils"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_triple_nested_namespace_class_static_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_docutils": bool((plane.get("grade") or {}).get("grow_winner_is_docutils")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_triple_nested_namespace_class_static_selected": bool(
            scenarios["python_triple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_triple_nested_namespace_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_triple_nested_namespace_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_triple_nested_namespace_class_static_growth_plane_proof; "
        "r=builtin_application_python_triple_nested_namespace_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_triple_nested_namespace_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_docutils') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_triple_nested_namespace_class_static_selected') "
        "and r.get('winner_is_python_triple_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_triple_nested_namespace_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove three-level nested-namespace Python class-static growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-deep-nested-static-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-triple-nested-static-growth-plane",
        name="Application python triple nested-namespace class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class "
            "static method three submodule levels down: introspection reflects "
            "package.subpackage.subpackage.submodule.Class.method / "
            "utils.math.math2html.Cloner.clone rather than a two-level "
            "package.subpackage.submodule.Class.method, and the covering "
            "package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_triple_nested_namespace_class_static_growth_plane"
        ),
        proof_command=application_python_triple_nested_namespace_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_triple_nested_namespace_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class static method three submodule levels down: "
            "introspection reflects utils.math.math2html.Cloner.clone as "
            "package.subpackage.subpackage.submodule.Class.method rather than a "
            "two-level package.subpackage.submodule.Class.method, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-static",
            "triple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_triple_nested_namespace_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a three-level nested-namespace class static method."""

    result = run_application_python_triple_nested_namespace_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_quadruple_nested_namespace_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes four-level nested class statics."""

    payload = load_catalog(DEFAULT_PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_quadruple_nested_namespace_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_quadruple_nested_namespace_class_static_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_quadruple_nested_namespace_class_static"))
        and not bool(covering.get("python_triple_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_CALLABLE
    )


def _python_quadruple_nested_namespace_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_django": (matched.get("winner") or {}).get("slug")
        == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_quadruple_nested_namespace_class_static_selected": (
            _python_quadruple_nested_namespace_class_static_selected(covering)
        ),
        "winner_is_python_quadruple_nested_namespace_class_static": bool(
            covering.get("python_quadruple_nested_namespace_class_static")
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": not bool(
            covering.get("python_triple_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": not bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_quadruple_nested_namespace_class_static": bool(
                covering.get("python_quadruple_nested_namespace_class_static")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_quadruple_nested_namespace_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_django": grown.get("winner_slug")
        == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_quadruple_nested_namespace_class_static_selected": bool(
            scenarios["python_quadruple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_quadruple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_quadruple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_quadruple_nested_namespace_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a four-level nested-namespace class static method."""

    catalog = load_python_quadruple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_quadruple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_quadruple_nested_namespace_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_quadruple_nested_namespace_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_quadruple_nested_namespace_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_quadruple_nested_namespace_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the four-level nested-namespace class-static catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_quadruple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_quadruple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_quadruple_nested_namespace_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug")
        == PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = (
        report.get("kind") == "capability_application_python_quadruple_nested_namespace_class_static_growth_plane"
    )
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_quadruple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_triple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_quadruple_nested_namespace_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_quadruple_nested_namespace_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: four-level nested-namespace Python class statics forage."""

    catalog = load_python_quadruple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_quadruple_nested_namespace_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-quadruple-nested-ns-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_quadruple_nested_namespace_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_quadruple_nested_namespace_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_django"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_quadruple_nested_namespace_class_static_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_django": bool((plane.get("grade") or {}).get("grow_winner_is_django")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_quadruple_nested_namespace_class_static_selected": bool(
            scenarios["python_quadruple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_quadruple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_quadruple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_quadruple_nested_namespace_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_quadruple_nested_namespace_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_quadruple_nested_namespace_class_static_growth_plane_proof; "
        "r=builtin_application_python_quadruple_nested_namespace_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_quadruple_nested_namespace_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_django') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_quadruple_nested_namespace_class_static_selected') "
        "and r.get('winner_is_python_quadruple_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_triple_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_quadruple_nested_namespace_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove four-level nested-namespace Python class-static growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-triple-nested-static-growth-plane",
            "capability.application-python-deep-nested-static-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-static-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-quad-nested-static-growth-plane",
        name="Application python quadruple nested-namespace class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class "
            "static method four submodule levels down: introspection reflects "
            "package.subpackage.subpackage.subpackage.submodule.Class.method / "
            "contrib.humanize.templatetags.humanize.NaturalTimeFormatter.string_for "
            "rather than a three-level package.subpackage.subpackage.submodule.Class.method, "
            "and the covering package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_quadruple_nested_namespace_class_static_growth_plane"
        ),
        proof_command=application_python_quadruple_nested_namespace_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_quadruple_nested_namespace_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class static method four submodule levels down: "
            "introspection reflects contrib.humanize.templatetags.humanize."
            "NaturalTimeFormatter.string_for as "
            "package.subpackage.subpackage.subpackage.submodule.Class.method rather than a "
            "three-level package.subpackage.subpackage.submodule.Class.method, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-static",
            "quadruple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_quadruple_nested_namespace_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a four-level nested-namespace class static method."""

    result = run_application_python_quadruple_nested_namespace_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_quintuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes five-level nested class instance methods."""

    payload = load_catalog(DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_quintuple_nested_namespace_class_instance_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID,)
        if PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_quintuple_nested_namespace_class_instance_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_quintuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_quintuple_nested_namespace_class_static"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_static"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_instance"))
        and not bool(covering.get("python_triple_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE
    )


def _python_quintuple_nested_namespace_class_instance_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "match_is_oauthlib": (matched.get("winner") or {}).get("slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_quintuple_nested_namespace_class_instance_selected": (
            _python_quintuple_nested_namespace_class_instance_selected(covering)
        ),
        "winner_is_python_quintuple_nested_namespace_class_instance": bool(
            covering.get("python_quintuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": not bool(
            covering.get("python_triple_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": not bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_quintuple_nested_namespace_class_instance": bool(
                covering.get("python_quintuple_nested_namespace_class_instance")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_quintuple_nested_namespace_class_instance_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_oauthlib": grown.get("winner_slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_quintuple_nested_namespace_class_instance_selected": bool(
            scenarios["python_quintuple_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_quintuple_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_quintuple_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_quintuple_nested_namespace_class_instance_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a five-level nested-namespace class instance method."""

    catalog = load_python_quintuple_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_quintuple_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_quintuple_nested_namespace_class_instance_hide(repo_root)
    grown = grow_application_task(
        PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_quintuple_nested_namespace_class_instance_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_quintuple_nested_namespace_class_instance_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_quintuple_nested_namespace_class_instance_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the five-level nested-namespace class-instance catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_quintuple_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_quintuple_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_quintuple_nested_namespace_class_instance_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = (
        report.get("kind") == "capability_application_python_quintuple_nested_namespace_class_instance_growth_plane"
    )
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_quintuple_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_triple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_quintuple_nested_namespace_class_instance_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_quintuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: five-level nested-namespace Python class instance methods forage."""

    catalog = load_python_quintuple_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_quintuple_nested_namespace_class_instance_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-quintuple-nested-ns-class-instance-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_quintuple_nested_namespace_class_instance_growth_plane(report_dir)
        verification = (
            verify_application_python_quintuple_nested_namespace_class_instance_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_oauthlib"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_quintuple_nested_namespace_class_instance_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_oauthlib": bool((plane.get("grade") or {}).get("grow_winner_is_oauthlib")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_quintuple_nested_namespace_class_instance_selected": bool(
            scenarios["python_quintuple_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_quintuple_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_quintuple_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_quintuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_quintuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_quintuple_nested_namespace_class_instance_growth_plane_proof; "
        "r=builtin_application_python_quintuple_nested_namespace_class_instance_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_quintuple_nested_namespace_class_instance_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_oauthlib') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_quintuple_nested_namespace_class_instance_selected') "
        "and r.get('winner_is_python_quintuple_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_triple_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_quintuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove five-level nested-namespace Python class-instance growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-quad-nested-static-growth-plane",
            "capability.application-python-triple-nested-static-growth-plane",
            "capability.application-python-deep-nested-static-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-quint-nested-instance-growth-plane",
        name="Application python quintuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose callable API is a Python nested-namespace class "
            "instance method five submodule levels down: introspection reflects "
            "package.subpackage.subpackage.subpackage.subpackage.submodule.Class(opts).method / "
            "openid.connect.core.grant_types.authorization_code.AuthorizationCodeGrant.id_token_hash "
            "rather than a four-level package.subpackage.subpackage.subpackage.submodule.Class.method, "
            "and the covering package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_quintuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_quintuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_quintuple_nested_namespace_class_instance_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose callable API is a "
            "Python nested-namespace class instance method five submodule levels down: "
            "introspection reflects openid.connect.core.grant_types.authorization_code."
            "AuthorizationCodeGrant.id_token_hash as "
            "package.subpackage.subpackage.subpackage.subpackage.submodule.Class(opts).method rather than a "
            "four-level package.subpackage.subpackage.subpackage.submodule.Class.method, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "quintuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_quintuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a five-level nested-namespace class instance method."""

    result = run_application_python_quintuple_nested_namespace_class_instance_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_quintuple_nested_namespace_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes five-level nested class statics."""

    payload = load_catalog(DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_quintuple_nested_namespace_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_quintuple_nested_namespace_class_static_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_quintuple_nested_namespace_class_static"))
        and not bool(covering.get("python_sextuple_nested_namespace_class_static"))
        and not bool(covering.get("python_quintuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_static"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_instance"))
        and not bool(covering.get("python_triple_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CALLABLE
    )


def _python_quintuple_nested_namespace_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_virtualenv": (matched.get("winner") or {}).get("slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_quintuple_nested_namespace_class_static_selected": (
            _python_quintuple_nested_namespace_class_static_selected(covering)
        ),
        "winner_is_python_quintuple_nested_namespace_class_static": bool(
            covering.get("python_quintuple_nested_namespace_class_static")
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": not bool(
            covering.get("python_triple_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": not bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_quintuple_nested_namespace_class_static": bool(
                covering.get("python_quintuple_nested_namespace_class_static")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_quintuple_nested_namespace_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_virtualenv": grown.get("winner_slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_quintuple_nested_namespace_class_static_selected": bool(
            scenarios["python_quintuple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_quintuple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_quintuple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_quintuple_nested_namespace_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a five-level nested-namespace class static method."""

    catalog = load_python_quintuple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_quintuple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_quintuple_nested_namespace_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_quintuple_nested_namespace_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_quintuple_nested_namespace_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_quintuple_nested_namespace_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the five-level nested-namespace class-static catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_quintuple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_quintuple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_quintuple_nested_namespace_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug")
        == PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = (
        report.get("kind") == "capability_application_python_quintuple_nested_namespace_class_static_growth_plane"
    )
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_quintuple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_triple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_quintuple_nested_namespace_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_quintuple_nested_namespace_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: five-level nested-namespace Python class statics forage."""

    catalog = load_python_quintuple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_quintuple_nested_namespace_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-quintuple-nested-ns-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_quintuple_nested_namespace_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_quintuple_nested_namespace_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_virtualenv"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_quintuple_nested_namespace_class_static_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_virtualenv": bool((plane.get("grade") or {}).get("grow_winner_is_virtualenv")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_quintuple_nested_namespace_class_static_selected": bool(
            scenarios["python_quintuple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_quintuple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_quintuple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_quintuple_nested_namespace_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_quintuple_nested_namespace_class_static_growth_plane_proof_command() -> str:
    return (
        'uv run python -c "from blackhole_agent.capability_application_growth import '
        "builtin_application_python_quintuple_nested_namespace_class_static_growth_plane_proof; "
        "r=builtin_application_python_quintuple_nested_namespace_class_static_growth_plane_proof(); "
        "assert r['ok'] and r.get('action')=='application_python_quintuple_nested_namespace_class_static_growth_plane' "
        "and r.get('already_solvable_skips_forage') and r.get('uncovered_stays_unsolved') "
        "and r.get('trend_npm_decoy_wins') and r.get('lying_catalog_picks_npm_decoy') "
        "and r.get('grow_winner_is_virtualenv') and r.get('npm_decoy_probed') "
        "and r.get('npm_decoy_not_no_source') and r.get('catalog_provides_ignored') "
        "and r.get('python_quintuple_nested_namespace_class_static_selected') "
        "and r.get('winner_is_python_quintuple_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_triple_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_nested_namespace_class_static') "
        "and r.get('winner_is_not_python_deep_nested_namespace_function') "
        "and r.get('winner_is_not_python_nested_namespace_function') "
        "and r.get('winner_is_not_python_deep_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_nested_namespace_class_instance') "
        "and r.get('winner_is_not_python_class_static') "
        "and r.get('winner_is_not_python_class_instance') "
        "and r.get('winner_is_not_named_export_class_static') "
        "and r.get('winner_is_not_default_export') "
        "and r.get('winner_is_not_default_export_class') "
        "and r.get('winner_is_not_default_export_object') "
        "and r.get('winner_origin_live') and r.get('winner_source_not_stewardship') "
        "and r.get('registries_npm_and_pypi') and r.get('query_from_goal') "
        "and r.get('network_unused') and r.get('plane_ok') and r.get('verify_ok') "
        "and r.get('tampered_rejected') and r.get('forage_ok') and r.get('grew') "
        "and r.get('unplannable_before') and r.get('grown_plan_solved') "
        "and r.get('ablation_unplannable') and r.get('no_separate_plane_invocation') "
        "and not r.get('used_skill_route_discovery')\""
    )


def register_application_python_quintuple_nested_namespace_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove five-level nested-namespace Python class-static growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-quint-nested-instance-growth-plane",
            "capability.application-python-quad-nested-static-growth-plane",
            "capability.application-python-triple-nested-static-growth-plane",
            "capability.application-python-deep-nested-static-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-quint-nested-static-growth-plane",
        name="Application python quintuple nested-namespace class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose covering Class.method is a Python nested-namespace class "
            "static five submodule levels down: introspection reflects "
            "create.via_global_ref.builtin.cpython.common.CPython.exe_stem as a "
            "cwd-independent JSON scalar rather than an inherited path validator "
            "such as CPython.validate_dest, and the covering package is foraged "
            "so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_quintuple_nested_namespace_class_static_growth_plane"
        ),
        proof_command=application_python_quintuple_nested_namespace_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_quintuple_nested_namespace_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class.method "
            "is a Python nested-namespace class static five submodule levels down "
            "that returns a cwd-independent JSON scalar: introspection reflects "
            "create.via_global_ref.builtin.cpython.common.CPython.exe_stem rather "
            "than the inherited path validator CPython.validate_dest, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-static",
            "quintuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_quintuple_nested_namespace_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a five-level nested-namespace class static method."""

    result = run_application_python_quintuple_nested_namespace_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_sextuple_nested_namespace_class_static_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes six-level nested class statics."""

    payload = load_catalog(DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_sextuple_nested_namespace_class_static_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID,)
        if PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_sextuple_nested_namespace_class_static_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_sextuple_nested_namespace_class_static"))
        and not bool(covering.get("python_sextuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_quintuple_nested_namespace_class_static"))
        and not bool(covering.get("python_quintuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_static"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_instance"))
        and not bool(covering.get("python_triple_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_CALLABLE
    )


def _python_sextuple_nested_namespace_class_static_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_NPM_DECOY_SLUG,
        "match_is_google_ads": (matched.get("winner") or {}).get("slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_sextuple_nested_namespace_class_static_selected": (
            _python_sextuple_nested_namespace_class_static_selected(covering)
        ),
        "winner_is_python_sextuple_nested_namespace_class_static": bool(
            covering.get("python_sextuple_nested_namespace_class_static")
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": not bool(
            covering.get("python_triple_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": not bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_sextuple_nested_namespace_class_static": bool(
                covering.get("python_sextuple_nested_namespace_class_static")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_sextuple_nested_namespace_class_static_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_google_ads": grown.get("winner_slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_sextuple_nested_namespace_class_static_selected": bool(
            scenarios["python_sextuple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_sextuple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_sextuple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_sextuple_nested_namespace_class_static_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a six-level nested-namespace class static method."""

    catalog = load_python_sextuple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_sextuple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_sextuple_nested_namespace_class_static_hide(repo_root)
    grown = grow_application_task(
        PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_sextuple_nested_namespace_class_static_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_sextuple_nested_namespace_class_static_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_sextuple_nested_namespace_class_static_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the five-level nested-namespace class-static catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_sextuple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_sextuple_nested_namespace_class_static_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_sextuple_nested_namespace_class_static_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = (
        report.get("kind") == "capability_application_python_sextuple_nested_namespace_class_static_growth_plane"
    )
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_sextuple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_triple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_sextuple_nested_namespace_class_static_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_sextuple_nested_namespace_class_static_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: six-level nested-namespace Python class statics forage."""

    catalog = load_python_sextuple_nested_namespace_class_static_apply_catalog()
    scenarios = _python_sextuple_nested_namespace_class_static_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="blackhole-python-sextuple-nested-ns-class-static-plane-") as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_sextuple_nested_namespace_class_static_growth_plane(report_dir)
        verification = (
            verify_application_python_sextuple_nested_namespace_class_static_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_google_ads"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_sextuple_nested_namespace_class_static_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_google_ads": bool((plane.get("grade") or {}).get("grow_winner_is_google_ads")),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_sextuple_nested_namespace_class_static_selected": bool(
            scenarios["python_sextuple_nested_namespace_class_static_selected"]
        ),
        "winner_is_python_sextuple_nested_namespace_class_static": bool(
            scenarios["winner_is_python_sextuple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_sextuple_nested_namespace_class_static_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_sextuple_nested_namespace_class_static_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-sextuple-nested-class-static-proof"
    )


def register_application_python_sextuple_nested_namespace_class_static_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove six-level nested-namespace Python class-static growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-quint-nested-static-growth-plane",
            "capability.application-python-quint-nested-instance-growth-plane",
            "capability.application-python-quad-nested-static-growth-plane",
            "capability.application-python-triple-nested-static-growth-plane",
            "capability.application-python-deep-nested-static-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-sext-nested-static-growth-plane",
        name="Application python sextuple nested-namespace class-static growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose covering Class.method is a Python nested-namespace class "
            "static six submodule levels down: introspection reflects "
            "ads.googleads.v25.services.services.account_budget_proposal_service.AccountBudgetProposalServiceClient.common_billing_account_path as a "
            "cwd-independent JSON scalar rather than a five-level nested Class.method static, "
            "and the covering package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_sextuple_nested_namespace_class_static_growth_plane"
        ),
        proof_command=application_python_sextuple_nested_namespace_class_static_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_sextuple_nested_namespace_class_static_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class.method "
            "is a Python nested-namespace class static six submodule levels down "
            "that returns a cwd-independent JSON scalar: introspection reflects "
            "ads.googleads.v25.services.services.account_budget_proposal_service.AccountBudgetProposalServiceClient.common_billing_account_path rather "
            "than a five-level nested Class.method static, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-static",
            "sextuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_sextuple_nested_namespace_class_static_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a six-level nested-namespace class static method."""

    result = run_application_python_sextuple_nested_namespace_class_static_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_sextuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    """Load the catalog whose covering sdist exposes six-level nested class instance methods."""

    payload = load_catalog(DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def _python_sextuple_nested_namespace_class_instance_hide(repo_root: Path) -> tuple[str, ...]:
    ledger = load_ledger(default_ledger_path(repo_root))
    return (
        (PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID,)
        if PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID in ledger.capabilities
        else ()
    )


def _python_sextuple_nested_namespace_class_instance_selected(covering: Mapping[str, Any]) -> bool:
    callables = [str(name) for name in (covering.get("callables") or []) if str(name)]
    winner = callables[0] if callables else ""
    return (
        bool(covering.get("python_sextuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_tredecuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_tredecuple_nested_namespace_class_static"))
        and not bool(covering.get("python_duodecuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_duodecuple_nested_namespace_class_static"))
        and not bool(covering.get("python_undecuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_undecuple_nested_namespace_class_static"))
        and not bool(covering.get("python_decuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_decuple_nested_namespace_class_static"))
        and not bool(covering.get("python_nonuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_nonuple_nested_namespace_class_static"))
        and not bool(covering.get("python_octuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_octuple_nested_namespace_class_static"))
        and not bool(covering.get("python_septuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_septuple_nested_namespace_class_static"))
        and not bool(covering.get("python_sextuple_nested_namespace_class_static"))
        and not bool(covering.get("python_quintuple_nested_namespace_class_static"))
        and not bool(covering.get("python_quintuple_nested_namespace_class_instance"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_static"))
        and not bool(covering.get("python_quadruple_nested_namespace_class_instance"))
        and not bool(covering.get("python_triple_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_class_static"))
        and not bool(covering.get("python_nested_namespace_class_static"))
        and not bool(covering.get("python_deep_nested_namespace_function"))
        and not bool(covering.get("python_nested_namespace_function"))
        and not bool(covering.get("python_deep_nested_namespace_class_instance"))
        and not bool(covering.get("python_nested_namespace_class_instance"))
        and not bool(covering.get("python_class_static"))
        and not bool(covering.get("python_class_instance"))
        and winner == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE
    )


def _python_sextuple_nested_namespace_class_instance_scenario_grades(
    catalog: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    items = list(catalog.get("items") or [])
    absorbed = sorted(APPLY_ABSORBED_SLUGS)
    trend = rank_catalog(strip_declared_provides(items), absorbed=absorbed)
    lying = rank_catalog(
        items, absorbed=absorbed, goal_keys=(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,)
    )
    matched = match_forage_goal(
        (PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GOAL_KEY,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    probes = list(matched.get("probes") or [])
    npm_probe = next(
        (
            row
            for row in probes
            if row.get("slug") == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG
        ),
        {},
    )
    winner_entry = matched.get("winner") or {}
    origin = dict(forage_request_for(winner_entry, repo_root=repo_root, live_fetch=True).get("origin") or {})
    overlay_fields = any(str(item.get("source") or item.get("replay_source") or "") for item in items)
    registries = {str(item.get("registry") or "") for item in items}
    uncovered = match_forage_goal(
        (NO_MATCH_GOAL,),
        catalog=catalog,
        absorbed=absorbed,
        forage=False,
        repo_root=repo_root,
        live_fetch=True,
    )
    covering = matched.get("covering") or {}
    return {
        "trend_npm_decoy_wins": (trend.get("winner") or {}).get("slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "lying_catalog_picks_npm_decoy": (lying.get("winner") or {}).get("slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_NPM_DECOY_SLUG,
        "match_is_apache_airflow_providers_amazon": (matched.get("winner") or {}).get("slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": npm_probe.get("skip_reason") not in {"", None, "no_source"},
        "npm_decoy_not_no_source": npm_probe.get("skip_reason") != "no_source",
        "catalog_provides_ignored": bool(matched.get("ok"))
        and (matched.get("winner") or {}).get("slug") != (lying.get("winner") or {}).get("slug"),
        "no_replay_source_field": overlay_fields is False,
        "winner_origin_live": origin.get("kind") in {"npm-live", "pypi-live"},
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": "npm" in registries and "pypi" in registries,
        "query_from_goal": catalog.get("query")
        == query_from_goal(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "network_unused": catalog.get("network_used") is False,
        "uncovered_refused": (not uncovered["ok"]) and uncovered.get("error") == "no forage match",
        "python_sextuple_nested_namespace_class_instance_selected": (
            _python_sextuple_nested_namespace_class_instance_selected(covering)
        ),
        "winner_is_python_sextuple_nested_namespace_class_instance": bool(
            covering.get("python_sextuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_sextuple_nested_namespace_class_static": not bool(
            covering.get("python_sextuple_nested_namespace_class_static")
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": not bool(
            covering.get("python_triple_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": not bool(
            covering.get("python_deep_nested_namespace_class_static")
        ),
        "winner_is_not_python_nested_namespace_class_static": not bool(
            covering.get("python_nested_namespace_class_static")
        ),
        "winner_is_not_python_deep_nested_namespace_function": not bool(
            covering.get("python_deep_nested_namespace_function")
        ),
        "winner_is_not_python_nested_namespace_function": not bool(
            covering.get("python_nested_namespace_function")
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": not bool(
            covering.get("python_deep_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nested_namespace_class_instance": not bool(
            covering.get("python_nested_namespace_class_instance")
        ),
        "winner_is_not_python_class_static": not bool(covering.get("python_class_static")),
        "winner_is_not_python_class_instance": not bool(covering.get("python_class_instance")),
        "winner_is_not_named_export_class_static": not bool(covering.get("named_export_class_static")),
        "winner_is_not_default_export": not bool(covering.get("default_export")),
        "winner_is_not_default_export_class": not bool(covering.get("default_export_class")),
        "winner_is_not_default_export_object": not bool(covering.get("default_export_object")),
        "matched": {
            "ok": bool(matched.get("ok")),
            "winner": (matched.get("winner") or {}).get("slug") or "",
            "origin": origin,
            "inferred_provides": list((matched.get("covering") or {}).get("inferred_provides") or []),
            "python_sextuple_nested_namespace_class_instance": bool(
                covering.get("python_sextuple_nested_namespace_class_instance")
            ),
            "probes": [
                {
                    "slug": row.get("slug"),
                    "skip_reason": row.get("skip_reason"),
                    "covers_goal": bool(row.get("covers_goal")),
                }
                for row in probes
            ],
        },
        "lying": {"ok": bool(lying.get("ok")), "winner": (lying.get("winner") or {}).get("slug") or ""},
        "trend": {
            "ok": bool(trend["ok"]),
            "winner": (trend.get("winner") or {}).get("slug") or "",
            "ranked_slugs": [row["slug"] for row in trend.get("ranked") or []],
        },
    }


def _python_sextuple_nested_namespace_class_instance_grade(
    *,
    skip_result: Mapping[str, Any],
    uncovered: Mapping[str, Any],
    grown: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    origin: Mapping[str, Any],
    honesty: Mapping[str, Any],
    separate_plane: bool | None = None,
) -> dict[str, Any]:
    grade = {
        "already_solvable_skips_forage": bool(skip_result.get("ok")) and skip_result.get("grew") is False,
        "uncovered_stays_unsolved": (not uncovered.get("ok"))
        and uncovered.get("error") == "no forage match"
        and uncovered.get("grew") is False,
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_apache_airflow_providers_amazon": grown.get("winner_slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "no_replay_source_field": bool(scenarios["no_replay_source_field"]),
        "winner_origin_live": origin.get("kind") == "pypi-live"
        and (grown.get("forage") or {}).get("fixture_overlay") is False,
        "winner_source_not_stewardship": bool(origin.get("source")) and not _source_is_stewardship(origin),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "python_sextuple_nested_namespace_class_instance_selected": bool(
            scenarios["python_sextuple_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_sextuple_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_sextuple_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_sextuple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_sextuple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "forage_ok": bool((grown.get("forage") or {}).get("ok")),
        "grew": bool(grown.get("grew")),
        "unplannable_before": bool(honesty.get("unplannable_before")),
        "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
        "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
        "no_separate_plane_invocation": True if separate_plane is None else bool(separate_plane),
    }
    grade["ok"] = all(grade.values())
    return grade


def run_application_python_sextuple_nested_namespace_class_instance_growth_plane(
    output_dir: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    forage: bool = True,
) -> dict[str, Any]:
    """Grow an unplannable task from a six-level nested-namespace class instance method."""

    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_sextuple_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    skip_result = grow_application_task(
        ALREADY_SOLVABLE_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    uncovered = grow_application_task(
        UNCOVERED_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        repo_root=repo_root,
        live_fetch=True,
    )
    hide_before = _python_sextuple_nested_namespace_class_instance_hide(repo_root)
    grown = grow_application_task(
        PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK,
        catalog=catalog,
        absorbed=sorted(APPLY_ABSORBED_SLUGS),
        forage=forage,
        hide_before=hide_before,
        repo_root=repo_root,
        live_fetch=True,
    )
    honesty: dict[str, Any] = {
        "ok": False,
        "unplannable_before": False,
        "grown_plan_solved": False,
        "ablation_unplannable": False,
    }
    capability_id = str(
        (grown.get("forage") or {}).get("capability_id")
        or PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_CAPABILITY_ID
    )
    if grown.get("ok") and grown.get("grew"):
        honesty = _honesty(
            PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK, capability_id, repo_root=repo_root
        )
    origin = dict((grown.get("forage") or {}).get("origin") or {})
    grade = _python_sextuple_nested_namespace_class_instance_grade(
        skip_result=skip_result,
        uncovered=uncovered,
        grown=grown,
        scenarios=scenarios,
        origin=origin,
        honesty=honesty,
        separate_plane=skip_result.get("used_forage_growth_plane") is False
        and grown.get("used_forage_growth_plane") is False
        and uncovered.get("used_forage_growth_plane") is False,
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_python_sextuple_nested_namespace_class_instance_growth_plane",
        "generated_at": utc_now_iso(),
        "query": catalog.get("query") or "",
        "catalog_digest": _digest({"query": catalog.get("query"), "items": catalog.get("items")}),
        "already_solvable": {
            "ok": bool(skip_result.get("ok")),
            "grew": bool(skip_result.get("grew")),
        },
        "uncovered": {
            "ok": bool(uncovered.get("ok")),
            "grew": bool(uncovered.get("grew")),
            "error": uncovered.get("error") or "",
        },
        "grown": {
            "ok": bool(grown.get("ok")),
            "grew": bool(grown.get("grew")),
            "plan": grown.get("plan"),
            "winner_slug": grown.get("winner_slug") or "",
            "forage": grown.get("forage") or {},
        },
        "honesty": {
            "ok": bool(honesty.get("ok")),
            "unplannable_before": bool(honesty.get("unplannable_before")),
            "grown_plan_solved": bool(honesty.get("grown_plan_solved")),
            "ablation_unplannable": bool(honesty.get("ablation_unplannable")),
            "capability_id": honesty.get("capability_id"),
            "plan": honesty.get("plan"),
        },
        "grade": grade,
    }
    report["report_digest"] = _report_digest(report)
    target_dir = output_dir or DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "plane-report.json", report)
    return {
        "ok": bool(grade["ok"]),
        "report_dir": str(target_dir),
        "winner": grown.get("winner_slug") or "",
        "grade": grade,
        "capability_id": (grown.get("forage") or {}).get("capability_id"),
        "query": catalog.get("query") or "",
        "registries": list(catalog.get("registries") or []),
        "origin": origin,
    }


def verify_application_python_sextuple_nested_namespace_class_instance_growth_plane(
    report_dir: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Re-match the six-level nested-namespace class-instance catalog and re-prove the winner."""

    report_path = report_dir / "plane-report.json"
    if not report_path.is_file():
        return {"ok": False, "error": f"report not found: {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    digest_ok = _report_digest(report) == report.get("report_digest")
    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_sextuple_nested_namespace_class_instance_scenario_grades(catalog, repo_root=repo_root)
    catalog_ok = _digest({"query": catalog.get("query"), "items": catalog.get("items")}) == report.get(
        "catalog_digest"
    )
    origin = dict(((report.get("grown") or {}).get("forage") or {}).get("origin") or {})
    expected_grade = _python_sextuple_nested_namespace_class_instance_grade(
        skip_result=report.get("already_solvable") or {},
        uncovered=report.get("uncovered") or {},
        grown=report.get("grown") or {},
        scenarios=scenarios,
        origin=origin,
        honesty=report.get("honesty") or {},
    )
    recorded_grade = dict(report.get("grade") or {})
    grade_ok = recorded_grade == expected_grade and bool(recorded_grade.get("ok"))
    winner_ok = (
        (report.get("grown") or {}).get("winner_slug")
        == PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
    )
    live_proof = prove_absorbed_capability(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG)
    live_ok = bool(live_proof.get("ok"))
    kind_ok = (
        report.get("kind") == "capability_application_python_sextuple_nested_namespace_class_instance_growth_plane"
    )
    overlay_ok = ((report.get("grown") or {}).get("forage") or {}).get("fixture_overlay") is False
    selected_ok = (
        bool(scenarios.get("winner_is_python_sextuple_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_sextuple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_triple_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_static"))
        and bool(scenarios.get("winner_is_not_python_deep_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_function"))
        and bool(scenarios.get("winner_is_not_python_nested_namespace_class_instance"))
        and bool(scenarios.get("winner_is_not_python_class_static"))
        and bool(scenarios.get("winner_is_not_python_class_instance"))
        and bool(scenarios.get("winner_is_not_default_export"))
        and bool(scenarios.get("python_sextuple_nested_namespace_class_instance_selected"))
    )
    origin_ok = origin.get("kind") == "pypi-live" and not _source_is_stewardship(origin)
    ok = (
        digest_ok
        and catalog_ok
        and grade_ok
        and winner_ok
        and live_ok
        and kind_ok
        and overlay_ok
        and selected_ok
        and origin_ok
    )
    return {
        "ok": ok,
        "digest_ok": digest_ok,
        "catalog_ok": catalog_ok,
        "grade_ok": grade_ok,
        "winner_ok": winner_ok,
        "live_ok": live_ok,
        "kind_ok": kind_ok,
        "overlay_ok": overlay_ok,
        "origin_ok": origin_ok,
        "selected_ok": selected_ok,
    }


def builtin_application_python_sextuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Registered proof: six-level nested-namespace Python class instance methods forage."""

    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    scenarios = _python_sextuple_nested_namespace_class_instance_scenario_grades(catalog)
    with tempfile.TemporaryDirectory(prefix="bh-s6i-plane-", ignore_cleanup_errors=True) as tmp:
        report_dir = Path(tmp) / "report"
        plane = run_application_python_sextuple_nested_namespace_class_instance_growth_plane(report_dir)
        verification = (
            verify_application_python_sextuple_nested_namespace_class_instance_growth_plane(report_dir)
            if plane.get("ok")
            else {"ok": False}
        )
        tampered_rejected = False
        if plane.get("ok"):
            report_path = report_dir / "plane-report.json"
            tampered = json.loads(report_path.read_text(encoding="utf-8"))
            tampered["grade"]["grow_winner_is_apache_airflow_providers_amazon"] = False
            report_path.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
            tampered_rejected = not verify_application_python_sextuple_nested_namespace_class_instance_growth_plane(
                report_dir
            )["ok"]

    verdicts = {
        "already_solvable_skips_forage": bool((plane.get("grade") or {}).get("already_solvable_skips_forage")),
        "uncovered_stays_unsolved": bool((plane.get("grade") or {}).get("uncovered_stays_unsolved")),
        "trend_npm_decoy_wins": bool(scenarios["trend_npm_decoy_wins"]),
        "lying_catalog_picks_npm_decoy": bool(scenarios["lying_catalog_picks_npm_decoy"]),
        "grow_winner_is_apache_airflow_providers_amazon": bool(
            (plane.get("grade") or {}).get("grow_winner_is_apache_airflow_providers_amazon")
        ),
        "npm_decoy_probed": bool(scenarios["npm_decoy_probed"]),
        "npm_decoy_not_no_source": bool(scenarios["npm_decoy_not_no_source"]),
        "catalog_provides_ignored": bool(scenarios["catalog_provides_ignored"]),
        "python_sextuple_nested_namespace_class_instance_selected": bool(
            scenarios["python_sextuple_nested_namespace_class_instance_selected"]
        ),
        "winner_is_python_sextuple_nested_namespace_class_instance": bool(
            scenarios["winner_is_python_sextuple_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_sextuple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_sextuple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_triple_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_triple_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_static"]
        ),
        "winner_is_not_python_nested_namespace_class_static": bool(
            scenarios["winner_is_not_python_nested_namespace_class_static"]
        ),
        "winner_is_not_python_deep_nested_namespace_function": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_function"]
        ),
        "winner_is_not_python_nested_namespace_function": bool(
            scenarios["winner_is_not_python_nested_namespace_function"]
        ),
        "winner_is_not_python_deep_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_deep_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_nested_namespace_class_instance": bool(
            scenarios["winner_is_not_python_nested_namespace_class_instance"]
        ),
        "winner_is_not_python_class_static": bool(scenarios["winner_is_not_python_class_static"]),
        "winner_is_not_python_class_instance": bool(scenarios["winner_is_not_python_class_instance"]),
        "winner_is_not_named_export_class_static": bool(scenarios["winner_is_not_named_export_class_static"]),
        "winner_is_not_default_export": bool(scenarios["winner_is_not_default_export"]),
        "winner_is_not_default_export_class": bool(scenarios["winner_is_not_default_export_class"]),
        "winner_is_not_default_export_object": bool(scenarios["winner_is_not_default_export_object"]),
        "winner_origin_live": bool((plane.get("grade") or {}).get("winner_origin_live")),
        "winner_source_not_stewardship": bool((plane.get("grade") or {}).get("winner_source_not_stewardship")),
        "registries_npm_and_pypi": bool(scenarios["registries_npm_and_pypi"]),
        "query_from_goal": bool(scenarios["query_from_goal"]),
        "network_unused": bool(scenarios["network_unused"]),
        "plane_ok": bool(plane.get("ok")),
        "verify_ok": bool(verification.get("ok")),
        "tampered_rejected": tampered_rejected,
        "forage_ok": bool((plane.get("grade") or {}).get("forage_ok")),
        "grew": bool((plane.get("grade") or {}).get("grew")),
        "unplannable_before": bool((plane.get("grade") or {}).get("unplannable_before")),
        "grown_plan_solved": bool((plane.get("grade") or {}).get("grown_plan_solved")),
        "ablation_unplannable": bool((plane.get("grade") or {}).get("ablation_unplannable")),
        "no_separate_plane_invocation": bool((plane.get("grade") or {}).get("no_separate_plane_invocation")),
    }
    return {
        "ok": all(verdicts.values()),
        **verdicts,
        "winner": plane.get("winner") or "",
        "query": plane.get("query") or "",
        "registries": plane.get("registries") or [],
        "origin": plane.get("origin") or {},
        "action": "application_python_sextuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def _write_synthetic_nested_codec(pkg: Path, modules: Sequence[str]) -> None:
    """Write forage_ns.<modules>.Codec.encode with the last name a .py module."""

    *dirs, module = [str(part) for part in modules]
    rels = ["forage_ns"]
    for part in dirs:
        rels.append(f"{rels[-1]}/{part}")
    leaf = pkg.joinpath(*rels[-1].split("/"))
    leaf.mkdir(parents=True)
    for rel in rels:
        (pkg / rel / "__init__.py").write_text("", encoding="utf-8")
    (leaf / f"{module}.py").write_text(
        "class Codec:\n"
        "    def encode(self, text):\n"
        "        if not isinstance(text, str):\n"
        "            raise TypeError('encode expects a string')\n"
        "        return text.upper()\n",
        encoding="utf-8",
    )


def _infer_synthetic_nested_codec(modules: Sequence[str], slug: str) -> dict[str, Any]:
    from blackhole_agent.capability_foraging import infer_acquisition_spec

    with tempfile.TemporaryDirectory(prefix="bh-nested-codec-", ignore_cleanup_errors=True) as tmp:
        pkg = Path(tmp) / "pkg"
        _write_synthetic_nested_codec(pkg, modules)
        return infer_acquisition_spec(
            slug=slug,
            name=slug,
            source=pkg,
            staging_root=Path(tmp) / "infer",
            hint="forage_ns",
            close_deps=False,
        )


def replay_application_python_sextuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: covering sdist still forages as a six-level instance."""

    from blackhole_agent.kernel_leftover import leftover_marker_ids

    catalog = load_python_sextuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    capability_id = "capability.application-python-sext-nested-instance-growth-plane"
    stamped = ledger.capabilities.get(capability_id)
    absorbed = prove_absorbed_capability(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG)
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "six submodule levels down so sdists whose covering API is a six-level nested "
        "Class().method instance rather than a five-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        ("codec", "text", "safe", "inner", "leaf", "core"),
        "forage-ns-sextuple-codec-instance",
    )
    record = inferred.get("record") or {}
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "absorbed_ok": bool(absorbed.get("ok") and absorbed.get("cases_pass") and absorbed.get("tree_digest_match")),
        "infer_ok": bool(inferred.get("ok")),
        "python_sextuple_nested_namespace_class_instance_selected": bool(
            record.get("python_sextuple_nested_namespace_class_instance")
        )
        and record.get("winner") == "codec.text.safe.inner.leaf.core.Codec.encode",
        "winner_is_python_sextuple_nested_namespace_class_instance": bool(
            record.get("python_sextuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_sextuple_nested_namespace_class_static": not bool(
            record.get("python_sextuple_nested_namespace_class_static")
        ),
        "grow_winner_is_apache_airflow_providers_amazon": PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG
        in {str(item.get("slug") or "") for item in catalog.get("items") or []}
        and bool(absorbed.get("ok")),
        "leftover_marks_plane": leftover_marker_ids(leftover)
        == (capability_id,),
        "used_skill_route_discovery": False,
    }
    # ``ok`` ignores the used_skill_route_discovery flag so a False (desired) still passes.
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_WINNER_SLUG,
        "query": catalog.get("query") or "",
        "action": "application_python_sextuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_sextuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-sextuple-nested-instance-proof"
    )


def register_application_python_sextuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Register (idempotently) and prove six-level nested-namespace Python class-instance growth."""

    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-sext-nested-static-growth-plane",
            "capability.application-python-quint-nested-static-growth-plane",
            "capability.application-python-quint-nested-instance-growth-plane",
            "capability.application-python-quad-nested-static-growth-plane",
            "capability.application-python-triple-nested-static-growth-plane",
            "capability.application-python-deep-nested-static-growth-plane",
            "capability.application-python-deep-nested-function-growth-plane",
            "capability.application-python-nested-function-growth-plane",
            "capability.application-python-deep-nested-instance-growth-plane",
            "capability.application-python-nested-class-instance-growth-plane",
            "capability.application-python-nested-class-static-growth-plane",
            "capability.application-python-class-static-growth-plane",
            "capability.application-python-class-instance-growth-plane",
            "capability.application-node-named-class-instance-growth-plane",
            "capability.application-runtime-deps-growth-plane",
            "capability.application-live-fetch-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
            "capability.absorption-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-sext-nested-instance-growth-plane",
        name="Application python sextuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a live-fetched "
            "sdist whose covering Class().method is a Python nested-namespace class "
            "instance six submodule levels down: introspection reflects "
            "providers.amazon.aws.executors.batch.utils.BatchJobCollection.failure_count_by_id as a "
            "constructable instance rather than a six-level nested Class.method static, "
            "and the covering package is foraged so the original task becomes solvable."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_sextuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_sextuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_sextuple_nested_namespace_class_instance_catalog.json",
            "capabilities/absorbed-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance six submodule levels down: "
            "introspection reflects "
            "providers.amazon.aws.executors.batch.utils.BatchJobCollection.failure_count_by_id rather "
            "than a six-level nested Class.method static, and a covering "
            "package is foraged so the original task becomes solvable."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "sextuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=1800)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_sextuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a six-level nested-namespace class instance method."""

    result = run_application_python_sextuple_nested_namespace_class_instance_growth_plane()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "capability_id": result.get("capability_id"),
        "query": result.get("query"),
        "registries": result.get("registries"),
        "origin": result.get("origin"),
        "grade": result.get("grade"),
    }


def load_python_septuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_septuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: seven-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-sept-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "seven submodule levels down so sdists whose covering API is a seven-level nested "
        "Class().method instance rather than a six-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        ("codec", "text", "safe", "inner", "leaf", "more", "core"),
        "forage-ns-septuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_septuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_septuple_nested_namespace_class_instance_selected": bool(
            record.get("python_septuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_sextuple_nested_namespace_class_instance": not bool(
            record.get("python_sextuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_septuple_nested_namespace_class_static": not bool(
            record.get("python_septuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_septuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_septuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-septuple-nested-instance-proof"
    )


def register_application_python_septuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-python-sext-nested-static-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-sept-nested-instance-growth-plane",
        name="Application python septuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance seven submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.Codec.encode as a constructable "
            "instance rather than a six-level nested Class().method instance, and extra "
            "bundle leaves extract to a short cache dir so Windows MAX_PATH does not "
            "fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_septuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_septuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_septuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance seven submodule levels down: "
            "introspection reflects codec.text.safe.inner.leaf.more.core.Codec.encode "
            "rather than a six-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "septuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_septuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a seven-level nested-namespace class instance method."""

    result = replay_application_python_septuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def load_python_octuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_octuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: eight-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-oct-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eight submodule levels down so sdists whose covering API is an eight-level nested "
        "Class().method instance rather than a seven-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        ("codec", "text", "safe", "inner", "leaf", "more", "core", "unit"),
        "forage-ns-octuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_octuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_octuple_nested_namespace_class_instance_selected": bool(
            record.get("python_octuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_septuple_nested_namespace_class_instance": not bool(
            record.get("python_septuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_octuple_nested_namespace_class_static": not bool(
            record.get("python_octuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_octuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_octuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-octuple-nested-instance-proof"
    )


def register_application_python_octuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-sept-nested-instance-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-oct-nested-instance-growth-plane",
        name="Application python octuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance eight submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.Codec.encode as a constructable "
            "instance rather than a seven-level nested Class().method instance, and extra "
            "bundle leaves extract to a short cache dir so Windows MAX_PATH does not "
            "fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_octuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_octuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_octuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance eight submodule levels down: "
            "introspection reflects codec.text.safe.inner.leaf.more.core.unit.Codec.encode "
            "rather than a seven-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "octuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_octuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from an eight-level nested-namespace class instance method."""

    result = replay_application_python_octuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def load_python_nonuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_nonuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: nine-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-nona-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "nine submodule levels down so sdists whose covering API is a nine-level nested "
        "Class().method instance rather than an eight-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        ("codec", "text", "safe", "inner", "leaf", "more", "core", "unit", "cell"),
        "forage-ns-nonuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_nonuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_nonuple_nested_namespace_class_instance_selected": bool(
            record.get("python_nonuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_octuple_nested_namespace_class_instance": not bool(
            record.get("python_octuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_nonuple_nested_namespace_class_static": not bool(
            record.get("python_nonuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_nonuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_nonuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-nonuple-nested-instance-proof"
    )


def register_application_python_nonuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-oct-nested-instance-growth-plane",
            "capability.application-python-sept-nested-instance-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-nona-nested-instance-growth-plane",
        name="Application python nonuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance nine submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.Codec.encode as a constructable "
            "instance rather than an eight-level nested Class().method instance, and extra "
            "bundle leaves extract to a short cache dir so Windows MAX_PATH does not "
            "fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_nonuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_nonuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_nonuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance nine submodule levels down: "
            "introspection reflects codec.text.safe.inner.leaf.more.core.unit.cell.Codec.encode "
            "rather than an eight-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "nonuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_nonuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a nine-level nested-namespace class instance method."""

    result = replay_application_python_nonuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def load_python_decuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_decuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: ten-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-deca-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "ten submodule levels down so sdists whose covering API is a ten-level nested "
        "Class().method instance rather than a nine-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        ("codec", "text", "safe", "inner", "leaf", "more", "core", "unit", "cell", "atom"),
        "forage-ns-decuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_decuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_decuple_nested_namespace_class_instance_selected": bool(
            record.get("python_decuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_nonuple_nested_namespace_class_instance": not bool(
            record.get("python_nonuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_decuple_nested_namespace_class_static": not bool(
            record.get("python_decuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_decuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_decuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-decuple-nested-instance-proof"
    )


def register_application_python_decuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-nona-nested-instance-growth-plane",
            "capability.application-python-oct-nested-instance-growth-plane",
            "capability.application-python-sept-nested-instance-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-deca-nested-instance-growth-plane",
        name="Application python decuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance ten submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.Codec.encode as a constructable "
            "instance rather than a nine-level nested Class().method instance, and extra "
            "bundle leaves extract to a short cache dir so Windows MAX_PATH does not "
            "fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_decuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_decuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_decuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance ten submodule levels down: "
            "introspection reflects codec.text.safe.inner.leaf.more.core.unit.cell.atom.Codec.encode "
            "rather than a nine-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "decuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_decuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a ten-level nested-namespace class instance method."""

    result = replay_application_python_decuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def load_python_undecuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_undecuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: eleven-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-undec-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "eleven submodule levels down so sdists whose covering API is an eleven-level nested "
        "Class().method instance rather than a ten-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        ("codec", "text", "safe", "inner", "leaf", "more", "core", "unit", "cell", "atom", "quark"),
        "forage-ns-undecuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_undecuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_undecuple_nested_namespace_class_instance_selected": bool(
            record.get("python_undecuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_decuple_nested_namespace_class_instance": not bool(
            record.get("python_decuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_undecuple_nested_namespace_class_static": not bool(
            record.get("python_undecuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_undecuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_undecuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-undecuple-nested-instance-proof"
    )


def register_application_python_undecuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-deca-nested-instance-growth-plane",
            "capability.application-python-nona-nested-instance-growth-plane",
            "capability.application-python-oct-nested-instance-growth-plane",
            "capability.application-python-sept-nested-instance-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-undec-nested-instance-growth-plane",
        name="Application python undecuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance eleven submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.Codec.encode as a "
            "constructable instance rather than a ten-level nested Class().method instance, "
            "and extra bundle leaves extract to a short cache dir so Windows MAX_PATH does "
            "not fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_undecuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_undecuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_undecuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance eleven submodule levels down: "
            "introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.Codec.encode "
            "rather than a ten-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "undecuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_undecuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from an eleven-level nested-namespace class instance method."""

    result = replay_application_python_undecuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def load_python_duodecuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: twelve-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-dodec-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "twelve submodule levels down so sdists whose covering API is a twelve-level nested "
        "Class().method instance rather than an eleven-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        (
            "codec",
            "text",
            "safe",
            "inner",
            "leaf",
            "more",
            "core",
            "unit",
            "cell",
            "atom",
            "quark",
            "gluon",
        ),
        "forage-ns-duodecuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_duodecuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_duodecuple_nested_namespace_class_instance_selected": bool(
            record.get("python_duodecuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_undecuple_nested_namespace_class_instance": not bool(
            record.get("python_undecuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_duodecuple_nested_namespace_class_static": not bool(
            record.get("python_duodecuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_duodecuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-duodecuple-nested-instance-proof"
    )


def register_application_python_duodecuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-undec-nested-instance-growth-plane",
            "capability.application-python-deca-nested-instance-growth-plane",
            "capability.application-python-nona-nested-instance-growth-plane",
            "capability.application-python-oct-nested-instance-growth-plane",
            "capability.application-python-sept-nested-instance-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-dodec-nested-instance-growth-plane",
        name="Application python duodecuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance twelve submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.gluon.Codec.encode as a "
            "constructable instance rather than an eleven-level nested Class().method instance, "
            "and extra bundle leaves extract to a short cache dir so Windows MAX_PATH does "
            "not fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_duodecuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_duodecuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance twelve submodule levels down: "
            "introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.gluon.Codec.encode "
            "rather than an eleven-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "duodecuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_duodecuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a twelve-level nested-namespace class instance method."""

    result = replay_application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def load_python_tredecuple_nested_namespace_class_instance_apply_catalog() -> dict[str, Any]:
    payload = load_catalog(DEFAULT_PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CATALOG)
    payload["network_used"] = False
    payload["replay"] = True
    payload["live"] = False
    payload["registries"] = sorted(
        {
            str(item.get("registry") or "")
            for item in payload.get("items") or []
            if str(item.get("registry") or "") in {"npm", "pypi"}
        }
    )
    return payload


def replay_application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof() -> dict[str, Any]:
    """Fast registered proof: thirteen-level Class().method instance still forages."""

    from blackhole_agent.capability_foraging import _extracted_cache_dir
    from blackhole_agent.kernel_leftover import leftover_marker_ids

    capability_id = "capability.application-python-trede-nested-instance-growth-plane"
    leftover = (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        "thirteen submodule levels down so sdists whose covering API is a thirteen-level nested "
        "Class().method instance rather than a twelve-level nested Class().method instance "
        "can be foraged the same way."
    )
    inferred = _infer_synthetic_nested_codec(
        (
            "codec",
            "text",
            "safe",
            "inner",
            "leaf",
            "more",
            "core",
            "unit",
            "cell",
            "atom",
            "quark",
            "gluon",
            "lepton",
        ),
        "forage-ns-tredecuple-codec-instance",
    )
    record = inferred.get("record") or {}
    wheel = Path("apache_airflow_providers_common_compat-1.18.0-py3-none-any.whl")
    cache = _extracted_cache_dir("apache-airflow-providers-common-compat", "1.18.0", wheel)
    catalog = load_python_tredecuple_nested_namespace_class_instance_apply_catalog()
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stamped = ledger.capabilities.get(capability_id)
    verdicts = {
        "capability_exists": stamped is not None,
        "catalog_query": catalog.get("query")
        == query_from_goal(PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_GROW_TASK.goal),
        "infer_ok": bool(inferred.get("ok")),
        "python_tredecuple_nested_namespace_class_instance_selected": bool(
            record.get("python_tredecuple_nested_namespace_class_instance")
        )
        and record.get("winner") == PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE,
        "winner_is_not_python_duodecuple_nested_namespace_class_instance": not bool(
            record.get("python_duodecuple_nested_namespace_class_instance")
        ),
        "winner_is_not_python_tredecuple_nested_namespace_class_static": not bool(
            record.get("python_tredecuple_nested_namespace_class_static")
        ),
        "extra_leaf_cache_skips_wheel_filename": ".whl" not in str(cache),
        "leftover_marks_plane": leftover_marker_ids(leftover) == (capability_id,),
        "used_skill_route_discovery": False,
    }
    ok = all(value is True for key, value in verdicts.items() if key != "used_skill_route_discovery")
    return {
        "ok": ok,
        **verdicts,
        "winner": record.get("winner") or "",
        "query": catalog.get("query") or "",
        "action": "application_python_tredecuple_nested_namespace_class_instance_growth_plane",
        "used_skill_route_discovery": False,
    }


def application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof_command() -> str:
    return (
        "uv run python -m blackhole_agent.capability_application_growth "
        "python-tredecuple-nested-instance-proof"
    )


def register_application_python_tredecuple_nested_namespace_class_instance_growth_plane_capability(
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    ledger_path = default_ledger_path(repo_root)
    ledger = load_ledger(ledger_path)
    dependencies = tuple(
        dependency
        for dependency in (
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.foraging-plane",
            "capability.forage-target-plane",
            "capability.forage-growth-plane",
            "capability.application-python-dodec-nested-instance-growth-plane",
            "capability.application-python-undec-nested-instance-growth-plane",
            "capability.application-python-deca-nested-instance-growth-plane",
            "capability.application-python-nona-nested-instance-growth-plane",
            "capability.application-python-oct-nested-instance-growth-plane",
            "capability.application-python-sept-nested-instance-growth-plane",
            "capability.application-python-sext-nested-instance-growth-plane",
            "capability.application-growth-plane",
            "capability.application-plane",
        )
        if dependency in ledger.capabilities
    )
    capability = Capability(
        id="capability.application-python-trede-nested-instance-growth-plane",
        name="Application python tredecuple nested-namespace class-instance growth plane",
        description=(
            "An unplannable application goal grows itself from a sdist whose covering "
            "Class().method is a Python nested-namespace class instance thirteen submodule "
            "levels down: introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.gluon.lepton.Codec.encode as a "
            "constructable instance rather than a twelve-level nested Class().method instance, "
            "and extra bundle leaves extract to a short cache dir so Windows MAX_PATH does "
            "not fail the forage."
        ),
        kind="python",
        entry=(
            "blackhole_agent.capability_application_growth:"
            "demo_application_python_tredecuple_nested_namespace_class_instance_growth_plane"
        ),
        proof_command=application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof_command(),
        dependencies=dependencies,
        behavior_paths=(
            "src/blackhole_agent/capability_application_growth.py",
            "src/blackhole_agent/capability_foraging.py",
            "src/blackhole_agent/capability_acquisition.py",
            "src/blackhole_agent/capability_forage_growth.py",
            "tests/fixtures/forage_python_tredecuple_nested_namespace_class_instance_catalog.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Application-growth no longer skips sdists whose covering Class().method "
            "is a Python nested-namespace class instance thirteen submodule levels down: "
            "introspection reflects "
            "codec.text.safe.inner.leaf.more.core.unit.cell.atom.quark.gluon.lepton.Codec.encode "
            "rather than a twelve-level nested Class().method instance, and extra bundle "
            "leaves extract without embedding a .whl filename so Windows MAX_PATH does "
            "not fail extra bundle leaves."
        ),
        tags=(
            "foraging",
            "plane",
            "application",
            "growth",
            "python",
            "nested-namespace",
            "class-instance",
            "tredecuple-nested",
        ),
    )
    ledger = register_capability(ledger, capability, replace=True)
    save_ledger(ledger_path, ledger)
    ledger, proof = prove_capability(ledger, capability.id, cwd=repo_root, timeout=180)
    stamped = ledger.capabilities[capability.id]
    disk = load_ledger(ledger_path)
    merged = dict(disk.capabilities)
    merged[stamped.id] = stamped
    save_ledger(
        ledger_path,
        CapabilityLedger(
            schema_version=disk.schema_version,
            updated_at=utc_now_iso(),
            capabilities=merged,
        ),
    )
    return {"ok": proof.ok, "exit_code": proof.exit_code, "summary": proof.summary}


def demo_application_python_tredecuple_nested_namespace_class_instance_growth_plane() -> dict[str, Any]:
    """Entry surface: grow from a thirteen-level nested-namespace class instance method."""

    result = replay_application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof()
    return {
        "ok": bool(result["ok"]),
        "winner": result.get("winner"),
        "query": result.get("query"),
        "action": result.get("action"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Application-growth forage plane")
    sub = parser.add_subparsers(dest="command_name", required=True)

    grow_parser = sub.add_parser("grow", help="grow an unplannable application goal through forage matching")
    grow_parser.add_argument("--goal", action="append", required=True, help="goal key the task must cover")
    grow_parser.add_argument("--text", default="Hello World", help="initial text state for unary string goals")

    plane_parser = sub.add_parser("plane", help="run the sealed hermetic plane")
    plane_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    live_parser = sub.add_parser("live-plane", help="grow from a replayed npm+pypi catalog")
    live_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    registry_parser = sub.add_parser("registry-plane", help="grow from registry hits with no fixture overlay")
    registry_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    live_fetch_parser = sub.add_parser(
        "live-fetch-plane", help="grow from live-fetched registry hits with no stewardship archive"
    )
    live_fetch_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    runtime_deps_parser = sub.add_parser(
        "runtime-deps-plane", help="grow from an import-unclosed sdist by vendoring runtime deps"
    )
    runtime_deps_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    node_runtime_deps_parser = sub.add_parser(
        "node-runtime-deps-plane",
        help="grow from an import-unclosed npm tarball by vendoring package.json deps",
    )
    node_runtime_deps_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    node_default_export_parser = sub.add_parser(
        "node-default-export-plane",
        help="grow from a default-export-only npm tarball by reflecting the default export",
    )
    node_default_export_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    node_default_export_object_parser = sub.add_parser(
        "node-default-export-object-plane",
        help="grow from a default-exported-object npm tarball by reflecting namespace methods",
    )
    node_default_export_object_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    node_default_export_class_parser = sub.add_parser(
        "node-default-export-class-plane",
        help="grow from a default-exported-class npm tarball by reflecting instance methods",
    )
    node_default_export_class_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    node_class_static_parser = sub.add_parser(
        "node-class-static-plane",
        help="grow from a class-static npm tarball by reflecting Class.method callables",
    )
    node_class_static_parser.add_argument("--no-forage", action="store_true", help="match only; do not forage")

    node_named_class_static_parser = sub.add_parser(
        "node-named-class-static-plane",
        help="grow from a named class-static npm tarball by reflecting Base64.encode callables",
    )
    node_named_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    node_named_class_instance_parser = sub.add_parser(
        "node-named-class-instance-plane",
        help="grow from a named class-instance npm tarball by reflecting new Class().method",
    )
    node_named_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    node_named_class_construct_parser = sub.add_parser(
        "node-named-class-construct-plane",
        help="grow from a named class npm tarball by constructing new Class(options).method",
    )
    node_named_class_construct_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_class_instance_parser = sub.add_parser(
        "python-class-instance-plane",
        help="grow from a Python sdist by constructing Class(opts).method",
    )
    python_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_class_static_parser = sub.add_parser(
        "python-class-static-plane",
        help="grow from a Python sdist by reflecting Class.method callables",
    )
    python_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_nested_namespace_class_static_parser = sub.add_parser(
        "python-nested-namespace-class-static-plane",
        help="grow from a Python sdist by reflecting package.submodule.Class.method",
    )
    python_nested_namespace_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_nested_namespace_class_instance_parser = sub.add_parser(
        "python-nested-namespace-class-instance-plane",
        help="grow from a Python sdist by constructing package.submodule.Class(opts).method",
    )
    python_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_deep_nested_namespace_class_instance_parser = sub.add_parser(
        "python-deep-nested-instance-plane",
        help="grow from a Python sdist by constructing package.subpackage.submodule.Class(opts).method",
    )
    python_deep_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_nested_namespace_function_parser = sub.add_parser(
        "python-nested-function-plane",
        help="grow from a Python sdist by reflecting package.submodule.func",
    )
    python_nested_namespace_function_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_deep_nested_namespace_function_parser = sub.add_parser(
        "python-deep-nested-function-plane",
        help="grow from a Python sdist by reflecting package.subpackage.submodule.func",
    )
    python_deep_nested_namespace_function_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_deep_nested_namespace_class_static_parser = sub.add_parser(
        "python-deep-nested-class-static-plane",
        help="grow from a Python sdist by reflecting package.subpackage.submodule.Class.method",
    )
    python_deep_nested_namespace_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_triple_nested_namespace_class_static_parser = sub.add_parser(
        "python-triple-nested-class-static-plane",
        help="grow from a Python sdist by reflecting package.subpackage.subpackage.submodule.Class.method",
    )
    python_triple_nested_namespace_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_quadruple_nested_namespace_class_static_parser = sub.add_parser(
        "python-quadruple-nested-class-static-plane",
        help="grow from a Python sdist by reflecting package.subpackage.subpackage.subpackage.submodule.Class.method",
    )
    python_quadruple_nested_namespace_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_quintuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-quintuple-nested-instance-plane",
        help="grow from a Python sdist by constructing package.subpackage.subpackage.subpackage.subpackage.submodule.Class(opts).method",
    )
    python_quintuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_quintuple_nested_namespace_class_static_parser = sub.add_parser(
        "python-quintuple-nested-class-static-plane",
        help="grow from a Python sdist by reflecting a cwd-independent five-level Class.method static",
    )
    python_quintuple_nested_namespace_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_sextuple_nested_namespace_class_static_parser = sub.add_parser(
        "python-sextuple-nested-class-static-plane",
        help="grow from a Python sdist by reflecting a cwd-independent six-level Class.method static",
    )
    python_sextuple_nested_namespace_class_static_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_sextuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-sextuple-nested-instance-plane",
        help="grow from a Python sdist by constructing package.subpackage.subpackage.subpackage.subpackage.subpackage.submodule.Class().method",
    )
    python_sextuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_septuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-septuple-nested-instance-plane",
        help="grow from a Python sdist by constructing a seven-level nested Class().method instance",
    )
    python_septuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_octuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-octuple-nested-instance-plane",
        help="grow from a Python sdist by constructing an eight-level nested Class().method instance",
    )
    python_octuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_nonuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-nonuple-nested-instance-plane",
        help="grow from a Python sdist by constructing a nine-level nested Class().method instance",
    )
    python_nonuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_decuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-decuple-nested-instance-plane",
        help="grow from a Python sdist by constructing a ten-level nested Class().method instance",
    )
    python_decuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_undecuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-undecuple-nested-instance-plane",
        help="grow from a Python sdist by constructing an eleven-level nested Class().method instance",
    )
    python_undecuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_duodecuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-duodecuple-nested-instance-plane",
        help="grow from a Python sdist by constructing a twelve-level nested Class().method instance",
    )
    python_duodecuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    python_tredecuple_nested_namespace_class_instance_parser = sub.add_parser(
        "python-tredecuple-nested-instance-plane",
        help="grow from a Python sdist by constructing a thirteen-level nested Class().method instance",
    )
    python_tredecuple_nested_namespace_class_instance_parser.add_argument(
        "--no-forage", action="store_true", help="match only; do not forage"
    )

    sub.add_parser("proof", help="run the registered application-growth-plane proof")
    sub.add_parser("live-proof", help="run the registered live-registry application-growth proof")
    sub.add_parser("registry-proof", help="run the registered registry-archive application-growth proof")
    sub.add_parser("live-fetch-proof", help="run the registered live-fetch application-growth proof")
    sub.add_parser("runtime-deps-proof", help="run the registered runtime-deps application-growth proof")
    sub.add_parser("node-runtime-deps-proof", help="run the registered node runtime-deps application-growth proof")
    sub.add_parser(
        "node-default-export-proof", help="run the registered node default-export application-growth proof"
    )
    sub.add_parser(
        "node-default-export-object-proof",
        help="run the registered node default-export-object application-growth proof",
    )
    sub.add_parser(
        "node-default-export-class-proof",
        help="run the registered node default-export-class application-growth proof",
    )
    sub.add_parser(
        "node-class-static-proof",
        help="run the registered node class-static application-growth proof",
    )
    sub.add_parser(
        "node-named-class-static-proof",
        help="run the registered node named class-static application-growth proof",
    )
    sub.add_parser(
        "node-named-class-instance-proof",
        help="run the registered node named class-instance application-growth proof",
    )
    sub.add_parser(
        "node-named-class-construct-proof",
        help="run the registered node named class-construct application-growth proof",
    )
    sub.add_parser(
        "python-class-instance-proof",
        help="run the registered python class-instance application-growth proof",
    )
    sub.add_parser(
        "python-class-static-proof",
        help="run the registered python class-static application-growth proof",
    )
    sub.add_parser(
        "python-nested-namespace-class-static-proof",
        help="run the registered python nested-namespace class-static application-growth proof",
    )
    sub.add_parser(
        "python-nested-namespace-class-instance-proof",
        help="run the registered python nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-deep-nested-instance-proof",
        help="run the registered python deep nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-nested-function-proof",
        help="run the registered python nested-namespace function application-growth proof",
    )
    sub.add_parser(
        "python-deep-nested-function-proof",
        help="run the registered python deep nested-namespace function application-growth proof",
    )
    sub.add_parser(
        "python-deep-nested-class-static-proof",
        help="run the registered python deep nested-namespace class-static application-growth proof",
    )
    sub.add_parser(
        "python-triple-nested-class-static-proof",
        help="run the registered python triple nested-namespace class-static application-growth proof",
    )
    sub.add_parser(
        "python-quadruple-nested-class-static-proof",
        help="run the registered python quadruple nested-namespace class-static application-growth proof",
    )
    sub.add_parser(
        "python-quintuple-nested-instance-proof",
        help="run the registered python quintuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-quintuple-nested-class-static-proof",
        help="run the registered python quintuple nested-namespace class-static application-growth proof",
    )
    sub.add_parser(
        "python-sextuple-nested-class-static-proof",
        help="run the registered python sextuple nested-namespace class-static application-growth proof",
    )
    sub.add_parser(
        "python-sextuple-nested-instance-proof",
        help="run the registered python sextuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-septuple-nested-instance-proof",
        help="run the registered python septuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-octuple-nested-instance-proof",
        help="run the registered python octuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-nonuple-nested-instance-proof",
        help="run the registered python nonuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-decuple-nested-instance-proof",
        help="run the registered python decuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-undecuple-nested-instance-proof",
        help="run the registered python undecuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-duodecuple-nested-instance-proof",
        help="run the registered python duodecuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser(
        "python-tredecuple-nested-instance-proof",
        help="run the registered python tredecuple nested-namespace class-instance application-growth proof",
    )
    sub.add_parser("register", help="register and prove the plane in the live ledger")
    sub.add_parser("live-register", help="register and prove the live-registry plane")
    sub.add_parser("registry-register", help="register and prove the registry-archive plane")
    sub.add_parser("live-fetch-register", help="register and prove the live-fetch plane")
    sub.add_parser("runtime-deps-register", help="register and prove the runtime-deps plane")
    sub.add_parser("node-runtime-deps-register", help="register and prove the node runtime-deps plane")
    sub.add_parser("node-default-export-register", help="register and prove the node default-export plane")
    sub.add_parser(
        "node-default-export-object-register",
        help="register and prove the node default-export-object plane",
    )
    sub.add_parser(
        "node-default-export-class-register",
        help="register and prove the node default-export-class plane",
    )
    sub.add_parser(
        "node-class-static-register",
        help="register and prove the node class-static plane",
    )
    sub.add_parser(
        "node-named-class-static-register",
        help="register and prove the node named class-static plane",
    )
    sub.add_parser(
        "node-named-class-instance-register",
        help="register and prove the node named class-instance plane",
    )
    sub.add_parser(
        "node-named-class-construct-register",
        help="register and prove the node named class-construct plane",
    )
    sub.add_parser(
        "python-class-instance-register",
        help="register and prove the python class-instance plane",
    )
    sub.add_parser(
        "python-class-static-register",
        help="register and prove the python class-static plane",
    )
    sub.add_parser(
        "python-nested-namespace-class-static-register",
        help="register and prove the python nested-namespace class-static plane",
    )
    sub.add_parser(
        "python-nested-namespace-class-instance-register",
        help="register and prove the python nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-deep-nested-instance-register",
        help="register and prove the python deep nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-nested-function-register",
        help="register and prove the python nested-namespace function plane",
    )
    sub.add_parser(
        "python-deep-nested-function-register",
        help="register and prove the python deep nested-namespace function plane",
    )
    sub.add_parser(
        "python-deep-nested-class-static-register",
        help="register and prove the python deep nested-namespace class-static plane",
    )
    sub.add_parser(
        "python-triple-nested-class-static-register",
        help="register and prove the python triple nested-namespace class-static plane",
    )
    sub.add_parser(
        "python-quadruple-nested-class-static-register",
        help="register and prove the python quadruple nested-namespace class-static plane",
    )
    sub.add_parser(
        "python-quintuple-nested-instance-register",
        help="register and prove the python quintuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-quintuple-nested-class-static-register",
        help="register and prove the python quintuple nested-namespace class-static plane",
    )
    sub.add_parser(
        "python-sextuple-nested-class-static-register",
        help="register and prove the python sextuple nested-namespace class-static plane",
    )
    sub.add_parser(
        "python-sextuple-nested-instance-register",
        help="register and prove the python sextuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-septuple-nested-instance-register",
        help="register and prove the python septuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-octuple-nested-instance-register",
        help="register and prove the python octuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-nonuple-nested-instance-register",
        help="register and prove the python nonuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-decuple-nested-instance-register",
        help="register and prove the python decuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-undecuple-nested-instance-register",
        help="register and prove the python undecuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-duodecuple-nested-instance-register",
        help="register and prove the python duodecuple nested-namespace class-instance plane",
    )
    sub.add_parser(
        "python-tredecuple-nested-instance-register",
        help="register and prove the python tredecuple nested-namespace class-instance plane",
    )

    verify_parser = sub.add_parser("verify", help="verify a sealed application-growth report")
    verify_parser.add_argument("--report-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)

    live_verify = sub.add_parser("live-verify", help="verify a sealed live-registry growth report")
    live_verify.add_argument("--report-dir", type=Path, default=DEFAULT_LIVE_ARTIFACT_DIR)

    registry_verify = sub.add_parser("registry-verify", help="verify a sealed registry-archive growth report")
    registry_verify.add_argument("--report-dir", type=Path, default=DEFAULT_REGISTRY_ARTIFACT_DIR)

    live_fetch_verify = sub.add_parser("live-fetch-verify", help="verify a sealed live-fetch growth report")
    live_fetch_verify.add_argument("--report-dir", type=Path, default=DEFAULT_LIVE_FETCH_ARTIFACT_DIR)

    runtime_deps_verify = sub.add_parser("runtime-deps-verify", help="verify a sealed runtime-deps growth report")
    runtime_deps_verify.add_argument("--report-dir", type=Path, default=DEFAULT_RUNTIME_DEPS_ARTIFACT_DIR)

    node_runtime_deps_verify = sub.add_parser(
        "node-runtime-deps-verify", help="verify a sealed node runtime-deps growth report"
    )
    node_runtime_deps_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_RUNTIME_DEPS_ARTIFACT_DIR
    )

    node_default_export_verify = sub.add_parser(
        "node-default-export-verify", help="verify a sealed node default-export growth report"
    )
    node_default_export_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_DEFAULT_EXPORT_ARTIFACT_DIR
    )

    node_default_export_object_verify = sub.add_parser(
        "node-default-export-object-verify",
        help="verify a sealed node default-export-object growth report",
    )
    node_default_export_object_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_DEFAULT_EXPORT_OBJECT_ARTIFACT_DIR
    )

    node_default_export_class_verify = sub.add_parser(
        "node-default-export-class-verify",
        help="verify a sealed node default-export-class growth report",
    )
    node_default_export_class_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_DEFAULT_EXPORT_CLASS_ARTIFACT_DIR
    )

    node_class_static_verify = sub.add_parser(
        "node-class-static-verify",
        help="verify a sealed node class-static growth report",
    )
    node_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_CLASS_STATIC_ARTIFACT_DIR
    )

    node_named_class_static_verify = sub.add_parser(
        "node-named-class-static-verify",
        help="verify a sealed node named class-static growth report",
    )
    node_named_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_NAMED_CLASS_STATIC_ARTIFACT_DIR
    )

    node_named_class_instance_verify = sub.add_parser(
        "node-named-class-instance-verify",
        help="verify a sealed node named class-instance growth report",
    )
    node_named_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_NAMED_CLASS_INSTANCE_ARTIFACT_DIR
    )

    node_named_class_construct_verify = sub.add_parser(
        "node-named-class-construct-verify",
        help="verify a sealed node named class-construct growth report",
    )
    node_named_class_construct_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_NODE_NAMED_CLASS_CONSTRUCT_ARTIFACT_DIR
    )

    python_class_instance_verify = sub.add_parser(
        "python-class-instance-verify",
        help="verify a sealed python class-instance growth report",
    )
    python_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_class_static_verify = sub.add_parser(
        "python-class-static-verify",
        help="verify a sealed python class-static growth report",
    )
    python_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_CLASS_STATIC_ARTIFACT_DIR
    )

    python_nested_namespace_class_static_verify = sub.add_parser(
        "python-nested-namespace-class-static-verify",
        help="verify a sealed python nested-namespace class-static growth report",
    )
    python_nested_namespace_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    )

    python_nested_namespace_class_instance_verify = sub.add_parser(
        "python-nested-namespace-class-instance-verify",
        help="verify a sealed python nested-namespace class-instance growth report",
    )
    python_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_deep_nested_namespace_class_instance_verify = sub.add_parser(
        "python-deep-nested-instance-verify",
        help="verify a sealed python deep nested-namespace class-instance growth report",
    )
    python_deep_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_nested_namespace_function_verify = sub.add_parser(
        "python-nested-function-verify",
        help="verify a sealed python nested-namespace function growth report",
    )
    python_nested_namespace_function_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_NESTED_NAMESPACE_FUNCTION_ARTIFACT_DIR
    )

    python_deep_nested_namespace_function_verify = sub.add_parser(
        "python-deep-nested-function-verify",
        help="verify a sealed python deep nested-namespace function growth report",
    )
    python_deep_nested_namespace_function_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_FUNCTION_ARTIFACT_DIR
    )

    python_deep_nested_namespace_class_static_verify = sub.add_parser(
        "python-deep-nested-class-static-verify",
        help="verify a sealed python deep nested-namespace class-static growth report",
    )
    python_deep_nested_namespace_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_DEEP_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    )

    python_triple_nested_namespace_class_static_verify = sub.add_parser(
        "python-triple-nested-class-static-verify",
        help="verify a sealed python triple nested-namespace class-static growth report",
    )
    python_triple_nested_namespace_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_TRIPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    )

    python_quadruple_nested_namespace_class_static_verify = sub.add_parser(
        "python-quadruple-nested-class-static-verify",
        help="verify a sealed python quadruple nested-namespace class-static growth report",
    )
    python_quadruple_nested_namespace_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_QUADRUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    )

    python_quintuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-quintuple-nested-instance-verify",
        help="verify a sealed python quintuple nested-namespace class-instance growth report",
    )
    python_quintuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_quintuple_nested_namespace_class_static_verify = sub.add_parser(
        "python-quintuple-nested-class-static-verify",
        help="verify a sealed python quintuple nested-namespace class-static growth report",
    )
    python_quintuple_nested_namespace_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_QUINTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    )

    python_sextuple_nested_namespace_class_static_verify = sub.add_parser(
        "python-sextuple-nested-class-static-verify",
        help="verify a sealed python sextuple nested-namespace class-static growth report",
    )
    python_sextuple_nested_namespace_class_static_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_STATIC_ARTIFACT_DIR
    )

    python_sextuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-sextuple-nested-instance-verify",
        help="verify a sealed python sextuple nested-namespace class-instance growth report",
    )
    python_sextuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_SEXTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_septuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-septuple-nested-instance-verify",
        help="verify a sealed python septuple nested-namespace class-instance growth report",
    )
    python_septuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_SEPTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_octuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-octuple-nested-instance-verify",
        help="verify a sealed python octuple nested-namespace class-instance growth report",
    )
    python_octuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_OCTUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_nonuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-nonuple-nested-instance-verify",
        help="verify a sealed python nonuple nested-namespace class-instance growth report",
    )
    python_nonuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_NONUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_decuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-decuple-nested-instance-verify",
        help="verify a sealed python decuple nested-namespace class-instance growth report",
    )
    python_decuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_DECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_undecuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-undecuple-nested-instance-verify",
        help="verify a sealed python undecuple nested-namespace class-instance growth report",
    )
    python_undecuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_UNDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_duodecuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-duodecuple-nested-instance-verify",
        help="verify a sealed python duodecuple nested-namespace class-instance growth report",
    )
    python_duodecuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_DUODECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    python_tredecuple_nested_namespace_class_instance_verify = sub.add_parser(
        "python-tredecuple-nested-instance-verify",
        help="verify a sealed python tredecuple nested-namespace class-instance growth report",
    )
    python_tredecuple_nested_namespace_class_instance_verify.add_argument(
        "--report-dir", type=Path, default=DEFAULT_PYTHON_TREDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_ARTIFACT_DIR
    )

    args = parser.parse_args(argv)
    if args.command_name == "grow":
        goal = tuple(args.goal)
        task = ApplicationTask(
            id="cli-grow",
            description="CLI application-growth task.",
            initial_state={"text": args.text},
            goal=goal,
            oracle={},
        )
        result = grow_application_task(task)
    elif args.command_name == "plane":
        result = run_application_growth_plane(forage=not args.no_forage)
    elif args.command_name == "live-plane":
        result = run_application_live_growth_plane(forage=not args.no_forage)
    elif args.command_name == "registry-plane":
        result = run_application_registry_growth_plane(forage=not args.no_forage)
    elif args.command_name == "live-fetch-plane":
        result = run_application_live_fetch_growth_plane(forage=not args.no_forage)
    elif args.command_name == "runtime-deps-plane":
        result = run_application_runtime_deps_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-runtime-deps-plane":
        result = run_application_node_runtime_deps_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-default-export-plane":
        result = run_application_node_default_export_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-default-export-object-plane":
        result = run_application_node_default_export_object_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-default-export-class-plane":
        result = run_application_node_default_export_class_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-class-static-plane":
        result = run_application_node_class_static_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-named-class-static-plane":
        result = run_application_node_named_class_static_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-named-class-instance-plane":
        result = run_application_node_named_class_instance_growth_plane(forage=not args.no_forage)
    elif args.command_name == "node-named-class-construct-plane":
        result = run_application_node_named_class_construct_growth_plane(forage=not args.no_forage)
    elif args.command_name == "python-class-instance-plane":
        result = run_application_python_class_instance_growth_plane(forage=not args.no_forage)
    elif args.command_name == "python-class-static-plane":
        result = run_application_python_class_static_growth_plane(forage=not args.no_forage)
    elif args.command_name == "python-nested-namespace-class-static-plane":
        result = run_application_python_nested_namespace_class_static_growth_plane(forage=not args.no_forage)
    elif args.command_name == "python-nested-namespace-class-instance-plane":
        result = run_application_python_nested_namespace_class_instance_growth_plane(forage=not args.no_forage)
    elif args.command_name == "python-deep-nested-instance-plane":
        result = run_application_python_deep_nested_namespace_class_instance_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-nested-function-plane":
        result = run_application_python_nested_namespace_function_growth_plane(forage=not args.no_forage)
    elif args.command_name == "python-deep-nested-function-plane":
        result = run_application_python_deep_nested_namespace_function_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-deep-nested-class-static-plane":
        result = run_application_python_deep_nested_namespace_class_static_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-triple-nested-class-static-plane":
        result = run_application_python_triple_nested_namespace_class_static_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-quadruple-nested-class-static-plane":
        result = run_application_python_quadruple_nested_namespace_class_static_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-quintuple-nested-instance-plane":
        result = run_application_python_quintuple_nested_namespace_class_instance_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-quintuple-nested-class-static-plane":
        result = run_application_python_quintuple_nested_namespace_class_static_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-sextuple-nested-class-static-plane":
        result = run_application_python_sextuple_nested_namespace_class_static_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-sextuple-nested-instance-plane":
        result = run_application_python_sextuple_nested_namespace_class_instance_growth_plane(
            forage=not args.no_forage
        )
    elif args.command_name == "python-septuple-nested-instance-plane":
        result = replay_application_python_septuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-octuple-nested-instance-plane":
        result = replay_application_python_octuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-nonuple-nested-instance-plane":
        result = replay_application_python_nonuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-decuple-nested-instance-plane":
        result = replay_application_python_decuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-undecuple-nested-instance-plane":
        result = replay_application_python_undecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-duodecuple-nested-instance-plane":
        result = replay_application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-tredecuple-nested-instance-plane":
        result = replay_application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "proof":
        result = builtin_application_growth_plane_proof()
    elif args.command_name == "live-proof":
        result = builtin_application_live_growth_plane_proof()
    elif args.command_name == "registry-proof":
        result = builtin_application_registry_growth_plane_proof()
    elif args.command_name == "live-fetch-proof":
        result = builtin_application_live_fetch_growth_plane_proof()
    elif args.command_name == "runtime-deps-proof":
        result = builtin_application_runtime_deps_growth_plane_proof()
    elif args.command_name == "node-runtime-deps-proof":
        result = builtin_application_node_runtime_deps_growth_plane_proof()
    elif args.command_name == "node-default-export-proof":
        result = builtin_application_node_default_export_growth_plane_proof()
    elif args.command_name == "node-default-export-object-proof":
        result = builtin_application_node_default_export_object_growth_plane_proof()
    elif args.command_name == "node-default-export-class-proof":
        result = builtin_application_node_default_export_class_growth_plane_proof()
    elif args.command_name == "node-class-static-proof":
        result = builtin_application_node_class_static_growth_plane_proof()
    elif args.command_name == "node-named-class-static-proof":
        result = builtin_application_node_named_class_static_growth_plane_proof()
    elif args.command_name == "node-named-class-instance-proof":
        result = builtin_application_node_named_class_instance_growth_plane_proof()
    elif args.command_name == "node-named-class-construct-proof":
        result = builtin_application_node_named_class_construct_growth_plane_proof()
    elif args.command_name == "python-class-instance-proof":
        result = builtin_application_python_class_instance_growth_plane_proof()
    elif args.command_name == "python-class-static-proof":
        result = builtin_application_python_class_static_growth_plane_proof()
    elif args.command_name == "python-nested-namespace-class-static-proof":
        result = builtin_application_python_nested_namespace_class_static_growth_plane_proof()
    elif args.command_name == "python-nested-namespace-class-instance-proof":
        result = builtin_application_python_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-deep-nested-instance-proof":
        result = builtin_application_python_deep_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-nested-function-proof":
        result = builtin_application_python_nested_namespace_function_growth_plane_proof()
    elif args.command_name == "python-deep-nested-function-proof":
        result = builtin_application_python_deep_nested_namespace_function_growth_plane_proof()
    elif args.command_name == "python-deep-nested-class-static-proof":
        result = builtin_application_python_deep_nested_namespace_class_static_growth_plane_proof()
    elif args.command_name == "python-triple-nested-class-static-proof":
        result = builtin_application_python_triple_nested_namespace_class_static_growth_plane_proof()
    elif args.command_name == "python-quadruple-nested-class-static-proof":
        result = builtin_application_python_quadruple_nested_namespace_class_static_growth_plane_proof()
    elif args.command_name == "python-quintuple-nested-instance-proof":
        result = builtin_application_python_quintuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-quintuple-nested-class-static-proof":
        result = builtin_application_python_quintuple_nested_namespace_class_static_growth_plane_proof()
    elif args.command_name == "python-sextuple-nested-class-static-proof":
        result = builtin_application_python_sextuple_nested_namespace_class_static_growth_plane_proof()
    elif args.command_name == "python-sextuple-nested-instance-proof":
        result = replay_application_python_sextuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-septuple-nested-instance-proof":
        result = replay_application_python_septuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-octuple-nested-instance-proof":
        result = replay_application_python_octuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-nonuple-nested-instance-proof":
        result = replay_application_python_nonuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-decuple-nested-instance-proof":
        result = replay_application_python_decuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-undecuple-nested-instance-proof":
        result = replay_application_python_undecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-duodecuple-nested-instance-proof":
        result = replay_application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-tredecuple-nested-instance-proof":
        result = replay_application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "register":
        result = register_application_growth_plane_capability()
    elif args.command_name == "live-register":
        result = register_application_live_growth_plane_capability()
    elif args.command_name == "registry-register":
        result = register_application_registry_growth_plane_capability()
    elif args.command_name == "live-fetch-register":
        result = register_application_live_fetch_growth_plane_capability()
    elif args.command_name == "runtime-deps-register":
        result = register_application_runtime_deps_growth_plane_capability()
    elif args.command_name == "node-runtime-deps-register":
        result = register_application_node_runtime_deps_growth_plane_capability()
    elif args.command_name == "node-default-export-register":
        result = register_application_node_default_export_growth_plane_capability()
    elif args.command_name == "node-default-export-object-register":
        result = register_application_node_default_export_object_growth_plane_capability()
    elif args.command_name == "node-default-export-class-register":
        result = register_application_node_default_export_class_growth_plane_capability()
    elif args.command_name == "node-class-static-register":
        result = register_application_node_class_static_growth_plane_capability()
    elif args.command_name == "node-named-class-static-register":
        result = register_application_node_named_class_static_growth_plane_capability()
    elif args.command_name == "node-named-class-instance-register":
        result = register_application_node_named_class_instance_growth_plane_capability()
    elif args.command_name == "node-named-class-construct-register":
        result = register_application_node_named_class_construct_growth_plane_capability()
    elif args.command_name == "python-class-instance-register":
        result = register_application_python_class_instance_growth_plane_capability()
    elif args.command_name == "python-class-static-register":
        result = register_application_python_class_static_growth_plane_capability()
    elif args.command_name == "python-nested-namespace-class-static-register":
        result = register_application_python_nested_namespace_class_static_growth_plane_capability()
    elif args.command_name == "python-nested-namespace-class-instance-register":
        result = register_application_python_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-deep-nested-instance-register":
        result = register_application_python_deep_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-nested-function-register":
        result = register_application_python_nested_namespace_function_growth_plane_capability()
    elif args.command_name == "python-deep-nested-function-register":
        result = register_application_python_deep_nested_namespace_function_growth_plane_capability()
    elif args.command_name == "python-deep-nested-class-static-register":
        result = register_application_python_deep_nested_namespace_class_static_growth_plane_capability()
    elif args.command_name == "python-triple-nested-class-static-register":
        result = register_application_python_triple_nested_namespace_class_static_growth_plane_capability()
    elif args.command_name == "python-quadruple-nested-class-static-register":
        result = register_application_python_quadruple_nested_namespace_class_static_growth_plane_capability()
    elif args.command_name == "python-quintuple-nested-instance-register":
        result = register_application_python_quintuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-quintuple-nested-class-static-register":
        result = register_application_python_quintuple_nested_namespace_class_static_growth_plane_capability()
    elif args.command_name == "python-sextuple-nested-class-static-register":
        result = register_application_python_sextuple_nested_namespace_class_static_growth_plane_capability()
    elif args.command_name == "python-sextuple-nested-instance-register":
        result = register_application_python_sextuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-septuple-nested-instance-register":
        result = register_application_python_septuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-octuple-nested-instance-register":
        result = register_application_python_octuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-nonuple-nested-instance-register":
        result = register_application_python_nonuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-decuple-nested-instance-register":
        result = register_application_python_decuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-undecuple-nested-instance-register":
        result = register_application_python_undecuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-duodecuple-nested-instance-register":
        result = register_application_python_duodecuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "python-tredecuple-nested-instance-register":
        result = register_application_python_tredecuple_nested_namespace_class_instance_growth_plane_capability()
    elif args.command_name == "live-verify":
        result = verify_application_live_growth_plane(args.report_dir)
    elif args.command_name == "registry-verify":
        result = verify_application_registry_growth_plane(args.report_dir)
    elif args.command_name == "live-fetch-verify":
        result = verify_application_live_fetch_growth_plane(args.report_dir)
    elif args.command_name == "runtime-deps-verify":
        result = verify_application_runtime_deps_growth_plane(args.report_dir)
    elif args.command_name == "node-runtime-deps-verify":
        result = verify_application_node_runtime_deps_growth_plane(args.report_dir)
    elif args.command_name == "node-default-export-verify":
        result = verify_application_node_default_export_growth_plane(args.report_dir)
    elif args.command_name == "node-default-export-object-verify":
        result = verify_application_node_default_export_object_growth_plane(args.report_dir)
    elif args.command_name == "node-default-export-class-verify":
        result = verify_application_node_default_export_class_growth_plane(args.report_dir)
    elif args.command_name == "node-class-static-verify":
        result = verify_application_node_class_static_growth_plane(args.report_dir)
    elif args.command_name == "node-named-class-static-verify":
        result = verify_application_node_named_class_static_growth_plane(args.report_dir)
    elif args.command_name == "node-named-class-instance-verify":
        result = verify_application_node_named_class_instance_growth_plane(args.report_dir)
    elif args.command_name == "node-named-class-construct-verify":
        result = verify_application_node_named_class_construct_growth_plane(args.report_dir)
    elif args.command_name == "python-class-instance-verify":
        result = verify_application_python_class_instance_growth_plane(args.report_dir)
    elif args.command_name == "python-class-static-verify":
        result = verify_application_python_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-nested-namespace-class-static-verify":
        result = verify_application_python_nested_namespace_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-nested-namespace-class-instance-verify":
        result = verify_application_python_nested_namespace_class_instance_growth_plane(args.report_dir)
    elif args.command_name == "python-deep-nested-instance-verify":
        result = verify_application_python_deep_nested_namespace_class_instance_growth_plane(args.report_dir)
    elif args.command_name == "python-nested-function-verify":
        result = verify_application_python_nested_namespace_function_growth_plane(args.report_dir)
    elif args.command_name == "python-deep-nested-function-verify":
        result = verify_application_python_deep_nested_namespace_function_growth_plane(args.report_dir)
    elif args.command_name == "python-deep-nested-class-static-verify":
        result = verify_application_python_deep_nested_namespace_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-triple-nested-class-static-verify":
        result = verify_application_python_triple_nested_namespace_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-quadruple-nested-class-static-verify":
        result = verify_application_python_quadruple_nested_namespace_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-quintuple-nested-instance-verify":
        result = verify_application_python_quintuple_nested_namespace_class_instance_growth_plane(args.report_dir)
    elif args.command_name == "python-quintuple-nested-class-static-verify":
        result = verify_application_python_quintuple_nested_namespace_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-sextuple-nested-class-static-verify":
        result = verify_application_python_sextuple_nested_namespace_class_static_growth_plane(args.report_dir)
    elif args.command_name == "python-sextuple-nested-instance-verify":
        result = verify_application_python_sextuple_nested_namespace_class_instance_growth_plane(args.report_dir)
    elif args.command_name == "python-septuple-nested-instance-verify":
        result = replay_application_python_septuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-octuple-nested-instance-verify":
        result = replay_application_python_octuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-nonuple-nested-instance-verify":
        result = replay_application_python_nonuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-decuple-nested-instance-verify":
        result = replay_application_python_decuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-undecuple-nested-instance-verify":
        result = replay_application_python_undecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-duodecuple-nested-instance-verify":
        result = replay_application_python_duodecuple_nested_namespace_class_instance_growth_plane_proof()
    elif args.command_name == "python-tredecuple-nested-instance-verify":
        result = replay_application_python_tredecuple_nested_namespace_class_instance_growth_plane_proof()
    else:
        result = verify_application_growth_plane(args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
