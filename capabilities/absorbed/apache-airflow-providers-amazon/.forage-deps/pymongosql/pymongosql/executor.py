# -*- coding: utf-8 -*-
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Union

from pymongo.errors import PyMongoError

from .error import DatabaseError, OperationalError, ProgrammingError, SqlSyntaxError
from .helper import SQLHelper
from .retry import execute_with_retry
from .sql.delete_builder import DeleteExecutionPlan
from .sql.explain_builder import ExplainExecutionPlan
from .sql.insert_builder import InsertExecutionPlan
from .sql.parser import SQLParser
from .sql.query_builder import QueryExecutionPlan
from .sql.update_builder import UpdateExecutionPlan
from .sql.view_builder import ViewExecutionPlan

_logger = logging.getLogger(__name__)


def _run_db_command(db: Any, command: Dict[str, Any], connection: Any, operation_name: str) -> Dict[str, Any]:
    """Run a MongoDB command with optional transaction session and retry policy."""
    retry_config = getattr(connection, "retry_config", None)
    # command() falls back to DEFAULT_CODEC_OPTIONS, ignoring client options like uuidRepresentation
    codec_options = db.codec_options

    if connection and connection.session and connection.session.in_transaction:
        return execute_with_retry(
            lambda: db.command(command, session=connection.session, codec_options=codec_options),
            retry_config,
            operation_name,
        )

    return execute_with_retry(
        lambda: db.command(command, codec_options=codec_options),
        retry_config,
        operation_name,
    )


@dataclass
class ExecutionContext:
    """Manages execution context for a single query"""

    query: str
    execution_mode: str = "standard"
    parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None

    def __repr__(self) -> str:
        return f"ExecutionContext(mode={self.execution_mode}, " f"query={self.query})"


