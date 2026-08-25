"""SQLAlchemy Workday Data Connect Dialect.

A SQLAlchemy dialect for Workday Data Connect that wraps Trino
with Workday-specific OAuth 2.0 JWT Bearer authentication.
"""

from . import dbapi
from .dbapi import connect
from .dialect import WorkdayDataConnectDialect

__version__ = "0.1.0"
__all__ = ["WorkdayDataConnectDialect", "dbapi", "connect"]


def register_dialect():
    """Register the dialect with SQLAlchemy."""
    try:
        from sqlalchemy.dialects import registry

        registry.register(
            "workday_data_connect",
            "sagemaker_studio.sql_engine._sqlalchemy_workday_data_connect.dialect",
            "WorkdayDataConnectDialect",
        )
        registry.register(
            "workday_data_connect.workday_data_connect",
            "sagemaker_studio.sql_engine._sqlalchemy_workday_data_connect.dialect",
            "WorkdayDataConnectDialect",
        )
    except ImportError:
        pass


# Auto-register on import
register_dialect()
