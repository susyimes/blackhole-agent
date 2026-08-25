"""
SQLAlchemy 2.0 compatible dialect for Vertica.

This dialect provides Vertica database support for SQLAlchemy 2.0+,
using vertica-python as the underlying DBAPI driver.
"""

import logging
import re

from sqlalchemy import __version__ as sqlalchemy_version
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _version_tuple(version_str):
    """Convert version string to tuple for comparison."""
    parts = version_str.split(".")[:3]
    return tuple(int(re.match(r"(\d+)", p).group(1)) for p in parts)


class VerticaDialect(DefaultDialect):
    """
    SQLAlchemy dialect for Vertica databases.

    This dialect inherits from DefaultDialect and provides Vertica-specific
    query introspection using vertica-python as the driver.
    """

    name = "vertica"
    driver = "vertica_python"

    # Enable statement caching for better performance
    supports_statement_cache = True

    # Rowcount support
    supports_sane_rowcount = True
    supports_sane_multi_rowcount = False

    # Result set handling
    supports_empty_insert = True
    supports_multivalues_insert = True

    # Vertica-specific features
    supports_sequences = False  # Vertica doesn't support sequences
    supports_native_boolean = True
    supports_native_decimal = True
    supports_smallserial = False  # Vertica doesn't support SMALLSERIAL

    default_schema_name = "public"

    def __init__(self, **kwargs):
        """Initialize the dialect."""
        # Verify SQLAlchemy version requirement
        min_version = "2.0.0"
        if _version_tuple(sqlalchemy_version) < _version_tuple(min_version):
            raise ImportError(
                f"SQLAlchemy version {min_version} or higher is required. "
                f"Current version: {sqlalchemy_version}"
            )

        super().__init__(**kwargs)

    @classmethod
    def import_dbapi(cls):
        """Import and return the vertica_python DBAPI module."""
        import vertica_python

        return vertica_python

    def create_connect_args(self, url):
        """
        Create connection arguments from SQLAlchemy URL.

        Args:
            url: SQLAlchemy URL object

        Returns:
            tuple: (args, kwargs) for connection creation

        Raises:
            ValueError: If host is not provided
        """
        # Validate required parameters
        if not url.host:
            raise ValueError(
                "Host is required for Vertica connection. "
                "Please provide a valid host in the connection URL."
            )

        opts = {
            "host": url.host,
            "port": url.port or 5433,
            "user": url.username,
            "password": url.password,
            "database": url.database,
        }

        # Add query parameters
        if url.query:
            for key, val in url.query.items():
                opts[key] = val if isinstance(val, str) else val[-1]

        # Return empty args list and connection parameters
        return ([], opts)

    def _get_server_version_info(self, connection):
        """
        Get server version information.

        Returns a tuple of ints representing the Vertica version (e.g., (11, 0, 1)).

        Raises:
            RuntimeError: If the version cannot be retrieved or parsed.
        """
        try:
            from sqlalchemy import text

            result = connection.execute(text("SELECT version()"))
            version_str = result.scalar()

            if version_str:
                match = re.search(r"v(\d+)\.(\d+)\.(\d+)", version_str)
                if match:
                    return tuple(int(x) for x in match.groups())
                raise RuntimeError(f"Unable to parse Vertica version from: {version_str}")
            raise RuntimeError("Vertica returned empty version string.")
        except SQLAlchemyError as e:
            raise RuntimeError(f"Failed to retrieve Vertica server version: {e}") from e

    def _get_default_schema_name(self, connection):
        """Get the default schema name."""
        try:
            from sqlalchemy import text

            result = connection.execute(text("SELECT current_schema()"))
            schema_name = result.scalar()
            return schema_name if schema_name else "public"
        except SQLAlchemyError as e:
            logger.warning(
                "Failed to retrieve default schema name: %s. Using 'public' as default.",
                str(e),
            )
            return "public"

    def initialize(self, connection):
        """Initialize the dialect."""
        super().initialize(connection)

        # Set Vertica-specific properties
        self.server_version_info = self._get_server_version_info(connection)
        self.default_schema_name = self._get_default_schema_name(connection)

    def do_rollback(self, dbapi_connection):
        """Rollback a transaction."""
        dbapi_connection.rollback()

    def do_commit(self, dbapi_connection):
        """Commit a transaction."""
        dbapi_connection.commit()

    def do_close(self, dbapi_connection):
        """Close a connection."""
        dbapi_connection.close()

    def get_schema_names(self, connection, **kw):
        """Return a list of schema names available in the database."""
        from sqlalchemy import text

        query = text("""
            SELECT schema_name
            FROM v_catalog.schemata
            WHERE schema_name NOT IN ('v_catalog', 'v_monitor', 'v_internal')
            ORDER BY schema_name
            """)
        result = connection.execute(query)
        return [row[0] for row in result]

    def get_table_names(self, connection, schema=None, **kw):
        """Return a list of table names in the given schema."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
            SELECT table_name
            FROM v_catalog.tables
            WHERE table_schema = :schema
            ORDER BY table_name
            """)
        result = connection.execute(query, {"schema": schema})
        return [row[0] for row in result]

    def get_view_names(self, connection, schema=None, **kw):
        """Return a list of view names in the given schema."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
            SELECT table_name
            FROM v_catalog.views
            WHERE table_schema = :schema
            ORDER BY table_name
            """)
        result = connection.execute(query, {"schema": schema})
        return [row[0] for row in result]

    def get_columns(self, connection, table_name, schema=None, **kw):
        """Return column information for the given table."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                ordinal_position
            FROM v_catalog.columns
            WHERE table_schema = :schema
            AND table_name = :table_name
            ORDER BY ordinal_position
            """)

        result = connection.execute(query, {"schema": schema, "table_name": table_name})
        columns = []

        for row in result:
            col_name = row[0]
            col_type = row[1]
            nullable = row[2] in (True, "t", "true", "YES", 1)
            default = row[3]
            char_max_length = row[4]
            numeric_precision = row[5]
            numeric_scale = row[6]

            # Convert Vertica types to SQLAlchemy types
            type_obj = self._get_column_type(
                col_type, char_max_length, numeric_precision, numeric_scale
            )

            column_info = {
                "name": col_name,
                "type": type_obj,
                "nullable": nullable,
                "default": default,
                "autoincrement": False,
                "comment": None,
            }
            columns.append(column_info)

        return columns

    def _get_column_type(
        self, type_name, char_max_length=None, numeric_precision=None, numeric_scale=None
    ):
        """Convert Vertica data type to SQLAlchemy type."""
        from sqlalchemy import types

        # Strip parenthesized parameters, e.g. "numeric(10,2)" -> "numeric"
        type_name = re.sub(r"\(.*\)", "", type_name.lower()).strip()

        # Handle timezone-aware types separately to preserve timezone=True
        if type_name in ("timestamptz", "timestamp with time zone"):
            return types.TIMESTAMP(timezone=True)
        if type_name in ("timetz", "time with time zone"):
            return types.Time(timezone=True)

        # Handle standard types
        type_map = {
            "int": types.Integer,
            "integer": types.Integer,
            "bigint": types.BigInteger,
            "smallint": types.SmallInteger,
            "tinyint": types.SmallInteger,
            "decimal": types.Numeric,
            "numeric": types.Numeric,
            "number": types.Numeric,
            "money": types.Numeric,
            "float": types.Float,
            "float8": types.Float,
            "real": types.Float,
            "double precision": types.Float,
            "boolean": types.Boolean,
            "bool": types.Boolean,
            "char": types.CHAR,
            "varchar": types.VARCHAR,
            "long varchar": types.Text,
            "text": types.Text,
            "date": types.Date,
            "datetime": types.DateTime,
            "timestamp": types.TIMESTAMP,
            "timestamp without time zone": types.TIMESTAMP,
            "time": types.Time,
            "time without time zone": types.Time,
            "interval": types.Interval,
            "interval day to second": types.Interval,
            "interval year to month": types.Interval,
            "binary": types.LargeBinary,
            "varbinary": types.LargeBinary,
            "long varbinary": types.LargeBinary,
            "bytea": types.LargeBinary,
            "uuid": types.String,
        }

        if type_name in type_map:
            type_class = type_map[type_name]

            # Handle types that need length/precision parameters
            if type_name in ("char", "varchar"):
                if char_max_length is not None:
                    return type_class(char_max_length)
                else:
                    return type_class()
            elif type_name in ("decimal", "numeric", "number", "money"):
                if numeric_precision is not None and numeric_scale is not None:
                    return type_class(numeric_precision, numeric_scale)
                elif numeric_precision is not None:
                    return type_class(numeric_precision)
                else:
                    return type_class()
            else:
                return type_class()

        # Default to Text for unknown types
        return types.Text()

    def get_indexes(self, connection, table_name, schema=None, **kw):
        """Return index information for the given table."""
        # Vertica doesn't have traditional indexes like PostgreSQL
        # It uses projections instead
        return []

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        """Return primary key constraint information for the given table."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
            SELECT column_name
            FROM v_catalog.primary_keys
            WHERE table_schema = :schema
            AND table_name = :table_name
            ORDER BY constraint_name, ordinal_position
            """)

        result = connection.execute(query, {"schema": schema, "table_name": table_name})
        columns = [row[0] for row in result]

        if columns:
            return {
                "constrained_columns": columns,
                "name": None,
            }
        else:
            return {"constrained_columns": [], "name": None}

    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        """Return foreign key information for the given table."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
            SELECT
                column_name,
                reference_table_schema,
                reference_table_name,
                reference_column_name,
                constraint_name
            FROM v_catalog.foreign_keys
            WHERE table_schema = :schema
            AND table_name = :table_name
            ORDER BY constraint_name, ordinal_position
            """)

        result = connection.execute(query, {"schema": schema, "table_name": table_name})
        fk_map = {}

        for row in result:
            name = row[4]
            if name not in fk_map:
                fk_map[name] = {
                    "name": name,
                    "constrained_columns": [],
                    "referred_schema": row[1],
                    "referred_table": row[2],
                    "referred_columns": [],
                }
            fk_map[name]["constrained_columns"].append(row[0])
            fk_map[name]["referred_columns"].append(row[3])

        return list(fk_map.values())

    def has_table(self, connection, table_name, schema=None, **kw):
        """Check if a table exists."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
            SELECT COUNT(*)
            FROM v_catalog.tables
            WHERE table_schema = :schema
            AND table_name = :table_name
            """)

        result = connection.execute(query, {"schema": schema, "table_name": table_name})
        return result.scalar() > 0

    def has_sequence(self, connection, sequence_name, schema=None, **kw):
        """Check if a sequence exists. Vertica doesn't support sequences."""
        return False

    def get_sequence_names(self, connection, schema=None, **kw):
        """Return sequence names. Vertica doesn't support sequences."""
        return []
