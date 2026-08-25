from typing import Any, Dict

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.connections.sql_helper.sql_helper import SqlHelper


class WorkdayDataConnectSqlHelper(SqlHelper):

    @staticmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        glue_connection = connection.physical_endpoints[0].glue_connection
        secret = connection.secret
        sql_configs = {}
        sql_configs["client_id"] = secret["wd.authn.clientId"]
        sql_configs["isu"] = secret["wd.authn.isu"]
        sql_configs["access_token_endpoint"] = secret["wd.authn.accessTokenEndpoint"]
        sql_configs["private_key_file"] = secret["wd.authn.privateKey"].replace("\\n", "")
        sql_configs["host"] = glue_connection.connection_properties.get("HOST")
        sql_configs["port"] = glue_connection.connection_properties.get("PORT")

        return sql_configs
