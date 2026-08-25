"""
SQLAlchemy dialect for OpenSearch.

This module provides a SQLAlchemy dialect that uses the OpenSearch Python client
for database connections and SQL query execution.
"""

import logging

from sqlalchemy import __version__ as sqlalchemy_version
from sqlalchemy.engine.default import DefaultDialect

logger = logging.getLogger(__name__)


# Simple version comparison without packaging dependency
def _version_tuple(version_str):
    """Convert version string to tuple for comparison."""
    return tuple(map(int, version_str.split(".")[:3]))


class OpenSearchDialect(DefaultDialect):
    """
    SQLAlchemy dialect for OpenSearch using the Python client.

    This dialect provides SQL interface to OpenSearch through its SQL plugin,
    using the opensearch-py client for connections.
    """

    name = "opensearch"
    driver = "opensearch"

    # Enable statement caching for better performance
    supports_statement_cache = True

    # OpenSearch SQL plugin provides reliable rowcount for some operations
    supports_sane_rowcount = True
    supports_sane_multi_rowcount = False

    # Result set handling
    supports_empty_insert = False  # OpenSearch doesn't support traditional INSERT
    supports_multivalues_insert = False

    # OpenSearch doesn't support traditional database features
    supports_sequences = False
    supports_native_boolean = True
    supports_native_decimal = True
    supports_alter = False  # OpenSearch doesn't support ALTER TABLE
    supports_foreign_keys = False  # OpenSearch doesn't support foreign keys
    supports_pk_autoincrement = False  # OpenSearch doesn't support autoincrement

    # Default schema/index name
    default_schema_name = "_all"

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
        from .dbapi.client import OpenSearchClient, create_client
        from .dbapi.connection import Connection
        from .dbapi.connection_params import (
            ConnectionParams,
            create_connection_params,
            parse_connection_url,
        )
        from .dbapi.cursor import Cursor
        from .dbapi.exceptions import (
            AuthenticationError,
            DatabaseError,
            DataError,
            Error,
            IntegrityError,
            InterfaceError,
            InternalError,
            InvalidParameterError,
            NotSupportedError,
            OpenSearchConnectionError,
            OperationalError,
            ProgrammingError,
            QueryExecutionError,
            TransientError,
            Warning,
        )

        def connect(*cargs, **cparams):
            """
            Create a connection to OpenSearch.

            This method is called by SQLAlchemy to create connections.

            Args:
                *cargs: Positional arguments (typically empty)
                **cparams: Connection parameters from URL and connect_args

            Returns:
                Connection: A DB-API 2.0 compatible connection object
            """
            from .dbapi.connection import Connection

            return Connection(**cparams)

        # Create a module-like object with the necessary attributes
        class DBAPIModule:
            def __init__(self):
                self.Connection = Connection
                self.Cursor = Cursor
                self.ConnectionParams = ConnectionParams
                self.create_connection_params = create_connection_params
                self.parse_connection_url = parse_connection_url
                self.OpenSearchClient = OpenSearchClient
                self.create_client = create_client
                self.connect = connect
                self.Error = Error
                self.Warning = Warning
                self.InterfaceError = InterfaceError
                self.DatabaseError = DatabaseError
                self.DataError = DataError
                self.OperationalError = OperationalError
                self.IntegrityError = IntegrityError
                self.InternalError = InternalError
                self.ProgrammingError = ProgrammingError
                self.NotSupportedError = NotSupportedError
                self.AuthenticationError = AuthenticationError
                self.ConnectionError = OpenSearchConnectionError
                self.QueryExecutionError = QueryExecutionError
                self.InvalidParameterError = InvalidParameterError
                self.TransientError = TransientError
                self.apilevel = "2.0"
                self.threadsafety = 1
                self.paramstyle = "named"

        return DBAPIModule()

    def create_connect_args(self, url):
        """
        Create connection arguments from SQLAlchemy URL.

        Supports connection strings like:
        - opensearch://user:password@host:port/index
        - opensearch://user:password@host/index (defaults to port 443)

        Args:
            url: SQLAlchemy URL object

        Returns:
            tuple: (args, kwargs) for connection creation
        """
        # Start with basic URL components
        opts = {}

        # Extract host and port with sensible defaults for AWS OpenSearch
        if url.host:
            opts["host"] = url.host
        else:
            opts["host"] = "localhost"

        if url.port:
            opts["port"] = url.port
        else:
            opts["port"] = 443  # Default OpenSearch port

        # Extract credentials
        if url.username:
            opts["username"] = url.username
        if url.password:
            opts["password"] = url.password

        # Extract index from path (database in SQLAlchemy terms)
        if url.database:
            opts["index"] = url.database
        else:
            opts["index"] = "_all"  # Default to all indices

        # Extract query parameters
        if url.query:
            for key, value in url.query.items():
                opts[key] = value[-1] if isinstance(value, tuple) else value

        # Set sensible defaults for OpenSearch if not specified
        if "use_ssl" not in opts:
            opts["use_ssl"] = True  # Default to SSL for AWS OpenSearch
        else:
            opts["use_ssl"] = opts["use_ssl"].lower() in ("true", "1", "yes")

        if "verify_certs" not in opts:
            opts["verify_certs"] = True  # Always verify certificates for security
        else:
            opts["verify_certs"] = opts["verify_certs"].lower() in ("true", "1", "yes")

        if "timeout" not in opts:
            opts["timeout"] = 30  # 30 second timeout
        else:
            opts["timeout"] = int(opts["timeout"])

        if "max_retries" not in opts:
            opts["max_retries"] = 3  # Retry up to 3 times
        else:
            opts["max_retries"] = int(opts["max_retries"])

        # Return empty args list and connection parameters
        return ([], opts)

    def connect(self, *cargs, **cparams):
        """
        Create a connection to OpenSearch.

        This method is called by SQLAlchemy to create connections.

        Args:
            *cargs: Positional arguments (typically empty)
            **cparams: Connection parameters from URL and connect_args

        Returns:
            Connection: A DB-API 2.0 compatible connection object
        """
        # Import here to avoid circular imports
        try:
            from .dbapi.connection import Connection
        except ImportError:
            try:
                from sagemaker_studio.sql_engine._sqlalchemy_opensearch.dbapi.connection import (
                    Connection,
                )
            except ImportError:
                # Use the Connection from our DBAPI module
                Connection = self.dbapi.Connection

        # Create connection using our DBAPI
        return Connection(**cparams)

    def _get_server_version_info(self, connection):
        """
        Get server version information.

        Returns a default version since OpenSearch version detection
        would require additional API calls.
        """
        # Return a reasonable default OpenSearch version
        return (2, 0, 0)  # Represents OpenSearch 2.0.0

    def _get_default_schema_name(self, connection):
        """
        Get the default schema name (index pattern).

        For OpenSearch, we use the index specified in connection or _all.
        """
        try:
            # Get the index from connection parameters
            if hasattr(connection, "connection_params"):
                return connection.connection_params.index
            return "_all"
        except Exception:
            return "_all"

    def initialize(self, connection):
        """
        Initialize the dialect.

        Override to set OpenSearch-specific properties.
        """
        # Call the base DefaultDialect.initialize
        super().initialize(connection)

        # Set OpenSearch-specific properties
        self.server_version_info = self._get_server_version_info(connection)
        self.default_schema_name = self._get_default_schema_name(connection)

        # Set OpenSearch-specific dialect properties
        self.supports_sequences = False
        self.supports_native_boolean = True
        self.supports_native_decimal = True

    def do_rollback(self, dbapi_connection):
        """Rollback a transaction - OpenSearch doesn't support transactions."""
        # OpenSearch doesn't support transactions, so this is a no-op
        pass

    def do_commit(self, dbapi_connection):
        """Commit a transaction - OpenSearch doesn't support transactions."""
        # OpenSearch doesn't support transactions, so this is a no-op
        pass

    def do_close(self, dbapi_connection):
        """Close a connection."""
        dbapi_connection.close()

    def get_schema_names(self, connection, **kw):
        """Return a list of index patterns available in OpenSearch."""
        from sqlalchemy import text

        # Use OpenSearch SQL to get indices
        query = text("SHOW TABLES")
        try:
            result = connection.execute(query)
            return [row[0] for row in result]
        except Exception:
            logger.warning("SHOW TABLES failed, returning empty schema list", exc_info=True)
            return []

    def get_table_names(self, connection, schema=None, **kw):
        """Return a list of table names (indices) in the given schema."""
        # In OpenSearch, tables are indices
        return self.get_schema_names(connection, **kw)

    def get_view_names(self, connection, schema=None, **kw):
        """Return a list of view names - OpenSearch doesn't have views."""
        return []

    def get_columns(self, connection, table_name, schema=None, **kw):
        """Return column information for the given table (index)."""
        from sqlalchemy import text

        try:
            # DESCRIBE is a metadata command that doesn't support bind
            # parameters, so we sanitize the identifier to prevent injection.
            if not table_name.replace("_", "").replace("-", "").replace(".", "").isalnum():
                raise ValueError(f"Invalid table name: {table_name}")
            query = text(f"DESCRIBE `{table_name}`")
            result = connection.execute(query)
            columns = []

            for row in result:
                col_name = row[0]
                col_type = row[1] if len(row) > 1 else "text"

                # Convert OpenSearch types to SQLAlchemy types
                type_obj = self._get_column_type(col_type)

                column_info = {
                    "name": col_name,
                    "type": type_obj,
                    "nullable": True,  # OpenSearch fields are generally nullable
                    "default": None,
                    "autoincrement": False,
                    "comment": None,
                }
                columns.append(column_info)

            return columns
        except Exception:
            # If DESCRIBE fails, return empty list
            return []

    def _get_column_type(self, type_name):
        """Convert OpenSearch data type to SQLAlchemy type."""
        from sqlalchemy import types

        from .types import NESTED, OBJECT

        type_name = type_name.lower()

        # Handle OpenSearch-specific types
        if type_name == "object":
            return OBJECT()
        elif type_name == "nested":
            return NESTED()

        # Handle standard types
        type_map = {
            "text": types.Text,
            "keyword": types.String,
            "long": types.BigInteger,
            "integer": types.Integer,
            "short": types.SmallInteger,
            "byte": types.SmallInteger,
            "double": types.Float,
            "float": types.Float,
            "half_float": types.Float,
            "scaled_float": types.Float,
            "boolean": types.Boolean,
            "date": types.DateTime,
            "binary": types.LargeBinary,
            "ip": types.String,
            "geo_point": types.String,
            "geo_shape": types.String,
        }

        return type_map.get(type_name, types.Text)()

    def get_indexes(self, connection, table_name, schema=None, **kw):
        """Return index information - OpenSearch doesn't have traditional indexes."""
        return []

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        """Return primary key constraint - OpenSearch uses _id field."""
        # OpenSearch documents have an implicit _id field as primary key
        return {
            "constrained_columns": ["_id"],
            "name": None,
        }

    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        """Return foreign key information - OpenSearch doesn't support foreign keys."""
        return []


# Register the dialect when the module is imported (for tests)
def _register_dialect():
    """Register the dialect with SQLAlchemy."""
    try:
        from sqlalchemy.dialects import registry

        registry.register(
            "opensearch",
            "sagemaker_studio.sql_engine._sqlalchemy_opensearch.dialect",
            "OpenSearchDialect",
        )
    except ImportError:
        pass


_register_dialect()
