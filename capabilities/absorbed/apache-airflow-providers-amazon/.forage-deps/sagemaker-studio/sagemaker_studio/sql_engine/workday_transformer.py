from typing import Any, Dict, List, Optional
from urllib.parse import quote

from . import _sqlalchemy_workday_data_connect  # noqa: F401
from .database_transformer import DatabaseTransformer
from .resource_fetching_definition import ResourceFetchingDefinition


class WorkdayTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "trino"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "client_id", "isu", "access_token_endpoint", "private_key_file"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        WorkdayTransformer.validate_required_fields(
            WorkdayTransformer.get_required_fields(), connection_data
        )

        host = connection_data["host"]
        port = connection_data["port"]
        client_id = connection_data["client_id"]
        isu = connection_data["isu"]
        token_endpoint = connection_data["access_token_endpoint"]
        private_key = connection_data["private_key_file"]

        connection_string = (
            f"workday_data_connect://{host}:{port}"
            f"?client_id={client_id}&isu={isu}"
            f"&token_endpoint={quote(token_endpoint, safe='')}"
            f"&private_key={quote(private_key, safe='')}"
        )

        return {
            "connection_string": connection_string,
            "connect_args": {},
        }

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str],
        parents: Optional[Dict[str, str]] = None,
    ) -> ResourceFetchingDefinition:
        match resource_type:
            case "SCHEMA":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                return ResourceFetchingDefinition.from_sql_execution(
                    f"SELECT schema_name FROM {database}.information_schema.schemata ORDER BY schema_name",
                    default_type="SCHEMA",
                    children=("TABLE",),
                )

            case "TABLE":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                schema = DatabaseTransformer.get_required_resource_parent(parents, "SCHEMA")
                return ResourceFetchingDefinition.from_sql_execution(
                    f"SELECT table_name FROM {database}.information_schema.tables WHERE table_schema = :schema ORDER BY table_name",
                    default_type="TABLE",
                    children=("COLUMN",),
                    sql_parameters={"schema": schema},
                )

            case "COLUMN":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                schema = DatabaseTransformer.get_required_resource_parent(parents, "SCHEMA")
                table = DatabaseTransformer.get_required_resource_parent(parents, "TABLE")
                return ResourceFetchingDefinition.from_sql_execution(
                    f"SELECT column_name FROM {database}.information_schema.columns WHERE table_schema = :schema AND table_name = :table ORDER BY ordinal_position",
                    default_type="COLUMN",
                    children=(),
                    sql_parameters={"schema": schema, "table": table},
                )

            case "DATABASE" | None:
                return ResourceFetchingDefinition.from_sql_execution(
                    "SHOW CATALOGS",
                    default_type="DATABASE",
                    children=("SCHEMA",),
                )

            case other:
                raise ValueError(f"Unsupported resource type: {other!r}")

    @staticmethod
    def get_loggers() -> List[str]:
        return ["trino"]
