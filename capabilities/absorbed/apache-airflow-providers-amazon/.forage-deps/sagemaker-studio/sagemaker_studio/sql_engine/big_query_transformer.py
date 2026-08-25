import base64
import json
from typing import Any, Dict, List, Optional

from sagemaker_studio.sql_engine.database_transformer import DatabaseTransformer


class BigQueryTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "bigquery"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["project_id"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform BigQuery connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the bigquery driver
        and passes all connection data as connect_args for sqlalchemy-bigquery.

        Args:
            connection_data (Dict[str, Any]): BigQuery service key.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: bigquery:// URL for the specified region
                - connect_args: Original connection_data passed to sqlalchemy-bigquery driver

        Raises:
            ValueError: If required fields (project_id) are missing.
        """
        BigQueryTransformer.validate_required_fields(
            BigQueryTransformer.get_required_fields(), connection_data
        )

        project = connection_data.get("project_id")

        encoded = base64.b64encode(json.dumps(connection_data).encode()).decode()

        return_obj = {"connection_string": f"bigquery://{project}?credentials_base64={encoded}"}
        return return_obj

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return [
            "sqlalchemy.dialects.bigquery",
            "google.cloud.bigquery",
            "google.api_core",
            "google.auth",
        ]
