# -*- coding: utf-8 -*-
import ast
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .handler import BaseHandler

_logger = logging.getLogger(__name__)


@dataclass
class InsertParseResult:
    """Result container for INSERT statement visitor parsing."""

    collection: Optional[str] = None
    insert_columns: Optional[List[str]] = None
    insert_values: Optional[List[List[Any]]] = None
    insert_documents: Optional[List[Dict[str, Any]]] = None
    insert_type: Optional[str] = None  # e.g., "values" | "bag"
    parameter_style: Optional[str] = None  # e.g., "qmark"
    parameter_count: int = 0
    has_errors: bool = False
    error_message: Optional[str] = None

    @classmethod
    def for_visitor(cls) -> "InsertParseResult":
        """Factory for a fresh insert parse result."""
        return cls()


class InsertHandler(BaseHandler):
    """Visitor handler to convert INSERT parse trees into InsertParseResult."""

    def can_handle(self, ctx: Any) -> bool:
        return hasattr(ctx, "INSERT")

    def handle_visitor(self, ctx: Any, parse_result: InsertParseResult) -> InsertParseResult:
        try:
            collection = self._extract_collection(ctx)

            # Check if this is a VALUES clause INSERT (new syntax)
            if hasattr(ctx, "values") and ctx.values():
                _logger.debug("Processing INSERT with VALUES clause")
                parse_result.collection = collection
                parse_result.insert_type = "values"
                # Return parse_result - visitor will call handle_column_list and handle_values
                return parse_result

            # Otherwise, handle legacy value expression INSERT
            value_text = self._extract_value_text(ctx)
            documents = self._parse_value_expr(value_text)
            param_style, param_count = self._detect_parameter_style(documents)

            parse_result.collection = collection
            parse_result.insert_documents = documents
            parse_result.insert_type = "bag" if value_text.strip().startswith("<<") else "value"
            parse_result.parameter_style = param_style
            parse_result.parameter_count = param_count
            parse_result.has_errors = False
            parse_result.error_message = None
            return parse_result
        except Exception as exc:  # pragma: no cover - defensive logging
            _logger.error("Failed to handle INSERT", exc_info=True)
            parse_result.has_errors = True
            parse_result.error_message = str(exc)
            return parse_result

    def handle_column_list(self, ctx: Any, parse_result: InsertParseResult) -> Optional[List[str]]:
        """Extract column names from columnList context."""
        _logger.debug("InsertHandler processing column list")
        try:
            columns = []
            column_names = ctx.columnName()
            if column_names:
                if not isinstance(column_names, list):
                    column_names = [column_names]
                for col_name_ctx in column_names:
                    # columnName contains a symbolPrimitive
                    symbol = col_name_ctx.symbolPrimitive()
                    if symbol:
                        columns.append(symbol.getText())
            parse_result.insert_columns = columns
            _logger.debug(f"Extracted columns for INSERT: {columns}")
            return columns
        except Exception as e:
            _logger.warning(f"Error processing column list: {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)
        return None

    def handle_values(self, ctx: Any, parse_result: InsertParseResult) -> Optional[List[List[Any]]]:
        """Extract value rows from VALUES clause."""
        _logger.debug("InsertHandler processing VALUES clause")
        try:
            rows = []
            value_rows = ctx.valueRow()
            if value_rows:
                if not isinstance(value_rows, list):
                    value_rows = [value_rows]
                for value_row_ctx in value_rows:
                    row_values = self._extract_value_row(value_row_ctx)
                    rows.append(row_values)

            parse_result.insert_values = rows

            # Convert rows to documents
            columns = parse_result.insert_columns
            documents = self._convert_rows_to_documents(columns, rows)
            parse_result.insert_documents = documents

            # Detect parameter style
            param_style, param_count = self._detect_parameter_style(documents)
            parse_result.parameter_style = param_style
            parse_result.parameter_count = param_count
            parse_result.has_errors = False
            parse_result.error_message = None

            _logger.debug(f"Extracted {len(rows)} value rows for INSERT")
            return rows
        except Exception as e:
            _logger.warning(f"Error processing VALUES clause: {e}")
            parse_result.has_errors = True
            parse_result.error_message = str(e)
        return None

    def _extract_value_row(self, value_row_ctx: Any) -> List[Any]:
        """Extract values from a single valueRow."""
        row_values = []
        exprs = value_row_ctx.expr()
        if exprs:
            if not isinstance(exprs, list):
                exprs = [exprs]
            for expr_ctx in exprs:
                value = self._parse_expression_value(expr_ctx)
                row_values.append(value)
        return row_values

    def _parse_expression_value(self, expr_ctx: Any) -> Any:
        """Parse a single expression value from the parse tree."""
        if not expr_ctx:
            return None

        text = expr_ctx.getText()

        # Handle NULL
        if text.upper() == "NULL":
            return None

        # Handle boolean literals
        if text.upper() == "TRUE":
            return True
        if text.upper() == "FALSE":
            return False

        # Handle string literals (quoted)
        if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
            return text[1:-1]

        # Handle numeric literals
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            pass

        # Handle parameters (? or :name)
        if text == "?":
            return "?"
        if text.startswith(":"):
            return text

        # For complex expressions, return as-is
        return text

    def _convert_rows_to_documents(self, columns: Optional[List[str]], rows: List[List[Any]]) -> List[Dict[str, Any]]:
        """Convert rows to MongoDB documents."""
        documents = []

        for row in rows:
            doc = {}

            if columns:
                # Use explicit column names
                if len(row) != len(columns):
                    raise ValueError(f"Column count ({len(columns)}) does not match value count ({len(row)})")

                for col, val in zip(columns, row):
                    doc[col] = val
            else:
                # Generate automatic column names (col0, col1, ...)
                for idx, val in enumerate(row):
                    doc[f"col{idx}"] = val

            documents.append(doc)

        return documents

    def _extract_collection(self, ctx: Any) -> str:
        if hasattr(ctx, "symbolPrimitive") and ctx.symbolPrimitive():
            return ctx.symbolPrimitive().getText()
        if hasattr(ctx, "pathSimple") and ctx.pathSimple():  # legacy form
            return ctx.pathSimple().getText()
        raise ValueError("INSERT statement missing collection name")

    def _extract_value_text(self, ctx: Any) -> str:
        if hasattr(ctx, "value") and ctx.value:
            return ctx.value.getText()
        if hasattr(ctx, "value") and callable(ctx.value):  # legacy form pathSimple VALUE expr
            value_ctx = ctx.value()
            if value_ctx:
                return value_ctx.getText()
        raise ValueError("INSERT statement missing value expression")

    def _parse_value_expr(self, text: str) -> List[Dict[str, Any]]:
        cleaned = text.strip()
        cleaned = self._normalize_literals(cleaned)

        if cleaned.startswith("<<") and cleaned.endswith(">>"):
            literal_text = cleaned.replace("<<", "[").replace(">>", "]")
            return self._parse_literal_list(literal_text)

        if cleaned.startswith("{") and cleaned.endswith("}"):
            doc = self._parse_literal_dict(cleaned)
            return [doc]

        raise ValueError("Unsupported INSERT value expression")

    def _parse_literal_list(self, literal_text: str) -> List[Dict[str, Any]]:
        try:
            value = ast.literal_eval(literal_text)
        except Exception as exc:
            raise ValueError(f"Failed to parse INSERT bag literal: {exc}") from exc
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError("INSERT bag must contain objects")
        return value

    def _parse_literal_dict(self, literal_text: str) -> Dict[str, Any]:
        try:
            value = ast.literal_eval(literal_text)
        except Exception as exc:
            raise ValueError(f"Failed to parse INSERT object literal: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("INSERT value expression must be an object")
        return value

    def _normalize_literals(self, text: str) -> str:
        # Replace PartiQL-style booleans/null with Python equivalents for literal_eval
        replacements = {
            r"\bnull\b": "None",
            r"\bNULL\b": "None",
            r"\btrue\b": "True",
            r"\bTRUE\b": "True",
            r"\bfalse\b": "False",
            r"\bFALSE\b": "False",
        }
        normalized = text
        for pattern, replacement in replacements.items():
            normalized = re.sub(pattern, replacement, normalized)
        return normalized

    def _detect_parameter_style(self, documents: List[Dict[str, Any]]) -> Tuple[Optional[str], int]:
        style = None
        count = 0

        def consider(value: Any):
            nonlocal style, count
            if value == "?":
                new_style = "qmark"
            elif isinstance(value, str) and value.startswith(":"):
                new_style = "named"
            else:
                return

            if style and style != new_style:
                raise ValueError("Mixed parameter styles are not supported")
            style = new_style
            count += 1

        for doc in documents:
            for val in doc.values():
                consider(val)

        return style, count
