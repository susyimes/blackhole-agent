from typing import Optional

from sagemaker_studio.connections.sql_helper.athena_sql_helper import AthenaSqlHelper
from sagemaker_studio.connections.sql_helper.big_query_sql_helper import BigQuerySqlHelper
from sagemaker_studio.connections.sql_helper.ddb_sql_helper import DDBSQLHelper
from sagemaker_studio.connections.sql_helper.documentdb_sql_helper import DocumentDBSqlHelper
from sagemaker_studio.connections.sql_helper.mssql_sql_helper import MSSQLHelper
from sagemaker_studio.connections.sql_helper.mysql_sql_helper import MySQLHelper
from sagemaker_studio.connections.sql_helper.opensearch_sql_helper import OpenSearchSQLHelper
from sagemaker_studio.connections.sql_helper.oracle_sql_helper import OracleSQLHelper
from sagemaker_studio.connections.sql_helper.postgresql_helper import PostgreSQLHelper
from sagemaker_studio.connections.sql_helper.redshift_sql_helper import RedshiftSqlHelper
from sagemaker_studio.connections.sql_helper.snowflake_sql_helper import SnowflakeSqlHelper
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper
from sagemaker_studio.connections.sql_helper.teradata_sql_helper import TeraDataSQLHelper
from sagemaker_studio.connections.sql_helper.vertica_sql_helper import VerticaSQLHelper
from sagemaker_studio.connections.sql_helper.workday_data_connect_sql_helper import (
    WorkdayDataConnectSqlHelper,
)


class HelperFactory:
    """
    Factory class for creating SQL helper instances.

    This factory provides a centralized way to create appropriate SQL helper
    instances based on connection type. It abstracts the instantiation logic
    and supports extensibility for new connection types.
    """

    @staticmethod
    def get_sql_helper(type: str) -> Optional[SqlHelper]:
        """
        Create and return an appropriate SQL helper instance based on connection type.

        Args:
            type (str): The connection type identifier (e.g., "ATHENA", "REDSHIFT").
            connection_data (dict): DataZone connection configuration data to be passed
                to the helper constructor.

        Returns:
            Optional[SqlHelper]: An instance of the appropriate SQL helper subclass,
                or None if the connection type is not supported.

        Supported connection types:
            - "ATHENA": Returns AthenaSqlHelper instance
            - "REDSHIFT": Returns RedshiftSqlHelper instance
        """
        if type == "ATHENA":
            return AthenaSqlHelper
        if type == "REDSHIFT":
            return RedshiftSqlHelper
        if type == "MYSQL":
            return MySQLHelper
        if type == "SNOWFLAKE":
            return SnowflakeSqlHelper
        if type == "BIGQUERY":
            return BigQuerySqlHelper
        if type == "DYNAMODB":
            return DDBSQLHelper
        if type == "DOCUMENTDB":
            return DocumentDBSqlHelper
        if type == "SQLSERVER":
            return MSSQLHelper
        if type == "POSTGRESQL":
            return PostgreSQLHelper
        if type == "OPENSEARCH":
            return OpenSearchSQLHelper
        if type == "ORACLE":
            return OracleSQLHelper
        if type == "TERADATA":
            return TeraDataSQLHelper
        if type == "VERTICA":
            return VerticaSQLHelper
        if type == "WORKDAYLDQ":
            return WorkdayDataConnectSqlHelper
        else:
            return None
