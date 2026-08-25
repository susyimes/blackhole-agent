from enum import Enum
from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer
from .resource_fetching_definition import ResourceFetchingDefinition


class SnowflakeAuthType(str, Enum):
    USERNAME_PASSWORD = "USERNAME_PASSWORD"
    PEM_PRIVATE_KEY = "PEM_PRIVATE_KEY"


class SnowflakeTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "snowflake"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["account", "database", "warehouse", "auth_type"]

    @staticmethod
    def _validate_auth_fields(connection_data: Dict[str, Any]) -> None:
        """Validate that the correct credential fields are present for the auth type."""
        auth_type = connection_data.get("auth_type")
        if auth_type == SnowflakeAuthType.PEM_PRIVATE_KEY:
            if not connection_data.get("user") or not connection_data.get("private_key"):
                raise ValueError(
                    "user and private_key are required for PEM_PRIVATE_KEY authentication"
                )
        else:
            if not connection_data.get("user") or not connection_data.get("password"):
                raise ValueError(
                    "user and password are required for USERNAME_PASSWORD authentication"
                )

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Snowflake connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the snowflake driver
        and passes all connection data as connect_args for snowflake-sqlalchemy.

        Args:
            connection_data (Dict[str, Any]): Snowflake connection configuration containing
                host, port, database, warehouse, user and password.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: snowflake:// URL for the given connection configuration
        Raises:
            ValueError: If required fields are missing.
        """
        SnowflakeTransformer.validate_required_fields(
            SnowflakeTransformer.get_required_fields(), connection_data
        )
        SnowflakeTransformer._validate_auth_fields(connection_data)

        database = connection_data.get("database")
        warehouse = connection_data.get("warehouse")
        account = connection_data.get("account")
        auth_type = connection_data.get("auth_type")

        if auth_type == SnowflakeAuthType.PEM_PRIVATE_KEY:
            import base64

            user = connection_data.get("user")
            pem_str = connection_data.get("private_key")
            pem_str = pem_str if isinstance(pem_str, str) else pem_str.decode("utf-8")
            pem_str = pem_str.replace("\\n", "\n").strip()
            # Strip PEM headers/footers if present to get raw base64
            pem_lines = [
                line for line in pem_str.splitlines() if line and not line.startswith("-----")
            ]
            private_key_bytes = base64.b64decode("".join(pem_lines))

            connection_string = f"snowflake://{user}@{account}/{database}?warehouse={warehouse}"
            connect_args = {
                k: v for k, v in connection_data.items() if k not in ("private_key", "auth_type")
            }
            connect_args["private_key"] = private_key_bytes
        else:
            user = connection_data.get("user")
            password = connection_data.get("password")
            connection_string = (
                f"snowflake://{user}:{password}@{account}/{database}?warehouse={warehouse}"
            )
            connect_args = {k: v for k, v in connection_data.items() if k not in ("auth_type",)}
        return {"connection_string": connection_string, "connect_args": connect_args}

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str],
        parents: Optional[Dict[str, str]] = None,
    ) -> ResourceFetchingDefinition:
        """
        Build a SQL-execution plan for listing Snowflake resources.

        Returns a `ResourceFetchingDefinition` configured to execute parameterized
        SQL against Amazon Redshift system views to enumerate resources at the
        requested level. Required parent identifiers are validated via
        `SqlHelper.get_required_resource_parent(...)` and injected into the query’s
        parameters.

        Supported levels:
          * **"DATABASE"** or `None` → lists databases from `svv_redshift_databases`.
          * **"SCHEMA"** → lists schemas in a database from `svv_all_schemas`
            (excluding `pg_catalog`, `pg_internal`, `information_schema`).
          * **"TABLE"** → lists tables in a schema from `SVV_ALL_TABLES`
            (only `TABLE` and `EXTERNAL TABLE`).
          * **"COLUMN"** → lists columns for a table from `SVV_ALL_COLUMNS`
            ordered by `ordinal_position`.

        Args:
          resource_type: Target level to enumerate. One of `"DATABASE"`, `"SCHEMA"`,
            `"TABLE"`, `"COLUMN"`. If `None`, treated as `"DATABASE"`.
          parents: Optional mapping of parent identifiers used to scope the query.
            Required keys by level:
              - `"SCHEMA"`: `{"DATABASE": "<db>"}`
              - `"TABLE"`: `{"DATABASE": "<db>", "SCHEMA": "<schema>"}`
              - `"COLUMN"`: `{"DATABASE": "<db>", "SCHEMA": "<schema>", "TABLE": "<table>"}`

        Returns:
          A `ResourceFetchingDefinition` in **SQL_EXECUTION** mode with:
            - `sql`: The parameterized Redshift query for the requested level.
            - `sql_parameters`: A dict containing the resolved parent values.
            - `default_type`: The resource type for returned items.
            - `children`: The allowable child resource kinds for each returned item.

        Raises:
          ValueError: If `resource_type` is unsupported, or if a required parent is
            missing (propagated from `SqlHelper.get_required_resource_parent`).
        """
        match resource_type:
            case "SCHEMA":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                return ResourceFetchingDefinition.from_sql_execution(
                    f"SELECT schema_name FROM {database}.INFORMATION_SCHEMA.SCHEMATA ORDER BY schema_name;",
                    default_type="SCHEMA",
                    children=("TABLE",),
                )

            case "TABLE":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                schema = DatabaseTransformer.get_required_resource_parent(parents, "SCHEMA")
                return ResourceFetchingDefinition.from_sql_execution(
                    f"SELECT table_name FROM {database}.INFORMATION_SCHEMA.TABLES WHERE table_schema = :schema ORDER BY table_name;",
                    default_type="TABLE",
                    children=("COLUMN",),
                    sql_parameters={"schema": schema},
                )

            case "COLUMN":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                schema = DatabaseTransformer.get_required_resource_parent(parents, "SCHEMA")
                table = DatabaseTransformer.get_required_resource_parent(parents, "TABLE")
                return ResourceFetchingDefinition.from_sql_execution(
                    f"SELECT column_name FROM {database}.INFORMATION_SCHEMA.COLUMNS WHERE table_schema = :schema AND table_name = :table ORDER BY ordinal_position",
                    default_type="COLUMN",
                    children=(),
                    sql_parameters={"schema": schema, "table": table},
                )

            case "DATABASE" | None:
                return ResourceFetchingDefinition.from_sql_execution(
                    "SELECT database_name FROM snowflake.information_schema.databases ORDER BY database_name;",
                    default_type="DATABASE",
                    children=("SCHEMA",),
                )

            case other:
                raise ValueError(f"Unsupported resource type: {other!r}")

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["snowflake.connector"]
