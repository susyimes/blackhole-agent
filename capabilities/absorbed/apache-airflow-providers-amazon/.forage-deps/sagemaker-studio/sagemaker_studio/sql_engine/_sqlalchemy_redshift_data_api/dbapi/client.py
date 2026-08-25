"""
Boto3 client management and authentication for Redshift Data API.

This module handles the creation and management of boto3 redshift-data clients,
including IAM credential handling and connection validation.
"""

from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from .connection_params import ConnectionParams
from .exceptions import ClusterNotFoundError, InterfaceError, OperationalError


class RedshiftDataAPIClient:
    """
    Manages boto3 redshift-data client with authentication and validation.

    This class handles:
    - boto3 client initialization with proper region configuration
    - IAM credential handling through boto3's credential chain
    - Connection validation through test API calls
    - Error mapping from boto3 exceptions to DB-API exceptions
    """

    def __init__(self, connection_params: ConnectionParams):
        """
        Initialize the Redshift Data API client.

        Args:
            connection_params: Connection parameters including region and authentication details

        Raises:
            InterfaceError: If client initialization fails
            OperationalError: If authentication fails
        """
        self.connection_params = connection_params
        self._client = None
        self._session = None

        # Initialize the client
        self._initialize_client()

        # Validate the connection
        self._validate_connection()

    def _initialize_client(self):
        """
        Initialize the boto3 redshift-data client with proper configuration.

        Supports multiple authentication methods:
        1. Explicit AWS credentials via aws_access_key_id, aws_secret_access_key, aws_session_token
        2. Named AWS profiles via profile_name parameter
        3. Fallback to boto3's default credential chain:
           - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
           - IAM roles for EC2 instances
           - AWS credentials file (~/.aws/credentials)
           - AWS config file (~/.aws/config)
           - IAM roles for tasks (ECS, Lambda, etc.)

        Raises:
            InterfaceError: If client initialization fails
            OperationalError: If credentials are invalid or missing
        """
        try:
            # Create a boto3 session based on the authentication method
            self._session = self._create_boto3_session()

            # Create the redshift-data client with the specified region
            self._client = self._session.client(
                "redshift-data", region_name=self.connection_params.region
            )

        except (NoCredentialsError, PartialCredentialsError) as e:
            # These are boto3 credential exceptions that should be caught at the session level
            # but if they bubble up here, we need to handle them properly
            if isinstance(e, NoCredentialsError):
                raise OperationalError(
                    f"AWS credentials not found. Please configure your credentials using "
                    f"explicit parameters (aws_access_key_id, aws_secret_access_key), "
                    f"named profile (profile_name), environment variables, IAM roles, "
                    f"or AWS credentials file. Error: {e}"
                )
            else:  # PartialCredentialsError
                raise OperationalError(
                    f"Incomplete AWS credentials. Please check your credential configuration. Error: {e}"
                )
        except Exception as e:
            raise InterfaceError(f"Failed to initialize Redshift Data API client: {e}")

    def _create_boto3_session(self) -> boto3.Session:
        """
        Create a boto3 session with the appropriate authentication method.

        Returns:
            boto3.Session: Configured session with credentials

        Raises:
            OperationalError: If credential configuration is invalid
        """
        params = self.connection_params

        # Method 1: Credential provider (refreshable)
        if params.credential_provider is not None and callable(params.credential_provider):
            from botocore.credentials import RefreshableCredentials
            from botocore.session import get_session

            def refresh():
                """Fetch fresh credentials from provider"""
                creds = params.credential_provider()
                required_keys = ["access_key_id", "secret_access_key", "expiration"]
                missing = [k for k in required_keys if k not in creds]
                if missing:
                    raise OperationalError(
                        f"credential_provider must return a dict with keys: {required_keys}. "
                        f"Missing: {missing}"
                    )
                return {
                    "access_key": creds["access_key_id"],
                    "secret_key": creds["secret_access_key"],
                    "token": creds.get("session_token"),
                    "expiry_time": creds.get("expiration"),
                }

            try:
                session_credentials = RefreshableCredentials.create_from_metadata(
                    metadata=refresh(),
                    refresh_using=refresh,
                    method="custom-provider",
                    advisory_timeout=60,  # Refresh 1 minute before expiry
                )
                botocore_session = get_session()
                botocore_session._credentials = session_credentials
                return boto3.Session(botocore_session=botocore_session)
            except Exception as e:
                raise OperationalError(f"Failed to create session with credential provider: {e}")

        # Method 2: Named AWS profile
        if params.profile_name:
            try:
                session = boto3.Session(profile_name=params.profile_name)
                return session
            except Exception as e:
                raise OperationalError(
                    f"Failed to create session with profile '{params.profile_name}': {e}"
                )

        # Method 3: Explicit AWS credentials
        elif params.aws_access_key_id and params.aws_secret_access_key:
            try:
                session_kwargs = {
                    "aws_access_key_id": params.aws_access_key_id,
                    "aws_secret_access_key": params.aws_secret_access_key,
                }

                # Add session token if provided (for temporary credentials)
                if params.aws_session_token:
                    session_kwargs["aws_session_token"] = params.aws_session_token

                session = boto3.Session(**session_kwargs)
                return session
            except Exception as e:
                raise OperationalError(f"Failed to create session with explicit credentials: {e}")

        # Method 4: Default credential chain
        else:
            try:
                session = boto3.Session()
                return session
            except (NoCredentialsError, PartialCredentialsError):
                # Re-raise boto3 credential exceptions so they can be handled at the right level
                raise
            except Exception as e:
                raise OperationalError(f"Failed to create session with default credentials: {e}")

    def _get_auth_method_description(self) -> str:
        """
        Get a description of the authentication method being used.

        Returns:
            str: Human-readable description of the auth method
        """
        params = self.connection_params

        if params.profile_name:
            return f"AWS profile '{params.profile_name}'"
        elif params.aws_access_key_id:
            if params.aws_session_token:
                return "explicit temporary AWS credentials"
            else:
                return "explicit AWS credentials"
        else:
            return "default AWS credential chain"

    def _validate_connection(self):
        """
        Validate the connection by making a test API call.

        This method attempts to list databases to verify:
        1. Credentials are valid
        2. Region is correct
        3. Cluster/workgroup exists and is accessible

        Raises:
            OperationalError: If connection validation fails
            ClusterNotFoundError: If cluster/workgroup is not found
        """
        try:
            # Prepare parameters for the list_databases call
            list_params = {
                "Database": self.connection_params.database_name,
            }

            # Only add DbUser if db_user is provided (not None) and not using secret ARN
            if self.connection_params.db_user is not None and not self.connection_params.secret_arn:
                list_params["DbUser"] = self.connection_params.db_user

            # Add cluster identifier or workgroup name
            if self.connection_params.cluster_identifier:
                list_params["ClusterIdentifier"] = self.connection_params.cluster_identifier
            elif self.connection_params.workgroup_name:
                list_params["WorkgroupName"] = self.connection_params.workgroup_name

            # Add secret ARN if provided
            if self.connection_params.secret_arn:
                list_params["SecretArn"] = self.connection_params.secret_arn

            # Make the test API call
            self._client.list_databases(**list_params)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            # Map specific AWS errors to appropriate DB-API exceptions
            if error_code in ["ClusterNotFoundFault", "InvalidClusterStateFault"]:
                raise ClusterNotFoundError(
                    f"Cluster '{self.connection_params.cluster_identifier}' not found or not available: {error_message}"
                )
            elif error_code in ["WorkgroupNotFoundFault"]:
                raise ClusterNotFoundError(
                    f"Workgroup '{self.connection_params.workgroup_name}' not found: {error_message}"
                )
            elif error_code in ["AccessDeniedFault", "UnauthorizedOperation"]:
                raise OperationalError(
                    f"Access denied. Check IAM permissions for Redshift Data API: {error_message}"
                )
            elif error_code in ["ValidationException"]:
                raise InterfaceError(f"Invalid parameters: {error_message}")
            else:
                raise OperationalError(
                    f"Connection validation failed ({error_code}): {error_message}"
                )

        except Exception as e:
            raise OperationalError(f"Unexpected error during connection validation: {e}")

    @property
    def client(self):
        """
        Get the boto3 redshift-data client.

        Returns:
            boto3.client: The initialized redshift-data client
        """
        if self._client is None:
            raise InterfaceError("Client not initialized")
        return self._client

    @property
    def session(self):
        """
        Get the boto3 session.

        Returns:
            boto3.Session: The boto3 session used for credential management
        """
        if self._session is None:
            raise InterfaceError("Session not initialized")
        return self._session

    def get_credentials_info(self) -> Dict[str, Any]:
        """
        Get information about the current AWS credentials.

        Returns:
            Dict containing credential information (without sensitive data)
        """
        try:
            credentials = self._session.get_credentials()
            if credentials:
                return {
                    "access_key_id": (
                        credentials.access_key[:8] + "..." if credentials.access_key else None
                    ),
                    "method": credentials.method if hasattr(credentials, "method") else "unknown",
                    "region": self.connection_params.region,
                }
            else:
                return {"error": "No credentials found"}
        except Exception as e:
            return {"error": f"Failed to get credential info: {e}"}

    def test_permissions(self) -> Dict[str, bool]:
        """
        Test various Redshift Data API permissions.

        Returns:
            Dict mapping permission names to boolean success status
        """
        permissions = {}

        # Test list_databases permission
        try:
            list_params = {
                "Database": self.connection_params.database_name,
            }

            # Only add DbUser if db_user is provided (not None) and not using secret ARN
            if self.connection_params.db_user is not None and not self.connection_params.secret_arn:
                list_params["DbUser"] = self.connection_params.db_user

            if self.connection_params.cluster_identifier:
                list_params["ClusterIdentifier"] = self.connection_params.cluster_identifier
            elif self.connection_params.workgroup_name:
                list_params["WorkgroupName"] = self.connection_params.workgroup_name

            if self.connection_params.secret_arn:
                list_params["SecretArn"] = self.connection_params.secret_arn

            self._client.list_databases(**list_params)
            permissions["list_databases"] = True
        except Exception:
            permissions["list_databases"] = False

        # Test execute_statement permission (with a simple SELECT 1)
        try:
            execute_params = {
                "Database": self.connection_params.database_name,
                "Sql": "SELECT 1",
            }

            # Only add DbUser if db_user is provided (not None) and not using secret ARN
            if self.connection_params.db_user is not None and not self.connection_params.secret_arn:
                execute_params["DbUser"] = self.connection_params.db_user

            if self.connection_params.cluster_identifier:
                execute_params["ClusterIdentifier"] = self.connection_params.cluster_identifier
            elif self.connection_params.workgroup_name:
                execute_params["WorkgroupName"] = self.connection_params.workgroup_name

            if self.connection_params.secret_arn:
                execute_params["SecretArn"] = self.connection_params.secret_arn

            response = self._client.execute_statement(**execute_params)
            # If we get a statement ID, the permission works
            permissions["execute_statement"] = bool(response.get("Id"))
        except Exception:
            permissions["execute_statement"] = False

        return permissions

    def close(self):
        """
        Clean up client resources.

        Note: boto3 clients don't require explicit cleanup, but this method
        is provided for consistency with DB-API patterns.
        """
        self._client = None
        self._session = None


def create_client(connection_params: ConnectionParams) -> RedshiftDataAPIClient:
    """
    Create and validate a Redshift Data API client.

    Args:
        connection_params: Connection parameters including region and authentication details

    Returns:
        RedshiftDataAPIClient: Initialized and validated client

    Raises:
        InterfaceError: If client creation fails
        OperationalError: If authentication or validation fails
    """
    return RedshiftDataAPIClient(connection_params)
