from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class MySQLHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone MySQL connection data into SQL interface configuration.

        Extracts MySQL-specific parameters including region, host, port and database. Reads the contents of the
        given secret in the connection to fetch the username and password for the database connection

        Returns:
            Dict[str, Any]: Configuration dictionary containing:
                - host: Host address of the database
                - port: Port number of the database
                - user: Username that will be used to login to the database
                - password: Password that will be used to login to the database
                - database: Name of the database
        """
        connection_data = SqlHelper.get_connection_data(connection)
        secret = connection.secret
        config = {
            "host": SqlHelper.get_glue_connection_property(connection_data, "HOST"),
            "port": int(SqlHelper.get_glue_connection_property(connection_data, "PORT")),
            "user": secret.get("username"),
            "database": SqlHelper.get_glue_connection_property(connection_data, "DATABASE"),
            "password": secret.get("password"),
        }
        return config
