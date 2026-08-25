from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer


class OracleTransformer(DatabaseTransformer):

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "oracle"

    @staticmethod
    def get_required_fields() -> List[str]:
        return ["host", "port", "database", "user", "password"]

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Oracle connection data into SQLAlchemy configuration.

        Creates a SQLAlchemy connection string using the oracledb driver
        for connecting to Oracle databases. Uses a TCPS connect descriptor
        passed via connect_args to support Oracle Autonomous Database and
        other TLS-enabled instances.

        Args:
            connection_data (Dict[str, Any]): Oracle connection configuration containing
                host, port, database (service name), user and password.

        Returns:
            Dict[str, Any]: SQLAlchemy configuration with:
                - connection_string: oracle+oracledb:// URL with credentials only
                - creator: A callable that returns an oracledb connection using TCPS
        Raises:
            ValueError: If required fields are missing.
        """
        OracleTransformer.validate_required_fields(
            OracleTransformer.get_required_fields(), connection_data
        )

        host = connection_data.get("host")
        port = connection_data.get("port")
        user = connection_data.get("user")
        password = connection_data.get("password")
        database = connection_data.get("database")

        # Build a TCPS connect descriptor for secure connections (required by Oracle ADB).
        # retry_count and retry_delay are recommended by Oracle for ADB connections to
        # handle transient network issues during TLS establishment.
        dsn = (
            f"(description="
            f"(retry_count=20)(retry_delay=3)"
            f"(address=(protocol=tcps)(port={port})(host={host}))"
            f"(connect_data=(service_name={database}))"
            f"(security=(ssl_server_dn_match=yes)))"
        )

        # Use a creator function to establish the connection directly via oracledb.
        # This is required because SQLAlchemy's URL-based connection uses plain TCP,
        # but Oracle ADB requires TCPS (TLS). The creator bypasses SQLAlchemy's
        # URL parsing and connects using the full TCPS connect descriptor.
        import oracledb

        def creator():
            return oracledb.connect(user=user, password=password, dsn=dsn)

        connection_string = "oracle+oracledb://@"

        from sqlalchemy.pool import NullPool

        return {
            "connection_string": connection_string,
            "creator": creator,
            "poolclass": NullPool,
            "isolation_level": "AUTOCOMMIT",
            "thick_mode": False,
        }

    @staticmethod
    def get_loggers() -> List[str]:
        """
        Get the list of loggers used for this database connection type.

        Returns:
            List[str]: List of loggers that are used for this database connection type.
        """
        return ["oracledb"]
