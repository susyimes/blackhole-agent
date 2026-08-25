from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class OpenSearchSQLHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone OpenSearch connection data into SQL interface configuration.

        Extracts OpenSearch-specific region parameter.

        Returns:
            Dict[str, Any]: Configuration dictionary containing:
                - domain_endpoint: OpenSearch domain endpoint URL
                - user: Username for authentication
                - password: Password for authentication
        """
        connection_data = SqlHelper.get_connection_data(connection)
        secret = connection.secret
        normalized_secret = {k.lower(): v for k, v in secret.items()} if secret else {}
        config = {
            "domain_endpoint": SqlHelper.get_glue_connection_property(
                connection_data, "DOMAIN_ENDPOINT"
            ),
            "user": normalized_secret.get("username"),
            "password": normalized_secret.get("password"),
        }
        return config
