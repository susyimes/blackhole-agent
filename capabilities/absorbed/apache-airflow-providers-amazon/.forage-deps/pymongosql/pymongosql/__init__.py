# -*- coding: utf-8 -*-
from typing import TYPE_CHECKING, FrozenSet

from .error import *  # noqa

if TYPE_CHECKING:
    from .connection import Connection

__version__: str = "0.7.3"

# Globals https://www.python.org/dev/peps/pep-0249/#globals
apilevel: str = "2.0"
threadsafety: int = 3
paramstyle: str = "qmark"


class DBAPITypeObject(FrozenSet[str]):
    """Type Objects and Constructors

    https://www.python.org/dev/peps/pep-0249/#type-objects-and-constructors
    """

    def __eq__(self, other: object):
        if isinstance(other, frozenset):
            return frozenset.__eq__(self, other)
        else:
            return other in self

    def __ne__(self, other: object):
        if isinstance(other, frozenset):
            return frozenset.__ne__(self, other)
        else:
            return other not in self

    def __hash__(self):
        return frozenset.__hash__(self)


# DB API 2.0 Type Objects for MongoDB Data Types
# https://www.python.org/dev/peps/pep-0249/#type-objects-and-constructors
# Mapping of MongoDB BSON types to DB API 2.0 type objects

# Null/None type
NULL = DBAPITypeObject(("null", "Null", "NULL"))

# String types
STRING = DBAPITypeObject(("string", "str", "String", "VARCHAR", "CHAR", "TEXT"))

# Numeric types - Integer
BINARY = DBAPITypeObject(("binary", "Binary", "BINARY", "VARBINARY", "BLOB", "ObjectId"))

# Numeric types - Integer
NUMBER = DBAPITypeObject(("int", "integer", "long", "int32", "int64", "Integer", "BIGINT", "INT"))

# Numeric types - Decimal/Float
FLOAT = DBAPITypeObject(("double", "decimal", "float", "Double", "DECIMAL", "FLOAT", "NUMERIC"))

# Boolean type
BOOLEAN = DBAPITypeObject(("bool", "boolean", "Bool", "BOOLEAN"))

# Date/Time types
DATE = DBAPITypeObject(("date", "Date", "DATE"))
TIME = DBAPITypeObject(("time", "Time", "TIME"))
DATETIME = DBAPITypeObject(("datetime", "timestamp", "Timestamp", "DATETIME", "TIMESTAMP"))

# Aggregate types
ARRAY = DBAPITypeObject(("array", "Array", "ARRAY", "list"))
OBJECT = DBAPITypeObject(("object", "Object", "OBJECT", "struct", "dict", "document"))

# Special MongoDB types
OBJECTID = DBAPITypeObject(("objectid", "ObjectId", "OBJECTID", "oid"))
REGEX = DBAPITypeObject(("regex", "Regex", "REGEX", "regexp"))

# Map MongoDB BSON type codes to DB API type objects
# This mapping helps cursor.description identify the correct type for each column
_MONGODB_TYPE_MAP = {
    "null": NULL,
    "string": STRING,
    "int": NUMBER,
    "integer": NUMBER,
    "long": NUMBER,
    "int32": NUMBER,
    "int64": NUMBER,
    "double": FLOAT,
    "decimal": FLOAT,
    "float": FLOAT,
    "bool": BOOLEAN,
    "boolean": BOOLEAN,
    "date": DATE,
    "datetime": DATETIME,
    "timestamp": DATETIME,
    "array": ARRAY,
    "object": OBJECT,
    "document": OBJECT,
    "bson.objectid": OBJECTID,
    "objectid": OBJECTID,
    "regex": REGEX,
    "binary": BINARY,
}


def get_type_code(value: object) -> str:
    """Get the type code for a MongoDB value.

    Maps a MongoDB/Python value to its corresponding DB API type code string.

    Args:
        value: The value to determine the type for

    Returns:
        A string representing the DB API type code
    """
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "bool"
    elif isinstance(value, int):
        return "int"
    elif isinstance(value, float):
        return "double"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, bytes):
        return "binary"
    elif isinstance(value, dict):
        return "object"
    elif isinstance(value, list):
        return "array"
    elif hasattr(value, "__class__") and value.__class__.__name__ == "ObjectId":
        return "objectid"
    else:
        return "object"


def get_type_object(value: object) -> DBAPITypeObject:
    """Get the DB API type object for a MongoDB value.

    Args:
        value: The value to get type information for

    Returns:
        A DBAPITypeObject representing the value's type
    """
    type_code = get_type_code(value)
    return _MONGODB_TYPE_MAP.get(type_code, OBJECT)


def connect(*args, **kwargs) -> "Connection":
    from .connection import Connection

    return Connection(*args, **kwargs)


# Register superset execution strategy for mongodb+superset:// connections
def _register_superset_executor() -> None:
    """Register SupersetExecution strategy for superset mode.

    This allows the executor and cursor to be unaware of superset -
    the execution strategy is automatically selected based on the connection mode.
    """
    try:
        from .executor import ExecutionPlanFactory
        from .superset_mongodb.executor import SupersetExecution

        ExecutionPlanFactory.register_strategy(SupersetExecution())
    except ImportError:
        # Superset module not available - skip registration
        pass


# Auto-register superset executor on module import
_register_superset_executor()

# SQLAlchemy integration (optional)
# For SQLAlchemy functionality, import from pymongosql.sqlalchemy_mongodb:
#   from pymongosql.sqlalchemy_mongodb import create_engine_url, create_engine_from_mongodb_uri
try:
    from .sqlalchemy_mongodb import __sqlalchemy_version__, __supports_sqlalchemy_2x__, __supports_sqlalchemy__
except ImportError:
    # SQLAlchemy integration not available
    __sqlalchemy_version__ = None
    __supports_sqlalchemy__ = False
    __supports_sqlalchemy_2x__ = False
