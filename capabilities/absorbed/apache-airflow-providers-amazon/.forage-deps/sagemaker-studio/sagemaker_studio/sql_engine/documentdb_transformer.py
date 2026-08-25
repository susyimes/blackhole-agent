from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from .database_transformer import DatabaseTransformer


class DocumentDBTransformer(DatabaseTransformer):
    """
    Database transformer for Amazon DocumentDB connections.

    Transforms DocumentDB connection configuration into SQLAlchemy-compatible format
    using the pymongosql driver. Supports both BASIC (username/password) and IAM
    (MONGODB-AWS) authentication mechanisms.
    """

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return None  # MongoDB query language, not a SQL dialect supported by sqlglot

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "database"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform DocumentDB connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the pymongosql driver.
        Handles both BASIC auth (username/password) and IAM auth (MONGODB-AWS mechanism).

        The connection string follows AWS DocumentDB recommended patterns:
        - retryWrites=false (DocumentDB does not support retryable writes)
        - replicaSet=rs0 (connect as replica set for cluster endpoints)
        - readPreference=secondaryPreferred (distribute reads to replicas)

        Args:
            connection_data (Dict[str, Any]): DocumentDB connection configuration containing:
                - host (required): DocumentDB cluster endpoint
                - port (required): Port number (typically 27017)
                - database (required): Database name
                - auth_mechanism (optional): "MONGODB-AWS" for IAM auth, None for BASIC
                - user (optional): Username for BASIC auth
                - password (optional): Password for BASIC auth
                - tls (optional): Whether to use TLS (default True)

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: mongodb:// URL for the given connection configuration

        Raises:
            ValueError: If required fields are missing.
        """
        DocumentDBTransformer.validate_required_fields(
            DocumentDBTransformer.get_required_fields(), connection_data
        )

        host = connection_data["host"]
        port = connection_data["port"]
        database = connection_data["database"]
        auth_mechanism = connection_data.get("auth_mechanism")
        tls = connection_data.get("tls", True)

        # Build query parameters following AWS DocumentDB best practices
        params = [
            "retryWrites=false",
            "replicaSet=rs0",
            "readPreference=secondaryPreferred",
        ]

        if tls:
            params.append("tls=true")

        if auth_mechanism == "MONGODB-AWS":
            # IAM auth — no credentials in URL, pymongo picks them up from environment
            params.append("authMechanism=MONGODB-AWS")
            params.append("authSource=%24external")
            query_string = "&".join(params)
            connection_string = f"mongodb://{host}:{port}/{database}?{query_string}"
        else:
            # BASIC auth — embed credentials in URL
            user = connection_data.get("user", "")
            password = connection_data.get("password", "")
            # URL-encode credentials to handle special characters
            encoded_user = quote_plus(str(user)) if user else ""
            encoded_password = quote_plus(str(password)) if password else ""
            query_string = "&".join(params)
            connection_string = (
                f"mongodb://{encoded_user}:{encoded_password}@{host}:{port}"
                f"/{database}?{query_string}"
            )

        return {"connection_string": connection_string}

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for DocumentDB connections.
        """
        return ["pymongo", "pymongosql"]
