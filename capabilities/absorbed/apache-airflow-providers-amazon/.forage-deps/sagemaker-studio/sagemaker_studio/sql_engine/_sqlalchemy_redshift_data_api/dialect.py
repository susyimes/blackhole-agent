"""
SQLAlchemy dialect for Redshift Data API.

This module provides a SQLAlchemy dialect that uses the AWS Redshift Data API
for database connections instead of direct TCP connections.
"""

from sqlalchemy import __version__ as sqlalchemy_version
from sqlalchemy.dialects.postgresql.base import PGDialect


# Simple version comparison without packaging dependency
def _version_tuple(version_str):
    """Convert version string to tuple for comparison."""
    return tuple(map(int, version_str.split(".")[:3]))


class RedshiftDataAPIDialect(PGDialect):
    """
    SQLAlchemy dialect for Amazon Redshift using the Data API.

    This dialect inherits from PostgreSQL dialect since Redshift
    is PostgreSQL-compatible, but uses the Data API for connections.
    """

    name = "redshift_data_api"
    driver = "redshift_data_api"

    # Enable statement caching for better performance
    supports_statement_cache = True

    # Rowcount support - Redshift Data API provides reliable rowcount for DML operations
    supports_sane_rowcount = True  # Whether rowcount is reliable for single statements
    supports_sane_multi_rowcount = False  # Redshift doesn't support multi-statement rowcount

    # Result set handling
    supports_empty_insert = True  # Support INSERT without VALUES
    supports_multivalues_insert = True  # Support INSERT with multiple value sets

    # Redshift version info (we'll use a default since Data API doesn't expose this easily)
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

        # Store our dbapi module before calling super().__init__
        self._our_dbapi = None

        super().__init__(**kwargs)

        # After parent init, restore our dbapi implementation
        self._our_dbapi = self.import_dbapi()

    @property
    def dbapi(self):
        """Return the DBAPI module."""
        if self._our_dbapi is not None:
            return self._our_dbapi
        return self.import_dbapi()

    @dbapi.setter
    def dbapi(self, value):
        """Setter for dbapi - ignore attempts to set it to None from parent class."""
        # The parent class tries to set this to None, but we want to keep our implementation
        if value is None:
            # Ignore None assignments from parent class
            pass
        else:
            # Allow setting to actual DBAPI modules
            self._our_dbapi = value

    @classmethod
    def import_dbapi(cls):
        """Return the DBAPI module."""
        from . import dbapi

        return dbapi

    def create_connect_args(self, url):
        """
        Create connection arguments from SQLAlchemy URL.

        Supports both provisioned and serverless connection strings:
        - Provisioned: redshift_data_api://cluster_identifier/database
        - Serverless: redshift_data_api:///database

        Also handles connect_args parameter as alternative to query parameters.

        Args:
            url: SQLAlchemy URL object

        Returns:
            tuple: (args, kwargs) for connection creation
        """
        # Start with basic URL components
        opts = {}

        # Extract database from path
        if url.database:
            opts["database_name"] = url.database
        else:
            raise ValueError("Database name must be specified in connection URL")

        # Handle provisioned vs serverless based on host presence
        if url.host:
            # Provisioned cluster format: redshift_data_api://cluster_identifier/database
            opts["cluster_identifier"] = url.host
        else:
            # Serverless format: redshift_data_api:///database
            # cluster_identifier will be None, workgroup_name should be in query params
            pass

        # Extract query parameters
        if url.query:
            opts.update(url.query)

        # Set default region if not specified
        if "region" not in opts:
            opts["region"] = "us-east-1"

        # Validate required parameters based on configuration type
        if url.host:
            # Provisioned cluster - cluster_identifier is required and should not be empty
            if not opts.get("cluster_identifier"):
                raise ValueError(
                    "cluster_identifier is required for provisioned cluster configuration"
                )
        else:
            # Serverless - workgroup_name is required
            if "workgroup_name" not in opts or not opts["workgroup_name"]:
                raise ValueError("workgroup_name is required for serverless configuration")

        # Return empty args list and connection parameters
        return ([], opts)

    def connect(self, *cargs, **cparams):
        """
        Create a connection to the database.

        This method is called by SQLAlchemy to create connections.
        It handles both URL parameters and connect_args.

        Args:
            *cargs: Positional arguments (typically empty)
            **cparams: Connection parameters from URL and connect_args

        Returns:
            Connection: A DB-API 2.0 compatible connection object
        """
        # Import here to avoid circular imports
        from .dbapi import Connection

        # Create connection using our DBAPI
        return Connection(**cparams)

    def _get_server_version_info(self, connection):
        """
        Get server version information.

        Since the Data API doesn't easily expose version info,
        we'll return a default Redshift version.
        """
        # Return a reasonable default Redshift version
        # This is used by SQLAlchemy for feature detection
        return (1, 0, 32321)  # Represents Redshift 1.0.32321

    def _get_default_schema_name(self, connection):
        """
        Get the default schema name.

        Override the PostgreSQL dialect's implementation to handle
        the Data API's asynchronous nature properly.
        """
        try:
            # Execute the query using our cursor implementation
            from sqlalchemy import text

            result = connection.execute(text("SELECT current_schema()"))
            schema_name = result.scalar()
            return schema_name if schema_name else "public"
        except Exception:
            # If we can't get the schema name, default to 'public'
            # This is the standard default schema in Redshift
            return "public"

    def initialize(self, connection):
        """
        Initialize the dialect.

        Override PostgreSQL's initialize method to avoid setting
        PostgreSQL-specific parameters that Redshift doesn't support.
        """
        # Call the base DefaultDialect.initialize, not PGDialect.initialize
        # This avoids PostgreSQL-specific initialization
        from sqlalchemy.engine.default import DefaultDialect

        DefaultDialect.initialize(self, connection)

        # Set Redshift-specific properties
        self.server_version_info = self._get_server_version_info(connection)
        self.default_schema_name = self._get_default_schema_name(connection)

        # Set Redshift-specific dialect properties
        self.supports_smallserial = False  # Redshift doesn't support SMALLSERIAL
        self.supports_sequences = False  # Redshift doesn't support sequences
        self.supports_native_boolean = True
        self.supports_native_decimal = True

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
FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
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
FROM information_schema.tables
WHERE table_schema = %s
AND table_type = 'BASE TABLE'
ORDER BY table_name
""")
        result = connection.execute(query, (schema,))
        return [row[0] for row in result]

    def get_view_names(self, connection, schema=None, **kw):
        """Return a list of view names in the given schema."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
