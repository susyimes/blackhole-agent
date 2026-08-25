"""
SQLAlchemy 2.0 compatible dialect for Vertica.

This module provides a custom SQLAlchemy dialect for Vertica databases
that is compatible with SQLAlchemy 2.0+.
"""

from .dialect import VerticaDialect

__version__ = "0.1.0"
__all__ = ["VerticaDialect"]


# Register the dialect with SQLAlchemy
def register_dialect():
    """Register the dialect with SQLAlchemy."""
    try:
        from sqlalchemy.dialects import registry

        registry.register(
            "vertica.vertica_python",
            "sagemaker_studio.sql_engine._sqlalchemy_vertica.dialect",
            "VerticaDialect",
        )
    except ImportError:
        pass


# Auto-register on import
register_dialect()
