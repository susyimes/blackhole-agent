from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class DocumentDBSqlHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone DocumentDB connection data into SQL interface configuration.

        Supports both BASIC (username/password) and IAM authentication.
        For BASIC auth, reads credentials from the connection's secret.
        For IAM auth, no credentials are needed — the pymongo driver picks up
        AWS credentials from the environment automatically via MONGODB-AWS mechanism.

        Returns:
            Dict[str, Any]: Configuration dictionary containing:
                - host: Host address of the DocumentDB cluster
                - port: Port number of the DocumentDB cluster
                - database: Name of the database (defaults to "test")
                - auth_mechanism: "MONGODB-AWS" for IAM auth, None for BASIC
                - user: Username for BASIC auth (None for IAM)
                - password: Password for BASIC auth (None for IAM)
                - tls: Whether TLS is enabled
        """
        connection_data = SqlHelper.get_connection_data(connection)

        host = SqlHelper.get_glue_connection_property(connection_data, "HOST")
        port = SqlHelper.get_glue_connection_property(connection_data, "PORT") or "27017"
        database = SqlHelper.get_glue_connection_property(connection_data, "DATABASE") or "test"

        # Detect authentication type from the Glue connection's AuthenticationConfiguration
        auth_type = DocumentDBSqlHelper._get_auth_type(connection_data)

        if auth_type == "IAM":
            return {
                "host": host,
                "port": int(port),
                "database": database,
                "auth_mechanism": "MONGODB-AWS",
                "user": None,
                "password": None,
                "tls": True,  # TLS is mandatory for IAM auth
            }
        else:
            # BASIC auth — fetch credentials from secret
            secret = connection.secret
            normalized_secret = {k.lower(): v for k, v in secret.items()} if secret else {}
            return {
                "host": host,
                "port": int(port),
                "database": database,
                "auth_mechanism": None,
                "user": normalized_secret.get("username"),
                "password": normalized_secret.get("password"),
                "tls": True,
            }

    @staticmethod
    def _get_auth_type(connection_data: Dict[str, Any]) -> str:
        """
        Determine the authentication type from the Glue connection configuration.

        Navigates the same structure as SqlHelper.get_glue_connection_property():
            physical_endpoints[0].glueConnection.authenticationConfiguration.authenticationType

        Returns:
            str: "IAM" or "BASIC"
        """
        try:
            physical_endpoints = connection_data.get("physical_endpoints")
            if not physical_endpoints or not isinstance(physical_endpoints, list):
                return "BASIC"

            first_endpoint = physical_endpoints[0]
            if not isinstance(first_endpoint, dict):
                return "BASIC"

            glue_conn = first_endpoint.get("glueConnection", {})
            auth_config = glue_conn.get("authenticationConfiguration", {})

            if not auth_config or not isinstance(auth_config, dict):
                return "BASIC"

            auth_type = auth_config.get("authenticationType", "BASIC")
            return auth_type.upper()
        except (AttributeError, IndexError, KeyError, TypeError):
            return "BASIC"
