"""
Type system and conversion utilities for Redshift Data API dialect.

This module provides type mapping between SQLAlchemy types, Python types,
and Redshift Data API formats, with special handling for Redshift-specific
types like SUPER and GEOMETRY.
"""

import decimal
import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from sqlalchemy import types as sqltypes
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import base as pg_base
from sqlalchemy.sql.type_api import TypeDecorator


class SUPER(TypeDecorator):
    """
    Redshift SUPER type for semi-structured data.

    Maps to JSON-like handling in Python, storing as string in Data API.
    """

    impl = sqltypes.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python value to Data API format."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def process_result_value(self, value, dialect):
        """Convert Data API result to Python value."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value


class GEOMETRY(TypeDecorator):
    """
    Redshift GEOMETRY type for spatial data.

    Maps to string representation in Python for now.
    """

    impl = sqltypes.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python value to Data API format."""
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        """Convert Data API result to Python value."""
        if value is None:
            return None
        return str(value)


class RedshiftTypeConverter:
    """
    Handles bidirectional type conversion between Python types and Data API formats.
    """

    # Mapping from Data API type names to Python conversion functions
    DATA_API_TO_PYTHON = {
        "bigint": lambda x: int(x) if x is not None else None,
        "boolean": lambda x: bool(x) if x is not None else None,
        "char": lambda x: str(x) if x is not None else None,
        "date": lambda x: datetime.fromisoformat(x).date() if x is not None else None,
        "decimal": lambda x: decimal.Decimal(str(x)) if x is not None else None,
        "double precision": lambda x: float(x) if x is not None else None,
        "integer": lambda x: int(x) if x is not None else None,
        "numeric": lambda x: decimal.Decimal(str(x)) if x is not None else None,
        "real": lambda x: float(x) if x is not None else None,
        "smallint": lambda x: int(x) if x is not None else None,
        "text": lambda x: str(x) if x is not None else None,
        "time": lambda x: (
            datetime.fromisoformat(f"1970-01-01T{x}").time() if x is not None else None
        ),
        "timestamp": lambda x: (
            datetime.fromisoformat(x.replace("Z", "+00:00")) if x is not None else None
        ),
        "timestamptz": lambda x: (
            datetime.fromisoformat(x.replace("Z", "+00:00")) if x is not None else None
        ),
        "uuid": lambda x: UUID(x) if x is not None else None,
        "varchar": lambda x: str(x) if x is not None else None,
        "super": lambda x: json.loads(x) if x is not None and x != "" else None,
        "geometry": lambda x: str(x) if x is not None else None,
    }

    # Mapping from Python types to Data API parameter format
    PYTHON_TO_DATA_API = {
        bool: lambda x: {"booleanValue": x},
        int: lambda x: {"longValue": x},
        float: lambda x: {"doubleValue": x},
        str: lambda x: {"stringValue": x},
        bytes: lambda x: {"blobValue": x},
        decimal.Decimal: lambda x: {"stringValue": str(x)},
        datetime: lambda x: {"stringValue": x.isoformat()},
        date: lambda x: {"stringValue": x.isoformat()},
        time: lambda x: {"stringValue": x.isoformat()},
        UUID: lambda x: {"stringValue": str(x)},
        dict: lambda x: {"stringValue": json.dumps(x)},
        list: lambda x: {"stringValue": json.dumps(x)},
    }

    @classmethod
    def python_to_data_api_param(cls, value: Any) -> Dict[str, Any]:
        """
        Convert Python value to Data API parameter format.

        Args:
            value: Python value to convert

        Returns:
            Dict containing the Data API parameter format
        """
        if value is None:
            return {"isNull": True}

        value_type = type(value)

        # Handle None explicitly
        if value is None:
            return {"isNull": True}

        # Try direct type mapping first
        if value_type in cls.PYTHON_TO_DATA_API:
            return cls.PYTHON_TO_DATA_API[value_type](value)

        # Handle subclasses and special cases
        if isinstance(value, bool):
            return {"booleanValue": value}
        elif isinstance(value, int):
            return {"longValue": value}
        elif isinstance(value, float):
            return {"doubleValue": value}
        elif isinstance(value, str):
            return {"stringValue": value}
        elif isinstance(value, bytes):
            return {"blobValue": value}
        elif isinstance(value, decimal.Decimal):
            return {"stringValue": str(value)}
        elif isinstance(value, (datetime, date, time)):
            return {"stringValue": value.isoformat()}
        elif isinstance(value, UUID):
            return {"stringValue": str(value)}
        elif isinstance(value, (dict, list)):
            return {"stringValue": json.dumps(value)}
        else:
            # Fallback to string representation
            return {"stringValue": str(value)}

    @classmethod
    def data_api_result_to_python(cls, value: Dict[str, Any], column_type: str = None) -> Any:
        """
        Convert Data API result value to Python type.

        Args:
            value: Data API result value dictionary
            column_type: Optional column type hint

        Returns:
            Python value
        """
        if value is None or value.get("isNull", False):
            return None

        # Extract the actual value from the Data API format
        if "stringValue" in value:
            raw_value = value["stringValue"]
        elif "longValue" in value:
            raw_value = value["longValue"]
        elif "doubleValue" in value:
            raw_value = value["doubleValue"]
        elif "booleanValue" in value:
            raw_value = value["booleanValue"]
        elif "blobValue" in value:
            raw_value = value["blobValue"]
        else:
            return None

        # If we have column type information, use it for conversion
        if column_type and column_type.lower() in cls.DATA_API_TO_PYTHON:
            converter = cls.DATA_API_TO_PYTHON[column_type.lower()]
            try:
                return converter(raw_value)
            except (ValueError, TypeError, json.JSONDecodeError):
                # Fallback to raw value if conversion fails
                return raw_value

        # Return the raw value as-is if no type conversion is needed
        return raw_value

    @classmethod
    def convert_parameters(cls, parameters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert a dictionary of parameters to Data API parameter format.

        Args:
            parameters: Dictionary of parameter name -> value mappings

        Returns:
            List of Data API parameter dictionaries
        """
        if not parameters:
            return []

        result = []
        for name, value in parameters.items():
            param = {"name": name, **cls.python_to_data_api_param(value)}
            result.append(param)

        return result

    @classmethod
    def convert_result_row(
        cls, row_data: List[Dict[str, Any]], column_metadata: List[Dict[str, str]]
    ) -> List[Any]:
        """
        Convert a Data API result row to Python values.

        Args:
            row_data: List of Data API field values
            column_metadata: List of column metadata dictionaries

        Returns:
            List of Python values
        """
        result = []
        for i, field_value in enumerate(row_data):
            column_type = None
            if i < len(column_metadata):
                column_type = column_metadata[i].get("typeName")

            python_value = cls.data_api_result_to_python(field_value, column_type)
            result.append(python_value)

        return result


# Type mapping for SQLAlchemy dialect
REDSHIFT_TYPE_MAP = {
    # Standard PostgreSQL types (inherited)
    **pg_base.PGDialect.colspecs,
    # Redshift-specific type extensions
    "SUPER": SUPER,
    "GEOMETRY": GEOMETRY,
}


def get_column_type(column_metadata: Dict[str, Any]) -> Type[sqltypes.TypeEngine]:
    """
    Get SQLAlchemy type class from Data API column metadata.

    Args:
        column_metadata: Column metadata from Data API

    Returns:
        SQLAlchemy type class
    """
    type_name = column_metadata.get("typeName", "").upper()

    # Handle Redshift-specific types
    if type_name == "SUPER":
        return SUPER
    elif type_name == "GEOMETRY":
        return GEOMETRY

    # Map common types to SQLAlchemy types
    type_mapping = {
        "BIGINT": sqltypes.BigInteger,
        "BOOLEAN": sqltypes.Boolean,
        "CHAR": sqltypes.CHAR,
        "DATE": sqltypes.Date,
        "DECIMAL": sqltypes.DECIMAL,
        "DOUBLE PRECISION": sqltypes.Float,
        "INTEGER": sqltypes.Integer,
        "NUMERIC": sqltypes.NUMERIC,
        "REAL": sqltypes.Float,
        "SMALLINT": sqltypes.SmallInteger,
        "TEXT": sqltypes.Text,
        "TIME": sqltypes.Time,
        "TIMESTAMP": sqltypes.TIMESTAMP,
        "TIMESTAMPTZ": sqltypes.TIMESTAMP,
        "UUID": PG_UUID,
        "VARCHAR": sqltypes.VARCHAR,
    }

    return type_mapping.get(type_name, sqltypes.String)
