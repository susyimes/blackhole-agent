from typing import Any, Dict, List, Optional

# Ensure the dialect is registered on import
import sagemaker_studio.sql_engine._sqlalchemy_opensearch.dialect  # noqa: F401
from sagemaker_studio.sql_engine.database_transformer import DatabaseTransformer
from sagemaker_studio.sql_engine.resource_fetching_definition import (
    ResourceFetchingDefinition,
    SQLAlchemyMetadataAction,
)


class OpenSearchTransformer(DatabaseTransformer):
    """
    Database transformer for OpenSearch connections.

    This transformer converts OpenSearch connection configuration into SQLAlchemy-compatible
    format using the native OpenSearch SQLAlchemy dialect. It handles OpenSearch-specific
    requirements including domain endpoints, authentication, and SSL configuration.
    """

    @staticmethod
    def get_required_fields() -> List[str]:
        """
        Get required fields for OpenSearch connections.

        Returns:
            List[str]: List containing required fields for OpenSearch connections:
                - domain_endpoint: OpenSearch domain endpoint (mandatory)
                - user: Username for authentication (mandatory)
                - password: Password for authentication (mandatory)
        """
        return ["domain_endpoint", "user", "password"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform OpenSearch connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the native OpenSearch dialect.
        All required fields must be provided, and the domain_endpoint is assumed to be HTTPS.

        Args:
            connection_data (Dict[str, Any]): OpenSearch connection configuration containing:
                - domain_endpoint (required): OpenSearch domain endpoint (assumed HTTPS)
                - user (required): user for basic authentication
                - password (required): Password for basic authentication

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: opensearch:// URL (without credentials)
                - connect_args: Dict with username and password

        Raises:
            ValueError: If required fields are missing.
        """
        OpenSearchTransformer.validate_required_fields(
            OpenSearchTransformer.get_required_fields(), connection_data
        )

        domain_endpoint = connection_data.get("domain_endpoint")
        username = connection_data.get("user")
        password = connection_data.get("password")

        # Clean up domain endpoint (remove protocol if present, assume HTTPS)
        if domain_endpoint.startswith("https://"):
            domain_endpoint = domain_endpoint[8:]
        elif domain_endpoint.startswith("http://"):
            domain_endpoint = domain_endpoint[7:]

        # Keep credentials out of the URL to avoid encoding issues with
        # special characters in passwords. Pass them via connect_args instead.
        connection_string = f"opensearch://{domain_endpoint}/_all"
        return {
            "connection_string": connection_string,
            "connect_args": {
                "username": username,
                "password": password,
            },
        }

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str], parents: Optional[Dict[str, str]] = None
    ) -> ResourceFetchingDefinition:
        """
        Build a definition for metadata-based resource discovery.

        Returns a `ResourceFetchingDefinition` configured to use SQLAlchemy's
        Inspector for listing resources, based on the requested `resource_type`.
        If `resource_type` is `None`, it defaults to the database level.

        For OpenSearch, the hierarchy is:
        - DATABASE level: OpenSearch indices (treated as schemas/databases)
        - TABLE level: Index mappings (treated as tables)
        - COLUMN level: Field mappings (treated as columns)

        Args:
          resource_type: Which level to discover. Supported values:
            `"DATABASE"`, `"TABLE"`, `"COLUMN"`. If `None`, treated as `"DATABASE"`.
          parents: Optional mapping of parent identifiers. For OpenSearch:
            - TABLE level requires: `{"DATABASE": "<index_name>"}`
            - COLUMN level requires: `{"DATABASE": "<index_name>", "TABLE": "<mapping_name>"}`

        Returns:
          A `ResourceFetchingDefinition` in SQLAlchemy-metadata mode with:
            - `GET_SCHEMA_NAMES` for `"DATABASE"` or `None` (lists indices)
            - `GET_TABLE_NAMES` for `"TABLE"` (lists mappings in an index)
            - `GET_COLUMN_NAMES` for `"COLUMN"` (lists fields in a mapping)

        Raises:
          ValueError: If `resource_type` is not one of the supported values.
        """
        match resource_type:
            case "TABLE":
                # In OpenSearch context, "tables" are indices or document mappings
                return ResourceFetchingDefinition.from_sqlalchemy_metadata(
                    SQLAlchemyMetadataAction.GET_TABLE_NAMES,
                    default_type="TABLE",
                    children=("COLUMN",),
                )
            case "COLUMN":
                # In OpenSearch context, "columns" are fields in the document mapping
                return ResourceFetchingDefinition.from_sqlalchemy_metadata(
                    SQLAlchemyMetadataAction.GET_COLUMN_NAMES,
                    default_type="COLUMN",
                    children=(),
                )
            case "DATABASE" | None:
                # In OpenSearch context, "databases" are indices (treated as schemas)
                return ResourceFetchingDefinition.from_sqlalchemy_metadata(
                    SQLAlchemyMetadataAction.GET_SCHEMA_NAMES,
                    default_type="DATABASE",
                    children=("TABLE",),
                )
            case other:
                raise ValueError(f"Unsupported resource type: {other!r}")

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for OpenSearch connections
                with the native OpenSearch SQLAlchemy dialect.
        """
        return [
            "opensearch",
            "opensearchpy",
            "opensearch.connection",
            "opensearch.transport",
            "sagemaker_studio.sql_engine._sqlalchemy_opensearch",
        ]
