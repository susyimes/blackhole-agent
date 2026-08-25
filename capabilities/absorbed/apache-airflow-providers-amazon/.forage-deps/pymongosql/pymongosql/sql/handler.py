# -*- coding: utf-8 -*-
import logging
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .query_handler import QueryParseResult

_logger = logging.getLogger(__name__)


# Constants
COMPARISON_OPERATORS = [">=", "<=", "!=", "<>", "=", "<", ">"]
LOGICAL_OPERATORS = ["AND", "OR", "NOT"]
OPERATOR_MAP = {
    "=": "$eq",
    "!=": "$ne",
    "<>": "$ne",
    "<": "$lt",
    "<=": "$lte",
    ">": "$gt",
    ">=": "$gte",
    "LIKE": "$regex",
    "IN": "$in",
    "NOT IN": "$nin",
}

# Pattern to count all comparison operations in ANTLR getText() output (no spaces).
# Includes standard operators and SQL keywords (IN, LIKE, BETWEEN, IS [NOT] NULL).
_COMPARISON_COUNT_PATTERN = re.compile(
    r">=|<=|!=|<>|=|<|>|IN\(|LIKE['\"]|BETWEEN|ISNOTNULL|ISNULL",
    re.IGNORECASE,
)


class ContextUtilsMixin:
    """Mixin providing common context utility methods"""

    @staticmethod
    def get_context_text(ctx: Any) -> str:
        """Safely extract text from context"""
        return ctx.getText() if hasattr(ctx, "getText") else str(ctx)

    @staticmethod
    def get_context_type_name(ctx: Any) -> str:
        """Get context type name safely"""
        return type(ctx).__name__

    @staticmethod
    def has_children(ctx: Any) -> bool:
        """Check if context has children"""
        return hasattr(ctx, "children") and bool(ctx.children)

    @staticmethod
    def normalize_field_path(path: str) -> str:
        """Normalize jmspath/bracket notation to MongoDB dot notation.

        Examples:
            items[0] -> items.0
            items[1].name -> items.1.name
            arr['key'] or arr["key"] -> arr.key
        """
        if not isinstance(path, str):
            return path

        s = path.strip()
        # Convert quoted bracket identifiers ["name"] or ['name'] -> .name
        s = re.sub(r"\[\s*['\"]([^'\"]+)['\"]\s*\]", r".\1", s)
        # Convert numeric bracket indexes [0] -> .0
        s = re.sub(r"\[\s*(\d+)\s*\]", r".\1", s)
        # Unquote quoted identifiers in dot notation (e.g., "date" -> date)
        s = re.sub(r'"([^"]+)"', r"\1", s)
        # Collapse multiple dots and strip leading/trailing dots
        s = re.sub(r"\.{2,}", ".", s).strip(".")
        return s


class LoggingMixin:
    """Mixin providing structured logging functionality"""

    def _log_operation_start(self, operation: str, ctx: Any, operation_id: int):
        """Log operation start with context"""
        _logger.debug(
            f"Starting {operation}",
            extra={
                "context_type": ContextUtilsMixin.get_context_type_name(ctx),
                "context_text": ContextUtilsMixin.get_context_text(ctx)[:100],
                "operation": operation,
                "operation_id": operation_id,
            },
        )

    def _log_operation_success(self, operation: str, operation_id: int, **extra_data):
        """Log successful operation completion"""
        log_data = {
            "operation": operation,
            "operation_id": operation_id,
        }
        log_data.update(extra_data)
        _logger.debug(f"{operation.title()} completed successfully", extra=log_data)

    def _log_operation_error(
        self,
        operation: str,
        ctx: Any,
        operation_id: int,
        error: Exception,
    ):
        """Log operation error with context"""
        _logger.error(
            f"Failed to handle {operation}",
            extra={
                "error": str(error),
                "error_type": type(error).__name__,
                "context_text": ContextUtilsMixin.get_context_text(ctx),
                "context_type": ContextUtilsMixin.get_context_type_name(ctx),
                "operation": operation,
                "operation_id": operation_id,
            },
            exc_info=True,
        )


