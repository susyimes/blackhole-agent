# -*- coding: utf-8 -*-
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .handler import BaseHandler, ContextUtilsMixin
from .partiql.PartiQLParser import PartiQLParser

_logger = logging.getLogger(__name__)


@dataclass
class QueryParseResult:
    """Result container for query (SELECT) expression parsing and visitor state management"""

    # Core parsing fields
    filter_conditions: Dict[str, Any] = field(default_factory=dict)  # Unified filter field for all MongoDB conditions
    has_errors: bool = False
    error_message: Optional[str] = None

    # Visitor parsing state fields
    collection: Optional[str] = None
    projection: Dict[str, Any] = field(default_factory=dict)
    column_aliases: Dict[str, str] = field(default_factory=dict)  # Maps field_name -> alias
    sort_fields: List[Dict[str, int]] = field(default_factory=list)
    limit_value: Optional[int] = None
    offset_value: Optional[int] = None

    # Aggregate pipeline support
    is_aggregate_query: bool = False  # Flag indicating this is an aggregate() call
    aggregate_pipeline: Optional[str] = None  # JSON string representation of pipeline
    aggregate_options: Optional[str] = None  # JSON string representation of options

    # SQL aggregate functions detected in SELECT (COUNT, SUM, AVG, MIN, MAX)
    aggregate_functions: List[Dict[str, Any]] = field(default_factory=list)

    # Subquery info (for wrapped subqueries, e.g., Superset outering)
    subquery_plan: Optional[Any] = None
    subquery_alias: Optional[str] = None

    # Factory methods for different use cases
    @classmethod
    def for_visitor(cls) -> "QueryParseResult":
        """Create QueryParseResult for visitor parsing"""
        return cls()

    def merge_expression(self, other: "QueryParseResult") -> "QueryParseResult":
        """Merge expression results from another QueryParseResult"""
        if other.has_errors:
            self.has_errors = True
            self.error_message = other.error_message

        # Merge filter conditions intelligently
        if other.filter_conditions:
            if not self.filter_conditions:
                self.filter_conditions = other.filter_conditions
            else:
                # If both have filters, combine them with $and
                self.filter_conditions = {"$and": [self.filter_conditions, other.filter_conditions]}

        return self

    # Backward compatibility properties
    @property
    def mongo_filter(self) -> Dict[str, Any]:
        """Backward compatibility property for mongo_filter"""
        return self.filter_conditions

    @mongo_filter.setter
    def mongo_filter(self, value: Dict[str, Any]):
        """Backward compatibility setter for mongo_filter"""
        self.filter_conditions = value


class EnhancedWhereHandler(ContextUtilsMixin):
    """Enhanced WHERE clause handler using expression handlers"""

    def handle(self, ctx: PartiQLParser.WhereClauseSelectContext) -> Dict[str, Any]:
        """Handle WHERE clause with proper expression parsing"""
        if not hasattr(ctx, "exprSelect") or not ctx.exprSelect():
            _logger.debug("No expression found in WHERE clause")
            return {}

        expression_ctx = ctx.exprSelect()
        # Local import to avoid circular dependency between query_handler and handler
        from .handler import HandlerFactory

        handler = HandlerFactory.get_expression_handler(expression_ctx)

        if handler:
            _logger.debug(
                f"Using {type(handler).__name__} for WHERE clause",
                extra={"context_text": self.get_context_text(expression_ctx)[:100]},
            )
            result = handler.handle_expression(expression_ctx)
            if result.has_errors:
                _logger.warning(
                    "Expression parsing error, falling back to text search",
                    extra={"error": result.error_message},
                )
                # Fallback to text-based filter
                return {"$text": {"$search": self.get_context_text(expression_ctx)}}
            return result.filter_conditions
        else:
            # Fallback to simple text-based search
            _logger.debug(
                "No suitable expression handler found, using text search",
                extra={"context_text": self.get_context_text(expression_ctx)[:100]},
            )
            return {"$text": {"$search": self.get_context_text(expression_ctx)}}


class SelectHandler(BaseHandler, ContextUtilsMixin):
    """Handles SELECT statement parsing"""

    # Pattern to detect SQL aggregate functions: COUNT(*), SUM(field), AVG(field), etc.
    _AGGREGATE_PATTERN = re.compile(
        r"^(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(\*|\w+(?:\.\w+)*)\s*\)$",
        re.IGNORECASE,
    )

    def can_handle(self, ctx: Any) -> bool:
        """Check if this is a select context"""
        return hasattr(ctx, "projectionItems")

    def handle_visitor(self, ctx: PartiQLParser.SelectItemsContext, parse_result: "QueryParseResult") -> Any:
        projection = {}
        column_aliases = {}

        if hasattr(ctx, "projectionItems") and ctx.projectionItems():
            for item in ctx.projectionItems().projectionItem():
                field_name, alias = self._extract_field_and_alias(item)

                # Check if this is an aggregate function (COUNT, SUM, etc.)
                agg_match = self._AGGREGATE_PATTERN.match(field_name)
                if agg_match:
                    func_name = agg_match.group(1).upper()
                    func_arg = agg_match.group(2)
                    parse_result.aggregate_functions.append(
                        {
                            "function": func_name,
                            "argument": func_arg,
                            "alias": alias or field_name,
                        }
                    )
                    continue

                # Use MongoDB standard projection format: {field: 1} to include field
                projection[field_name] = 1
                # Store alias if present
                if alias:
                    column_aliases[field_name] = alias

        parse_result.projection = projection
        parse_result.column_aliases = column_aliases
        return projection

    def _extract_field_and_alias(self, item) -> Tuple[str, Optional[str]]:
        """Extract field name and alias from projection item context with nested field support"""
        if not hasattr(item, "children") or not item.children:
            return str(item), None

        # According to grammar: projectionItem : expr ( AS? symbolPrimitive )? ;
        # children[0] is always the expression
        # If there's an alias, children[1] might be AS and children[2] symbolPrimitive
        # OR children[1] might be just symbolPrimitive (without AS)

        field_name = item.children[0].getText()
        # Normalize bracket notation (jmspath) to Mongo dot notation
        field_name = self.normalize_field_path(field_name)

        alias = None

        if len(item.children) >= 2:
            # Check if we have an alias
            if len(item.children) == 3:
                # Pattern: expr AS symbolPrimitive
                if hasattr(item.children[1], "getText") and item.children[1].getText().upper() == "AS":
                    alias = item.children[2].getText()
            elif len(item.children) == 2:
                # Pattern: expr symbolPrimitive (without AS)
                alias = item.children[1].getText()

        return field_name, alias


