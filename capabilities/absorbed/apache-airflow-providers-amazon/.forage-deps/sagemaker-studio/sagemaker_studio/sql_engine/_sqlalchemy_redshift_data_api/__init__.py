"""
SQLAlchemy Redshift Data API Dialect

A SQLAlchemy dialect for Amazon Redshift using the Data API.
"""

from . import dbapi
from .dbapi import connect
from .dialect import RedshiftDataAPIDialect

__version__ = "0.1.0"
__all__ = ["RedshiftDataAPIDialect", "dbapi", "connect"]


# Register the dialect with SQLAlchemy
def register_dialect():
    """Register the dialect with SQLAlchemy."""
    try:
        from sqlalchemy.dialects import registry

        registry.register(
            "redshift_data_api",
            "sagemaker_studio.sql_engine._sqlalchemy_redshift_data_api.dialect",
            "RedshiftDataAPIDialect",
        )
        registry.register(
            "redshift_data_api.redshift_data_api",
            "sagemaker_studio.sql_engine._sqlalchemy_redshift_data_api.dialect",
            "RedshiftDataAPIDialect",
        )
    except ImportError:
        pass


# Auto-register on import
register_dialect()
