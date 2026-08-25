# -*- coding: utf-8 -*-
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from ..error import ProgrammingError, SqlSyntaxError
from ..helper import SQLHelper
from .builder import ExecutionPlan
from .query_builder import QueryExecutionPlan

_logger = logging.getLogger(__name__)


_ALLOWED_VERBOSITIES = frozenset({"queryPlanner", "executionStats", "allPlansExecution"})


@dataclass
class ExplainExecutionPlan(ExecutionPlan):
    """Execution plan that wraps another plan with server-side explain semantics."""

    inner_plan: Optional[ExecutionPlan] = None
    verbosity: str = "queryPlanner"
    options: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collection": self.collection,
            "verbosity": self.verbosity,
            "options": dict(self.options),
            "inner_plan": self.inner_plan.to_dict() if self.inner_plan else None,
        }

    def validate(self) -> bool:
        errors: list[str] = []

        if self.inner_plan is None:
            errors.append("EXPLAIN requires an inner statement")
        elif not self.inner_plan.validate():
            errors.append("Inner statement for EXPLAIN is invalid")

        if self.verbosity not in _ALLOWED_VERBOSITIES:
            errors.append(
                f"Unsupported EXPLAIN verbosity '{self.verbosity}'. " f"Allowed: {sorted(_ALLOWED_VERBOSITIES)}"
            )

        if errors:
            for err in errors:
                _logger.warning(f"Explain plan validation error: {err}")
            return False

        return True

    # ------------------------------------------------------------------ #
    # Command construction
    # ------------------------------------------------------------------ #
    def build_inner_command(
        self,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build the MongoDB command (``find`` or ``aggregate``) to be explained.

        Only :class:`QueryExecutionPlan` inner plans are currently supported.
        Placeholders in the filter stage are substituted using ``qmark`` style.
        """
        inner_plan = self.inner_plan
        if not isinstance(inner_plan, QueryExecutionPlan):
            raise SqlSyntaxError(
                "EXPLAIN currently only supports SELECT statements "
                f"(got {type(inner_plan).__name__ if inner_plan is not None else 'None'})"
            )

        if getattr(inner_plan, "is_aggregate_query", False):
            try:
                pipeline = json.loads(inner_plan.aggregate_pipeline or "[]")
                options = json.loads(inner_plan.aggregate_options or "{}")
            except json.JSONDecodeError as e:
                raise ProgrammingError(f"Invalid JSON in aggregate pipeline or options: {e}")

            command: Dict[str, Any] = {
                "aggregate": inner_plan.collection,
                "pipeline": pipeline,
                "cursor": {},
            }
            for k, v in options.items():
                if k not in command:
                    command[k] = v
            return command

        if not inner_plan.collection:
            raise ProgrammingError("No collection specified in query")

        filter_stage = inner_plan.filter_stage or {}
        if parameters:
            filter_stage = SQLHelper.replace_placeholders_generic(filter_stage, parameters, "qmark")

        command = {"find": inner_plan.collection, "filter": filter_stage}

        if inner_plan.projection_stage:
            command["projection"] = inner_plan.projection_stage
        if inner_plan.sort_stage:
            sort_spec: Dict[str, int] = {}
            for sort_dict in inner_plan.sort_stage:
                for field_name, direction in sort_dict.items():
                    sort_spec[field_name] = direction
            command["sort"] = sort_spec
        if inner_plan.skip_stage:
            command["skip"] = inner_plan.skip_stage
        if inner_plan.limit_stage:
            command["limit"] = inner_plan.limit_stage

        return command

    def build_command(
        self,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build the server-side ``{explain: <inner>, verbosity: <mode>}`` command."""
        return {"explain": self.build_inner_command(parameters), "verbosity": self.verbosity}

    # ------------------------------------------------------------------ #
    # Result-set shaping
    # ------------------------------------------------------------------ #
    @property
    def result_plan(self) -> QueryExecutionPlan:
        """Synthetic :class:`QueryExecutionPlan` describing the ``(stage, details)`` result rows.

        Used by :class:`~pymongosql.result_set.ResultSet` to build a stable column
        description and row ordering for EXPLAIN output.
        """
        collection = (self.inner_plan.collection if self.inner_plan else None) or "explain"
        return QueryExecutionPlan(
            collection=collection,
            projection_stage={"stage": 1, "details": 1},
        )

    @staticmethod
    def flatten_result(explain_result: Dict[str, Any]) -> List[Dict[str, str]]:
        """Flatten a MongoDB explain result into rows with ``stage`` and ``details`` columns.

        The winning plan tree (from ``queryPlanner.winningPlan`` or, for aggregate
        pipelines, ``stages[*].$cursor.queryPlanner.winningPlan``) is rendered as
        an indented tree. Pipeline stages and high-level metadata (namespace,
        rejected plan count, executionStats summary) are included as header /
        footer rows.
        """
        rows: List[Dict[str, str]] = []

        def fmt_details(d: Dict[str, Any]) -> str:
            if not d:
                return ""
            try:
                return json.dumps(d, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(d)

        def walk_plan(node: Dict[str, Any], depth: int, is_last: bool, prefix: str) -> None:
            if not isinstance(node, dict):
                return
            stage_name = node.get("stage") or "UNKNOWN"
            if depth == 0:
                label = stage_name
                child_prefix = ""
            else:
                connector = "└─ " if is_last else "├─ "
                label = prefix + connector + stage_name
                child_prefix = prefix + ("   " if is_last else "│  ")

            details = {k: v for k, v in node.items() if k not in ("stage", "inputStage", "inputStages")}
            rows.append({"stage": label, "details": fmt_details(details)})

            children = []
            if isinstance(node.get("inputStage"), dict):
                children.append(node["inputStage"])
            if isinstance(node.get("inputStages"), list):
                children.extend(c for c in node["inputStages"] if isinstance(c, dict))
            for i, child in enumerate(children):
                walk_plan(child, depth + 1, i == len(children) - 1, child_prefix)

        # Header metadata
        qp = explain_result.get("queryPlanner") if isinstance(explain_result, dict) else None
        if isinstance(qp, dict):
            ns = qp.get("namespace")
            if ns:
                rows.append({"stage": "namespace", "details": str(ns)})
            if "parsedQuery" in qp:
                rows.append({"stage": "parsedQuery", "details": fmt_details(qp.get("parsedQuery") or {})})
            rejected = qp.get("rejectedPlans") or []
            if rejected:
                rows.append({"stage": "rejectedPlans", "details": str(len(rejected))})

            winning = qp.get("winningPlan")
            if isinstance(winning, dict):
                walk_plan(winning, 0, True, "")

        # Aggregate pipeline explain: stages list with embedded $cursor plan
        stages = explain_result.get("stages") if isinstance(explain_result, dict) else None
        if isinstance(stages, list) and stages:
            for idx, st in enumerate(stages):
                if not isinstance(st, dict):
                    continue
                for stage_key, stage_val in st.items():
                    rows.append({"stage": f"pipeline[{idx}]: {stage_key}", "details": ""})
                    if stage_key == "$cursor" and isinstance(stage_val, dict):
                        cur_qp = stage_val.get("queryPlanner", {})
                        ns = cur_qp.get("namespace")
                        if ns:
                            rows.append({"stage": "  namespace", "details": str(ns)})
                        winning = cur_qp.get("winningPlan")
                        if isinstance(winning, dict):
                            walk_plan(winning, 0, True, "  ")
                    else:
                        detail_val = stage_val if isinstance(stage_val, dict) else {"value": stage_val}
                        rows.append({"stage": f"  {stage_key}", "details": fmt_details(detail_val)})

        # Execution stats summary (when verbosity >= executionStats)
        exec_stats = explain_result.get("executionStats") if isinstance(explain_result, dict) else None
        if isinstance(exec_stats, dict):
            summary_keys = (
                "executionSuccess",
                "nReturned",
                "executionTimeMillis",
                "totalKeysExamined",
                "totalDocsExamined",
            )
            summary = {k: exec_stats.get(k) for k in summary_keys if k in exec_stats}
            if summary:
                rows.append({"stage": "executionStats", "details": fmt_details(summary)})

        # Fallback: if we produced nothing, dump the raw explain result
        if not rows:
            rows.append({"stage": "explain", "details": fmt_details(explain_result or {})})

        return rows


__all__ = ["ExplainExecutionPlan"]