SELECT table_name
FROM information_schema.views
WHERE table_schema = %s
ORDER BY table_name
""")
        result = connection.execute(query, (schema,))
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
FROM information_schema.columns
WHERE table_schema = %s
AND table_name = %s
ORDER BY ordinal_position
""")

        result = connection.execute(query, (schema, table_name))
        columns = []

        for row in result:
            col_name = row[0]
            col_type = row[1]
            nullable = row[2] == "YES"
            default = row[3]
            char_max_length = row[4]
            numeric_precision = row[5]
            numeric_scale = row[6]

            # Convert Redshift/PostgreSQL types to SQLAlchemy types
            type_obj = self._get_column_type(
                col_type, char_max_length, numeric_precision, numeric_scale
            )

            column_info = {
                "name": col_name,
                "type": type_obj,
                "nullable": nullable,
                "default": default,
                "autoincrement": False,  # Redshift doesn't have true autoincrement
                "comment": None,
            }
            columns.append(column_info)

        return columns

    def _get_column_type(
        self, type_name, char_max_length=None, numeric_precision=None, numeric_scale=None
    ):
        """Convert Redshift data type to SQLAlchemy type."""
        from sqlalchemy import types

        from .types import GEOMETRY, SUPER

        type_name = type_name.lower()

        # Handle Redshift-specific types
        if type_name == "super":
            return SUPER()
        elif type_name == "geometry":
            return GEOMETRY()

        # Handle standard PostgreSQL/Redshift types
        type_map = {
            "smallint": types.SmallInteger,
            "integer": types.Integer,
            "bigint": types.BigInteger,
            "decimal": types.Numeric,
            "numeric": types.Numeric,
            "real": types.Float,
            "double precision": types.Float,
            "boolean": types.Boolean,
            "char": types.CHAR,
            "character": types.CHAR,
            "varchar": types.VARCHAR,
            "character varying": types.VARCHAR,
            "text": types.Text,
            "date": types.Date,
            "timestamp": types.TIMESTAMP,
            "timestamp without time zone": types.TIMESTAMP,
            "timestamp with time zone": types.TIMESTAMP,
            "time": types.Time,
            "time without time zone": types.Time,
            "time with time zone": types.Time,
        }

        if type_name in type_map:
            type_class = type_map[type_name]

            # Handle types that need length/precision parameters
            if type_name in ("char", "character", "varchar", "character varying"):
                if char_max_length:
                    return type_class(char_max_length)
                else:
                    return type_class()
            elif type_name in ("decimal", "numeric"):
                if numeric_precision and numeric_scale:
                    return type_class(numeric_precision, numeric_scale)
                elif numeric_precision:
                    return type_class(numeric_precision)
                else:
                    return type_class()
            else:
                return type_class()

        # Default to Text for unknown types
        return types.Text()

    def get_indexes(self, connection, table_name, schema=None, **kw):
        """Return index information for the given table."""
        if schema is None:
            schema = self.default_schema_name

        # Redshift doesn't have traditional indexes like PostgreSQL
        # It uses sort keys and distribution keys instead
        # For compatibility, we'll return an empty list since Redshift
        # doesn't expose traditional index information through information_schema
        return []

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        """Return primary key constraint information for the given table."""
        if schema is None:
            schema = self.default_schema_name

        from sqlalchemy import text

        query = text("""
SELECT
    kcu.column_name,
    kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
    AND tc.table_name = kcu.table_name
WHERE tc.constraint_type = 'PRIMARY KEY'
    AND tc.table_schema = %s
    AND tc.table_name = %s
ORDER BY kcu.ordinal_position
""")

        result = connection.execute(query, (schema, table_name))
        columns = [row[0] for row in result]

        if columns:
            return {
                "constrained_columns": columns,
                "name": None,  # Redshift doesn't always name PK constraints
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
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
    AND tc.table_name = kcu.table_name
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema = %s
    AND tc.table_name = %s
ORDER BY kcu.ordinal_position
""")

        result = connection.execute(query, (schema, table_name))
        foreign_keys = []

        for row in result:
            fk_info = {
                "name": row[4],
                "constrained_columns": [row[0]],
                "referred_schema": row[1],
                "referred_table": row[2],
                "referred_columns": [row[3]],
            }
            foreign_keys.append(fk_info)

        return foreign_keys
