from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class RedshiftSqlHelper(SqlHelper):
    """
    SQL helper for Amazon Redshift connections.

    This class transforms DataZone Redshift connection data into a standardized format
    for SQL interface consumption. It handles both serverless and provisioned
    Redshift clusters, including workgroup and cluster configurations.
    """

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone Redshift connection data into SQL interface configuration.

        Extracts Redshift-specific parameters including cluster/workgroup identifiers,
        database information, and AWS credentials from DataZone connection data. Handles both serverless and
        provisioned Redshift configurations.

        Returns:
            dict: Configuration dictionary containing:
                - region: AWS region for Redshift service
                - cluster_identifier: Redshift cluster identifier (for provisioned)
                - workgroup_name: Redshift workgroup name (for serverless)
                - database_name: Target database name
                - secret_arn: ARN of AWS Secrets Manager secret (if used)
                - db_user: Database user (for provisioned clusters)
                - aws_access_key_id: AWS access key
                - aws_secret_access_key: AWS secret key
                - aws_session_token: AWS session token (if present)
                - credential_provider: Callable that returns fresh credentials (if provided)
        """
        connection_data = SqlHelper.get_connection_data(connection)

        physical_endpoints = connection_data["physical_endpoints"]
        endpoint = physical_endpoints[0]
        aws_location = endpoint.get("awsLocation", {})
        region = aws_location.get("awsRegion")

        # Use provided database name, otherwise fall back to connection default
        database_name = kwargs.get("database_name", connection_data["database_name"])
        storage = connection_data.get("storage", {})
        workgroup_name = storage.get("workgroupName")
        cluster_identifier = storage.get("clusterName")
        try:
            secret_arn = connection._find_secret_arn()
        except Exception:
            secret_arn = None

        config = {
            "region": region,
            "cluster_identifier": cluster_identifier,
            "workgroup_name": workgroup_name,
            "database_name": database_name,
            "secret_arn": secret_arn,
        }

        # Use credential_provider if provided, otherwise use static credentials
        credential_provider = kwargs.get("credential_provider")

        if credential_provider is not None:
            config["credential_provider"] = credential_provider
        else:
            connection_creds = connection_data["connection_creds"]
            config["aws_access_key_id"] = connection_creds.get("access_key_id")
            config["aws_secret_access_key"] = connection_creds.get("secret_access_key")
            if connection_creds.get("session_token"):
                config["aws_session_token"] = connection_creds.get("session_token")

        return config
