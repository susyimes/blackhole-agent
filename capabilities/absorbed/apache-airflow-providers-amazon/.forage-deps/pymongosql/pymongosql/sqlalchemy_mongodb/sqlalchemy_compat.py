# -*- coding: utf-8 -*-
import warnings
from typing import Any, Dict, Optional

try:
    import sqlalchemy

    SQLALCHEMY_VERSION = tuple(map(int, sqlalchemy.__version__.split(".")[:2]))
    SQLALCHEMY_2X = SQLALCHEMY_VERSION >= (2, 0)
    HAS_SQLALCHEMY = True
except ImportError:
    SQLALCHEMY_VERSION = None
    SQLALCHEMY_2X = False
    HAS_SQLALCHEMY = False


def get_sqlalchemy_version() -> Optional[tuple]:
    """Get the installed SQLAlchemy version as a tuple.

    Returns:
        Tuple of (major, minor) version numbers, or None if not installed.

    Example:
        >>> get_sqlalchemy_version()
        (2, 0)
    """
    return SQLALCHEMY_VERSION


def is_sqlalchemy_2x() -> bool:
    """Check if SQLAlchemy 2.x is installed.

    Returns:
        True if SQLAlchemy 2.x or later is installed, False otherwise.
    """
    return SQLALCHEMY_2X


def check_sqlalchemy_compatibility() -> Dict[str, Any]:
    """Check SQLAlchemy compatibility and return status information.

    Returns:
        Dictionary with compatibility information.
    """
    if not HAS_SQLALCHEMY:
        return {
            "installed": False,
            "version": None,
            "compatible": False,
            "message": "SQLAlchemy not installed. Install with: pip install sqlalchemy>=1.4.0",
        }

    if SQLALCHEMY_VERSION < (1, 4):
        return {
            "installed": True,
            "version": SQLALCHEMY_VERSION,
            "compatible": False,
            "message": f'SQLAlchemy {".".join(map(str, SQLALCHEMY_VERSION))} is too old. Requires 1.4.0 or later.',
        }

    return {
        "installed": True,
        "version": SQLALCHEMY_VERSION,
        "compatible": True,
        "is_2x": SQLALCHEMY_2X,
        "message": f'SQLAlchemy {".".join(map(str, SQLALCHEMY_VERSION))} is compatible.',
    }


def get_base_class():
    """Get the appropriate base class for ORM models.

    Returns version-appropriate base class for declarative models.

    Returns:
        Base class for SQLAlchemy ORM models.

    Example:
        >>> Base = get_base_class()
        >>> class User(Base):
        ...     __tablename__ = 'users'
        ...     # ... model definition
    """
    if not HAS_SQLALCHEMY:
        raise ImportError("SQLAlchemy is required but not installed")

    if SQLALCHEMY_2X:
        # SQLAlchemy 2.x style
        try:
            from sqlalchemy.orm import DeclarativeBase

            class Base(DeclarativeBase):
                pass

            return Base
        except ImportError:
            # Fallback to 1.x style if DeclarativeBase not available
            from sqlalchemy.ext.declarative import declarative_base

            return declarative_base()
    else:
        # SQLAlchemy 1.x style
        from sqlalchemy.ext.declarative import declarative_base

        return declarative_base()


def create_pymongosql_engine(url: str, **kwargs):
    """Create a PyMongoSQL engine with version-appropriate settings.

    Args:
        url: Database URL (e.g., 'pymongosql://localhost:27017/mydb')
        **kwargs: Additional arguments passed to create_engine

    Returns:
        SQLAlchemy engine configured for PyMongoSQL.

    Example:
        >>> engine = create_pymongosql_engine('pymongosql://localhost:27017/mydb')
    """
    if not HAS_SQLALCHEMY:
        raise ImportError("SQLAlchemy is required but not installed")

    from sqlalchemy import create_engine

    # Version-specific default configurations
    if SQLALCHEMY_2X:
        # SQLAlchemy 2.x defaults
        defaults = {
            "echo": False,
            "future": True,  # Use future engine interface
        }
    else:
        # SQLAlchemy 1.x defaults
        defaults = {
            "echo": False,
        }

    # Merge user kwargs with defaults
    engine_kwargs = {**defaults, **kwargs}

    return create_engine(url, **engine_kwargs)


def get_session_maker(engine, **kwargs):
    """Get a session maker with version-appropriate configuration.

    Args:
        engine: SQLAlchemy engine
        **kwargs: Additional arguments for sessionmaker

    Returns:
        Configured sessionmaker class.
    """
    if not HAS_SQLALCHEMY:
        raise ImportError("SQLAlchemy is required but not installed")

    from sqlalchemy.orm import sessionmaker

    if SQLALCHEMY_2X:
        # SQLAlchemy 2.x session configuration
        defaults = {}
    else:
        # SQLAlchemy 1.x session configuration
        defaults = {}

    session_kwargs = {**defaults, **kwargs}

    return sessionmaker(bind=engine, **session_kwargs)


def warn_if_incompatible():
    """Issue a warning if SQLAlchemy version is incompatible."""
    compat_info = check_sqlalchemy_compatibility()

    if not compat_info["compatible"]:
        warnings.warn(f"PyMongoSQL SQLAlchemy integration: {compat_info['message']}", UserWarning, stacklevel=2)


# Compatibility constants for easy access
__all__ = [
    "SQLALCHEMY_VERSION",
    "SQLALCHEMY_2X",
    "HAS_SQLALCHEMY",
    "get_sqlalchemy_version",
    "is_sqlalchemy_2x",
    "check_sqlalchemy_compatibility",
    "get_base_class",
    "create_pymongosql_engine",
    "get_session_maker",
    "warn_if_incompatible",
]

# Warn on import if incompatible
if HAS_SQLALCHEMY:
    warn_if_incompatible()
