from typing import Any, Dict, List
from urllib.parse import quote_plus

# Import to register the custom Vertica dialect with SQLAlchemy
from . import _sqlalchemy_vertica  # noqa: F401
from .database_transformer import DatabaseTransformer


class VerticaTransformer(DatabaseTransformer):

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "database", "user", "password"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Vertica connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the vertica-python driver
        for connecting to Vertica databases.

        Args:
            connection_data (Dict[str, Any]): Vertica connection configuration containing
                host, port, database, user and password.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: vertica+vertica_python:// URL for the given connection configuration
        Raises:
            ValueError: If required fields are missing.
        """
        VerticaTransformer.validate_required_fields(
            VerticaTransformer.get_required_fields(), connection_data
        )

        host = connection_data.get("host")
        port = connection_data.get("port")
        user = connection_data.get("user")
        password = connection_data.get("password")
        database = connection_data.get("database")

        # URL-encode user, password, and database to handle special characters
        encoded_user = quote_plus(str(user))
        encoded_password = quote_plus(str(password))
        encoded_database = quote_plus(str(database))

        connection_string = f"vertica+vertica_python://{encoded_user}:{encoded_password}@{host}:{port}/{encoded_database}"
        return {"connection_string": connection_string}

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["vertica_python"]
