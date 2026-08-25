# -*- coding: utf-8 -*-
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

if TYPE_CHECKING:
    from .delete_builder import DeleteExecutionPlan
    from .delete_handler import DeleteParseResult
    from .insert_builder import InsertExecutionPlan
    from .insert_handler import InsertParseResult
    from .query_builder import QueryExecutionPlan
    from .query_handler import QueryParseResult
    from .update_builder import UpdateExecutionPlan
    from .update_handler import UpdateParseResult

_logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Base class for execution plans (query, insert, etc.).

    Provides common attributes and shared validation helpers.
    """

    collection: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to a serializable dictionary. Must be implemented by subclasses."""
        raise NotImplementedError()

    def validate_base(self) -> list[str]:
        """Common validation checks for all plans.

        Returns a list of error messages for the caller to aggregate and log.
        """
        errors: list[str] = []
        if not self.collection:
            errors.append("Collection name is required")
        return errors


class BuilderFactory:
    """Factory for creating builders for different operations."""

    @staticmethod
    def create_query_builder():
        """Create a builder for SELECT queries"""
        # Local import to avoid circular dependency during module import
        from .query_builder import MongoQueryBuilder

        return MongoQueryBuilder()

    @staticmethod
    def create_insert_builder():
        """Create a builder for INSERT queries"""
        # Local import to avoid circular dependency during module import
        from .insert_builder import MongoInsertBuilder

        return MongoInsertBuilder()

    @staticmethod
    def create_delete_builder():
        """Create a builder for DELETE queries"""
        # Local import to avoid circular dependency during module import
        from .delete_builder import MongoDeleteBuilder

        return MongoDeleteBuilder()

    @staticmethod
    def create_update_builder():
        """Create a builder for UPDATE queries"""
        # Local import to avoid circular dependency during module import
        from .update_builder import MongoUpdateBuilder

        return MongoUpdateBuilder()


