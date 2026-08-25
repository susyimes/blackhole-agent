"""
Connection parameter parsing and validation for OpenSearch.

This module handles parsing of connection URLs and validation of connection parameters.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote

from .exceptions import InterfaceError


@dataclass
class ConnectionParams:
    """
    Connection parameters for OpenSearch.

    Attributes:
        host: The OpenSearch host (defaults to 'localhost')
        port: The OpenSearch port (defaults to 443)
        index: The default index to query (defaults to '_all')
        username: Username for authentication (optional)
        password: Password for authentication (optional)
        use_ssl: Whether to use SSL/TLS (defaults to True)
        verify_certs: Whether to verify SSL certificates (defaults to True)
        ca_certs: Path to CA certificate file (optional)
        client_cert: Path to client certificate file (optional)
        client_key: Path to client key file (optional)
        timeout: Request timeout in seconds (defaults to 30)
        max_retries: Maximum number of retries (defaults to 3)
        api_key: API key for authentication (optional)
        api_key_id: API key ID for authentication (optional)
    """

    host: str = "localhost"
    port: int = 443
    index: str = "_all"
    username: Optional[str] = None
    password: Optional[str] = None
    use_ssl: bool = True
    verify_certs: bool = True
    ca_certs: Optional[str] = None
    client_cert: Optional[str] = None
    client_key: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    api_key: Optional[str] = None
    api_key_id: Optional[str] = None

    def __post_init__(self):
        """Validate connection parameters after initialization."""
        self.validate()

    def validate(self):
        """Validate that parameters are valid."""
        # Validate host format
        if not self.host:
            raise InterfaceError("host cannot be empty")

        # Validate port range
        if not (1 <= self.port <= 65535):
            raise InterfaceError("port must be between 1 and 65535")

        # Validate index name format (basic validation)
        if self.index and not re.match(r"^[a-zA-Z0-9_*.-]+$", self.index):
            raise InterfaceError(
                "index name must contain only letters, numbers, underscores, dots, hyphens, and asterisks"
            )

        # Validate timeout
        if self.timeout <= 0:
            raise InterfaceError("timeout must be positive")

        # Validate max_retries
        if self.max_retries < 0:
            raise InterfaceError("max_retries must be non-negative")

        # Validate authentication parameter combinations
        self._validate_authentication()

        # Validate SSL parameter combinations
        self._validate_ssl_params()

    def _validate_authentication(self):
        """Validate authentication parameter combinations."""
        # Cannot specify both basic auth and API key auth
        if (self.username or self.password) and (self.api_key or self.api_key_id):
            raise InterfaceError("Cannot specify both basic auth and API key authentication")

        # If username is provided, password should also be provided (and vice versa)
        if self.username and not self.password:
            raise InterfaceError("password is required when username is provided")
        if self.password and not self.username:
            raise InterfaceError("username is required when password is provided")

        # If api_key_id is provided, api_key should also be provided (and vice versa)
        if self.api_key_id and not self.api_key:
            raise InterfaceError("api_key is required when api_key_id is provided")
        if self.api_key and not self.api_key_id:
            raise InterfaceError("api_key_id is required when api_key is provided")

    def _validate_ssl_params(self):
        """Validate SSL parameter combinations."""
        # If client_cert is provided, client_key should also be provided (and vice versa)
        if self.client_cert and not self.client_key:
            raise InterfaceError("client_key is required when client_cert is provided")
        if self.client_key and not self.client_cert:
            raise InterfaceError("client_cert is required when client_key is provided")

        # SSL-related parameters only make sense when use_ssl is True
        if not self.use_ssl:
            if self.ca_certs or self.client_cert or self.client_key:
                raise InterfaceError(
                    "SSL certificate parameters (ca_certs, client_cert, client_key) "
                    "can only be used when use_ssl=True"
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert connection parameters to dictionary."""
        result = {
            "host": self.host,
            "port": self.port,
            "index": self.index,
            "use_ssl": self.use_ssl,
            "verify_certs": self.verify_certs,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }

        # Add optional parameters if they are set
        if self.username:
            result["username"] = self.username
        if self.password:
            result["password"] = self.password
        if self.ca_certs:
            result["ca_certs"] = self.ca_certs
        if self.client_cert:
            result["client_cert"] = self.client_cert
        if self.client_key:
            result["client_key"] = self.client_key
        if self.api_key:
            result["api_key"] = self.api_key
        if self.api_key_id:
            result["api_key_id"] = self.api_key_id

        return result


