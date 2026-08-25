from typing import Any, Dict, List, Optional

from sqlalchemy.engine import URL

from .database_transformer import DatabaseTransformer

try:  # pragma: no cover
    import teradatasql  # noqa: F401
    import teradatasqlalchemy  # noqa: F401

    _TERADATA_DEPS_AVAILABLE = True
except ImportError:
    _TERADATA_DEPS_AVAILABLE = False


class TeraDataTransformer(DatabaseTransformer):
    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "teradata"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "database", "user", "password"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Teradata connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy URL using URL.create() for safe encoding of all
        connection components, preventing connection-string injection attacks.
        Enforces TLS with sslmode=REQUIRE to prevent cleartext credential exposure.

        Args:
            connection_data (Dict[str, Any]): Teradata connection configuration containing
                host, port, database, user and password.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: SQLAlchemy URL object for the given connection configuration
                - connect_args: Additional connection arguments including dbs_port and TLS settings
        Raises:
            ImportError: If teradatasql or teradatasqlalchemy packages are not installed.
            ValueError: If required fields are missing.
        """
        if not _TERADATA_DEPS_AVAILABLE:
            raise ImportError(
                "Teradata support requires the 'teradatasql' and 'teradatasqlalchemy' packages. "
                "Install them with: pip install sagemaker-studio[teradata]"
            )
        TeraDataTransformer.validate_required_fields(
            TeraDataTransformer.get_required_fields(), connection_data
        )

        host = connection_data.get("host")
        port = connection_data.get("port")
        user = connection_data.get("user")
        password = connection_data.get("password")
        database = connection_data.get("database")

        connection_url = URL.create(
            drivername="teradatasql",
            username=user,
            password=password,
            host=host,
            query={"database": database},
        )

        connect_args = {
            "dbs_port": port,
            "sslmode": "REQUIRE",
        }

        return {"connection_string": connection_url, "connect_args": connect_args}

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["sqlalchemy.dialects.teradata", "teradatasql"]
