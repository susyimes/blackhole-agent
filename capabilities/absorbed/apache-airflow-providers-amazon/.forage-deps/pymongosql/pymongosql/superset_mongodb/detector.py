# -*- coding: utf-8 -*-
import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class QueryInfo:
    """Information about a detected subquery"""

    has_subquery: bool = False
    is_wrapped: bool = False  # True if query is wrapped like SELECT * FROM (...) AS alias
    subquery_text: Optional[str] = None
    outer_query_text: Optional[str] = None
    subquery_alias: Optional[str] = None
    query_depth: int = 0  # Nesting depth


class SubqueryDetector:
    """Detects and analyzes SQL subqueries in query strings"""

    # Pattern to detect wrapped subqueries: SELECT ... FROM (SELECT ...) AS alias
    WRAPPED_SUBQUERY_PATTERN = re.compile(
        r"SELECT\s+.*?\s+FROM\s*\(\s*(SELECT\s+.*?)\s*\)\s+(?:AS\s+)?(\w+)",
        re.IGNORECASE | re.DOTALL,
    )

    # Pattern to detect simple SELECT start
    SELECT_PATTERN = re.compile(r"^\s*SELECT\s+", re.IGNORECASE)

    @classmethod
    def detect(cls, query: str) -> QueryInfo:
        """
        Detect if a query contains subqueries.

        Args:
            query: SQL query string

        Returns:
            QueryInfo with detection results
        """
        query = query.strip()

        # Check for wrapped subquery pattern (most common Superset case)
        match = cls.WRAPPED_SUBQUERY_PATTERN.search(query)
        if match:
            subquery_text = match.group(1)
            subquery_alias = match.group(2)

            if subquery_alias is None or subquery_alias == "":
                subquery_alias = "subquery_result"

            return QueryInfo(
                has_subquery=True,
                is_wrapped=True,
                subquery_text=subquery_text,
                outer_query_text=query,
                subquery_alias=subquery_alias,
                query_depth=2,
            )

        # Check if query itself is a SELECT (no subquery)
        if cls.SELECT_PATTERN.match(query):
            return QueryInfo(
                has_subquery=False,
                is_wrapped=False,
                query_depth=1,
            )

        # Unknown pattern
        return QueryInfo(has_subquery=False)

    @classmethod
    def extract_subquery(cls, query: str) -> Optional[str]:
        """Extract the subquery text from a wrapped query"""
        info = cls.detect(query)
        return info.subquery_text if info.is_wrapped else None

    @classmethod
    def extract_outer_query(cls, query: str) -> Optional[Tuple[str, str]]:
        """
        Extract outer query with subquery placeholder.

        Preserves the complete outer query structure while replacing the subquery
        with a reference to the temporary table.

        Returns:
            Tuple of (outer_query, subquery_alias) or None if not a wrapped subquery
        """
        info = cls.detect(query)
        if not info.is_wrapped:
            return None

        # Pattern to capture: SELECT <columns> FROM ( <subquery> ) AS <alias> <rest>
        # Matches both SELECT col1, col2 and SELECT col1 AS alias1, col2 AS alias2 formats
        pattern = re.compile(
            r"(SELECT\s+.+?)\s+FROM\s*\(\s*(?:select|SELECT)\s+.+?\s*\)\s+(?:AS\s+)?(\w+)(.*)",
            re.IGNORECASE | re.DOTALL,
        )

        match = pattern.search(query)
        if match:
            select_clause = match.group(1).strip()
            table_alias = match.group(2)
            rest_of_query = match.group(3).strip()

            if rest_of_query:
                outer = f"{select_clause} FROM {table_alias} {rest_of_query}"
            else:
                outer = f"{select_clause} FROM {table_alias}"

            return outer, table_alias

        # If pattern doesn't match exactly, fall back to preserving SELECT clause
        # Extract from SELECT to FROM keyword
        select_match = re.search(r"(SELECT\s+.+?)\s+FROM", query, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return None

        select_clause = select_match.group(1).strip()

        # Extract table alias and rest of query after the closing paren
        rest_match = re.search(r"\)\s+(?:AS\s+)?(\w+)(.*)", query, re.IGNORECASE | re.DOTALL)
        if rest_match:
            table_alias = rest_match.group(1)
            rest_of_query = rest_match.group(2).strip()

            if rest_of_query:
                outer = f"{select_clause} FROM {table_alias} {rest_of_query}"
            else:
                outer = f"{select_clause} FROM {table_alias}"

            return outer, table_alias

        return None

    @classmethod
    def is_simple_select(cls, query: str) -> bool:
        """Check if query is a simple SELECT without subqueries"""
        info = cls.detect(query)
        return not info.has_subquery and cls.SELECT_PATTERN.match(query)
