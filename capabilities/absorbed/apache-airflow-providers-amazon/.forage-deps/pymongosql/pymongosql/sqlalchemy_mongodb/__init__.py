# -*- coding: utf-8 -*-
# SQLAlchemy integration
try:
    # Import and register the dialect automatically
    from .sqlalchemy_compat import (
        get_sqlalchemy_version,
        is_sqlalchemy_2x,
    )

    # Make compatibility info easily accessible
    __sqlalchemy_version__ = get_sqlalchemy_version()
    __supports_sqlalchemy__ = __sqlalchemy_version__ is not None
    __supports_sqlalchemy_2x__ = is_sqlalchemy_2x()

except ImportError:
    # SQLAlchemy not available
    __sqlalchemy_version__ = None
    __supports_sqlalchemy__ = False
    __supports_sqlalchemy_2x__ = False


def create_engine_url(
    host: str = "localhost", port: int = 27017, database: str = "test", mode: str = "standard", **kwargs
) -> str:
    """Create a SQLAlchemy engine URL for PyMongoSQL.

    Args:
        host: MongoDB host
        port: MongoDB port
        database: Database name
        mode: Connection mode - "standard" (default) or "superset" (with subquery support)
        **kwargs: Additional connection parameters

    Returns:
        SQLAlchemy URL string

    Example:
        >>> # Standard mode
        >>> url = create_engine_url("localhost", 27017, "mydb")
        >>> engine = sqlalchemy.create_engine(url)
        >>> # Superset mode with subquery support
        >>> url = create_engine_url("localhost", 27017, "mydb", mode="superset")
        >>> engine = sqlalchemy.create_engine(url)
    """
    scheme = "mongodb"

    params = []
    for key, value in kwargs.items():
        params.append(f"{key}={value}")

    # Add mode parameter if not standard
    if mode != "standard":
        params.append(f"mode={mode}")

    param_str = "&".join(params)
    if param_str:
        param_str = "?" + param_str

    return f"{scheme}://{host}:{port}/{database}{param_str}"


def register_dialect():
    """Register the PyMongoSQL dialect with SQLAlchemy.

    This function handles registration for both SQLAlchemy 1.x and 2.x.
    Registers support for standard, SRV, and superset MongoDB connection strings.
    """
    try:
        from sqlalchemy.dialects import registry

        # Register for standard MongoDB URLs
        registry.register("mongodb", "pymongosql.sqlalchemy_mongodb.sqlalchemy_dialect", "PyMongoSQLDialect")
        # Register for MongoDB SRV URLs
        try:
            registry.register("mongodb+srv", "pymongosql.sqlalchemy_mongodb.sqlalchemy_dialect", "PyMongoSQLDialect")
            registry.register("mongodb.srv", "pymongosql.sqlalchemy_mongodb.sqlalchemy_dialect", "PyMongoSQLDialect")
        except Exception:
            # If registration fails, users can convert URIs to standard mongodb:// format
            pass

        return True
    except ImportError:
        # Fallback for versions without registry
        return False
    except Exception:
        # Handle other registration errors gracefully
        return False


# Attempt registration on module import
_registration_successful = register_dialect()

# Export all SQLAlchemy-related functionality
__all__ = [
    "create_engine_url",
    "register_dialect",
    "__sqlalchemy_version__",
    "__supports_sqlalchemy__",
    "__supports_sqlalchemy_2x__",
    "_registration_successful",
]

# Note: PyMongoSQL now uses standard MongoDB connection strings directly
# No need for PyMongoSQL-specific URL format