class OperatorExtractorMixin:
    """Mixin for extracting operators from expressions"""

    def _find_operator_in_text(self, text: str, operators: List[str]) -> Optional[str]:
        """Find first matching operator in text (ordered by length)"""
        for op in operators:
            if op in text:
                return op
        return None

    def _split_by_operator(self, text: str, operator: str) -> List[str]:
        """Split text by operator, returning non-empty parts"""
        parts = text.split(operator, 1)  # Split only on first occurrence
        return [part.strip() for part in parts if part.strip()]

    def _parse_value(self, value_text: str) -> Any:
        """Parse string value to appropriate Python type"""
        value_text = value_text.strip()

        # Remove parentheses from values
        value_text = value_text.strip("()")

        # Remove quotes from string values
        if (value_text.startswith("'") and value_text.endswith("'")) or (
            value_text.startswith('"') and value_text.endswith('"')
        ):
            return value_text[1:-1]

        # Try to parse as number
        try:
            return int(value_text) if "." not in value_text else float(value_text)
        except ValueError:
            pass

        # Handle boolean values
        if value_text.lower() in ["true", "false"]:
            return value_text.lower() == "true"

        # Handle NULL
        if value_text.upper() == "NULL":
            return None

        return value_text


class BaseHandler(ABC):
    """Unified base class for all handlers (expression and visitor)"""

    @abstractmethod
    def can_handle(self, ctx: Any) -> bool:
        """Check if this handler can process the given context"""
        pass

    def handle(self, ctx: Any, parse_result: Optional[Any] = None) -> Any:
        """Handle the context and return appropriate result"""
        # Default implementation for expression handlers
        if parse_result is None:
            return self.handle_expression(ctx)
        else:
            return self.handle_visitor(ctx, parse_result)

    def handle_expression(self, ctx: Any) -> Any:
        """Handle expression parsing (to be overridden by expression handlers)"""
        raise NotImplementedError("Expression handlers must implement handle_expression")

    def handle_visitor(self, ctx: Any, parse_result: Optional[Any] = None) -> Any:
        """Handle visitor operations (to be overridden by visitor handlers)"""
        raise NotImplementedError("Visitor handlers must implement handle_visitor")


