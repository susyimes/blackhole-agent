from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class BigQuerySqlHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone BigQuery connection data into SQL interface configuration.

        Extracts BigQuery-specific parameters including region and secret which includes a service key

        Returns:
            Dict[str, Any]: Service key of the BigQuery connection.
        """
        return connection.secret
