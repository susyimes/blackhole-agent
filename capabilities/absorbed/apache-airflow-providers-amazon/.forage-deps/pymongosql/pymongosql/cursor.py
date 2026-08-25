# -*- coding: utf-8 -*-
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, TypeVar

from .common import BaseCursor, CursorIterator
from .error import DatabaseError, OperationalError, ProgrammingError, SqlSyntaxError
from .executor import ExecutionContext, ExecutionPlanFactory
from .result_set import DictResultSet, ResultSet
from .sql.query_builder import QueryExecutionPlan

if TYPE_CHECKING:
    from .connection import Connection

_logger = logging.getLogger(__name__)  # type: ignore
_T = TypeVar("_T", bound="Cursor")


class Cursor(BaseCursor, CursorIterator):
    """SQL-compatible cursor that translates SQL to MongoDB operations"""

    NO_RESULT_SET = "No result set."

    def __init__(self, connection: "Connection", mode: str = "standard", **kwargs) -> None:
        super().__init__(
            connection=connection,
            mode=mode,
            **kwargs,
        )
        self._kwargs = kwargs
        self._result_set: Optional[ResultSet] = None
        self._result_set_class = ResultSet
        self._current_execution_plan: Optional[Any] = None
        self._is_closed = False

    @property
    def result_set(self) -> Optional[ResultSet]:
        return self._result_set

    @result_set.setter
    def result_set(self, rs: ResultSet) -> None:
        self._result_set = rs

    @property
    def has_result_set(self) -> bool:
        return self._result_set is not None

    @property
    def result_set_class(self) -> Optional[type]:
        return self._result_set_class

    @result_set_class.setter
    def result_set_class(self, rs_cls: type) -> None:
        self._result_set_class = rs_cls

    @property
    def rowcount(self) -> int:
        return self._result_set.rowcount if self._result_set else -1

    @property
    def rownumber(self) -> Optional[int]:
        return self._result_set.rownumber if self._result_set else None

    @property
    def description(
        self,
    ) -> Optional[List[Tuple[str, str, None, None, None, None, None]]]:
        return self._result_set.description if self._result_set else None

    @property
    def errors(self) -> List[Dict[str, str]]:
        return self._result_set.errors if self._result_set else []

    def _check_closed(self) -> None:
        """Check if cursor is closed"""
        if self._is_closed:
            raise ProgrammingError("Cursor is closed")

    def execute(self: _T, operation: str, parameters: Optional[Any] = None) -> _T:
        """Execute a SQL statement

        Args:
            operation: SQL statement to execute
            parameters: Parameters to substitute placeholders in the SQL
                - Sequence for positional parameters with ? placeholders
                - Dict for named parameters with :name placeholders

        Returns:
            Self for method chaining
        """
        self._check_closed()

        try:
            # Create execution context
            context = ExecutionContext(operation, self.mode)

            # Get appropriate execution strategy
            strategy = ExecutionPlanFactory.get_strategy(context)

            # Execute using selected strategy (Standard or Subquery)
            result = strategy.execute(context, self.connection, parameters)

            # Store execution plan for reference
            self._current_execution_plan = strategy.execution_plan

            # Create result set from command result
            # For SELECT/QUERY operations, use the execution plan directly
            if isinstance(self._current_execution_plan, QueryExecutionPlan):
                execution_plan_for_rs = self._current_execution_plan
                self._result_set = self._result_set_class(
                    command_result=result,
                    execution_plan=execution_plan_for_rs,
                    database=self.connection.database,
                    retry_config=self.connection.retry_config,
                    **self._kwargs,
                )
            else:
                # For INSERT and other non-query operations, create a minimal synthetic result
                # since INSERT commands don't return a cursor structure
                stub_plan = QueryExecutionPlan(collection=self._current_execution_plan.collection)
                self._result_set = self._result_set_class(
                    command_result={
                        "cursor": {
                            "id": 0,
                            "firstBatch": [],
                        }
                    },
                    execution_plan=stub_plan,
                    database=self.connection.database,
                    retry_config=self.connection.retry_config,
                    **self._kwargs,
                )
                # Store the actual insert result for reference
                self._result_set._insert_result = result

            return self

        except (SqlSyntaxError, DatabaseError, OperationalError, ProgrammingError):
            # Re-raise known errors
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during execute: {e}")
            raise DatabaseError(f"Execute failed: {e}")

    def executemany(
        self,
        operation: str,
        seq_of_parameters: List[Optional[Any]],
    ) -> None:
        """Execute a SQL statement multiple times with different parameters

        This method executes the operation once for each parameter set in
        seq_of_parameters. It's particularly useful for bulk INSERT, UPDATE,
        or DELETE operations.

        Args:
            operation: SQL statement to execute
            seq_of_parameters: Sequence of parameter sets. Each element should be
                a sequence (list/tuple) for positional parameters with ? placeholders,
                or a dict for named parameters with :name placeholders.

        Returns:
            None (executemany does not produce a result set)

        Note: The rowcount property will reflect the total number of rows affected
        across all executions.
        """
        self._check_closed()

        if not seq_of_parameters:
            return

        total_rowcount = 0

        try:
            # Execute the operation for each parameter set
            for params in seq_of_parameters:
                self.execute(operation, params)
                # Accumulate rowcount from each execution
                if self.rowcount > 0:
                    total_rowcount += self.rowcount

            # Update the final result set with accumulated rowcount
            if self._result_set:
                self._result_set._rowcount = total_rowcount

        except (SqlSyntaxError, DatabaseError, OperationalError, ProgrammingError):
            # Re-raise known errors
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during executemany: {e}")
            raise DatabaseError(f"executemany failed: {e}")

    def execute_transaction(self) -> None:
        """Execute transaction - not yet implemented"""
        self._check_closed()

        raise NotImplementedError("Transaction using this function not yet implemented")

    def flush(self) -> None:
        """Flush any pending operations"""
        # In MongoDB context, this might involve ensuring writes are acknowledged
        # For now, this is a no-op
        pass

    def fetchone(self) -> Optional[Sequence[Any]]:
        """Fetch the next row from the result set"""
        self._check_closed()

        if not self.has_result_set:
            raise ProgrammingError(self.NO_RESULT_SET)

        return self._result_set.fetchone()

    def fetchmany(self, size: Optional[int] = None) -> List[Sequence[Any]]:
        """Fetch multiple rows from the result set"""
        self._check_closed()

        if not self.has_result_set:
            raise ProgrammingError(self.NO_RESULT_SET)

        return self._result_set.fetchmany(size)

    def fetchall(self) -> List[Sequence[Any]]:
        """Fetch all remaining rows from the result set"""
        self._check_closed()

        if not self.has_result_set:
            raise ProgrammingError(self.NO_RESULT_SET)

        return self._result_set.fetchall()

    def close(self) -> None:
        """Close the cursor and free resources"""
        try:
            if self._result_set:
                # Close result set
                try:
                    self._result_set.close()
                except Exception as e:
                    _logger.warning(f"Error closing result set: {e}")
                finally:
                    self._result_set = None

            self._is_closed = True

            # Remove from connection's cursor pool
            try:
                self.connection.cursor_pool.remove(self)
            except (ValueError, AttributeError):
                pass  # Cursor not in pool or connection gone

            _logger.debug("Cursor closed successfully")

        except Exception as e:
            _logger.error(f"Error during cursor close: {e}")

    def __del__(self):
        """Destructor to ensure resources are cleaned up"""
        if not self._is_closed:
            try:
                self.close()
            except Exception:
                pass  # Ignore errors during cleanup


class DictCursor(Cursor):
    """Cursor that returns results as dictionaries instead of tuples/sequences"""

    def __init__(self, connection: "Connection", **kwargs) -> None:
        super().__init__(connection=connection, **kwargs)
        # Override result set class to use DictResultSet
        self._result_set_class = DictResultSet
