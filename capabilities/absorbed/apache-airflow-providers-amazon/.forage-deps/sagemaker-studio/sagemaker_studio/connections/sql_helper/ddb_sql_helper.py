from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class DDBSQLHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone DynamoDB connection data into SQL interface configuration.

        Extracts DynamoDB-specific region parameter.

        Returns:
            Dict[str, Any]: Configuration dictionary containing:
                - region: AWS region for DynamoDB service
        """
        connection_data = SqlHelper.get_connection_data(connection)
        physical_endpoints = connection_data["physical_endpoints"]
        aws_location = physical_endpoints[0].get("awsLocation", {})
        region = aws_location.get("awsRegion")

        config = {"region": region}

        return config
