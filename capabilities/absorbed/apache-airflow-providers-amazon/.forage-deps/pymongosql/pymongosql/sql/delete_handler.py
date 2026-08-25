# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .handler import BaseHandler
from .partiql.PartiQLParser import PartiQLParser

_logger = logging.getLogger(__name__)


@dataclass
class DeleteParseResult:
    """Result of parsing a DELETE statement.

    Stores the extracted information needed to build a DeleteExecutionPlan.
    """

    collection: Optional[str] = None
    filter_conditions: Dict[str, Any] = field(default_factory=dict)
    has_errors: bool = False
    error_message: Optional[str] = None

    @staticmethod
    def for_visitor() -> "DeleteParseResult":
        """Factory method to create a fresh DeleteParseResult for visitor pattern."""
        return DeleteParseResult()

    def validate(self) -> bool:
        """Validate that required fields are populated."""
        if not self.collection:
            self.error_message = "Collection name is required"
            self.has_errors = True
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation for debugging."""
        return {
            "collection": self.collection,
            "filter_conditions": self.filter_conditions,
            "has_errors": self.has_errors,
            "error_message": self.error_message,
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DeleteParseResult(collection={self.collection}, "
            f"filter_conditions={self.filter_conditions}, "
            f"has_errors={self.has_errors})"
        )


class DeleteHandler(BaseHandler):
    """Handler for DELETE statement visitor parsing."""

    def can_handle(self, ctx: Any) -> bool:
        """Check if this handler can process the given context."""
        return hasattr(ctx, "DELETE") or isinstance(ctx, PartiQLParser.DeleteCommandContext)

    def handle_visitor(self, ctx: Any, parse_result: DeleteParseResult) -> DeleteParseResult:
        """Handle DELETE statement parsing - entry point from visitDeleteCommand."""
        try:
            _logger.debug("DeleteHandler processing DELETE statement")
            # Reset parse result for new statement
            parse_result.collection = None
            parse_result.filter_conditions = {}
            parse_result.has_errors = False
            parse_result.error_message = None
            return parse_result
        except Exception as exc:
            _logger.error("Failed to handle DELETE", exc_info=True)
            parse_result.has_errors = True
            parse_result.error_message = str(exc)
            return parse_result

    def handle_from_clause_explicit(
        self, ctx: PartiQLParser.FromClauseSimpleExplicitContext, parse_result: DeleteParseResult
    ) -> Optional[str]:
        """Extract collection name from FROM clause (explicit form)."""
        _logger.debug("DeleteHandler processing FROM clause (simple, explicit)")
        try:
            if ctx.pathSimple():
                collection_name = ctx.pathSimple().getText()
                parse_result.collection = collection_name
                _logger.debug(f"Extracted collection for DELETE (explicit): {collection_name}")
                return collection_name
        except Exception as e:
            _logger.warning(f"Error processing FROM clause (explicit): {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)
        return None

    def handle_from_clause_implicit(
        self, ctx: PartiQLParser.FromClauseSimpleImplicitContext, parse_result: DeleteParseResult
    ) -> Optional[str]:
        """Extract collection name from FROM clause (implicit form)."""
        _logger.debug("DeleteHandler processing FROM clause (simple, implicit)")
        try:
            if ctx.pathSimple():
                collection_name = ctx.pathSimple().getText()
                parse_result.collection = collection_name
                _logger.debug(f"Extracted collection for DELETE (implicit): {collection_name}")
                return collection_name
        except Exception as e:
            _logger.warning(f"Error processing FROM clause (implicit): {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)
        return None

    def handle_where_clause(
        self, ctx: PartiQLParser.WhereClauseContext, parse_result: DeleteParseResult
    ) -> Dict[str, Any]:
        """Handle WHERE clause for DELETE statements."""
        _logger.debug("DeleteHandler processing WHERE clause")
        try:
            # Get the expression context - it could be ctx.arg or ctx.expr()
            expression_ctx = None
            if hasattr(ctx, "arg") and ctx.arg:
                expression_ctx = ctx.arg
            elif hasattr(ctx, "expr"):
                expression_ctx = ctx.expr()

            if expression_ctx:
                # Debug: log the raw context text
                raw_text = expression_ctx.getText() if hasattr(expression_ctx, "getText") else str(expression_ctx)
                _logger.debug(f"[WHERE_CLAUSE_DEBUG] Raw expression text: {raw_text}")
                _logger.debug(f"[WHERE_CLAUSE_DEBUG] Expression context type: {type(expression_ctx).__name__}")

                from .handler import HandlerFactory

                handler = HandlerFactory.get_expression_handler(expression_ctx)

                if handler:
                    result = handler.handle_expression(expression_ctx)
                    if not result.has_errors:
                        parse_result.filter_conditions = result.filter_conditions
                        _logger.debug(f"Extracted filter conditions for DELETE: {result.filter_conditions}")
                        return result.filter_conditions
            # If no handler or error, leave filter_conditions empty (delete all)
            _logger.debug("Extracted filter conditions for DELETE: {}")
            return {}
        except Exception as e:
            _logger.warning(f"Error processing WHERE clause: {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)
            return {}
