from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer


class MSSQLTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "tsql"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "database", "user", "password"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform MSSQL connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the mssql driver
        and passes all connection data as connect_args for sqlalchemy-bigquery.

        Args:
            connection_data (Dict[str, Any]):  MSSQL connection configuration containing
                host, port, database, user and password.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: mssql+pymssql:// URL for the given connection configuration
        Raises:
            ValueError: If required fields are missing.
        """
        MSSQLTransformer.validate_required_fields(
            MSSQLTransformer.get_required_fields(), connection_data
        )

        host = connection_data.get("host")
        port = connection_data.get("port")
        user = connection_data.get("user")
        password = connection_data.get("password")
        database = connection_data.get("database")

        connection_string = f"mssql+pymssql://{user}:{password}@{host}:{port}/{database}"

        return {"connection_string": connection_string}

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["pymssql", "pymssql._pymssql"]
