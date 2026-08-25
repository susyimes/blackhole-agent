# -*- coding: utf-8 -*-
import logging
from abc import ABCMeta
from typing import Any, Optional, Union

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from ..error import SqlSyntaxError
from .ast import MongoSQLLexer, MongoSQLParser, MongoSQLParserVisitor
from .builder import ExecutionPlanBuilder
from .delete_builder import DeleteExecutionPlan
from .explain_builder import ExplainExecutionPlan
from .insert_builder import InsertExecutionPlan
from .query_builder import QueryExecutionPlan
from .update_builder import UpdateExecutionPlan

_logger = logging.getLogger(__name__)


class SQLParseErrorListener(ErrorListener):
    """Custom error listener for better error handling"""

    def __init__(self):
        super().__init__()
        self.errors = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error_msg = f"Syntax error at line {line}, column {column}: {msg}"
        self.errors.append(error_msg)
        _logger.error(error_msg)


class SQLParser(metaclass=ABCMeta):
    """Enhanced SQL Parser with better error handling and readability"""

    def __init__(self, sql: str) -> None:
        if not sql or not sql.strip():
            raise ValueError("SQL statement cannot be empty")

        self._original_sql = sql
        self._preprocessed_sql: Optional[str] = None
        self._ast: Optional[Any] = None
        self._visitor: Optional[MongoSQLParserVisitor] = None
        self._error_listener = SQLParseErrorListener()

        # Process the SQL statement
        self._process_sql()

    @property
    def original_sql(self) -> str:
        """Get the original SQL statement"""
        return self._original_sql

    @property
    def preprocessed_sql(self) -> str:
        """Get the preprocessed SQL statement"""
        return self._preprocessed_sql or self._original_sql

    @property
    def has_errors(self) -> bool:
        """Check if parsing encountered any errors"""
        return len(self._error_listener.errors) > 0

    @property
    def errors(self) -> list:
        """Get list of parsing errors"""
        return self._error_listener.errors.copy()

    def _process_sql(self) -> None:
        """Process the SQL statement through preprocessing and parsing"""
        try:
            # Step 1: Preprocess the SQL
            self._preprocess()

            # Step 2: Generate AST
            self._generate_ast()

            # Step 3: Validate AST
            self._validate_ast()

        except Exception as e:
            _logger.error(f"Failed to process SQL statement: {e}")
            raise

    def _preprocess(self) -> None:
        """Preprocess the SQL statement"""
        # Remove extra whitespace and normalize
        sql = self._original_sql.strip()

        # Remove comments (basic implementation)
        lines = []
        for line in sql.split("\n"):
            # Remove single-line comments
            if "--" in line:
                line = line[: line.index("--")]
            lines.append(line)

        self._preprocessed_sql = " ".join(lines).strip()
        _logger.debug(f"Preprocessed SQL: {self._preprocessed_sql}")

    def _generate_ast(self) -> None:
        """Generate Abstract Syntax Tree from SQL"""
        try:
            # Create lexer and parser
            input_stream = InputStream(self.preprocessed_sql)
            lexer = MongoSQLLexer(input_stream)
            lexer.addErrorListener(self._error_listener)

            token_stream = CommonTokenStream(lexer)
            parser = MongoSQLParser(token_stream)
            parser.addErrorListener(self._error_listener)

            # Generate AST
            self._ast = parser.root()

            if self.has_errors:
                error_summary = "; ".join(self.errors)
                raise SqlSyntaxError(f"SQL parsing failed: {error_summary}")

        except Exception as e:
            _logger.error(f"Failed to generate AST for SQL: {self.preprocessed_sql}")
            if not isinstance(e, SqlSyntaxError):
                raise SqlSyntaxError(f"AST generation failed: {e}") from e
            raise

    def _validate_ast(self) -> None:
        """Validate the generated AST"""
        if self._ast is None:
            raise SqlSyntaxError("AST generation resulted in None")

        _logger.debug("AST validation successful")

    def get_execution_plan(
        self,
    ) -> Union[QueryExecutionPlan, InsertExecutionPlan, DeleteExecutionPlan, UpdateExecutionPlan, ExplainExecutionPlan]:
        """Parse SQL and return an execution plan (SELECT, INSERT, DELETE, UPDATE, or EXPLAIN)."""
        if self._ast is None:
            raise SqlSyntaxError("No AST available - parsing may have failed")

        try:
            self._visitor = MongoSQLParserVisitor()
            self._visitor.visit(self._ast)

            # Use ExecutionPlanBuilder to create the inner plan from parse result
            execution_plan = ExecutionPlanBuilder.build_from_parse_result(
                self._visitor.parse_result, self._visitor.current_operation
            )

            if not execution_plan.validate():
                raise SqlSyntaxError("Generated execution plan is invalid")

            # If the statement was wrapped in EXPLAIN, wrap the inner plan.
            if getattr(self._visitor, "is_explain", False):
                options = self._visitor.explain_options
                # Option key names are case-insensitive; normalize to lower-case lookups.
                normalized = {k.lower(): v for k, v in options.items()}
                verbosity = normalized.get("verbosity", "queryPlanner")
                explain_plan = ExplainExecutionPlan(
                    collection=execution_plan.collection,
                    inner_plan=execution_plan,
                    verbosity=verbosity,
                    options=options,
                )
                if not explain_plan.validate():
                    raise SqlSyntaxError("Generated EXPLAIN plan is invalid")
                _logger.debug(
                    f"Generated EXPLAIN plan (verbosity={verbosity}) for collection: {execution_plan.collection}"
                )
                return explain_plan

            _logger.debug(f"Generated execution plan for collection: {execution_plan.collection}")
            return execution_plan

        except Exception as e:
            _logger.error(f"Failed to generate execution plan from AST: {e}")
            raise SqlSyntaxError(f"Execution plan generation failed: {e}") from e

    def get_parse_info(self) -> dict:
        """Get detailed parsing information for debugging"""
        return {
            "original_sql": self.original_sql,
            "preprocessed_sql": self.preprocessed_sql,
            "has_errors": self.has_errors,
            "errors": self.errors,
            "ast_available": self._ast is not None,
            "visitor_available": self._visitor is not None,
            "parse_context": self._visitor.parse_context if self._visitor else None,
        }
