# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .handler import BaseHandler
from .partiql.PartiQLParser import PartiQLParser

_logger = logging.getLogger(__name__)


@dataclass
class UpdateParseResult:
    """Result of parsing an UPDATE statement.

    Stores the extracted information needed to build an UpdateExecutionPlan.
    """

    collection: Optional[str] = None
    update_fields: Dict[str, Any] = field(default_factory=dict)  # Field -> new value mapping
    filter_conditions: Dict[str, Any] = field(default_factory=dict)
    has_errors: bool = False
    error_message: Optional[str] = None

    @staticmethod
    def for_visitor() -> "UpdateParseResult":
        """Factory method to create a fresh UpdateParseResult for visitor pattern."""
        return UpdateParseResult()

    def validate(self) -> bool:
        """Validate that required fields are populated."""
        if not self.collection:
            self.error_message = "Collection name is required"
            self.has_errors = True
            return False
        if not self.update_fields:
            self.error_message = "At least one field to update is required"
            self.has_errors = True
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation for debugging."""
        return {
            "collection": self.collection,
            "update_fields": self.update_fields,
            "filter_conditions": self.filter_conditions,
            "has_errors": self.has_errors,
            "error_message": self.error_message,
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"UpdateParseResult(collection={self.collection}, "
            f"update_fields={self.update_fields}, "
            f"filter_conditions={self.filter_conditions}, "
            f"has_errors={self.has_errors})"
        )


class UpdateHandler(BaseHandler):
    """Handler for UPDATE statement visitor parsing."""

    def can_handle(self, ctx: Any) -> bool:
        """Check if this handler can process the given context."""
        return hasattr(ctx, "UPDATE") or isinstance(ctx, PartiQLParser.UpdateClauseContext)

    def handle_visitor(self, ctx: Any, parse_result: UpdateParseResult) -> UpdateParseResult:
        """Handle UPDATE clause during visitor traversal."""
        _logger.debug("UpdateHandler processing UPDATE clause")
        try:
            # Extract collection name from UPDATE clause
            # updateClause: UPDATE tableBaseReference
            if hasattr(ctx, "tableBaseReference") and ctx.tableBaseReference():
                collection_name = self._extract_collection_from_table_ref(ctx.tableBaseReference())
                parse_result.collection = collection_name
                _logger.debug(f"Extracted collection for UPDATE: {collection_name}")
        except Exception as e:
            _logger.warning(f"Error processing UPDATE clause: {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)

        return parse_result

    def _extract_collection_from_table_ref(self, ctx: Any) -> Optional[str]:
        """Extract collection name from tableBaseReference context."""
        try:
            # tableBaseReference can have multiple forms:
            # - source=exprSelect symbolPrimitive
            # - source=exprSelect asIdent? atIdent? byIdent?
            # - source=exprGraphMatchOne asIdent? atIdent? byIdent?

            # For simple UPDATE statements, we expect exprSelect to be a simple identifier
            if hasattr(ctx, "source") and ctx.source:
                source_text = ctx.source.getText()
                _logger.debug(f"Extracted collection from tableBaseReference: {source_text}")
                return source_text

            # Fallback: try to get text directly
            return ctx.getText()
        except Exception as e:
            _logger.warning(f"Error extracting collection from tableBaseReference: {e}")
            return None

    def handle_set_command(self, ctx: Any, parse_result: UpdateParseResult) -> UpdateParseResult:
        """Handle SET command during visitor traversal.

        setCommand: SET setAssignment ( COMMA setAssignment )*
        setAssignment: pathSimple EQ expr
        """
        _logger.debug("UpdateHandler processing SET command")
        try:
            if hasattr(ctx, "setAssignment") and ctx.setAssignment():
                for assignment_ctx in ctx.setAssignment():
                    field_name, field_value = self._extract_set_assignment(assignment_ctx)
                    if field_name:
                        parse_result.update_fields[field_name] = field_value
                        _logger.debug(f"Extracted SET assignment: {field_name} = {field_value}")
        except Exception as e:
            _logger.warning(f"Error processing SET command: {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)

        return parse_result

    def _extract_set_assignment(self, ctx: Any) -> tuple[Optional[str], Any]:
        """Extract field name and value from setAssignment.

        setAssignment: pathSimple EQ expr
        """
        try:
            field_name = None
            field_value = None

            # Extract field name from pathSimple
            if hasattr(ctx, "pathSimple") and ctx.pathSimple():
                field_name = ctx.pathSimple().getText()

            # Extract value from expr
            if hasattr(ctx, "expr") and ctx.expr():
                expr_text = ctx.expr().getText()
                # Parse the expression to get the actual value
                field_value = self._parse_value(expr_text)

            return field_name, field_value
        except Exception as e:
            _logger.warning(f"Error extracting set assignment: {e}")
            return None, None

    def _parse_value(self, text: str) -> Any:
        """Parse expression text to extract the actual value."""
        # Remove surrounding quotes if present
        text = text.strip()

        if text.startswith("'") and text.endswith("'"):
            return text[1:-1]
        elif text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        elif text.lower() == "null":
            return None
        elif text.lower() == "true":
            return True
        elif text.lower() == "false":
            return False
        elif text.startswith("?") or text.startswith(":"):
            # Parameter placeholder
            return text
        else:
            # Try to parse as number
            try:
                if "." in text:
                    return float(text)
                else:
                    return int(text)
            except ValueError:
                # Return as string if not a number
                return text

    def handle_where_clause(self, ctx: Any, parse_result: UpdateParseResult) -> Dict[str, Any]:
        """Handle WHERE clause for UPDATE statements."""
        _logger.debug("UpdateHandler processing WHERE clause")
        try:
            # Get the expression context
            expression_ctx = None
            if hasattr(ctx, "arg") and ctx.arg:
                expression_ctx = ctx.arg
            elif hasattr(ctx, "expr"):
                expression_ctx = ctx.expr()

            if expression_ctx:
                from .handler import HandlerFactory

                handler = HandlerFactory.get_expression_handler(expression_ctx)

                if handler:
                    result = handler.handle_expression(expression_ctx)
                    if not result.has_errors:
                        parse_result.filter_conditions = result.filter_conditions
                        _logger.debug(f"Extracted filter conditions for UPDATE: {result.filter_conditions}")
                        return result.filter_conditions

            # No WHERE clause means update all documents
            _logger.debug("No WHERE clause for UPDATE")
            return {}
        except Exception as e:
            _logger.warning(f"Error processing WHERE clause: {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)
            return {}
