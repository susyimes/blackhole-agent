"""
OpenSearch client management and authentication.

This module handles the creation and management of OpenSearch Python clients,
including authentication and connection validation.
"""

from typing import Any, Dict

from .connection_params import ConnectionParams
from .exceptions import Error, InterfaceError, OperationalError


class OpenSearchClient:
    """
    Manages OpenSearch Python client with authentication and validation.

    This class handles:
    - OpenSearch client initialization with proper configuration
    - Authentication handling (basic auth, API keys)
    - Connection validation through test API calls
    - Error mapping from OpenSearch exceptions to DB-API exceptions
    """

    def __init__(self, connection_params: ConnectionParams):
        """
        Initialize the OpenSearch client.

        Args:
            connection_params: Connection parameters including host, auth, and SSL details

        Raises:
            InterfaceError: If client initialization fails
            OperationalError: If authentication fails
        """
        self.connection_params = connection_params
        self._client = None

        # Initialize the client
        self._initialize_client()

        # Validate the connection
        self._validate_connection()

    def _initialize_client(self):
        """
        Initialize the OpenSearch Python client with proper configuration.

        Supports multiple authentication methods:
        1. Basic authentication via username/password
        2. API key authentication via api_key/api_key_id
        3. No authentication (for development/testing)

        Raises:
            InterfaceError: If client initialization fails
            OperationalError: If credentials are invalid or missing
        """
        try:
            # Import OpenSearch client
            from opensearchpy import OpenSearch
        except ImportError as e:
            raise InterfaceError(
                f"OpenSearch Python client not available. Please install opensearch-py: {e}"
            )

        try:
            # Build client configuration
            client_config = self._build_client_config()

            # Create the OpenSearch client
            self._client = OpenSearch(**client_config)

        except Error:
            raise  # Don't re-wrap our own DB-API exceptions
        except Exception as e:
            raise InterfaceError(f"Failed to initialize OpenSearch client: {e}") from e

    def _build_client_config(self) -> Dict[str, Any]:
        """
        Build OpenSearch client configuration from connection parameters.

        Returns:
            Dict containing client configuration
        """
        params = self.connection_params

        # Base configuration
        config = {
            "hosts": [{"host": params.host, "port": params.port}],
            "timeout": params.timeout,
            "max_retries": params.max_retries,
            "use_ssl": params.use_ssl,
            "verify_certs": params.verify_certs,
        }

        # Add authentication if provided
        if params.username and params.password:
            config["http_auth"] = (params.username, params.password)
        elif params.api_key and params.api_key_id:
            config["api_key"] = (params.api_key_id, params.api_key)

        # Add SSL configuration if using SSL
        if params.use_ssl:
            if params.ca_certs:
                config["ca_certs"] = params.ca_certs
            if params.client_cert and params.client_key:
                config["client_cert"] = params.client_cert
                config["client_key"] = params.client_key

        return config

    def _get_auth_method_description(self) -> str:
        """
        Get a description of the authentication method being used.

        Returns:
            str: Human-readable description of the auth method
        """
        params = self.connection_params

        if params.username:
            return f"basic auth (user: {params.username})"
        elif params.api_key:
            return f"API key (id: {params.api_key_id})"
        else:
            return "no authentication"

    def _validate_connection(self):
        """
        Validate the connection by making a test API call.

        This method attempts to get cluster info to verify:
        1. Connection is successful
        2. Credentials are valid (if provided)
        3. OpenSearch is responding

        Raises:
            OperationalError: If connection validation fails
            AuthenticationError: If authentication fails
        """
        try:
            # Make a simple API call to validate the connection
            info = self._client.info()

            # Check if we got a valid response
            if not isinstance(info, dict) or "version" not in info:
                raise OperationalError("Invalid response from OpenSearch cluster")

        except Error:
            raise  # Don't re-wrap our own DB-API exceptions
        except Exception as e:
            # Map OpenSearch exceptions to appropriate DB-API exceptions
            from .exceptions import map_opensearch_exception

            execution_context = {
                "host": self.connection_params.host,
                "port": self.connection_params.port,
                "auth_method": self._get_auth_method_description(),
            }

            mapped_exception = map_opensearch_exception(e, execution_context)
            raise mapped_exception from e

    @property
    def client(self):
        """
        Get the OpenSearch client.

        Returns:
            OpenSearch: The initialized OpenSearch client
        """
        if self._client is None:
            raise InterfaceError("Client not initialized")
        return self._client

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get information about the current connection.

        Returns:
            Dict containing connection information
        """
        try:
            info = self._client.info()
            return {
                "cluster_name": info.get("cluster_name", "unknown"),
                "version": info.get("version", {}).get("number", "unknown"),
                "host": self.connection_params.host,
                "port": self.connection_params.port,
                "auth_method": self._get_auth_method_description(),
            }
        except Exception as e:
            return {"error": f"Failed to get connection info: {e}"}

    def test_permissions(self) -> Dict[str, bool]:
        """
        Test various OpenSearch permissions.

        Returns:
            Dict mapping permission names to boolean success status
        """
        permissions = {}

        # Test cluster info permission
        try:
            self._client.info()
            permissions["cluster_info"] = True
        except Exception:
            permissions["cluster_info"] = False

        # Test indices listing permission
        try:
            self._client.cat.indices(format="json")
            permissions["list_indices"] = True
        except Exception:
            permissions["list_indices"] = False

        # Test SQL query permission (if SQL plugin is available)
        try:
            self._client.transport.perform_request(
                "POST", "/_plugins/_sql", body={"query": "SELECT 1"}
            )
            permissions["sql_query"] = True
        except Exception:
            permissions["sql_query"] = False

        return permissions

    def execute_sql(self, query: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a SQL query using OpenSearch SQL plugin.

        Args:
            query: SQL query string
            parameters: Optional query parameters

        Returns:
            Dict containing query results

        Raises:
            QueryExecutionError: If query execution fails
        """
        try:
            # Build request body
            body = {"query": query}
            if parameters:
                body["parameters"] = parameters

            # Execute the query
            response = self._client.transport.perform_request("POST", "/_plugins/_sql", body=body)

            return response

        except Error:
            raise  # Don't re-wrap our own DB-API exceptions
        except Exception as e:
            from .exceptions import map_opensearch_exception

            execution_context = {
                "query": query[:200] + "..." if len(query) > 200 else query,
                "host": self.connection_params.host,
                "port": self.connection_params.port,
            }

            mapped_exception = map_opensearch_exception(e, execution_context)
            raise mapped_exception from e

    def close(self):
        """
        Clean up client resources and close underlying HTTP connections.
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass  # Best-effort cleanup
        self._client = None


def create_client(connection_params: ConnectionParams) -> OpenSearchClient:
    """
    Create and validate an OpenSearch client.

    Args:
        connection_params: Connection parameters including host, auth, and SSL details

    Returns:
        OpenSearchClient: Initialized and validated client

    Raises:
        InterfaceError: If client creation fails
        OperationalError: If authentication or validation fails
    """
    return OpenSearchClient(connection_params)
