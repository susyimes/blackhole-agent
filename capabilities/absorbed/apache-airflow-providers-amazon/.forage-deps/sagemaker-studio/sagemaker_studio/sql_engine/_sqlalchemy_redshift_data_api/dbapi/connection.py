"""
DB-API 2.0 Connection class for Redshift Data API.

This module provides the Connection class that manages boto3 client
and implements basic DB-API 2.0 connection interface.
"""

import time

from .client import RedshiftDataAPIClient
from .connection_params import create_connection_params
from .cursor import Cursor
from .exceptions import DatabaseError, InterfaceError, map_boto3_exception


class Connection:
    """
    DB-API 2.0 Connection class for Redshift Data API.

    This class manages the boto3 redshift-data client and provides
    the standard DB-API 2.0 connection interface.
    """

    def __init__(
        self, database_name, cluster_identifier=None, db_user=None, region="us-east-1", **kwargs
    ):
        """
        Initialize connection with boto3 client management.

        Supports both provisioned and serverless configurations with auto-detection:
        - Provisioned: Requires cluster_identifier
        - Serverless: Requires workgroup_name (passed in kwargs)

        Args:
            database_name: The database name (required for both configurations)
            cluster_identifier: The Redshift cluster identifier (required for provisioned)
            db_user: The database user name (optional, can use IAM)
            region: The AWS region (defaults to 'us-east-1')
            **kwargs: Additional connection parameters:
                - workgroup_name: Required for serverless configuration
                - secret_arn: Optional secret ARN for authentication
                - with_event: Whether to include event information
        """
        # Create connection parameters
        self.connection_params = create_connection_params(
            cluster_identifier=cluster_identifier,
            database_name=database_name,
            db_user=db_user,
            region=region,
            **kwargs,
        )

        # Initialize the boto3 client with authentication and validation
        self.client_manager = RedshiftDataAPIClient(self.connection_params)

        # Connection state
        self._closed = False
        self.transaction_id = None
        self.autocommit = True  # Default to autocommit mode

        # Session management - API generates and returns session ID
        self._session_id = None  # Captured from execute_statement response
        self._session_keep_alive_seconds = 900  # Default 15 minutes to match Kernel's idle timeout
        self._persist_session = kwargs.get("persist_session", True)  # Default enabled
        self._last_query_time = None  # Track last query time

    @property
    def client(self):
        """Get the boto3 redshift-data client."""
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

        If there is an active transaction, commits it using the Data API.
        If no transaction is active, this is a no-op.

        Raises:
            DatabaseError: If commit operation fails
            InterfaceError: If connection is closed
        """
        if self._closed:
            raise InterfaceError("Connection is closed")

        if self.transaction_id is not None:
            execution_context = {
                "operation": "commit_transaction",
                "transaction_id": self.transaction_id,
                "database_name": self.connection_params.database_name,
                "cluster_identifier": self.connection_params.cluster_identifier,
                "workgroup_name": self.connection_params.workgroup_name,
            }

            try:
                self.client.commit_transaction(TransactionId=self.transaction_id)

                self.transaction_id = None

            except Exception as e:
                mapped_exception = map_boto3_exception(e, execution_context)

                raise DatabaseError(
                    f"Failed to commit transaction: {mapped_exception}"
                ) from mapped_exception

    def rollback(self):
        """
        Rollback current transaction.

        If there is an active transaction, rolls it back using the Data API.
        If no transaction is active, this is a no-op.

        Raises:
            DatabaseError: If rollback operation fails
            InterfaceError: If connection is closed
        """
        if self._closed:
            raise InterfaceError("Connection is closed")

        if self.transaction_id is not None:
            execution_context = {
                "operation": "rollback_transaction",
                "transaction_id": self.transaction_id,
                "database_name": self.connection_params.database_name,
                "cluster_identifier": self.connection_params.cluster_identifier,
                "workgroup_name": self.connection_params.workgroup_name,
            }

            try:
                self.client.rollback_transaction(TransactionId=self.transaction_id)

                self.transaction_id = None

            except Exception as e:
                mapped_exception = map_boto3_exception(e, execution_context)

                raise DatabaseError(
                    f"Failed to rollback transaction: {mapped_exception}"
                ) from mapped_exception

    def begin_transaction(self):
        """
        Begin a new transaction.

        If a transaction is already active, this is a no-op.

        Returns:
            str: The transaction ID

        Raises:
            DatabaseError: If transaction creation fails
            InterfaceError: If connection is closed
        """
        if self._closed:
            raise InterfaceError("Connection is closed")

        if self.transaction_id is None:
            execution_context = {
                "operation": "begin_transaction",
                "database_name": self.connection_params.database_name,
                "cluster_identifier": self.connection_params.cluster_identifier,
                "workgroup_name": self.connection_params.workgroup_name,
            }

            try:
                # Prepare parameters for begin_transaction
                begin_params = {
                    "Database": self.connection_params.database_name,
                }

                # Only add DbUser if db_user is provided (not None) and not using secret ARN
                if (
                    self.connection_params.db_user is not None
                    and not self.connection_params.secret_arn
                ):
                    begin_params["DbUser"] = self.connection_params.db_user

                # Add cluster identifier or workgroup name
                if self.connection_params.cluster_identifier:
                    begin_params["ClusterIdentifier"] = self.connection_params.cluster_identifier
                elif self.connection_params.workgroup_name:
                    begin_params["WorkgroupName"] = self.connection_params.workgroup_name

                # Add secret ARN if provided
                if self.connection_params.secret_arn:
                    begin_params["SecretArn"] = self.connection_params.secret_arn

                response = self.client.begin_transaction(**begin_params)
                self.transaction_id = response["TransactionId"]

            except Exception as e:
                mapped_exception = map_boto3_exception(e, execution_context)

                raise DatabaseError(
                    f"Failed to begin transaction: {mapped_exception}"
                ) from mapped_exception

        return self.transaction_id

    def get_transaction_id(self):
        """
        Get the current transaction ID.

        Returns:
            str or None: The current transaction ID, or None if no transaction is active
        """
        return self.transaction_id

    def set_autocommit(self, autocommit):
        """
        Set autocommit mode.

        Args:
            autocommit (bool): True to enable autocommit, False to disable
        """
        if self._closed:
            raise InterfaceError("Connection is closed")
        self.autocommit = autocommit

    def _invalidate_session_if_expired(self):
        """Clear session if it's been idle longer than keep-alive period"""
        if self._session_id and self._last_query_time:
            idle_seconds = time.time() - self._last_query_time
            if idle_seconds >= self._session_keep_alive_seconds:
                self._session_id = None

    def _update_last_query_time(self):
        """Update the last query timestamp"""
        self._last_query_time = time.time()

    def close(self):
        """
        Close the connection and clean up resources.

        If there is an active transaction, it will be rolled back before closing.
        """
        if not self._closed:
            # Rollback any active transaction before closing
            if self.transaction_id is not None:
                try:
                    self.rollback()
                except Exception:
                    # Ignore rollback errors during close
                    pass

            # Clear session - it will auto-expire on Redshift side
            self._session_id = None

            self.client_manager.close()
            self._closed = True

    def is_closed(self):
        """Check if the connection is closed."""
        return self._closed

    def get_client_info(self):
        """Get information about the boto3 client and credentials."""
        if self._closed:
            raise InterfaceError("Connection is closed")
        return self.client_manager.get_credentials_info()

    def test_permissions(self):
        """Test Redshift Data API permissions."""
        if self._closed:
            raise InterfaceError("Connection is closed")
        return self.client_manager.test_permissions()
