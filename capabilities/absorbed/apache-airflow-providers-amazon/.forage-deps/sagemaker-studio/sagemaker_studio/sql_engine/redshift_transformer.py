from typing import Any, Dict, List, Optional

from . import _sqlalchemy_redshift_data_api  # noqa: F401
from .database_transformer import DatabaseTransformer
from .resource_fetching_definition import ResourceFetchingDefinition


class RedshiftTransformer(DatabaseTransformer):
    """
    Database transformer for Amazon Redshift connections.

    This transformer converts Redshift connection configuration into SQLAlchemy-compatible
    format using the redshift_data_api driver. It handles both serverless and provisioned
    Redshift clusters with appropriate connection string formatting.
    """

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "redshift"

    @staticmethod
    def get_execution_metadata(cursor: Any) -> Optional[Dict[str, Any]]:
        """Extract Redshift Data API execution metadata from the cursor.

        Returns:
            Dict with statement_id, session_id, has_result_set, and records_updated.
        """
        if hasattr(cursor, "get_execution_metadata"):
            return cursor.get_execution_metadata()
        return None

    @staticmethod
    def get_required_fields() -> List[str]:
        """
        Get required fields for Redshift connections.

        Returns:
            List[str]: List containing "database_name" as the mandatory field
                for Redshift connections.
        """
        return ["database_name"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Redshift connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the redshift_data_api driver
        with appropriate formatting for serverless vs provisioned clusters.

        Args:
            connection_data (Dict[str, Any]): Redshift connection configuration containing
                database_name, region, and either cluster_identifier (provisioned) or
                workgroup_name (serverless), plus optional db_user.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: redshift_data_api:// URL with cluster/workgroup info
                - connect_args: Original connection_data passed to the driver

        Connection string formats:
            - Provisioned: redshift_data_api://cluster_id/database?region=region&db_user=user
            - Serverless: redshift_data_api:///database?region=region&workgroup_name=workgroup

        Raises:
            ValueError: If required field (database_name) is missing.
        """
        RedshiftTransformer.validate_required_fields(
            RedshiftTransformer.get_required_fields(), connection_data
        )

        cluster_identifier = connection_data.get("cluster_identifier")
        workgroup_name = connection_data.get("workgroup_name")
        database_name = connection_data.get("database_name")
        region = connection_data.get("region")
        db_user = connection_data.get("db_user")

        is_serverless = workgroup_name is not None and cluster_identifier is None

        connection_string = "redshift_data_api://"

        if not is_serverless:
            connection_string += f"{cluster_identifier}"

        connection_string += f"/{database_name}?region={region}"

        if is_serverless:
            connection_string += f"&workgroup_name={workgroup_name}"

        if db_user:
            connection_string += f"&db_user={db_user}"

        return {"connection_string": connection_string, "connect_args": connection_data}

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str],
        parents: Optional[Dict[str, str]] = None,
    ) -> ResourceFetchingDefinition:
        """
        Build a SQL-execution plan for listing Redshift resources.

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
                    "SELECT schema_name FROM svv_all_schemas "
                    "WHERE database_name=:database "
                    "AND schema_name NOT IN ('pg_catalog', 'pg_internal', 'information_schema')",
                    default_type="SCHEMA",
                    children=("TABLE",),
                    sql_parameters={"database": database},
                )

            case "TABLE":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                schema = DatabaseTransformer.get_required_resource_parent(parents, "SCHEMA")
                return ResourceFetchingDefinition.from_sql_execution(
                    "SELECT table_name FROM SVV_ALL_TABLES "
                    "WHERE database_name=:database AND schema_name=:schema "
                    "AND table_type IN ('TABLE','EXTERNAL TABLE')",
                    default_type="TABLE",
                    children=("COLUMN",),
                    sql_parameters={"database": database, "schema": schema},
                )

            case "COLUMN":
                database = DatabaseTransformer.get_required_resource_parent(parents, "DATABASE")
                schema = DatabaseTransformer.get_required_resource_parent(parents, "SCHEMA")
                table = DatabaseTransformer.get_required_resource_parent(parents, "TABLE")
                return ResourceFetchingDefinition.from_sql_execution(
                    "SELECT * FROM SVV_ALL_COLUMNS "
                    "WHERE database_name =:database AND schema_name =:schema AND table_name=:table "
                    "ORDER BY ordinal_position",
                    default_type="COLUMN",
                    children=(),
                    sql_parameters={"database": database, "schema": schema, "table": table},
                )

            case "DATABASE" | None:
                return ResourceFetchingDefinition.from_sql_execution(
                    "SELECT database_name as databasename, "
                    "database_type as databasetype FROM svv_redshift_databases",
                    default_type="DATABASE",
                    children=("SCHEMA",),
                )

            case other:
                raise ValueError(f"Unsupported resource type: {other!r}")