class ExecutionStrategy(ABC):
    """Abstract base class for query execution strategies"""

    @property
    @abstractmethod
    def execution_plan(self) -> Union[QueryExecutionPlan, InsertExecutionPlan]:
        """Name of the execution plan"""
        pass

    @abstractmethod
    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute query and return result set.

        Args:
            context: ExecutionContext with query and subquery info
            connection: MongoDB connection
            parameters: Sequence for positional (?) or Dict for named (:param) parameters

        Returns:
            command_result with query results
        """
        pass

    @abstractmethod
    def supports(self, context: ExecutionContext) -> bool:
        """Check if this strategy supports the given context"""
        pass


class StandardQueryExecution(ExecutionStrategy):
    """Standard execution strategy for simple SELECT queries without subqueries"""

    @property
    def execution_plan(self) -> QueryExecutionPlan:
        """Return standard execution plan"""
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        """Support simple queries without subqueries"""
        normalized = context.query.lstrip().upper()
        return "standard" in context.execution_mode.lower() and normalized.startswith("SELECT")

    def _parse_sql(self, sql: str) -> QueryExecutionPlan:
        """Parse SQL statement and return QueryExecutionPlan"""
        try:
            parser = SQLParser(sql)
            execution_plan = parser.get_execution_plan()

            if not execution_plan.validate():
                raise SqlSyntaxError("Generated query plan is invalid")

            return execution_plan

        except SqlSyntaxError:
            raise
        except Exception as e:
            _logger.error(f"SQL parsing failed: {e}")
            raise SqlSyntaxError(f"Failed to parse SQL: {e}")

    def _replace_placeholders(self, obj: Any, parameters: Sequence[Any]) -> Any:
        """Recursively replace ? placeholders with parameter values in filter/projection dicts"""
        return SQLHelper.replace_placeholders_generic(obj, parameters, "qmark")

    def _execute_find_plan(
        self,
        execution_plan: QueryExecutionPlan,
        connection: Any = None,
        parameters: Optional[Sequence[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a QueryExecutionPlan against MongoDB using db.command

        Args:
            execution_plan: QueryExecutionPlan to execute
            connection: Connection object (for session and database access)
            parameters: Parameters for placeholder replacement
        """
        try:
            # Get database from connection
            if not connection:
                raise OperationalError("No connection provided")

            db = connection.database

            # Get database
            if not execution_plan.collection:
                raise ProgrammingError("No collection specified in query")

            # Replace placeholders with parameters in filter_stage only (not in projection)
            filter_stage = execution_plan.filter_stage or {}

            if parameters:
                # Positional parameters with ? (named parameters are converted to positional in execute())
                filter_stage = self._replace_placeholders(filter_stage, parameters)

            projection_stage = execution_plan.projection_stage or {}

            # Build MongoDB find command
            find_command = {"find": execution_plan.collection, "filter": filter_stage}

            # Apply projection if specified
            if projection_stage:
                find_command["projection"] = projection_stage

            # Apply sort if specified
            if execution_plan.sort_stage:
                sort_spec = {}
                for sort_dict in execution_plan.sort_stage:
                    for field_name, direction in sort_dict.items():
                        sort_spec[field_name] = direction
                find_command["sort"] = sort_spec

            # Apply skip if specified
            if execution_plan.skip_stage:
                find_command["skip"] = execution_plan.skip_stage

            # Apply limit if specified
            if execution_plan.limit_stage:
                find_command["limit"] = execution_plan.limit_stage

            _logger.debug(f"Executing MongoDB command: {find_command}")

            # Execute find command with retry for transient system-level errors
            result = _run_db_command(db, find_command, connection, "find command")

            # Create command result
            return result

        except PyMongoError as e:
            _logger.error(f"MongoDB command execution failed: {e}")
            raise DatabaseError(f"Command execution failed: {e}")
        except Exception as e:
            _logger.error(f"Unexpected error during command execution: {e}")
            raise OperationalError(f"Command execution error: {e}")

    def _execute_aggregate_plan(
        self,
        execution_plan: QueryExecutionPlan,
        connection: Any = None,
        parameters: Optional[Sequence[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute a QueryExecutionPlan with aggregate() call.

        Args:
            execution_plan: QueryExecutionPlan with aggregate_pipeline and aggregate_options
            connection: Connection object (for database access)
            parameters: Parameters for placeholder replacement

        Returns:
            Command result with aggregation results
        """
        try:
            import json

            # Get database from connection
            if not connection:
                raise OperationalError("No connection provided")

            db = connection.database

            if not execution_plan.collection:
                raise ProgrammingError("No collection specified in aggregate query")

            # Parse pipeline and options from JSON strings
            try:
                pipeline = json.loads(execution_plan.aggregate_pipeline or "[]")
                options = json.loads(execution_plan.aggregate_options or "{}")
            except json.JSONDecodeError as e:
                raise ProgrammingError(f"Invalid JSON in aggregate pipeline or options: {e}")

            _logger.debug(f"Executing aggregate on collection {execution_plan.collection}")
            _logger.debug(f"Pipeline: {pipeline}")
            _logger.debug(f"Options: {options}")

            # Get collection and call aggregate()
            collection = db[execution_plan.collection]

            # Execute aggregate with retry for transient system-level errors
            retry_config = getattr(connection, "retry_config", None)
            results = execute_with_retry(
                lambda: list(collection.aggregate(pipeline, **options)),
                retry_config,
                "aggregate command",
            )

            # Apply additional filters if specified (from WHERE clause)
            if execution_plan.filter_stage:
                _logger.debug(f"Applying additional filter: {execution_plan.filter_stage}")
                # Would need to filter results in Python, as aggregate already ran
                # For now, log that we're applying filters
                results = self._filter_results(results, execution_plan.filter_stage)

            # Apply sorting if specified
            if execution_plan.sort_stage:
                for sort_dict in reversed(execution_plan.sort_stage):
                    for field_name, direction in sort_dict.items():
                        reverse = direction == -1
                        results = sorted(results, key=lambda x: x.get(field_name), reverse=reverse)

            # Apply skip and limit
            if execution_plan.skip_stage:
                results = results[execution_plan.skip_stage :]

            if execution_plan.limit_stage:
                results = results[: execution_plan.limit_stage]

            # Apply projection if specified
            if execution_plan.projection_stage:
                results = self._apply_projection(results, execution_plan.projection_stage)

            # Return in command result format
            return {
                "cursor": {"firstBatch": results},
                "ok": 1,
            }

        except (ProgrammingError, OperationalError):
            raise
        except PyMongoError as e:
            _logger.error(f"MongoDB aggregate execution failed: {e}")
            raise DatabaseError(f"Aggregate execution failed: {e}")
        except Exception as e:
            _logger.error(f"Unexpected error during aggregate execution: {e}")
            raise OperationalError(f"Aggregate execution error: {e}")

    @staticmethod
    def _filter_results(results: list, filter_conditions: dict) -> list:
        """Apply MongoDB filter conditions to Python results"""
        # Basic filtering implementation
        # This is a simplified version - can be enhanced with full MongoDB query operators
        filtered = []
        for doc in results:
            if StandardQueryExecution._matches_filter(doc, filter_conditions):
                filtered.append(doc)
        return filtered

    @staticmethod
    def _matches_filter(doc: dict, filter_conditions: dict) -> bool:
        """Check if a document matches the filter conditions"""
        for field, condition in filter_conditions.items():
            if field == "$and":
                return all(StandardQueryExecution._matches_filter(doc, cond) for cond in condition)
            elif field == "$or":
                return any(StandardQueryExecution._matches_filter(doc, cond) for cond in condition)
            elif isinstance(condition, dict):
                # Handle operators like $eq, $gt, etc.
                for op, value in condition.items():
                    if op == "$eq":
                        if doc.get(field) != value:
                            return False
                    elif op == "$ne":
                        if doc.get(field) == value:
                            return False
                    elif op == "$gt":
                        if not (doc.get(field) > value):
                            return False
                    elif op == "$gte":
                        if not (doc.get(field) >= value):
                            return False
                    elif op == "$lt":
                        if not (doc.get(field) < value):
                            return False
                    elif op == "$lte":
                        if not (doc.get(field) <= value):
                            return False
            else:
                if doc.get(field) != condition:
                    return False
        return True

    @staticmethod
    def _apply_projection(results: list, projection_stage: dict) -> list:
        """Apply projection to results"""
        projected = []
        include_fields = {k for k, v in projection_stage.items() if v == 1}
        exclude_fields = {k for k, v in projection_stage.items() if v == 0}

        for doc in results:
            if include_fields:
                # Include mode: only include specified fields
                projected_doc = (
                    {"_id": doc.get("_id")} if "_id" in include_fields or "_id" not in projection_stage else {}
                )
                for field in include_fields:
                    if field != "_id" and field in doc:
                        projected_doc[field] = doc[field]
                projected.append(projected_doc)
            else:
                # Exclude mode: exclude specified fields
                projected_doc = {k: v for k, v in doc.items() if k not in exclude_fields}
                projected.append(projected_doc)

        return projected

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute standard query directly against MongoDB"""
        _logger.debug(f"Using standard execution for query: {context.query[:100]}")

        # Preprocess query to convert named parameters to positional
        processed_query = context.query
        processed_params = parameters
        if isinstance(parameters, dict):
            # Convert :param_name to ? for parsing
            import re

            param_names = re.findall(r":(\w+)", context.query)
            # Convert dict parameters to list in order of appearance
            processed_params = [parameters[name] for name in param_names]
            # Replace :param_name with ?
            processed_query = re.sub(r":(\w+)", "?", context.query)

        # Parse the query
        self._execution_plan = self._parse_sql(processed_query)

        # Route to appropriate execution plan handler
        if hasattr(self._execution_plan, "is_aggregate_query") and self._execution_plan.is_aggregate_query:
            return self._execute_aggregate_plan(self._execution_plan, connection, processed_params)
        else:
            return self._execute_find_plan(self._execution_plan, connection, processed_params)


class InsertExecution(ExecutionStrategy):
    """Execution strategy for INSERT statements."""

    @property
    def execution_plan(self) -> InsertExecutionPlan:
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        return context.query.lstrip().upper().startswith("INSERT")

    def _parse_sql(self, sql: str) -> InsertExecutionPlan:
        try:
            parser = SQLParser(sql)
            plan = parser.get_execution_plan()

            if not isinstance(plan, InsertExecutionPlan):
                raise SqlSyntaxError("Expected INSERT execution plan")

            if not plan.validate():
                raise SqlSyntaxError("Generated insert plan is invalid")

            return plan
        except SqlSyntaxError:
            raise
        except Exception as e:
            _logger.error(f"SQL parsing failed: {e}")
            raise SqlSyntaxError(f"Failed to parse SQL: {e}")

    def _replace_placeholders(
        self,
        documents: Sequence[Dict[str, Any]],
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]],
        style: Optional[str],
    ) -> Sequence[Dict[str, Any]]:
        return SQLHelper.replace_placeholders_generic(documents, parameters, style)

    def _execute_execution_plan(
        self,
        execution_plan: InsertExecutionPlan,
        connection: Any = None,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            # Get database from connection
            if not connection:
                raise OperationalError("No connection provided")

            db = connection.database

            if not execution_plan.collection:
                raise ProgrammingError("No collection specified in insert")

            docs = execution_plan.insert_documents or []
            docs = self._replace_placeholders(docs, parameters, execution_plan.parameter_style)

            command = {"insert": execution_plan.collection, "documents": docs}

            _logger.debug(f"Executing MongoDB insert command: {command}")

            return _run_db_command(db, command, connection, "insert command")
        except PyMongoError as e:
            _logger.error(f"MongoDB insert failed: {e}")
            raise DatabaseError(f"Insert execution failed: {e}")
        except (ProgrammingError, DatabaseError, OperationalError):
            # Re-raise our own errors without wrapping
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during insert execution: {e}")
            raise OperationalError(f"Insert execution error: {e}")

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        _logger.debug(f"Using insert execution for query: {context.query[:100]}")

        self._execution_plan = self._parse_sql(context.query)

        return self._execute_execution_plan(self._execution_plan, connection, parameters)


class DeleteExecution(ExecutionStrategy):
    """Strategy for executing DELETE statements."""

    @property
    def execution_plan(self) -> Any:
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        return context.query.lstrip().upper().startswith("DELETE")

    def _parse_sql(self, sql: str) -> Any:
        try:
            parser = SQLParser(sql)
            plan = parser.get_execution_plan()

            if not isinstance(plan, DeleteExecutionPlan):
                raise SqlSyntaxError("Expected DELETE execution plan")

            if not plan.validate():
                raise SqlSyntaxError("Generated delete plan is invalid")

            return plan
        except SqlSyntaxError:
            raise
        except Exception as e:
            _logger.error(f"SQL parsing failed: {e}")
            raise SqlSyntaxError(f"Failed to parse SQL: {e}")

    def _execute_execution_plan(
        self,
        execution_plan: Any,
        connection: Any = None,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            # Get database from connection
            if not connection:
                raise OperationalError("No connection provided")

            db = connection.database

            if not execution_plan.collection:
                raise ProgrammingError("No collection specified in delete")

            filter_conditions = execution_plan.filter_conditions or {}

            # Replace placeholders in filter if parameters provided
            if parameters and filter_conditions:
                filter_conditions = SQLHelper.replace_placeholders_generic(
                    filter_conditions, parameters, execution_plan.parameter_style
                )

            command = {"delete": execution_plan.collection, "deletes": [{"q": filter_conditions, "limit": 0}]}

            _logger.debug(f"Executing MongoDB delete command: {command}")

            return _run_db_command(db, command, connection, "delete command")
        except PyMongoError as e:
            _logger.error(f"MongoDB delete failed: {e}")
            raise DatabaseError(f"Delete execution failed: {e}")
        except (ProgrammingError, DatabaseError, OperationalError):
            # Re-raise our own errors without wrapping
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during delete execution: {e}")
            raise OperationalError(f"Delete execution error: {e}")

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        _logger.debug(f"Using delete execution for query: {context.query[:100]}")

        self._execution_plan = self._parse_sql(context.query)

        return self._execute_execution_plan(self._execution_plan, connection, parameters)


class UpdateExecution(ExecutionStrategy):
    """Strategy for executing UPDATE statements."""

    @property
    def execution_plan(self) -> Any:
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        return context.query.lstrip().upper().startswith("UPDATE")

    def _parse_sql(self, sql: str) -> Any:
        try:
            parser = SQLParser(sql)
            plan = parser.get_execution_plan()

            if not isinstance(plan, UpdateExecutionPlan):
                raise SqlSyntaxError("Expected UPDATE execution plan")

            if not plan.validate():
                raise SqlSyntaxError("Generated update plan is invalid")

            return plan
        except SqlSyntaxError:
            raise
        except Exception as e:
            _logger.error(f"SQL parsing failed: {e}")
            raise SqlSyntaxError(f"Failed to parse SQL: {e}")

    def _execute_execution_plan(
        self,
        execution_plan: Any,
        connection: Any = None,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            # Get database from connection
            if not connection:
                raise OperationalError("No connection provided")

            db = connection.database

            if not execution_plan.collection:
                raise ProgrammingError("No collection specified in update")

            if not execution_plan.update_fields:
                raise ProgrammingError("No fields to update specified")

            filter_conditions = execution_plan.filter_conditions or {}
            update_fields = execution_plan.update_fields or {}

            # Replace placeholders if parameters provided
            # Note: We need to replace both update_fields and filter_conditions in one pass
            # to maintain correct parameter ordering (SET clause first, then WHERE clause)
            if parameters:
                # Combine structures for replacement in correct order
                combined = {"update_fields": update_fields, "filter_conditions": filter_conditions}
                replaced = SQLHelper.replace_placeholders_generic(combined, parameters, execution_plan.parameter_style)
                update_fields = replaced["update_fields"]
                filter_conditions = replaced["filter_conditions"]

            # MongoDB update command format
            # https://www.mongodb.com/docs/manual/reference/command/update/
            command = {
                "update": execution_plan.collection,
                "updates": [
                    {
                        "q": filter_conditions,  # query filter
                        "u": {"$set": update_fields},  # update document using $set operator
                        "multi": True,  # update all matching documents (like SQL UPDATE)
                        "upsert": False,  # don't insert if no match
                    }
                ],
            }

            _logger.debug(f"Executing MongoDB update command: {command}")

            return _run_db_command(db, command, connection, "update command")
        except PyMongoError as e:
            _logger.error(f"MongoDB update failed: {e}")
            raise DatabaseError(f"Update execution failed: {e}")
        except (ProgrammingError, DatabaseError, OperationalError):
            # Re-raise our own errors without wrapping
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during update execution: {e}")
            raise OperationalError(f"Update execution error: {e}")

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        _logger.debug(f"Using update execution for query: {context.query[:100]}")

        self._execution_plan = self._parse_sql(context.query)

        return self._execute_execution_plan(self._execution_plan, connection, parameters)


class ViewExecution(ExecutionStrategy):
    """Execution strategy for view statements (CREATE VIEW, DROP VIEW)."""

    _DDL_PATTERN = re.compile(
        r"^\s*(CREATE\s+VIEW|DROP\s+VIEW)\b",
        re.IGNORECASE,
    )

    @property
    def execution_plan(self) -> ViewExecutionPlan:
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        return bool(self._DDL_PATTERN.match(context.query))

    def _parse_sql(self, sql: str) -> ViewExecutionPlan:
        normalized = " ".join(sql.split())

        # CREATE VIEW view_name ON collection_name AS 'pipeline_json'
        create_match = re.match(
            r"CREATE\s+VIEW\s+(\w+)\s+ON\s+(\w+)\s+AS\s+'(.*)'",
            normalized,
            re.IGNORECASE | re.DOTALL,
        )
        if create_match:
            import json

            view_name = create_match.group(1)
            source_collection = create_match.group(2)
            pipeline_str = create_match.group(3)
            try:
                pipeline = json.loads(pipeline_str)
            except json.JSONDecodeError as e:
                raise SqlSyntaxError(f"Invalid pipeline JSON in CREATE VIEW: {e}")

            if not isinstance(pipeline, list):
                raise SqlSyntaxError("Pipeline must be a JSON array")

            return ViewExecutionPlan(
                collection=view_name,
                ddl_type="create_view",
                view_on=source_collection,
                pipeline=pipeline,
            )

        # DROP VIEW view_name
        drop_match = re.match(
            r"DROP\s+VIEW\s+(\w+)\s*$",
            normalized,
            re.IGNORECASE,
        )
        if drop_match:
            view_name = drop_match.group(1)
            return ViewExecutionPlan(
                collection=view_name,
                ddl_type="drop_view",
            )

        raise SqlSyntaxError(f"Unsupported DDL statement: {sql}")

    def _execute_execution_plan(
        self,
        execution_plan: ViewExecutionPlan,
        connection: Any = None,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            if not connection:
                raise OperationalError("No connection provided")

            db = connection.database

            if execution_plan.ddl_type == "create_view":
                command = {
                    "create": execution_plan.collection,
                    "viewOn": execution_plan.view_on,
                    "pipeline": execution_plan.pipeline,
                }
                _logger.debug(f"Executing MongoDB create view command: {command}")
                return _run_db_command(db, command, connection, "create view")

            elif execution_plan.ddl_type == "drop_view":
                # MongoDB drops views with the regular drop command
                command = {"drop": execution_plan.collection}
                _logger.debug(f"Executing MongoDB drop view command: {command}")
                return _run_db_command(db, command, connection, "drop view")

            else:
                raise ProgrammingError(f"Unknown DDL type: {execution_plan.ddl_type}")

        except PyMongoError as e:
            _logger.error(f"MongoDB DDL execution failed: {e}")
            raise DatabaseError(f"DDL execution failed: {e}")
        except (ProgrammingError, DatabaseError, OperationalError):
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during DDL execution: {e}")
            raise OperationalError(f"DDL execution error: {e}")

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        _logger.debug(f"Using DDL execution for query: {context.query[:100]}")
        self._execution_plan = self._parse_sql(context.query)

        if not self._execution_plan.validate():
            raise SqlSyntaxError("Generated DDL plan is invalid")

        return self._execute_execution_plan(self._execution_plan, connection, parameters)


class ExplainExecution(ExecutionStrategy):
    """Execution strategy for ``EXPLAIN [ (opt val, ...) ] <statement>`` wrappers.

    Parses via :class:`SQLParser` (grammar-native EXPLAIN production) to obtain
    an :class:`ExplainExecutionPlan`, delegates command construction and result
    flattening to the plan, and runs the resulting ``explain`` command through
    the shared connection/retry path.
    """

    _EXPLAIN_PATTERN = re.compile(r"^\s*EXPLAIN\b", re.IGNORECASE)

    @property
    def execution_plan(self) -> QueryExecutionPlan:
        return self._execution_plan

    def supports(self, context: ExecutionContext) -> bool:
        return bool(self._EXPLAIN_PATTERN.match(context.query))

    def _parse_sql(self, sql: str) -> ExplainExecutionPlan:
        try:
            parser = SQLParser(sql)
            plan = parser.get_execution_plan()
            if not isinstance(plan, ExplainExecutionPlan):
                raise SqlSyntaxError("Expected EXPLAIN execution plan")
            if not plan.validate():
                raise SqlSyntaxError("Generated EXPLAIN plan is invalid")
            return plan
        except SqlSyntaxError:
            raise
        except Exception as e:
            _logger.error(f"SQL parsing failed: {e}")
            raise SqlSyntaxError(f"Failed to parse SQL: {e}")

    def execute(
        self,
        context: ExecutionContext,
        connection: Any,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        _logger.debug(f"Using explain execution for query: {context.query[:100]}")

        # Normalize named parameters to positional, matching StandardQueryExecution.
        processed_query = context.query
        processed_params = parameters
        if isinstance(parameters, dict):
            param_names = re.findall(r":(\w+)", context.query)
            processed_params = [parameters[name] for name in param_names]
            processed_query = re.sub(r":(\w+)", "?", context.query)

        explain_plan = self._parse_sql(processed_query)
        # Store the synthesized result plan (QueryExecutionPlan) so the cursor
        # can wire it directly into the ResultSet for column description.
        self._execution_plan = explain_plan.result_plan

        # Build the explain command (validates inner plan is a supported SELECT).
        explain_cmd = explain_plan.build_command(processed_params)

        if not connection:
            raise OperationalError("No connection provided")

        _logger.debug(f"Executing MongoDB explain command: {explain_cmd}")

        try:
            explain_result = _run_db_command(connection.database, explain_cmd, connection, "explain command")
        except PyMongoError as e:
            _logger.error(f"MongoDB explain execution failed: {e}")
            raise DatabaseError(f"Explain execution failed: {e}")

        # Return flattened rows as a command result. The cursor handles
        # ExplainExecutionPlan -> result_plan translation when wiring the ResultSet.
        return {
            "cursor": {"id": 0, "firstBatch": explain_plan.flatten_result(explain_result)},
            "ok": 1,
        }


class ExecutionPlanFactory:
    """Factory for creating appropriate execution strategy based on query context"""

    _strategies = [
        ExplainExecution(),
        ViewExecution(),
        StandardQueryExecution(),
        InsertExecution(),
        UpdateExecution(),
        DeleteExecution(),
    ]

    @classmethod
    def get_strategy(cls, context: ExecutionContext) -> ExecutionStrategy:
        """Get appropriate execution strategy for context"""
        for strategy in cls._strategies:
            if strategy.supports(context):
                _logger.debug(f"Selected strategy: {strategy.__class__.__name__}")
                return strategy

        # Fallback to standard execution
        return StandardQueryExecution()

    @classmethod
    def register_strategy(cls, strategy: ExecutionStrategy) -> None:
        """
        Register a custom execution strategy.

        Args:
            strategy: ExecutionStrategy instance
        """
        cls._strategies.append(strategy)
        _logger.debug(f"Registered strategy: {strategy.__class__.__name__}")
