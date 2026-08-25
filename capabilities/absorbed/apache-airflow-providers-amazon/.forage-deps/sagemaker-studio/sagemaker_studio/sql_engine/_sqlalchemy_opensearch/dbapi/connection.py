"""
DB-API 2.0 Connection class for OpenSearch.

This module provides the Connection class that manages OpenSearch client
and implements basic DB-API 2.0 connection interface.
"""

from .client import OpenSearchClient
from .connection_params import create_connection_params
from .cursor import Cursor
from .exceptions import Error, InterfaceError, map_opensearch_exception


class Connection:
    """
    DB-API 2.0 Connection class for OpenSearch.

    This class manages the OpenSearch Python client and provides
    the standard DB-API 2.0 connection interface.
    """

    def __init__(self, host="localhost", port=443, index="_all", **kwargs):
        """
        Initialize connection with OpenSearch client management.

        Args:
            host: The OpenSearch host (defaults to 'localhost')
            port: The OpenSearch port (defaults to 443)
            index: The default index to query (defaults to '_all')
            **kwargs: Additional connection parameters:
                - username: Username for basic authentication
                - password: Password for basic authentication
                - use_ssl: Whether to use SSL/TLS
                - verify_certs: Whether to verify SSL certificates
                - ca_certs: Path to CA certificate file
                - client_cert: Path to client certificate file
                - client_key: Path to client key file
                - timeout: Request timeout in seconds
                - max_retries: Maximum number of retries
                - api_key: API key for authentication
                - api_key_id: API key ID for authentication
        """
        # Create connection parameters
        self.connection_params = create_connection_params(
            host=host, port=port, index=index, **kwargs
        )

        # Initialize the OpenSearch client with authentication and validation
        self.client_manager = OpenSearchClient(self.connection_params)

        # Connection state
        self._closed = False
        self.autocommit = True  # OpenSearch doesn't support transactions, always autocommit

    @property
    def client(self):
        """Get the OpenSearch client."""
        if self._closed:
            raise InterfaceError("Connection is closed")
        return self.client_manager.client

    def cursor(self):
        """
        Return a new cursor object.

        Returns:
            Cursor: A new cursor object for executing statements
        """
        if self._closed:
            raise InterfaceError("Connection is closed")
        return Cursor(self)

    def commit(self):
        """
        Commit current transaction.

        OpenSearch doesn't support transactions, so this is a no-op.
        """
        if self._closed:
            raise InterfaceError("Connection is closed")
        # OpenSearch doesn't support transactions, so this is a no-op
        pass

    def rollback(self):
        """
        Rollback current transaction.

        OpenSearch doesn't support transactions, so this is a no-op.
        """
        if self._closed:
            raise InterfaceError("Connection is closed")
        # OpenSearch doesn't support transactions, so this is a no-op
        pass

    def close(self):
        """
        Close the connection and clean up resources.
        """
        if not self._closed:
            self.client_manager.close()
            self._closed = True

    def is_closed(self):
        """Check if the connection is closed."""
        return self._closed

    def get_client_info(self):
        """Get information about the OpenSearch client and connection."""
        if self._closed:
            raise InterfaceError("Connection is closed")
        return self.client_manager.get_connection_info()

    def test_permissions(self):
        """Test OpenSearch permissions."""
        if self._closed:
            raise InterfaceError("Connection is closed")
        return self.client_manager.test_permissions()

    def execute_sql(self, query: str, parameters=None):
        """
        Execute a SQL query directly using the OpenSearch SQL plugin.

        Args:
            query: SQL query string
            parameters: Optional query parameters

        Returns:
            Dict containing query results

        Raises:
            DatabaseError: If query execution fails
            InterfaceError: If connection is closed
        """
        if self._closed:
            raise InterfaceError("Connection is closed")

        try:
            return self.client_manager.execute_sql(query, parameters)
        except Error:
            # Already a DB-API exception, re-raise as-is
            raise
        except Exception as e:
            mapped_exception = map_opensearch_exception(e)
            raise mapped_exception from e