class ExecutionPlanBuilder:
    """Builder class to create execution plans from parse results.

    This class decouples the AST visitor from execution plan creation,
    providing a clean separation between parsing and plan generation.
    """

    @staticmethod
    def build_from_parse_result(
        parse_result: Union["QueryParseResult", "InsertParseResult", "DeleteParseResult", "UpdateParseResult"],
        operation: str,
    ) -> Union["QueryExecutionPlan", "InsertExecutionPlan", "DeleteExecutionPlan", "UpdateExecutionPlan"]:
        """Build an execution plan from a parse result based on the operation type.

        Args:
            parse_result: The parse result from the AST visitor
            operation: The operation type ('select', 'insert', 'delete', or 'update')

        Returns:
            The appropriate execution plan for the operation

        Raises:
            SqlSyntaxError: If the parse result is invalid or plan generation fails
        """
        if operation == "insert":
            return ExecutionPlanBuilder._build_insert_plan(parse_result)
        elif operation == "delete":
            return ExecutionPlanBuilder._build_delete_plan(parse_result)
        elif operation == "update":
            return ExecutionPlanBuilder._build_update_plan(parse_result)
        else:  # Default to SELECT/query
            return ExecutionPlanBuilder._build_query_plan(parse_result)

    @staticmethod
    def _build_query_plan(parse_result: "QueryParseResult") -> "QueryExecutionPlan":
        """Build a query execution plan from SELECT parsing."""

        # Auto-generate aggregate pipeline for SQL aggregate functions (COUNT, SUM, etc.)
        if getattr(parse_result, "aggregate_functions", None):
            return ExecutionPlanBuilder._build_sql_aggregate_plan(parse_result)

        builder = BuilderFactory.create_query_builder().collection(parse_result.collection)

        builder.filter(parse_result.filter_conditions).project(parse_result.projection).column_aliases(
            parse_result.column_aliases
        ).sort(parse_result.sort_fields).limit(parse_result.limit_value).skip(parse_result.offset_value)

        # Set aggregate flags BEFORE building (needed for validation)
        if hasattr(parse_result, "is_aggregate_query") and parse_result.is_aggregate_query:
            builder._execution_plan.is_aggregate_query = True
            builder._execution_plan.aggregate_pipeline = parse_result.aggregate_pipeline
            builder._execution_plan.aggregate_options = parse_result.aggregate_options

        # Now build and validate
        plan = builder.build()
        return plan

    @staticmethod
    def _build_sql_aggregate_plan(parse_result: "QueryParseResult") -> "QueryExecutionPlan":
        """Build an aggregate execution plan from SQL aggregate functions like COUNT(*), SUM(), etc."""
        _FUNCTION_TO_ACCUMULATOR = {
            "COUNT": "$sum",
            "SUM": "$sum",
            "AVG": "$avg",
            "MIN": "$min",
            "MAX": "$max",
        }

        builder = BuilderFactory.create_query_builder().collection(parse_result.collection)

        pipeline = []

        # Add $match stage if there are filter conditions (from WHERE clause)
        if parse_result.filter_conditions:
            pipeline.append({"$match": parse_result.filter_conditions})

        # Build $group stage from aggregate functions
        group_stage = {"_id": None}
        for func_info in parse_result.aggregate_functions:
            alias = func_info["alias"]
            func_name = func_info["function"]
            arg = func_info["argument"]
            accumulator = _FUNCTION_TO_ACCUMULATOR[func_name]

            if func_name == "COUNT":
                group_stage[alias] = {accumulator: 1}
            else:
                group_stage[alias] = {accumulator: f"${arg}"}

        pipeline.append({"$group": group_stage})

        # Add $project to exclude _id
        project_stage = {"_id": 0}
        for func_info in parse_result.aggregate_functions:
            project_stage[func_info["alias"]] = 1
        pipeline.append({"$project": project_stage})

        # Configure the execution plan as an aggregate query
        builder._execution_plan.is_aggregate_query = True
        builder._execution_plan.aggregate_pipeline = json.dumps(pipeline)
        builder._execution_plan.aggregate_options = json.dumps({})

        # Set projection for ResultSet description
        agg_projection = {}
        for func_info in parse_result.aggregate_functions:
            agg_projection[func_info["alias"]] = 1
        builder._execution_plan.projection_stage = agg_projection

        plan = builder.build()
        return plan

    @staticmethod
    def _build_insert_plan(parse_result: "InsertParseResult") -> "InsertExecutionPlan":
        """Build an INSERT execution plan from INSERT parsing."""
        from ..error import SqlSyntaxError

        if parse_result.has_errors:
            raise SqlSyntaxError(parse_result.error_message or "INSERT parsing failed")

        builder = BuilderFactory.create_insert_builder().collection(parse_result.collection)

        documents = parse_result.insert_documents or []
        builder.insert_documents(documents)

        if parse_result.parameter_style:
            builder.parameter_style(parse_result.parameter_style)

        if parse_result.parameter_count > 0:
            builder.parameter_count(parse_result.parameter_count)

        return builder.build()

    @staticmethod
    def _build_delete_plan(parse_result: "DeleteParseResult") -> "DeleteExecutionPlan":
        """Build a DELETE execution plan from DELETE parsing."""
        _logger.debug(
            f"Building DELETE plan with collection: {parse_result.collection}, "
            f"filters: {parse_result.filter_conditions}"
        )
        builder = BuilderFactory.create_delete_builder().collection(parse_result.collection)

        if parse_result.filter_conditions:
            builder.filter_conditions(parse_result.filter_conditions)

        return builder.build()

    @staticmethod
    def _build_update_plan(parse_result: "UpdateParseResult") -> "UpdateExecutionPlan":
        """Build an UPDATE execution plan from UPDATE parsing."""
        _logger.debug(
            f"Building UPDATE plan with collection: {parse_result.collection}, "
            f"update_fields: {parse_result.update_fields}, "
            f"filters: {parse_result.filter_conditions}"
        )
        builder = BuilderFactory.create_update_builder().collection(parse_result.collection)

        if parse_result.update_fields:
            builder.update_fields(parse_result.update_fields)

        if parse_result.filter_conditions:
            builder.filter_conditions(parse_result.filter_conditions)

        return builder.build()


__all__ = [
    "ExecutionPlan",
    "BuilderFactory",
    "ExecutionPlanBuilder",
]
