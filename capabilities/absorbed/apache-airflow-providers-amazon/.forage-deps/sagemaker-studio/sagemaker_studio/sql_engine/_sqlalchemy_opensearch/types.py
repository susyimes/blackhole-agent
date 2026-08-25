"""
Type system and conversion utilities for OpenSearch dialect.

This module provides type mapping between SQLAlchemy types, Python types,
and OpenSearch formats, with special handling for OpenSearch-specific
types like OBJECT and NESTED.
"""

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from sqlalchemy import types as sqltypes
from sqlalchemy.sql.type_api import TypeDecorator


class OBJECT(TypeDecorator):
    """
    OpenSearch OBJECT type for structured data.

    Maps to JSON-like handling in Python, storing as dict.
    """

    impl = sqltypes.JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python value to OpenSearch format."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {"value": value}
        return {"value": str(value)}

    def process_result_value(self, value, dialect):
        """Convert OpenSearch result to Python value."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (json.JSONDecodeError, TypeError):
            return value


class NESTED(TypeDecorator):
    """
    OpenSearch NESTED type for arrays of objects.

    Maps to list of dictionaries in Python.
    """

    impl = sqltypes.JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python value to OpenSearch format."""
        if value is None:
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else [parsed]
            except (json.JSONDecodeError, TypeError):
                return [{"value": value}]
        return [{"value": str(value)}]

    def process_result_value(self, value, dialect):
        """Convert OpenSearch result to Python value."""
        if value is None:
            return []  # Return empty list instead of None for NESTED type
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(str(value))
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, TypeError):
            return [value] if value is not None else []


class GEO_POINT(TypeDecorator):
    """
    OpenSearch GEO_POINT type for geographic coordinates.

    Maps to string representation in Python for now.
    """

    impl = sqltypes.String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python value to OpenSearch format."""
        if value is None:
            return None
        if isinstance(value, dict) and "lat" in value and "lon" in value:
            lat = value["lat"]
            lon = value["lon"]
            return f"{lat},{lon}"
        return str(value)

    def process_result_value(self, value, dialect):
        """Convert OpenSearch result to Python value."""
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and "," in value:
            try:
                lat, lon = value.split(",", 1)
                return {"lat": float(lat.strip()), "lon": float(lon.strip())}
            except (ValueError, AttributeError):
                pass
        return str(value)


class OpenSearchTypeConverter:
    """
    Handles bidirectional type conversion between Python types and OpenSearch formats.
    """

    # Mapping from OpenSearch type names to Python conversion functions
    OPENSEARCH_TO_PYTHON = {
        "text": lambda x: str(x) if x is not None else None,
        "keyword": lambda x: str(x) if x is not None else None,
        "long": lambda x: int(x) if x is not None else None,
        "integer": lambda x: int(x) if x is not None else None,
        "short": lambda x: int(x) if x is not None else None,
        "byte": lambda x: int(x) if x is not None else None,
        "double": lambda x: float(x) if x is not None else None,
        "float": lambda x: float(x) if x is not None else None,
        "half_float": lambda x: float(x) if x is not None else None,
        "scaled_float": lambda x: float(x) if x is not None else None,
        "boolean": lambda x: bool(x) if x is not None else None,
        "date": lambda x: (
            datetime.fromisoformat(x.replace("Z", "+00:00"))
            if isinstance(x, str) and x is not None
            else x
        ),
        "binary": lambda x: bytes(x) if x is not None else None,
        "ip": lambda x: str(x) if x is not None else None,
        "geo_point": lambda x: x,  # Keep as-is, handled by GEO_POINT type
        "geo_shape": lambda x: x,  # Keep as-is
        "object": lambda x: (
            x if isinstance(x, dict) else json.loads(str(x)) if x is not None else None
        ),
        "nested": lambda x: OpenSearchTypeConverter._convert_nested_value(x),
    }

    @staticmethod
    def _convert_nested_value(x):
        """Helper method to convert nested values with proper JSON parsing."""
        if x is None:
            return []
        if isinstance(x, list):
            return x
        if isinstance(x, str):
            try:
                parsed = json.loads(x)
                return parsed if isinstance(parsed, list) else [parsed]
            except (json.JSONDecodeError, TypeError):
                return [x]
        return [x]

    # Mapping from Python types to OpenSearch parameter format
    PYTHON_TO_OPENSEARCH = {
        bool: lambda x: x,
        int: lambda x: x,
        float: lambda x: x,
        str: lambda x: x,
        bytes: lambda x: x.decode("utf-8") if isinstance(x, bytes) else str(x),
        datetime: lambda x: x.isoformat(),
        date: lambda x: x.isoformat(),
        time: lambda x: x.isoformat(),
        UUID: lambda x: str(x),
        dict: lambda x: x,
        list: lambda x: x,
    }

    @classmethod
    def python_to_opensearch_param(cls, value: Any) -> Any:
        """
        Convert Python value to OpenSearch parameter format.

        Args:
            value: Python value to convert

        Returns:
            Value in OpenSearch format
        """
        if value is None:
            return None

        value_type = type(value)

        # Try direct type mapping first
        if value_type in cls.PYTHON_TO_OPENSEARCH:
            return cls.PYTHON_TO_OPENSEARCH[value_type](value)

        # Handle subclasses and special cases
        if isinstance(value, bool):
            return value
        elif isinstance(value, int):
            return value
        elif isinstance(value, float):
            return value
        elif isinstance(value, str):
            return value
        elif isinstance(value, bytes):
            return value.decode("utf-8")
        elif isinstance(value, (datetime, date, time)):
            return value.isoformat()
        elif isinstance(value, UUID):
            return str(value)
        elif isinstance(value, (dict, list)):
            return value
        else:
            # Fallback to string representation
            return str(value)

    @classmethod
    def opensearch_result_to_python(cls, value: Any, column_type: str = None) -> Any:
        """
        Convert OpenSearch result value to Python type.

        Args:
            value: OpenSearch result value
            column_type: Optional column type hint

        Returns:
            Python value
        """
        if value is None:
            return None

        # If we have column type information, use it for conversion
        if column_type and column_type.lower() in cls.OPENSEARCH_TO_PYTHON:
            converter = cls.OPENSEARCH_TO_PYTHON[column_type.lower()]
            try:
                return converter(value)
            except (ValueError, TypeError, json.JSONDecodeError):
                # Fallback to raw value if conversion fails
                return value

        # Return the value as-is if no type conversion is needed
        return value

    @classmethod
    def convert_parameters(cls, parameters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert a dictionary of parameters to OpenSearch format.

        Args:
            parameters: Dictionary of parameter name -> value mappings

        Returns:
            Dictionary of OpenSearch parameters
        """
        if not parameters:
            return {}

        result = {}
        for name, value in parameters.items():
            result[name] = cls.python_to_opensearch_param(value)

        return result

    @classmethod
    def convert_result_row(
        cls, row_data: List[Any], column_metadata: List[Dict[str, str]]
    ) -> List[Any]:
        """
        Convert an OpenSearch result row to Python values.

        Args:
            row_data: List of field values from OpenSearch
            column_metadata: List of column metadata dictionaries

        Returns:
            List of Python values
        """
        result = []
        for i, field_value in enumerate(row_data):
            column_type = None
            if i < len(column_metadata):
                column_type = column_metadata[i].get("type")

            python_value = cls.opensearch_result_to_python(field_value, column_type)
            result.append(python_value)

        return result


