# -*- coding: utf-8 -*-
import logging
from importlib.metadata import version as _get_version
from typing import Any, Optional, Sequence, Type, Union

from bson.codec_options import TypeRegistry
from pymongo import MongoClient
from pymongo.client_session import ClientSession
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.driver_info import DriverInfo
from pymongo.errors import ConnectionFailure

from . import __version__
from .common import BaseCursor
from .cursor import Cursor
from .error import DatabaseError, OperationalError
from .helper import ConnectionHelper
from .retry import RetryConfig, execute_with_retry

try:
    _VERSION = _get_version("pymongosql")
except Exception:
    _VERSION = __version__

_DRIVER_INFO = DriverInfo(name="PyMongoSQL", version=_VERSION)


_logger = logging.getLogger(__name__)


class Connection:
    """MongoDB connection wrapper that provides SQL-like interface"""

    def __init__(
        self,
        host: Optional[Union[str, Sequence[str]]] = None,
        port: Optional[int] = None,
        document_class: Optional[Type[Any]] = None,
        tz_aware: Optional[bool] = None,
        connect: Optional[bool] = None,
        type_registry: Optional[TypeRegistry] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize MongoDB connection with full PyMongo Client compatibility.

        This constructor has the exact same signature as PyMongo's MongoClient
        to ensure full compatibility. All parameters are passed through directly
        to the underlying MongoClient.

        Supports connection string patterns:
        - mongodb://host:port/database - Core driver (no subquery support)
        - mongodb+srv://host:port/database - Cloud/SRV connection string
        - mongodb://host:port/database?mode=superset - Superset driver with subquery support
        - mongodb+srv://host:port/database?mode=superset - Cloud SRV with superset mode

        Mode is specified via the ?mode= query parameter. If not specified, defaults to "standard".

        See PyMongo MongoClient documentation for full parameter details.
        https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/mongoclient/
        """
        # Check if connection string specifies mode
        connection_string = host if isinstance(host, str) else None
        mode, db_from_uri, host = ConnectionHelper.parse_connection_string(connection_string)

        self._mode = kwargs.pop("mode", None)
        if not self._mode and mode:
            self._mode = mode

        # Retry behavior for transient system-level PyMongo failures.
        # These kwargs are consumed by PyMongoSQL and are not passed to MongoClient.
        self._retry_config = RetryConfig.from_kwargs(kwargs)

        # Extract commonly used parameters for backward compatibility
        self._host = host or "localhost"
        self._port = port or 27017

        # Handle database parameter separately (not a MongoClient parameter)
        # Explicit 'database' parameter takes precedence over database in URI
        self._database_name = kwargs.pop("database", None)
        if not self._database_name and db_from_uri:
            self._database_name = db_from_uri

        # Store all PyMongo parameters to pass through directly
        self._pymongo_params = kwargs.copy()

        # Add explicit parameters to kwargs for MongoClient
        if host is not None:
            self._pymongo_params["host"] = host
        if port is not None:
            self._pymongo_params["port"] = port
        if document_class is not None:
            self._pymongo_params["document_class"] = document_class
        if tz_aware is not None:
            self._pymongo_params["tz_aware"] = tz_aware
        if connect is not None:
            self._pymongo_params["connect"] = connect
        if type_registry is not None:
            self._pymongo_params["type_registry"] = type_registry

        # Inject MongoDB client metadata so the handshake identifies this library
        if "driver" not in self._pymongo_params:
            self._pymongo_params["driver"] = _DRIVER_INFO

        # Connection state
        self._autocommit = True
        self._in_transaction = False
        self._client: Optional[MongoClient] = None
        self._database: Optional[Database] = None
        self._session: Optional[ClientSession] = None
        self.cursor_pool = []
        self.cursor_class = Cursor
        self.cursor_kwargs = {}

        # Establish connection - respect connect parameter (default is True in PyMongo)
        if connect is not False:  # Connect by default, unless explicitly set to False
            self._connect()
        else:
            # Just create the client without testing connection
            self._client = MongoClient(**self._pymongo_params)
            # Initialize the database according to explicit parameter or client's default
            self._init_database()

    def _connect(self) -> None:
        """Establish connection to MongoDB"""
        try:
            # Create client with all PyMongo parameters - PyMongo handles connection string building internally
            # We pass all parameters directly to match MongoClient behavior exactly
            self._client = MongoClient(**self._pymongo_params)

            # Test connection
            execute_with_retry(
                lambda: self._client.admin.command("ping"),
                self._retry_config,
                "initial MongoDB ping",
            )

            # Initialize the database according to explicit parameter or client's default
            # This may raise OperationalError if no database could be determined; allow it to bubble up
            self._init_database()

            _logger.info(f"Successfully connected to MongoDB at {self._host}:{self._port}")

        except OperationalError:
            # Allow OperationalError (e.g., no database selected) to propagate unchanged
            raise
        except ConnectionFailure as e:
            _logger.error(f"Failed to connect to MongoDB: {e}")
            raise OperationalError(f"Could not connect to MongoDB: {e}")
        except Exception as e:
            _logger.error(f"Unexpected error during connection: {e}")
            raise DatabaseError(f"Database connection error: {e}")

    def _init_database(self) -> None:
        """Internal helper to initialize `self._database`.

        Behavior:
        - If `database` parameter was provided explicitly, use that database name.
        - Otherwise, try to use the MongoClient's default database (from the URI path).
          If no default is set, leave `self._database` as None.
        """
        if self._client is None:
            self._database = None
            return

        if self._database_name is not None:
            # Explicit database parameter takes precedence
            try:
                self._database = self._client.get_database(self._database_name)
            except Exception:
                # Fallback to subscription style access
                self._database = self._client[self._database_name]
        else:
            # No explicit database; try to get client's default
            try:
                self._database = self._client.get_default_database()
            except Exception:
                # PyMongo can raise various exceptions for missing database
                self._database = None

        # Enforce that a database must be selected
        if self._database is None:
            raise OperationalError(
                "No database selected. Provide 'database' parameter or include a database in the URI path."
            )

    @property
    def client(self) -> MongoClient:
        """Get the PyMongo client"""
        if self._client is None:
            raise OperationalError("No active connection")
        return self._client

    @property
    def database(self) -> Database:
        """Get the current database"""
        if self._database is None:
            raise OperationalError("No database selected")
        return self._database

    @property
    def mode(self) -> str:
        """Get the specified mode"""
        return self._mode

    @property
    def retry_config(self) -> RetryConfig:
        """Get retry configuration used for transient system-level errors."""
        return self._retry_config

    def use_database(self, database_name: str) -> None:
        """Switch to a different database"""
        if self._client is None:
            raise OperationalError("No active connection")
        self._database_name = database_name
        self._database = self._client[database_name]
        _logger.info(f"Switched to database: {database_name}")

    def get_collection(self, collection_name: str) -> Collection:
        """Get a collection from the current database"""
        if self._database is None:
            raise OperationalError("No database selected")
        return self._database[collection_name]

    @property
    def autocommit(self) -> bool:
        return self._autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        try:
            if not self._autocommit and value:
                self._autocommit = True
                for cursor_ in self.cursor_pool:
                    cursor_.flush()
        finally:
            self._autocommit = value

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    @in_transaction.setter
    def in_transaction(self, value: bool) -> None:
        self._in_transaction = value

    @property
    def host(self) -> str:
        """Get the MongoDB connection string/URL used by PyMongo"""
        if self._client is None:
            # If not connected yet, construct basic connection string
            if isinstance(self._host, str):
                return f"mongodb://{self._host}:{self._port}"
            elif isinstance(self._host, list):
                hosts = [f"{h}:{self._port}" if ":" not in str(h) else str(h) for h in self._host]
                return f"mongodb://{','.join(hosts)}"
            else:
                return f"mongodb://localhost:{self._port}"
        else:
            # Return the actual connection string from PyMongo client
            # PyMongo stores the connection info in the client
            nodes = self._client.nodes
            if nodes:
                # Get primary node or first available node
                node = next(iter(nodes))
                return f"mongodb://{node[0]}:{node[1]}"
            else:
                # Fallback to original host/port
                return f"mongodb://{self._host}:{self._port}"

    @property
    def port(self) -> int:
        """Get the port number"""
        return self._port

    @property
    def database_name(self) -> str:
        """Get the database name"""
        return self._database_name

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # If there's an active transaction, abort it on exception
        if exc_type is not None and self._session and self._session.in_transaction:
            try:
                self._abort_transaction()
            except Exception as e:
                _logger.error(f"Error aborting transaction during exit: {e}")
        self.close()

    @property
    def is_connected(self) -> bool:
        """Check if connected to MongoDB"""
        return self._client is not None

    @property
    def database_instance(self):
        """Get the database instance"""
        return self._database

    @property
    def session(self) -> Optional[ClientSession]:
        """Get the current session"""
        return self._session

    def disconnect(self) -> None:
        """Disconnect from MongoDB (alias for close)"""
        self.close()

    def __str__(self) -> str:
        """String representation of the connection"""
        status = "connected" if self.is_connected else "disconnected"
        return f"Connection(host={self._host}, port={self._port}, database={self._database_name}, status={status})"

    def cursor(self, cursor: Optional[Type[BaseCursor]] = None, **kwargs) -> BaseCursor:
        kwargs.update(self.cursor_kwargs)
        if not cursor:
            cursor = self.cursor_class

        new_cursor = cursor(
            connection=self,
            mode=self._mode,
            **kwargs,
        )
        self.cursor_pool.append(new_cursor)
        return new_cursor

    def close(self) -> None:
        """Close the MongoDB connection"""
        try:
            # Close all cursors
            for cursor in self.cursor_pool:
                cursor.close()
            self.cursor_pool.clear()

            # End session if active
            if self._session is not None:
                self._end_session()

            # Close client connection
            if self._client:
                self._client.close()
                self._client = None
                self._database = None

            _logger.info("MongoDB connection closed")
        except Exception as e:
            _logger.error(f"Error closing connection: {e}")

    def _start_session(self, **kwargs) -> ClientSession:
        """Start a new PyMongo session (internal method)

        Args:
            **kwargs: Additional options for session creation (causal_consistency, default_transaction_options, etc.)

        Returns:
            ClientSession: PyMongo session object
        """
        if self._client is None:
            raise OperationalError("No active connection")

        session = execute_with_retry(
            lambda: self._client.start_session(**kwargs),
            self._retry_config,
            "start MongoDB session",
        )
        self._session = session
        _logger.info("Started new MongoDB session")
        return session

    def _end_session(self) -> None:
        """End the current session (internal method)"""
        if self._session is not None:
            execute_with_retry(
                lambda: self._session.end_session(),
                self._retry_config,
                "end MongoDB session",
            )
            self._session = None
            _logger.info("Ended MongoDB session")

    def _start_transaction(self, **kwargs) -> None:
        """Start a transaction within the current session (internal method)

        Args:
            **kwargs: Transaction options (read_concern, write_concern, read_preference, max_commit_time_ms)
        """
        if self._session is None:
            # Auto-create session if not exists
            self._start_session()

        if self._session is None:
            raise OperationalError("No active session")

        execute_with_retry(
            lambda: self._session.start_transaction(**kwargs),
            self._retry_config,
            "start MongoDB transaction",
        )
        self._in_transaction = True
        self._autocommit = False
        _logger.info("Started MongoDB transaction")

    def _commit_transaction(self) -> None:
        """Commit the current transaction (internal method)"""
        if self._session is None:
            raise OperationalError("No active session")

        if not self._session.in_transaction:
            raise OperationalError("No active transaction to commit")

        execute_with_retry(
            lambda: self._session.commit_transaction(),
            self._retry_config,
            "commit MongoDB transaction",
        )
        self._in_transaction = False
        self._autocommit = True
        _logger.info("Committed MongoDB transaction")

    def _abort_transaction(self) -> None:
        """Abort the current transaction (internal method)"""
        if self._session is None:
            raise OperationalError("No active session")

        if not self._session.in_transaction:
            raise OperationalError("No active transaction to abort")

        execute_with_retry(
            lambda: self._session.abort_transaction(),
            self._retry_config,
            "abort MongoDB transaction",
        )
        self._in_transaction = False
        self._autocommit = True
        _logger.info("Aborted MongoDB transaction")

    def _with_transaction(self, callback, **kwargs):
        """Execute a callback within a transaction (internal method)

        Args:
            callback: Function to execute within transaction
            **kwargs: Transaction options

        Returns:
            Result of callback function
        """
        if self._session is None:
            self._start_session()

        if self._session is None:
            raise OperationalError("No active session")

        return self._session.with_transaction(callback, **kwargs)

    def begin(self) -> None:
        """Begin transaction (DB-API 2.0 standard method)

        Starts an explicit transaction. After calling begin(), operations
        are executed within the transaction context until commit() or
        rollback() is called. Requires MongoDB 4.0+ for multi-document
        transactions on replica sets or sharded clusters.

        Example:
            conn.begin()
            try:
                cursor.execute("INSERT INTO users VALUES (...)")
                cursor.execute("UPDATE accounts SET balance = balance - 100")
                conn.commit()
            except Exception:
                conn.rollback()

        Raises:
            OperationalError: If unable to start transaction
        """
        self._start_transaction()

    def commit(self) -> None:
        """Commit transaction (DB-API 2.0 standard method)

        Commits the current transaction to the database. All operations
        executed since begin() will be atomically persisted. If no
        transaction is active, this is a no-op (DB-API 2.0 compliant).

        Raises:
            OperationalError: If commit fails
        """
        if self._session and self._session.in_transaction:
            self._commit_transaction()
        # If no transaction, this is a no-op (DB-API 2.0 compliant)

    def rollback(self) -> None:
        """Rollback transaction (DB-API 2.0 standard method)

        Rolls back (aborts) the current transaction, undoing all operations
        executed since begin(). If no transaction is active, this is a no-op
        (DB-API 2.0 compliant).

        Raises:
            OperationalError: If rollback fails
        """
        if self._session and self._session.in_transaction:
            self._abort_transaction()
        # If no transaction, this is a no-op (DB-API 2.0 compliant)

    def test_connection(self) -> bool:
        """Test if the connection is alive"""
        try:
            if self._client:
                execute_with_retry(
                    lambda: self._client.admin.command("ping"),
                    self._retry_config,
                    "connection health check ping",
                )
                return True
            return False
        except Exception as e:
            _logger.error(f"Connection test failed: {e}")
            return False

    def session_context(self, **kwargs):
        """Context manager for session handling

        Usage:
            with conn.session_context() as session:
                # operations with session
                pass
        """
        return SessionContext(self, **kwargs)


class SessionContext:
    """Context manager for PyMongo sessions"""

    def __init__(self, connection: Connection, **session_kwargs):
        self.connection = connection
        self.session_kwargs = session_kwargs
        self.session = None

    def __enter__(self) -> ClientSession:
        self.session = self.connection._start_session(**self.session_kwargs)
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            # If there's an exception and an active transaction, abort it
            if exc_type is not None and self.session.in_transaction:
                try:
                    self.session.abort_transaction()
                except Exception as e:
                    _logger.error(f"Error aborting transaction: {e}")

            # End the session
            self.connection._end_session()

    def transaction(self, **transaction_kwargs):
        """Start a transaction context within this session

        Usage:
            with conn.session_context() as session:
                with session_context.transaction():
                    # operations within transaction
                    pass
        """
        return TransactionContext(self.connection, **transaction_kwargs)


class TransactionContext:
    """Context manager for PyMongo transactions"""

    def __init__(self, connection: Connection, **transaction_kwargs):
        self.connection = connection
        self.transaction_kwargs = transaction_kwargs

    def __enter__(self):
        self.connection._start_transaction(**self.transaction_kwargs)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Exception occurred, abort transaction
            try:
                self.connection._abort_transaction()
            except Exception as e:
                _logger.error(f"Error aborting transaction: {e}")
        else:
            # No exception, commit transaction
            try:
                self.connection._commit_transaction()
            except Exception as e:
                _logger.error(f"Error committing transaction: {e}")
                # Try to abort after failed commit
                try:
                    self.connection._abort_transaction()
                except Exception:
                    pass
                raise
