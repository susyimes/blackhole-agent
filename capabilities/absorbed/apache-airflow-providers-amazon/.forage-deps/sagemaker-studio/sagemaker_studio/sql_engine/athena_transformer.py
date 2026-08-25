import logging
from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer
from .resource_fetching_definition import ResourceFetchingDefinition, SQLAlchemyMetadataAction

logger = logging.getLogger(__name__)


class AthenaTransformer(DatabaseTransformer):
    """
    Database transformer for Amazon Athena connections.

    This transformer converts Athena connection configuration into SQLAlchemy-compatible
    format using the PyAthena driver. It handles Athena-specific requirements including
    workgroup configuration. The S3 query result location is resolved by the
    workgroup rather than passed client-side.
    """

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "presto"

    @staticmethod
    def get_execution_metadata(cursor: Any) -> Optional[Dict[str, Any]]:
        """Extract Athena execution metadata from the PyAthena cursor."""
        try:
            metadata: Dict[str, Any] = {}
            if hasattr(cursor, "query_id") and cursor.query_id:
                metadata["query_execution_id"] = cursor.query_id
            if (
                hasattr(cursor, "data_scanned_in_bytes")
                and cursor.data_scanned_in_bytes is not None
            ):
                metadata["data_scanned_bytes"] = cursor.data_scanned_in_bytes
            if (
                hasattr(cursor, "engine_execution_time_in_millis")
                and cursor.engine_execution_time_in_millis is not None
            ):
                metadata["engine_execution_time_ms"] = cursor.engine_execution_time_in_millis
            if (
                hasattr(cursor, "total_execution_time_in_millis")
                and cursor.total_execution_time_in_millis is not None
            ):
                metadata["total_execution_time_ms"] = cursor.total_execution_time_in_millis
            if (
                hasattr(cursor, "query_queue_time_in_millis")
                and cursor.query_queue_time_in_millis is not None
            ):
                metadata["query_queue_time_ms"] = cursor.query_queue_time_in_millis
            if (
                hasattr(cursor, "query_planning_time_in_millis")
                and cursor.query_planning_time_in_millis is not None
            ):
                metadata["query_planning_time_ms"] = cursor.query_planning_time_in_millis
            if (
                hasattr(cursor, "service_processing_time_in_millis")
                and cursor.service_processing_time_in_millis is not None
            ):
                metadata["service_processing_time_ms"] = cursor.service_processing_time_in_millis
            if hasattr(cursor, "submission_date_time") and cursor.submission_date_time:
                metadata["submission_time"] = cursor.submission_date_time.isoformat()
            if hasattr(cursor, "completion_date_time") and cursor.completion_date_time:
                metadata["completion_time"] = cursor.completion_date_time.isoformat()
            if hasattr(cursor, "state") and cursor.state:
                metadata["state"] = cursor.state
            if hasattr(cursor, "output_location") and cursor.output_location:
                metadata["output_location"] = cursor.output_location
            return metadata if metadata else None
        except Exception:
            logger.debug("Failed to extract Athena metadata", exc_info=True)
            return None

    @staticmethod
    def get_required_fields() -> List[str]:
        """
        Get required fields for Athena connections.

        Returns:
            List[str]: List containing "work_group" as the mandatory field
                for Athena connections. The S3 query result location is supplied
                by the workgroup configuration rather than client-side.
        """
        return ["work_group"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Athena connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the awsathena+rest driver
        and passes all connection data as connect_args for PyAthena.

        Args:
            connection_data (Dict[str, Any]): Athena connection configuration containing
                work_group, region, and AWS credentials.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: awsathena+rest:// URL for the specified region
                - connect_args: Original connection_data passed to PyAthena driver

        Raises:
            ValueError: If required fields (work_group) are missing.
        """
        AthenaTransformer.validate_required_fields(
            AthenaTransformer.get_required_fields(), connection_data
        )

        region = connection_data.get("region")

        connection_string = f"awsathena+rest://@athena.{region}.amazonaws.com"

        return {"connection_string": connection_string, "connect_args": connection_data}

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str], parents: Optional[Dict[str, str]] = None
    ) -> ResourceFetchingDefinition:
        """
        Build a definition for metadata-based resource discovery.

        Returns a `ResourceFetchingDefinition` configured to use SQLAlchemy’s
        Inspector for listing resources, based on the requested `resource_type`.
        If `resource_type` is `None`, it defaults to the database level.

        This method does **not** read `parents`; any required parent context
        (e.g., schema when listing tables) is supplied later by the consumer
        when executing the definition.

        Args:
          resource_type: Which level to discover. Supported values:
            `"DATABASE"`, `"TABLE"`, `"COLUMN"`. If `None`, treated as `"DATABASE"`.
          parents: Optional mapping of parent identifiers. Ignored here, kept
            for syntax purposes.

        Returns:
          A `ResourceFetchingDefinition` in SQLAlchemy-metadata mode with:
            - `GET_TABLE_NAMES` for `"TABLE"` (children: `("COLUMN",)`),
            - `GET_COLUMN_NAMES` for `"COLUMN"` (children: `()`),
            - `GET_SCHEMA_NAMES` for `"DATABASE"` or `None` (children: `("TABLE",)`).

        Raises:
          ValueError: If `resource_type` is not one of the supported values.
        """
        match resource_type:
            case "TABLE":
                return ResourceFetchingDefinition.from_sqlalchemy_metadata(
                    SQLAlchemyMetadataAction.GET_TABLE_NAMES,
                    default_type="TABLE",
                    children=("COLUMN",),
                )
            case "COLUMN":
                return ResourceFetchingDefinition.from_sqlalchemy_metadata(
                    SQLAlchemyMetadataAction.GET_COLUMN_NAMES,
                    default_type="COLUMN",
                    children=(),
                )
            case "DATABASE" | None:
                return ResourceFetchingDefinition.from_sqlalchemy_metadata(
                    SQLAlchemyMetadataAction.GET_SCHEMA_NAMES,
                    default_type="DATABASE",
                    children=("TABLE",),
                )
            case other:
                raise ValueError(f"Unsupported resource type: {other!r}")
