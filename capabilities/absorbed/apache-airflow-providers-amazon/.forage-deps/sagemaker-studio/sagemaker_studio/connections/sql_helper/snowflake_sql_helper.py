import re
from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper
from sagemaker_studio.sql_engine.snowflake_transformer import SnowflakeAuthType

HOST_PATTERN = r"^[a-zA-Z0-9._-]+[.]snowflakecomputing[.](com|cn)$"


class SnowflakeSqlHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform Snowflake connection data into SQL interface configuration.

        Extracts Snowflake-specific parameters including region, host, port and database. Reads the contents of the
        given secret in the connection to fetch the username and password for the database connection

        Returns:
         Dict[str, Any]: Configuration dictionary containing:
             - host: Host address of the database
             - port: Port number of the database
             - user: Username that will be used to login to the database
             - password: Password that will be used to login to the database
             - database: Name of the database
             - region: AWS region for Snowflake service
             - warehouse: Warehouse name of the snowflake database
        """
        connection_data = SqlHelper.get_connection_data(connection)
        secret = connection.secret

        physical_endpoints = connection_data["physical_endpoints"]

        region = physical_endpoints[0].get("awsLocation").get("awsRegion")
        # Strip 'https://' prefix as SqlAlchemy doesn't support it in host strings
        host = SqlHelper.get_glue_connection_property(connection_data, "HOST").removeprefix(
            "https://"
        )

        if not SnowflakeSqlHelper.validate_snowflake_host(host):
            raise ValueError(f"Invalid Snowflake host: {host}\n")

        account = (
            host.removesuffix(".snowflakecomputing.com").removesuffix(".snowflakecomputing.cn")
            + "."
            + region
        )

        if "sfUser" in secret and "pem_private_key" in secret:
            auth_type = SnowflakeAuthType.PEM_PRIVATE_KEY
        else:
            auth_type = SnowflakeAuthType.USERNAME_PASSWORD

        config = {
            "account": account,
            "host": host,
            "port": int(SqlHelper.get_glue_connection_property(connection_data, "PORT")),
            "region": region,
            "database": SqlHelper.get_glue_connection_property(connection_data, "DATABASE"),
            "warehouse": SqlHelper.get_glue_connection_property(connection_data, "WAREHOUSE"),
            "auth_type": auth_type,
        }

        if auth_type == SnowflakeAuthType.PEM_PRIVATE_KEY:
            config["user"] = secret.get("sfUser")
            config["private_key"] = secret.get("pem_private_key")
        else:
            config["user"] = secret.get("username")
            config["password"] = secret.get("password")

        return config

    @staticmethod
    def validate_snowflake_host(host: str) -> bool:
        """Validate Snowflake account contains only allowed chars."""
        return bool(re.match(HOST_PATTERN, host.lower()))
