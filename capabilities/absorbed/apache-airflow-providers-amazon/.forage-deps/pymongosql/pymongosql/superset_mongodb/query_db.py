# -*- coding: utf-8 -*-
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

_logger = logging.getLogger(__name__)


class QueryDatabase(ABC):
    """Abstract base class for query database backends"""

    @abstractmethod
    def create_table(self, table_name: str, schema: Dict[str, str]) -> None:
        """
        Create a table with the specified schema.

        Args:
            table_name: Name of the table to create
            schema: Dictionary mapping column names to SQL types
        """
        pass

    @abstractmethod
    def insert_records(self, table_name: str, records: List[Dict[str, Any]], infer_schema: bool = True) -> None:
        """
        Insert records into a table.

        Args:
            table_name: Name of the table
            records: List of dictionaries with data
            infer_schema: If True and table doesn't exist, infer schema from records
        """
        pass

    @abstractmethod
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute a query and return results as list of dictionaries.

        Args:
            query: SQL query string

        Returns:
            List of dictionaries with query results
        """
        pass

    @abstractmethod
    def execute_query_cursor(self, query: str) -> Any:
        """
        Execute a query and return a cursor-like object.

        Args:
            query: SQL query string

        Returns:
            Cursor object for row-by-row iteration
        """
        pass

    @abstractmethod
    def drop_table(self, table_name: str) -> None:
        """
        Drop a table.

        Args:
            table_name: Name of the table to drop
        """
        pass

    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists.

        Args:
            table_name: Name of the table

        Returns:
            True if table exists, False otherwise
        """
        pass

    @abstractmethod
    def list_tables(self) -> List[str]:
        """
        List all tables in the database.

        Returns:
            List of table names
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection and cleanup resources."""
        pass

    @abstractmethod
    def __enter__(self) -> "QueryDatabase":
        """Context manager entry"""
        pass

    @abstractmethod
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit"""
        pass