class ComparisonExpressionHandler(BaseHandler, ContextUtilsMixin, LoggingMixin, OperatorExtractorMixin):
    """Handles comparison expressions like field = value, field > value, etc."""

    def can_handle(self, ctx: Any) -> bool:
        """Check if context represents a comparison expression"""
        try:
            text = self.get_context_text(ctx)
            text_upper = text.upper()

            # Count comparison operator *occurrences* (not distinct types) so that
            # "B=trueANDA=1" is correctly seen as having 2 comparisons even though
            # both use the same "=" operator.  Also counts IN(, LIKE, BETWEEN, etc.
            comparison_count = len(_COMPARISON_COUNT_PATTERN.findall(text))

            # If there are multiple comparisons and logical operators, it's a logical expression
            has_logical_ops = any(op in text_upper for op in LOGICAL_OPERATORS)
            if has_logical_ops and comparison_count > 1:
                return False  # This should be handled by LogicalExpressionHandler
        except Exception as e:
            _logger.debug(f"ComparisonHandler: Error checking logical context: {e}")

        # Check various PartiQL expression types that represent comparisons
        return (
            hasattr(ctx, "comparisonOperator") or self._is_comparison_context(ctx) or self._has_comparison_pattern(ctx)
        )

    def handle_expression(self, ctx: Any) -> "QueryParseResult":
        """Convert comparison expression to MongoDB filter"""
        from .query_handler import QueryParseResult

        operation_id = id(ctx)
        self._log_operation_start("comparison_parsing", ctx, operation_id)

        try:
            field_name = self._extract_field_name(ctx)
            operator = self._extract_operator(ctx)
            value = self._extract_value(ctx)

            mongo_filter = self._build_mongo_filter(field_name, operator, value)

            self._log_operation_success(
                "comparison_parsing",
                operation_id,
                field_name=field_name,
                operator=operator,
            )

            return QueryParseResult(filter_conditions=mongo_filter)

        except Exception as e:
            self._log_operation_error("comparison_parsing", ctx, operation_id, e)
            return QueryParseResult(has_errors=True, error_message=str(e))

    def _build_mongo_filter(self, field_name: str, operator: str, value: Any) -> Dict[str, Any]:
        """Build MongoDB filter from field, operator and value"""
        if operator == "=":
            return {field_name: value}

        # Handle special operators
        if operator == "IN":
            return {field_name: {"$in": value if isinstance(value, list) else [value]}}
        elif operator == "LIKE":
            # Convert SQL LIKE pattern to regex
            if isinstance(value, str):
                # Replace % with .* and _ with . for regex
                regex_pattern = value.replace("%", ".*").replace("_", ".")
                # Add anchors based on pattern
                if not regex_pattern.startswith(".*"):
                    regex_pattern = "^" + regex_pattern
                if not regex_pattern.endswith(".*"):
                    regex_pattern = regex_pattern + "$"
                return {field_name: {"$regex": regex_pattern}}
            return {field_name: value}
        elif operator == "BETWEEN":
            if isinstance(value, tuple) and len(value) == 2:
                start_val, end_val = value
                return {"$and": [{field_name: {"$gte": start_val}}, {field_name: {"$lte": end_val}}]}
            return {field_name: value}
        elif operator == "IS NULL":
            return {field_name: {"$eq": None}}
        elif operator == "IS NOT NULL":
            return {field_name: {"$ne": None}}

        mongo_op = OPERATOR_MAP.get(operator.upper())
        if mongo_op == "$regex" and isinstance(value, str):
            # Convert SQL LIKE pattern to regex
            regex_pattern = value.replace("%", ".*").replace("_", ".")
            return {field_name: {"$regex": regex_pattern, "$options": "i"}}
        elif mongo_op:
            return {field_name: {mongo_op: value}}
        else:
            # Fallback to equality
            _logger.warning(f"Unknown operator '{operator}', falling back to equality")
            return {field_name: value}

    def _is_comparison_context(self, ctx: Any) -> bool:
        """Check if context is a comparison based on structure"""
        context_name = self.get_context_type_name(ctx).lower()
        structure_indicators = ["comparison", "predicate", "condition"]

        return (
            any(indicator in context_name for indicator in structure_indicators)
            or (hasattr(ctx, "left") and hasattr(ctx, "right"))
            or self._contains_comparison_operators(ctx)
        )

    def _has_comparison_pattern(self, ctx: Any) -> bool:
        """Check if the expression text contains comparison patterns"""
        try:
            text = self.get_context_text(ctx).upper()
            # Extended pattern matching for SQL constructs
            patterns = COMPARISON_OPERATORS + ["LIKE", "IN", "BETWEEN", "ISNULL", "ISNOTNULL"]
            return any(op in text for op in patterns)
        except Exception as e:
            _logger.debug(f"ComparisonHandler: Error checking comparison pattern: {e}")
            return False

    def _contains_comparison_operators(self, ctx: Any) -> bool:
        """Check if context contains comparison operators"""
        if not self.has_children(ctx):
            return False

        try:
            for child in ctx.children:
                child_text = self.get_context_text(child)
                if child_text in COMPARISON_OPERATORS:
                    return True
            return False
        except Exception:
            return False

    def _extract_field_name(self, ctx: Any) -> str:
        """Extract field name from comparison expression"""
        try:
            text = self.get_context_text(ctx)
            text_upper = text.upper()

            # Handle SQL constructs with keywords
            sql_keywords = ["IN(", "LIKE", "BETWEEN", "ISNULL", "ISNOTNULL"]
            for keyword in sql_keywords:
                if keyword in text_upper:
                    idx = text_upper.index(keyword)
                    candidate = text[:idx].strip()
                    return self.normalize_field_path(candidate)

            # Try operator-based splitting
            operator = self._find_operator_in_text(text, COMPARISON_OPERATORS)
            if operator:
                parts = self._split_by_operator(text, operator)
                if parts:
                    candidate = parts[0].strip("'\"()")
                    return self.normalize_field_path(candidate)

            # Fallback to children parsing
            if self.has_children(ctx):
                for child in ctx.children:
                    child_text = self.get_context_text(child)
                    if child_text not in COMPARISON_OPERATORS and not child_text.startswith(("'", '"')):
                        return self.normalize_field_path(child_text)

            return "unknown_field"
        except Exception as e:
            _logger.debug(f"Failed to extract field name: {e}")
            return "unknown_field"

    def _extract_operator(self, ctx: Any) -> str:
        """Extract comparison operator"""
        try:
            text = self.get_context_text(ctx)
            text_upper = text.upper()

            # Check SQL constructs first (order matters for ISNOTNULL vs ISNULL)
            sql_constructs = {
                "ISNOTNULL": "IS NOT NULL",
                "ISNULL": "IS NULL",
                "IN(": "IN",
                "LIKE": "LIKE",
                "BETWEEN": "BETWEEN",
            }

            for construct, operator in sql_constructs.items():
                if construct in text_upper:
                    return operator

            # Look for comparison operators
            operator = self._find_operator_in_text(text, COMPARISON_OPERATORS)
            if operator:
                return operator

            # Check children for operator nodes
            if self.has_children(ctx):
                for child in ctx.children:
                    child_text = self.get_context_text(child)
                    if child_text in COMPARISON_OPERATORS:
                        return child_text

            return "="  # Default
        except Exception as e:
            _logger.debug(f"Failed to extract operator: {e}")
            return "="

    def _extract_value(self, ctx: Any) -> Any:
        """Extract value from comparison expression"""
        try:
            text = self.get_context_text(ctx)
            text_upper = text.upper()

            # Handle SQL constructs with specific parsing needs
            if "IN(" in text_upper:
                return self._extract_in_values(text)
            elif "LIKE" in text_upper:
                return self._extract_like_pattern(text)
            elif "BETWEEN" in text_upper:
                return self._extract_between_range(text)
            elif "ISNULL" in text_upper or "ISNOTNULL" in text_upper:
                return None

            # Standard operator-based extraction
            operator = self._find_operator_in_text(text, COMPARISON_OPERATORS)
            if operator:
                parts = self._split_by_operator(text, operator)
                if len(parts) >= 2:
                    value_text = parts[1].strip()
                    # Check if value is a function call
                    return self._extract_value_or_function(value_text)

            return None
        except Exception as e:
            _logger.debug(f"Failed to extract value: {e}")
            return None

    def _extract_value_or_function(self, value_text: str) -> Any:
        """
        Extract value, which could be a literal or a value function call.

        Detects and executes value functions like str_to_datetime(...), str_to_timestamp(...).

        Args:
            value_text: Text representing the value, possibly a function call

        Returns:
            Processed value (result of function execution if function, otherwise parsed literal)
        """
        value_text = value_text.strip()

        # Check if this looks like a function call: func_name(...)
        if "(" in value_text and value_text.endswith(")"):
            # Extract function name and arguments
            paren_pos = value_text.find("(")
            func_name = value_text[:paren_pos].strip()

            # Check if it's a valid identifier (function name)
            if func_name.isidentifier():
                try:
                    from .value_function_registry import get_default_registry

                    registry = get_default_registry()
                    if registry.has_function(func_name):
                        # It's a registered value function - execute it
                        args_text = value_text[paren_pos + 1 : -1]
                        args = self._parse_function_arguments(args_text)
                        result = registry.execute(func_name, args)
                        _logger.debug(f"Executed value function: {func_name}({args}) -> {result}")
                        return result
                except Exception as e:
                    _logger.warning(f"Failed to execute value function '{func_name}': {e}")
                    # Fall through to treat as regular value

        # Not a function call or function execution failed - treat as regular value
        return self._parse_value(value_text)

    def _parse_function_arguments(self, args_text: str) -> list:
        """
        Parse function arguments from comma-separated string.

        Handles string literals with quotes and nested structures.

        Args:
            args_text: Text of function arguments (e.g., "'2024-01-01', '%m/%d/%Y'")

        Returns:
            List of parsed argument values
        """
        if not args_text.strip():
            return []

        args = []
        current_arg = ""
        in_quotes = False
        quote_char = None

        for char in args_text:
            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
                current_arg += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current_arg += char
            elif char == "," and not in_quotes:
                # End of argument
                arg = current_arg.strip()
                if arg:
                    args.append(self._parse_value(arg))
                current_arg = ""
            else:
                current_arg += char

        # Don't forget the last argument
        if current_arg.strip():
            args.append(self._parse_value(current_arg.strip()))

        return args

    def _extract_in_values(self, text: str) -> List[Any]:
        """Extract values from IN clause"""
        # Handle both 'IN(' and 'IN (' patterns
        in_pos = text.upper().find(" IN ")
        if in_pos == -1:
            in_pos = text.upper().find("IN(")
            start = in_pos + 3 if in_pos != -1 else -1
        else:
            start = text.find("(", in_pos) + 1

        end = text.rfind(")")
        if end > start >= 0:
            values_text = text[start:end]
            values = []
            for val in values_text.split(","):
                cleaned_val = val.strip().strip("'\"")
                if cleaned_val:  # Skip empty values
                    values.append(self._parse_value(f"'{cleaned_val}'"))
            return values
        return []

    def _extract_like_pattern(self, text: str) -> str:
        """Extract pattern from LIKE clause"""
        idx = text.upper().find("LIKE")
        if idx == -1:
            return ""
        return text[idx + 4 :].strip().strip("'\"")

    def _extract_between_range(self, text: str) -> Optional[Tuple[Any, Any]]:
        """Extract range values from BETWEEN clause"""
        text_upper = text.upper()
        between_idx = text_upper.find("BETWEEN")
        if between_idx == -1:
            return None
        after = text[between_idx + 7 :]
        after_upper = after.upper()
        and_idx = after_upper.find("AND")
        if and_idx != -1:
            low = after[:and_idx].strip()
            high = after[and_idx + 3 :].strip()
            return (self._parse_value(low), self._parse_value(high))
        return None


