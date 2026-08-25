from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer


class MySQLTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "mysql"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "database", "user", "password"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform MySQL connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the mysql driver
        and passes all connection data as connect_args for pymysql.

        Args:
            connection_data (Dict[str, Any]): MySQL connection configuration containing
                host, port, database, user and password.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: mysql+pymysql:// URL for the given connection configuration
        Raises:
            ValueError: If required fields are missing.
        """
        MySQLTransformer.validate_required_fields(
            MySQLTransformer.get_required_fields(), connection_data
        )

        host = connection_data.get("host")
        port = connection_data.get("port")
        user = connection_data.get("user")
        database = connection_data.get("database")

        connection_string = f"mysql+pymysql://{user}@{host}:{port}/{database}"

        return {"connection_string": connection_string, "connect_args": connection_data}

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["pymysql"]
