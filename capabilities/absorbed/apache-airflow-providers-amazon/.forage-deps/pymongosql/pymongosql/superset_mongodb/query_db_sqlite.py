# -*- coding: utf-8 -*-
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from .query_db import QueryDatabase

_logger = logging.getLogger(__name__)


class SQLiteTypeMapper:
    """Maps Python/MongoDB data types to SQLite3 types"""

    # Type mapping from Python types to SQLite3 types
    TYPE_MAP = {
        str: "TEXT",
        int: "INTEGER",
        float: "REAL",
        bool: "INTEGER",  # SQLite3 uses 0/1 for boolean
        bytes: "BLOB",
        type(None): "NULL",
        dict: "TEXT",  # Store as JSON string
        list: "TEXT",  # Store as JSON string
    }

    @classmethod
    def get_sqlite_type(cls, value: Any) -> str:
        """Get SQLite type for a Python value"""
        if value is None:
            return "NULL"

        value_type = type(value)
        if value_type in cls.TYPE_MAP:
            return cls.TYPE_MAP[value_type]

        # Default to TEXT for unknown types
        return "TEXT"

    @classmethod
    def infer_schema(cls, records: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Infer SQLite schema from a list of records.

        Args:
            records: List of dictionaries with data

        Returns:
            Dictionary mapping column names to SQLite types
        """
        schema = {}

        for record in records:
            for col_name, value in record.items():
                if col_name not in schema:
                    # First occurrence, determine type
                    schema[col_name] = cls.get_sqlite_type(value)
                elif schema[col_name] != "TEXT":
                    # If we've already determined type, check compatibility
                    new_type = cls.get_sqlite_type(value)
                    # Upgrade to TEXT if types differ (safest option)
                    if new_type != schema[col_name]:
                        schema[col_name] = "TEXT"

        return schema

    @classmethod
    def convert_value(cls, value: Any, target_type: str) -> Any:
        """Convert value to appropriate SQLite type"""
        if value is None:
            return None

        if target_type == "INTEGER":
            return int(value) if value is not None else None
        elif target_type == "REAL":
            return float(value) if value is not None else None
        elif target_type == "TEXT":
            if isinstance(value, (dict, list)):
                import json

                return json.dumps(value)
            return str(value)
        elif target_type == "BLOB":
            if isinstance(value, bytes):
                return value
            return str(value).encode()

        return value


class QueryDBSQLite(QueryDatabase):
    """Manages SQLite3 in-memory database for query database operations.

    This is the default implementation of QueryDatabase using SQLite3.
    Other RDBMS backends can be created by implementing the QueryDatabase interface.
    """

    def __init__(self) -> None:
        """Initialize SQLite3 bridge with in-memory database"""
        self._connection: Optional[sqlite3.Connection] = None
        self._tables: Dict[str, Dict[str, str]] = {}  # table_name -> schema
        self._is_closed = False

    def _ensure_connection(self) -> sqlite3.Connection:
        """Ensure SQLite3 connection is available"""
        if self._is_closed:
            raise RuntimeError("SQLiteBridge is closed")

        if self._connection is None:
            # Create in-memory database
            self._connection = sqlite3.connect(":memory:")
            # Enable row factory to get dict-like rows
            self._connection.row_factory = sqlite3.Row
            _logger.debug("Created in-memory SQLite3 database")

        return self._connection

    def create_table(self, table_name: str, schema: Dict[str, str]) -> None:
        """
        Create a table in SQLite3.

        Args:
            table_name: Name of the table
            schema: Dictionary mapping column names to SQLite types
        """
        conn = self._ensure_connection()

        # Build CREATE TABLE statement
        columns = ", ".join([f'"{col}" {dtype}' for col, dtype in schema.items()])
        create_sql = f"CREATE TABLE {table_name} ({columns})"

        try:
            conn.execute(create_sql)
            conn.commit()
            self._tables[table_name] = schema
            _logger.debug(f"Created SQLite3 table: {table_name}")
        except sqlite3.Error as e:
            _logger.error(f"Error creating table {table_name}: {e}")
            raise

    def insert_records(
        self, table_name: str, records: List[Dict[str, Any]], schema: Optional[Dict[str, str]] = None
    ) -> int:
        """
        Insert records into a SQLite3 table.

        Args:
            table_name: Name of the table
            records: List of dictionaries to insert
            schema: Optional schema (will be inferred if not provided)

        Returns:
            Number of records inserted
        """
        if not records:
            return 0

        conn = self._ensure_connection()

        # Create table if not exists
        if table_name not in self._tables:
            if schema is None:
                schema = SQLiteTypeMapper.infer_schema(records)
            self.create_table(table_name, schema)

        # Build INSERT statement
        columns = list(records[0].keys())
        placeholders = ", ".join(["?" for _ in columns])
        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

        # Convert values to appropriate types
        schema = self._tables[table_name]
        converted_records = []

        for record in records:
            converted_row = tuple(
                SQLiteTypeMapper.convert_value(record.get(col), schema.get(col, "TEXT")) for col in columns
            )
            converted_records.append(converted_row)

        try:
            conn.executemany(insert_sql, converted_records)
            conn.commit()
            _logger.debug(f"Inserted {len(records)} records into {table_name}")
            return len(records)
        except sqlite3.Error as e:
            _logger.error(f"Error inserting records into {table_name}: {e}")
            raise

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute a query against the SQLite3 database.

        Args:
            query: SQL query string

        Returns:
            List of dictionaries with query results
        """
        conn = self._ensure_connection()

        try:
            cursor = conn.execute(query)
            # Fetch all rows and convert from sqlite3.Row to dict
            rows = cursor.fetchall()

            column_names = [desc[0] for desc in cursor.description] if cursor.description else []
            return [dict(zip(column_names, row)) for row in rows]
        except sqlite3.Error as e:
            _logger.error(f"Error executing query: {e}")
            raise

    def execute_query_cursor(self, query: str) -> sqlite3.Cursor:
        """
        Execute a query and return cursor for manual iteration.

        Args:
            query: SQL query string

        Returns:
            SQLite3 cursor for iteration
        """
        conn = self._ensure_connection()
        return conn.execute(query)

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database"""
        return table_name in self._tables

    def get_table_schema(self, table_name: str) -> Optional[Dict[str, str]]:
        """Get the schema of a table"""
        return self._tables.get(table_name)

    def list_tables(self) -> List[str]:
        """List all tables in the database"""
        return list(self._tables.keys())

    def drop_table(self, table_name: str) -> None:
        """Drop a table from the database"""
        if table_name not in self._tables:
            return

        conn = self._ensure_connection()
        try:
            conn.execute(f"DROP TABLE {table_name}")
            conn.commit()
            del self._tables[table_name]
            _logger.debug(f"Dropped table: {table_name}")
        except sqlite3.Error as e:
            _logger.error(f"Error dropping table {table_name}: {e}")
            raise

    def close(self) -> None:
        """Close the SQLite3 connection"""
        if self._connection is not None:
            try:
                self._connection.close()
                _logger.debug("Closed SQLite3 database connection")
            except sqlite3.Error as e:
                _logger.error(f"Error closing SQLite3 connection: {e}")
            finally:
                self._connection = None
                self._is_closed = True

    def __enter__(self) -> "QueryDBSQLite":
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        self.close()

    def __repr__(self) -> str:
        return f"QueryDBSQLite(tables={list(self._tables.keys())}, closed={self._is_closed})"
