from typing import Any, Dict, List, Optional

from sagemaker_studio.sql_engine.database_transformer import DatabaseTransformer


class DynamoDBTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return None  # PartiQL not supported by sqlglot

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["region"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform DynamoDB connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the dynamodb driver
        and passes all connection data as connect_args for pydynamodb.

        Args:
            connection_data (Dict[str, Any]): Includes region to be connected to.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: dynamodb:// URL for the specified region
        Raises:
            ValueError: If required fields (region) are missing.
        """
        DynamoDBTransformer.validate_required_fields(
            DynamoDBTransformer.get_required_fields(), connection_data
        )
        region = connection_data["region"]

        connection_string = f"dynamodb://@dynamodb.{region}.amazonaws.com:443?region_name={region}"

        return {"connection_string": connection_string}

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["pydynamodb"]
