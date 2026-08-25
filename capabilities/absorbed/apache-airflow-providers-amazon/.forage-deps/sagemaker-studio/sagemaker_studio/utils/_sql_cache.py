"""Internal module for SQL connection cache management."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)


@dataclass
class ManagedConnection:
    """Represents a managed database connection with its engine and lifecycle metadata."""

    engine: Engine
    connection: Optional[Connection]  # None for non-persisted sessions
    id: str  # Unique identifier for this cache entry (UUID)
    cache_key: str  # Full cache key including config: "conn_123::catalog_name=prod"
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_used is None:
            self.last_used = datetime.now()


class ConnectionCache:
    """
    Manages persistent database connections for reuse across queries.

    Connections are cached by their identifier (connection_id or connection_name)
    and remain open until explicitly closed or the kernel restarts.
    """

    def __init__(self):
        self._cache: Dict[str, ManagedConnection] = {}  # cache_key -> ManagedConnection
        self._id_to_key: Dict[str, str] = {}  # id (UUID) -> cache_key

    def get(self, key: str) -> Optional[ManagedConnection]:
        """Retrieve a cached connection by key."""
        cached = self._cache.get(key)
        if not cached:
            return None

        # Lazy health check - validate connection is not closed
        try:
            if cached.connection is not None and cached.connection.closed:
                logger.warning(f"Cached connection {key} is closed, removing from cache")
                self.remove(key)
                return None
        except Exception as e:
            logger.warning(f"Error checking connection {key} status: {e}, removing from cache")
            self.remove(key)
            return None

        # Update last_used timestamp
        cached.last_used = datetime.now()
        return cached

    def put(self, key: str, managed_conn: ManagedConnection) -> None:
        """Cache a connection."""
        self._cache[key] = managed_conn
        self._id_to_key[managed_conn.id] = key

    def remove(self, key: str) -> bool:
        """
        Remove and close a cached connection.

        Returns:
            bool: True if connection was found and closed, False otherwise.
        """
        if key not in self._cache:
            return False

        cached = self._cache[key]
        try:
            if cached.connection is not None:
                cached.connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection {key}: {e}")
        try:
            cached.engine.dispose()
        except Exception as e:
            logger.warning(f"Error disposing engine for {key}: {e}")
        finally:
            # Clean up both mappings
            del self._cache[key]
            if cached.id in self._id_to_key:
                del self._id_to_key[cached.id]
        return True

    def remove_by_id(self, id: str) -> bool:
        """
        Remove and close a cached connection by its unique ID.

        Args:
            id: Unique identifier of the connection to remove

        Returns:
            bool: True if connection was found and closed, False otherwise.
        """
        if id not in self._id_to_key:
            return False

        cache_key = self._id_to_key[id]
        return self.remove(cache_key)

    def clear(self) -> int:
        """
        Close and remove all cached connections.

        Returns:
            int: Number of connections closed.
        """
        count = 0
        for key in list(self._cache.keys()):
            if self.remove(key):
                count += 1
        return count

    def list_keys(self) -> List[str]:
        """Return list of all cached connection identifiers."""
        return list(self._cache.keys())

    def __len__(self) -> int:
        """Return number of cached connections."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if a connection is cached."""
        return key in self._cache