def parse_connection_url(url: str) -> ConnectionParams:
    """
    Parse an OpenSearch connection URL.

    Supported formats:
    - opensearch://host:port/index
    - opensearch://user:password@host:port/index
    - opensearch://host:port/index?use_ssl=true&verify_certs=false

    Args:
        url: The connection URL string

    Returns:
        ConnectionParams: Parsed and validated connection parameters

    Raises:
        InterfaceError: If URL format is invalid or required parameters are missing
    """
    if not url:
        raise InterfaceError("Connection URL cannot be empty")

    # Custom URL parsing since urlparse doesn't handle schemes with underscores
    if "://" not in url:
        raise InterfaceError("Invalid URL format: missing '://'")

    try:
        scheme_part, rest = url.split("://", 1)
    except ValueError:
        raise InterfaceError("Invalid URL format")

    # Validate scheme
    scheme = scheme_part
    if "+" in scheme:
        # Handle SQLAlchemy driver specification format (dialect+driver://)
        dialect_part, driver_part = scheme.split("+", 1)
        if dialect_part != "opensearch":
            raise InterfaceError(
                f"Invalid URL scheme '{scheme}'. Expected 'opensearch' or 'opensearch+driver'"
            )
        scheme = dialect_part

    if scheme != "opensearch":
        raise InterfaceError(f"Invalid URL scheme '{scheme}'. Expected 'opensearch'")

    # Split the rest into path and query parts
    if "?" in rest:
        path_part, query_part = rest.split("?", 1)
    else:
        path_part = rest
        query_part = ""

    # Parse path to extract host, port, and index
    username = None
    password = None
    host = "localhost"
    port = 443
    index = "_all"

    if "/" in path_part:
        host_part, index = path_part.split("/", 1)
    else:
        host_part = path_part

    # Extract username and password if present
    if "@" in host_part:
        auth_part, host_part = host_part.rsplit("@", 1)
        if ":" in auth_part:
            username, password = auth_part.split(":", 1)
            username = unquote(username)
            password = unquote(password)
        else:
            username = unquote(auth_part)

    # Extract host and port
    if ":" in host_part:
        host, port_str = host_part.split(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            raise InterfaceError(f"Invalid port number: {port_str}")
    else:
        host = host_part

    # Use defaults if not specified
    if not host:
        host = "localhost"
    if not index:
        index = "_all"

    # Parse query parameters
    try:
        query_params = parse_qs(query_part) if query_part else {}
    except Exception as e:
        raise InterfaceError(f"Invalid query parameters: {e}")

    def get_single_param(name: str, default: Optional[str] = None) -> Optional[str]:
        """Extract a single parameter value from query parameters."""
        values = query_params.get(name, [])
        if not values:
            return default
        if len(values) > 1:
            raise InterfaceError(f"Parameter '{name}' specified multiple times")
        return values[0]

    def get_bool_param(name: str, default: bool = False) -> bool:
        """Extract a boolean parameter value from query parameters."""
        value_str = get_single_param(name)
        if value_str is None:
            return default
        value_str = value_str.lower()
        if value_str in ("true", "1", "yes", "on"):
            return True
        elif value_str in ("false", "0", "no", "off"):
            return False
        else:
            raise InterfaceError(
                f"Invalid boolean value for {name}: '{value_str}'. "
                "Expected true/false, 1/0, yes/no, or on/off"
            )

    def get_int_param(name: str, default: int) -> int:
        """Extract an integer parameter value from query parameters."""
        value_str = get_single_param(name)
        if value_str is None:
            return default
        try:
            return int(value_str)
        except ValueError:
            raise InterfaceError(f"Invalid integer value for {name}: '{value_str}'")

    # Extract parameters with defaults
    use_ssl = get_bool_param("use_ssl", True)
    verify_certs = get_bool_param("verify_certs", True)
    timeout = get_int_param("timeout", 30)
    max_retries = get_int_param("max_retries", 3)

    # Extract optional parameters
    ca_certs = get_single_param("ca_certs")
    client_cert = get_single_param("client_cert")
    client_key = get_single_param("client_key")
    api_key = get_single_param("api_key")
    api_key_id = get_single_param("api_key_id")

    # Override username/password from query params if provided
    username = get_single_param("username") or username
    password = get_single_param("password") or password

    # Create and validate connection parameters
    return ConnectionParams(
        host=host,
        port=port,
        index=index,
        username=username,
        password=password,
        use_ssl=use_ssl,
        verify_certs=verify_certs,
        ca_certs=ca_certs,
        client_cert=client_cert,
        client_key=client_key,
        timeout=timeout,
        max_retries=max_retries,
        api_key=api_key,
        api_key_id=api_key_id,
    )


def create_connection_params(**kwargs) -> ConnectionParams:
    """
    Create connection parameters from keyword arguments.

    Args:
        **kwargs: Connection parameters as keyword arguments

    Returns:
        ConnectionParams: Validated connection parameters
    """
    return ConnectionParams(**kwargs)