# Type mapping for SQLAlchemy dialect
OPENSEARCH_TYPE_MAP = {
    # OpenSearch-specific type extensions
    "OBJECT": OBJECT,
    "NESTED": NESTED,
    "GEO_POINT": GEO_POINT,
}


def get_column_type(column_metadata: Dict[str, Any]) -> Type[sqltypes.TypeEngine]:
    """
    Get SQLAlchemy type class from OpenSearch column metadata.

    Args:
        column_metadata: Column metadata from OpenSearch

    Returns:
        SQLAlchemy type class
    """
    type_name = column_metadata.get("type", "").upper()

    # Handle OpenSearch-specific types
    if type_name == "OBJECT":
        return OBJECT
    elif type_name == "NESTED":
        return NESTED
    elif type_name == "GEO_POINT":
        return GEO_POINT

    # Map common types to SQLAlchemy types
    type_mapping = {
        "TEXT": sqltypes.Text,
        "KEYWORD": sqltypes.String,
        "LONG": sqltypes.BigInteger,
        "INTEGER": sqltypes.Integer,
        "SHORT": sqltypes.SmallInteger,
        "BYTE": sqltypes.SmallInteger,
        "DOUBLE": sqltypes.Float,
        "FLOAT": sqltypes.Float,
        "HALF_FLOAT": sqltypes.Float,
        "SCALED_FLOAT": sqltypes.Float,
        "BOOLEAN": sqltypes.Boolean,
        "DATE": sqltypes.DateTime,
        "BINARY": sqltypes.LargeBinary,
        "IP": sqltypes.String,
        "GEO_SHAPE": sqltypes.String,
    }

    return type_mapping.get(type_name, sqltypes.String)