class LogicalExpressionHandler(BaseHandler, ContextUtilsMixin, LoggingMixin, OperatorExtractorMixin):
    """Handles logical expressions like AND, OR, NOT"""

    def can_handle(self, ctx: Any) -> bool:
        """Check if context represents a logical expression"""
        return hasattr(ctx, "logicalOperator") or self._is_logical_context(ctx) or self._has_logical_operators(ctx)

    def _find_operator_positions(self, text: str, operator: str) -> List[int]:
        """Find all valid positions of an operator in text, respecting quotes and parentheses"""
        positions = []
        i = 0
        while i < len(text):
            if text[i : i + len(operator)].upper() == operator.upper():
                # Check word boundary - don't split inside words
                if (
                    i > 0
                    and text[i - 1].isalpha()
                    and i + len(operator) < len(text)
                    and text[i + len(operator)].isalpha()
                ):
                    # ANTLR getText() concatenates tokens without spaces, so
                    # "B=true AND A=1" becomes "B=trueANDA=1".  We must still
                    # recognise AND/OR here when the preceding text ends with a
                    # SQL literal keyword (true/false/null) that is itself
                    # preceded by a comparison operator (=, <, >, !, etc.).
                    # This avoids false positives like "category" containing "OR".
                    before_upper = text[:i].upper()
                    is_value_boundary = False
                    for keyword in ("TRUE", "FALSE", "NULL"):
                        if before_upper.endswith(keyword):
                            prefix = text[: i - len(keyword)]
                            if prefix and prefix[-1] in ("=", "<", ">", "!"):
                                is_value_boundary = True
                                break
                    if not is_value_boundary:
                        i += len(operator)
                        continue

                # Check parentheses and quote depth
                if self._is_at_valid_split_position(text, i):
                    positions.append(i)
                i += len(operator)
            else:
                i += 1
        return positions

    def _is_at_valid_split_position(self, text: str, position: int) -> bool:
        """Check if position is valid for splitting (not inside quotes or parentheses)"""
        paren_depth = 0
        quote_depth = 0
        for j in range(position):
            if text[j] == "'" and (j == 0 or text[j - 1] != "\\"):
                quote_depth = 1 - quote_depth
            elif quote_depth == 0:
                if text[j] == "(":
                    paren_depth += 1
                elif text[j] == ")":
                    paren_depth -= 1
        return paren_depth == 0 and quote_depth == 0

    def _has_logical_operators(self, ctx: Any) -> bool:
        """Check if the expression text contains logical operators"""
        try:
            text = self.get_context_text(ctx).upper()

            # Count comparison operator occurrences, not just distinct operator types
            # so that "a = 1 OR b = 2" counts as 2 comparisons and is treated
            # as a logical expression instead of a single comparison.
            comparison_count = len(_COMPARISON_COUNT_PATTERN.findall(text))
            has_logical_ops = any(op in text for op in ["AND", "OR"])
            return has_logical_ops and comparison_count >= 2
        except Exception:
            return False

    def _is_logical_context(self, ctx: Any) -> bool:
        """Check if context is a logical expression based on structure"""
        try:
            context_name = self.get_context_type_name(ctx).lower()
            return any(
                indicator in context_name for indicator in ["logical", "and", "or"]
            ) or self._has_logical_operators(ctx)
        except Exception:
            return False

    def handle_expression(self, ctx: Any) -> "QueryParseResult":
        """Convert logical expression to MongoDB filter"""
        from .query_handler import QueryParseResult

        operation_id = id(ctx)
        self._log_operation_start("logical_parsing", ctx, operation_id)

        try:
            # Set current context to avoid infinite recursion
            self._current_context = ctx

            operator = self._extract_logical_operator(ctx)
            operands = self._extract_operands(ctx)

            # Process each operand recursively
            processed_operands = self._process_operands(operands)

            # Combine operands based on logical operator
            mongo_filter = self._combine_operands(operator, processed_operands)

            self._log_operation_success(
                "logical_parsing",
                operation_id,
                operator=operator,
                processed_count=len(processed_operands),
            )

            return QueryParseResult(filter_conditions=mongo_filter)

        except Exception as e:
            self._log_operation_error("logical_parsing", ctx, operation_id, e)
            return QueryParseResult(has_errors=True, error_message=str(e))

    def _process_operands(self, operands: List[Any]) -> List[Dict[str, Any]]:
        """Process operands and return processed filters"""
        processed_operands = []

        for operand in operands:
            operand_text = self.get_context_text(operand).strip()

            # Try comparison handler first for leaf nodes
            comparison_handler = ComparisonExpressionHandler()
            if comparison_handler.can_handle(operand):
                result = comparison_handler.handle_expression(operand)
                if not result.has_errors and result.filter_conditions:
                    processed_operands.append(result.filter_conditions)
                continue

            # If this is still a logical expression, handle it recursively
            # but check for different content to avoid infinite recursion
            current_text = self.get_context_text(self._current_context) if hasattr(self, "_current_context") else ""
            if self._has_logical_operators(operand) and operand_text != current_text:
                # Save current context to prevent recursion
                old_context = getattr(self, "_current_context", None)
                self._current_context = operand
                try:
                    result = self.handle_expression(operand)
                    if not result.has_errors and result.filter_conditions:
                        processed_operands.append(result.filter_conditions)
                finally:
                    self._current_context = old_context
                continue

            _logger.warning(f"Unable to process operand: {operand_text}")

        return processed_operands

    def _combine_operands(self, operator: str, operands: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine operands based on logical operator"""
        if not operands:
            return {}

        if len(operands) == 1:
            return operands[0]

        operator_upper = operator.upper()
        if operator_upper == "AND":
            return {"$and": operands}
        elif operator_upper == "OR":
            return {"$or": operands}
        elif operator_upper == "NOT":
            return {"$not": operands[0]}
        else:
            _logger.warning(f"Unknown logical operator '{operator}', using empty filter")
            return {}

    def _extract_logical_operator(self, ctx: Any) -> str:
        """Extract logical operator (AND, OR, NOT) with proper precedence"""
        try:
            text = self.get_context_text(ctx)
            # OR has lower precedence, so check it first
            for operator in ["OR", "AND", "NOT"]:
                if operator in text.upper() and self._has_operator_at_top_level(text, operator):
                    return operator
            return "AND"  # Default
        except Exception as e:
            _logger.debug(f"Failed to extract logical operator: {e}")
            return "AND"

    def _extract_operands(self, ctx: Any) -> List[Any]:
        """Extract operands for logical expression"""
        try:
            text = self.get_context_text(ctx)
            # Use the same precedence logic as operator extraction
            for operator in ["OR", "AND"]:
                if operator in text.upper() and self._has_operator_at_top_level(text, operator):
                    return self._split_operands_by_operator(text, operator)

            # Single operand
            return [self._create_operand_context(text)]
        except Exception as e:
            _logger.debug(f"Failed to extract operands: {e}")
            return []

    def _split_operands_by_operator(self, text: str, operator: str) -> List[Any]:
        """Split text by logical operator, handling quotes and parentheses"""
        operator_positions = self._find_operator_positions(text, operator)

        if not operator_positions:
            return [self._create_operand_context(text.strip())]

        operands = []
        start = 0
        for pos in operator_positions:
            part = text[start:pos].strip()
            if part:
                operands.append(self._create_operand_context(part))
            start = pos + len(operator)

        # Add the last part
        last_part = text[start:].strip()
        if last_part:
            operands.append(self._create_operand_context(last_part))

        return operands

    def _create_operand_context(self, text: str):
        """Create a context-like object for operand text"""

        class SimpleContext:
            def __init__(self, text_content):
                text_content = text_content.strip()
                # Only strip outer parentheses if they're grouping parentheses, not functional ones
                if text_content.startswith("(") and text_content.endswith(")"):
                    inner_text = text_content[1:-1].strip()

                    # Don't strip if it contains IN clauses with parentheses
                    if " IN (" in inner_text.upper():
                        # Keep the parentheses for IN clause
                        pass
                    # Don't strip if it contains function calls
                    elif any(func in inner_text.upper() for func in ["COUNT(", "MAX(", "MIN(", "AVG(", "SUM("]):
                        # Keep the parentheses for function calls
                        pass
                    else:
                        # Remove grouping parentheses
                        text_content = inner_text

                self._text = text_content

            def getText(self):
                return self._text

        return SimpleContext(text)

    def _has_operator_at_top_level(self, text: str, operator: str) -> bool:
        """Check if operator exists at top level (not inside parentheses)"""
        return len(self._find_operator_positions(text, operator)) > 0


class FunctionExpressionHandler(BaseHandler, ContextUtilsMixin, LoggingMixin):
    """Handles function expressions like COUNT(), MAX(), etc."""

    FUNCTION_MAP = {
        "COUNT": "$sum",
        "MAX": "$max",
        "MIN": "$min",
        "AVG": "$avg",
        "SUM": "$sum",
    }

    def can_handle(self, ctx: Any) -> bool:
        """Check if context represents a function call"""
        return hasattr(ctx, "functionName") or self._is_function_context(ctx)

    def handle_expression(self, ctx: Any) -> "QueryParseResult":
        """Handle function expressions"""
        from .query_handler import QueryParseResult

        operation_id = id(ctx)
        self._log_operation_start("function_parsing", ctx, operation_id)

        try:
            function_name = self._extract_function_name(ctx)
            arguments = self._extract_function_arguments(ctx)

            # For now, just return a placeholder - this would need full implementation
            mongo_filter = {"$expr": {self.FUNCTION_MAP.get(function_name.upper(), "$sum"): arguments}}

            self._log_operation_success(
                "function_parsing",
                operation_id,
                function_name=function_name,
            )

            return QueryParseResult(filter_conditions=mongo_filter)

        except Exception as e:
            self._log_operation_error("function_parsing", ctx, operation_id, e)
            return QueryParseResult(has_errors=True, error_message=str(e))

    def _is_function_context(self, ctx: Any) -> bool:
        """Check if context is a function call"""
        # TODO: Implement proper function detection
        return False

    def _extract_function_name(self, ctx: Any) -> str:
        """Extract function name"""
        # TODO: Implement proper function name extraction
        return "COUNT"

    def _extract_function_arguments(self, ctx: Any) -> List[str]:
        """Extract function arguments"""
        # TODO: Implement proper argument extraction
        return []


class HandlerFactory:
    """Unified factory for creating appropriate handlers"""

    _expression_handlers = None
    _visitor_handlers = None

    @classmethod
    def _initialize_expression_handlers(cls):
        """Lazy initialization of expression handlers"""
        if cls._expression_handlers is None:
            cls._expression_handlers = [
                LogicalExpressionHandler(),  # Check logical first (AND/OR)
                ComparisonExpressionHandler(),  # Then simple comparisons
                FunctionExpressionHandler(),
            ]
        return cls._expression_handlers

    @classmethod
    def _initialize_visitor_handlers(cls):
        """Lazy initialization of visitor handlers"""
        if cls._visitor_handlers is None:
            from .delete_handler import DeleteHandler
            from .insert_handler import InsertHandler
            from .query_handler import FromHandler, SelectHandler, WhereHandler
            from .update_handler import UpdateHandler

            cls._visitor_handlers = {
                "select": SelectHandler(),
                "from": FromHandler(),
                "where": WhereHandler(),
                "insert": InsertHandler(),
                "delete": DeleteHandler(),
                "update": UpdateHandler(),
            }
        return cls._visitor_handlers

    @classmethod
    def get_expression_handler(cls, ctx: Any) -> Optional[BaseHandler]:
        """Get appropriate expression handler for the given context"""
        handlers = cls._initialize_expression_handlers()
        for handler in handlers:
            if handler.can_handle(ctx):
                return handler
        return None

    @classmethod
    def get_visitor_handler(cls, handler_type: str) -> Optional[BaseHandler]:
        """Get visitor handler by type"""
        handlers = cls._initialize_visitor_handlers()
        return handlers.get(handler_type)

    @classmethod
    def register_expression_handler(cls, handler: BaseHandler) -> None:
        """Register a new expression handler"""
        handlers = cls._initialize_expression_handlers()
        handlers.append(handler)

    @classmethod
    def register_visitor_handler(cls, handler_type: str, handler: BaseHandler) -> None:
        """Register a new visitor handler"""
        handlers = cls._initialize_visitor_handlers()
        handlers[handler_type] = handler

    # Backward compatibility
    @classmethod
    def get_handler(cls, ctx: Any) -> Optional[BaseHandler]:
        """Backward compatibility method"""
        return cls.get_expression_handler(ctx)
