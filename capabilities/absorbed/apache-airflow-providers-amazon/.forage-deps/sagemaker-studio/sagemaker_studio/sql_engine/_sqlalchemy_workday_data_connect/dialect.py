"""SQLAlchemy dialect for Workday Data Connect.

Registers as workday_data_connect:// and uses the Workday DBAPI layer
which wraps trino with SDEAuth internally.
"""

from trino.sqlalchemy.dialect import TrinoDialect


class WorkdayDataConnectDialect(TrinoDialect):
    """SQLAlchemy dialect for Workday Data Connect over Trino wire protocol."""

    name = "workday_data_connect"
    driver = "workday_data_connect"
    supports_statement_cache = True

    @classmethod
    def import_dbapi(cls):
        from . import dbapi

        return dbapi

    @classmethod
    def dbapi(cls):
        from . import dbapi

        return dbapi

    def create_connect_args(self, url):
        """Parse workday_data_connect:// URL into connection kwargs.

        URL format:
            workday_data_connect://host:port?client_id=...&isu=...&token_endpoint=...&private_key=...
        """
        opts = {}
        opts["host"] = url.host or "localhost"
        opts["port"] = url.port or 443

        # Auth params from query string
        query = dict(url.query) if url.query else {}
        opts["client_id"] = query.pop("client_id", "")
        opts["isu"] = query.pop("isu", "")
        opts["token_endpoint"] = query.pop("token_endpoint", "")
        opts["private_key"] = query.pop("private_key", "")

        if "include_path_prefix" in query:
            opts["include_path_prefix"] = query.pop("include_path_prefix")
        if "session_properties" in query:
            opts["session_properties"] = query.pop("session_properties")

        return ([], opts)

    def connect(self, *cargs, **cparams):
        from .dbapi import Connection

        return Connection(**cparams)