class FromHandler(BaseHandler):
    """Handles FROM clause parsing with support for regular collections and aggregate() function calls"""

    def can_handle(self, ctx: Any) -> bool:
        """Check if this is a from context"""
        return hasattr(ctx, "tableReference")

    @staticmethod
    def _strip_collection_quotes(name: str) -> str:
        """Strip surrounding double quotes from collection name if present.

        Args:
            name: Collection name, potentially quoted

        Returns:
            Collection name with quotes removed
        """
        return re.sub(r'^"([^"]+)"$', r"\1", name)

    def _parse_function_call(self, ctx: Any) -> Optional[Dict[str, Any]]:
        """
        Detect and parse aggregate() function calls in FROM clause.

        Supports:
        - collection.aggregate('pipeline_json', 'options_json')
        - aggregate('pipeline_json', 'options_json')

        Returns dict with:
        - function_name: 'aggregate'
        - collection: collection name (or None if unqualified)
        - pipeline: JSON string for pipeline
        - options: JSON string for options
        """
        try:
            # Get the tableReference from FROM clause
            if not hasattr(ctx, "tableReference"):
                return None

            table_ref = ctx.tableReference()
            if not table_ref:
                return None

            # Get the text to analyze
            text = table_ref.getText() if hasattr(table_ref, "getText") else str(table_ref)

            # Pattern: [qualifier.]functionName(arg1, arg2)
            # We need to match: (optional_collection.)aggregate('...', '...')
            # Support collection names with double quotes for special characters like hyphens
            pattern = r"^(?:(\"[^\"]+\"|\w+)\.)?aggregate\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)$"
            match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)

            if not match:
                return None

            collection = match.group(1)  # Can be None for unqualified aggregate()
            # Strip quotes from collection name if present
            if collection:
                collection = self._strip_collection_quotes(collection)
            pipeline = match.group(2)
            options = match.group(3)

            _logger.debug(
                f"Detected aggregate call: collection={collection}, pipeline={pipeline[:50]}..., options={options}"
            )

            return {
                "function_name": "aggregate",
                "collection": collection,
                "pipeline": pipeline,
                "options": options,
            }
        except Exception as e:
            _logger.debug(f"Error parsing function call: {e}")
            return None

    def handle_visitor(self, ctx: PartiQLParser.FromClauseContext, parse_result: "QueryParseResult") -> Any:
        """Handle FROM clause - detect aggregate calls or regular collections"""
        if hasattr(ctx, "tableReference") and ctx.tableReference():
            # Try to detect aggregate function call
            func_info = self._parse_function_call(ctx)

            if func_info and func_info["function_name"] == "aggregate":
                # Mark as aggregate query
                if hasattr(parse_result, "is_aggregate_query"):
                    parse_result.is_aggregate_query = True
                if hasattr(parse_result, "aggregate_pipeline"):
                    parse_result.aggregate_pipeline = func_info["pipeline"]
                if hasattr(parse_result, "aggregate_options"):
                    parse_result.aggregate_options = func_info["options"]

                # Set collection name if qualified, otherwise it's collection-agnostic
                if func_info["collection"]:
                    parse_result.collection = func_info["collection"]

                _logger.info(f"Parsed aggregate call: collection={func_info['collection']}")
                return func_info

            # Regular collection reference
            table_text = ctx.tableReference().getText()
            # Strip surrounding quotes from collection name (e.g., "user.accounts" -> user.accounts)
            collection_name = self._strip_collection_quotes(table_text)
            parse_result.collection = collection_name
            _logger.debug(f"Parsed regular collection: {collection_name}")
            return collection_name

        return None


class WhereHandler(BaseHandler):
    """Handles WHERE clause parsing"""

    def __init__(self):
        self._expression_handler = EnhancedWhereHandler()

    def can_handle(self, ctx: Any) -> bool:
        """Check if this is a where context"""
        return hasattr(ctx, "exprSelect")

    def handle_visitor(self, ctx: PartiQLParser.WhereClauseSelectContext, parse_result: "QueryParseResult") -> Any:
        if hasattr(ctx, "exprSelect") and ctx.exprSelect():
            try:
                # Use enhanced expression handler for better parsing
                filter_conditions = self._expression_handler.handle(ctx)
                parse_result.filter_conditions = filter_conditions
                return filter_conditions
            except Exception as e:
                _logger.warning(f"Failed to parse WHERE expression, falling back to text search: {e}")
                # Fallback to simple text search
                filter_text = ctx.exprSelect().getText()
                fallback_filter = {"$text": {"$search": filter_text}}
                parse_result.filter_conditions = fallback_filter
                return fallback_filter
        return {}
