# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from bson.timestamp import Timestamp

_logger = logging.getLogger(__name__)


class ValueFunctionExecutionError(Exception):
    """Raised when a value function execution fails"""

    pass


class ValueFunctionRegistry:
    """Registry for managing custom value transformation functions"""

    def __init__(self):
        """Initialize the registry with built-in functions"""
        self._functions: Dict[str, Callable] = {}
        self._register_builtin_functions()

    def _register_builtin_functions(self) -> None:
        """Register built-in value transformation functions"""
        self.register("str_to_datetime", self.str_to_datetime)
        self.register("str_to_timestamp", self.str_to_timestamp)

    def register(self, func_name: str, func: Callable) -> None:
        """
        Register a custom value function.

        Args:
            func_name: Name of the function (case-insensitive)
            func: Callable that takes arguments and returns transformed value

        Raises:
            ValueError: If func_name is already registered or invalid
        """
        if not isinstance(func_name, str) or not func_name.strip():
            raise ValueError("Function name must be a non-empty string")

        if not callable(func):
            raise ValueError(f"Function {func_name} must be callable")

        func_name_lower = func_name.lower()
        if func_name_lower in self._functions:
            _logger.warning(f"Overwriting existing function: {func_name}")

        self._functions[func_name_lower] = func
        _logger.debug(f"Registered value function: {func_name}")

    def unregister(self, func_name: str) -> None:
        """
        Unregister a value function.

        Args:
            func_name: Name of the function to unregister
        """
        func_name_lower = func_name.lower()
        if func_name_lower in self._functions:
            del self._functions[func_name_lower]
            _logger.debug(f"Unregistered value function: {func_name}")

    def execute(self, func_name: str, args: List[Any]) -> Any:
        """
        Execute a registered value function.

        Args:
            func_name: Name of the function to execute
            args: List of arguments to pass to the function

        Returns:
            The result of the function execution

        Raises:
            ValueFunctionExecutionError: If function not found or execution fails
        """
        func_name_lower = func_name.lower()

        if func_name_lower not in self._functions:
            raise ValueFunctionExecutionError(
                f"Value function '{func_name}' not found. " f"Available functions: {list(self._functions.keys())}"
            )

        try:
            func = self._functions[func_name_lower]
            result = func(*args)
            _logger.debug(f"Executed value function: {func_name}({args}) -> {result}")
            return result
        except TypeError as e:
            raise ValueFunctionExecutionError(f"Invalid arguments for function '{func_name}': {str(e)}") from e
        except Exception as e:
            raise ValueFunctionExecutionError(f"Error executing function '{func_name}': {str(e)}") from e

    def has_function(self, func_name: str) -> bool:
        """Check if a function is registered"""
        return func_name.lower() in self._functions

    def list_functions(self) -> List[str]:
        """Get list of registered function names"""
        return list(self._functions.keys())

    # =========================================================================
    # Built-in Value Functions
    # =========================================================================

    @staticmethod
    def str_to_datetime(*args) -> datetime:
        """
        Convert string value to Python datetime object.

        Supports two signatures:
        - str_to_datetime(val): Convert ISO 8601 formatted string to datetime
        - str_to_datetime(val, format): Convert string using custom format

        Args:
            *args: Either (val,) or (val, format)
                val: String representation of datetime
                format: Python datetime format string (Python strftime directives)

        Returns:
            datetime: Python datetime object with UTC timezone

        Raises:
            ValueError: If arguments are invalid or parsing fails

        Examples:
            str_to_datetime('2024-01-15')              # ISO 8601
            str_to_datetime('2024-01-15T10:30:00Z')    # ISO 8601 with time
            str_to_datetime('01/15/2024', '%m/%d/%Y')  # Custom format
        """
        if not args:
            raise ValueError("str_to_datetime() requires at least 1 argument (val)")

        if len(args) > 2:
            raise ValueError(f"str_to_datetime() takes at most 2 arguments ({len(args)} given)")

        val = args[0]

        # Validate input
        if not isinstance(val, str):
            raise ValueError(f"str_to_datetime() val must be string, got {type(val).__name__}")

        val = val.strip()
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"

        try:
            if len(args) == 1:
                # ISO 8601 format - use fromisoformat for standard parsing
                dt = datetime.fromisoformat(val)
                # Ensure UTC timezone
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            else:
                # Custom format
                format_str = args[1]
                if not isinstance(format_str, str):
                    raise ValueError(f"str_to_datetime() format must be string, got {type(format_str).__name__}")
                dt = datetime.strptime(val, format_str.strip())
                # Ensure UTC timezone
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt

        except ValueError as e:
            raise ValueError(f"Failed to parse str_to_datetime from '{val}': {str(e)}") from e

    @staticmethod
    def str_to_timestamp(*args) -> Timestamp:
        """
        Convert string value to BSON Timestamp object.

        Supports two signatures:
        - str_to_timestamp(val): Convert ISO 8601 formatted string to Timestamp
        - str_to_timestamp(val, format): Convert string using custom format

        Args:
            *args: Either (val,) or (val, format)
                val: String representation of datetime
                format: Python datetime format string (Python strftime directives)

        Returns:
            bson.timestamp.Timestamp: BSON Timestamp object

        Raises:
            ValueError: If arguments are invalid or parsing fails

        Notes:
            - Timestamp uses Unix epoch seconds and an increment counter
            - This function uses seconds from epoch and increments by 1 for the counter
            - Used primarily for MongoDB replication operations

        Examples:
            str_to_timestamp('2024-01-15')              # ISO 8601
            str_to_timestamp('2024-01-15T10:30:00Z')    # ISO 8601 with time
            str_to_timestamp('01/15/2024', '%m/%d/%Y')  # Custom format
        """
        if not args:
            raise ValueError("str_to_timestamp() requires at least 1 argument (val)")

        if len(args) > 2:
            raise ValueError(f"str_to_timestamp() takes at most 2 arguments ({len(args)} given)")

        val = args[0]

        # Validate input
        if not isinstance(val, str):
            raise ValueError(f"str_to_timestamp() val must be string, got {type(val).__name__}")

        val = val.strip()
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"

        try:
            # First parse to datetime using same logic as datetime function
            if len(args) == 1:
                # ISO 8601 format
                dt = datetime.fromisoformat(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Custom format
                format_str = args[1]
                if not isinstance(format_str, str):
                    raise ValueError(f"str_to_timestamp() format must be string, got {type(format_str).__name__}")
                dt = datetime.strptime(val, format_str.strip())
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

            # Convert datetime to Timestamp
            # Timestamp(time, inc) where time is Unix epoch in seconds
            time_seconds = int(dt.timestamp())
            # Use increment of 1 for conversion operations
            ts = Timestamp(time=time_seconds, inc=1)
            return ts

        except ValueError as e:
            raise ValueError(f"Failed to parse str_to_timestamp from '{val}': {str(e)}") from e


# Global singleton instance
_default_registry: Optional[ValueFunctionRegistry] = None


def get_default_registry() -> ValueFunctionRegistry:
    """Get or create the default value function registry"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ValueFunctionRegistry()
    return _default_registry


def execute_value_function(func_name: str, args: List[Any]) -> Any:
    """
    Execute a value function using the default registry.

    Args:
        func_name: Name of the function
        args: Arguments to pass to the function

    Returns:
        Result of function execution

    Raises:
        ValueFunctionExecutionError: If function execution fails
    """
    return get_default_registry().execute(func_name, args)
