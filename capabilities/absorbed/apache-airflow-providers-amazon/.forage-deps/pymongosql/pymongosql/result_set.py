# -*- coding: utf-8 -*-
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import jmespath
from pymongo.errors import PyMongoError

from . import STRING
from .common import CursorIterator
from .error import DatabaseError, ProgrammingError
from .retry import RetryConfig, execute_with_retry
from .sql.query_builder import QueryExecutionPlan

_logger = logging.getLogger(__name__)


class ResultSet(CursorIterator):
    """Result set wrapper for MongoDB command results"""

    def __init__(
        self,
        command_result: Optional[Dict[str, Any]] = None,
        execution_plan: QueryExecutionPlan = None,
        arraysize: int = None,
        database: Optional[Any] = None,
        retry_config: Optional[RetryConfig] = None,
        **kwargs,
    ) -> None:
        super().__init__(arraysize=arraysize or self.DEFAULT_FETCH_SIZE, **kwargs)

        # Handle command results from db.command
        if command_result is not None:
            self._command_result = command_result
            self._database = database
            # Extract cursor info from command result
            self._result_cursor = command_result.get("cursor", {})
            self._cursor_id = self._result_cursor.get("id", 0)  # 0 means no more results
            self._raw_results = self._result_cursor.get("firstBatch", [])
            self._cached_results: List[Sequence[Any]] = []
        else:
            raise ProgrammingError("command_result must be provided")

        self._retry_config = retry_config

        self._execution_plan = execution_plan
        self._is_closed = False
        self._cache_exhausted = False
        self._total_fetched = 0
        self._description: Optional[List[Tuple[str, Any, None, None, None, None, None]]] = None
        self._column_names: Optional[List[str]] = None  # Track column order for sequences
        self._errors: List[Dict[str, str]] = []

        # Process firstBatch immediately if available (after all attributes are set)
        if command_result is not None and self._raw_results:
            self._process_and_cache_batch(self._raw_results)

        # Build description from projection
        self._build_description()

    def _process_and_cache_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Process and cache a batch of documents"""
        if not batch:
            return
        # Process results through projection mapping
        processed_batch = [self._process_document(doc) for doc in batch]
        # Convert dictionaries to output format (sequence or dict)
        formatted_batch = [self._format_result(doc) for doc in processed_batch]
        self._cached_results.extend(formatted_batch)
        self._total_fetched += len(batch)

    def _build_description(self) -> None:
        """Build column description from execution plan projection or established column names"""
        if not self._execution_plan.projection_stage:
            # No projection specified, build description from column names if available
            if self._column_names:
                self._description = [
                    (col_name, STRING, None, None, None, None, None) for col_name in self._column_names
                ]
            else:
                # Will be built dynamically when columns are established
                self._description = None
            return

        # Build description from projection (now in MongoDB format {field: 1})
        description = []
        column_aliases = getattr(self._execution_plan, "column_aliases", {})

        for field_name, include_flag in self._execution_plan.projection_stage.items():
            # SQL cursor description format: (name, type_code, display_size, internal_size, precision, scale, null_ok)
            if include_flag == 1:  # Field is included in projection
                # Use alias if available, otherwise use field name
                display_name = column_aliases.get(field_name, field_name)
                description.append((display_name, STRING, None, None, None, None, None))

        self._description = description

    def _ensure_results_available(self, count: int = 1) -> None:
        """Ensure we have at least 'count' results available in cache"""
        if self._is_closed:
            raise ProgrammingError("ResultSet is closed")

        if self._cache_exhausted:
            return

        # Fetch more results if needed and cursor has more data
        while len(self._cached_results) < count and self._cursor_id != 0:
            try:
                # Use getMore to fetch next batch
                if self._database is not None and self._execution_plan.collection:
                    getmore_cmd = {
                        "getMore": self._cursor_id,
                        "collection": self._execution_plan.collection,
                    }
                    # Decode later batches like the first one, not with DEFAULT_CODEC_OPTIONS
                    codec_options = self._database.codec_options
                    result = execute_with_retry(
                        lambda: self._database.command(getmore_cmd, codec_options=codec_options),
                        self._retry_config,
                        "getMore command",
                    )

                    # Extract and process next batch
                    cursor_info = result.get("cursor", {})
                    next_batch = cursor_info.get("nextBatch", [])
                    self._process_and_cache_batch(next_batch)

                    # Update cursor ID for next iteration
                    self._cursor_id = cursor_info.get("id", 0)
                else:
                    # No database access, mark as exhausted
                    self._cache_exhausted = True
                    break

            except PyMongoError as e:
                self._errors.append({"error": str(e), "type": type(e).__name__})
                self._cache_exhausted = True
                raise DatabaseError(f"Error fetching more results: {e}")

        # Mark as exhausted if no more results available
        if self._cursor_id == 0:
            self._cache_exhausted = True

    def _process_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Process a MongoDB document according to projection mapping"""
        if not self._execution_plan.projection_stage:
            # No projection, return document as-is (including _id)
            return dict(doc)

        # Apply projection mapping (now using MongoDB format {field: 1})
        processed = {}
        for field_name, include_flag in self._execution_plan.projection_stage.items():
            if include_flag == 1:  # Field is included in projection
                # Extract value using jmespath-compatible field path (convert numeric dot indexes to bracket form)
                value = self._get_nested_value(doc, field_name)
                # Convert the projection key back to bracket notation for client-facing results
                display_key = self._mongo_to_bracket_key(field_name)
                processed[display_key] = value

        return processed

    def _mongo_to_bracket_key(self, field_path: str) -> str:
        """Convert Mongo dot-index notation to bracket notation.

        Transforms numeric dot segments into bracket indices for both display keys
        and JMESPath-compatible field paths.

        Examples:
            items.0 -> items[0]
            items.1.name -> items[1].name
        """
        if not isinstance(field_path, str):
            return field_path
        # Replace .<number> with [<number>]
        return re.sub(r"\.(\d+)", r"[\1]", field_path)

    def _get_nested_value(self, doc: Dict[str, Any], field_path: str) -> Any:
        """Extract nested field value from document using JMESPath

        Supports:
            - Simple fields: "name" -> doc["name"]
            - Nested fields: "profile.bio" -> doc["profile"]["bio"]
            - Array indexing: "address.coordinates[1]" -> doc["address"]["coordinates"][1]
            - Wildcards: "items[*].name" -> [item["name"] for item in items]
        """
        try:
            # Optimization: for simple field names without dots/brackets, use direct access
            if "." not in field_path and "[" not in field_path:
                return doc.get(field_path)

            # Convert normalized Mongo-style numeric segments to bracket notation
            normalized_field = self._mongo_to_bracket_key(field_path)
            # Use jmespath for complex paths
            return jmespath.search(normalized_field, doc)
        except Exception as e:
            _logger.debug(f"Error extracting field '{field_path}': {e}")
            return None

    def _format_result(self, doc: Dict[str, Any]) -> Tuple[Any, ...]:
        """Format processed document to output format (tuple for DB API 2.0 compliance)"""
        if self._column_names is None:
            # First time - establish column order
            self._column_names = list(doc.keys())

        # Return values in consistent column order
        return tuple(doc.get(col_name) for col_name in self._column_names)

    @property
    def errors(self) -> List[Dict[str, str]]:
        return self._errors.copy()

    @property
    def rowcount(self) -> int:
        """Return number of rows fetched/affected"""
        # Check for write operation results (UPDATE, DELETE, INSERT)
        if hasattr(self, "_insert_result") and self._insert_result:
            # INSERT operation - return number of inserted documents
            return self._insert_result.get("n", 0)

        # Check command result for write operations
        if self._command_result:
            # For UPDATE/DELETE operations, check 'n' (modified count) or 'nModified'
            if "n" in self._command_result:
                return self._command_result.get("n", 0)
            if "nModified" in self._command_result:
                return self._command_result.get("nModified", 0)

        # For SELECT/QUERY operations, return number of fetched rows
        return self._total_fetched

    @property
    def description(
        self,
    ) -> Optional[List[Tuple[str, Any, None, None, None, None, None]]]:
        """Return column description"""
        if self._description is None:
            # Try to build description from established column names
            try:
                if self._column_names:
                    # Build description from established column names
                    self._description = [
                        (col_name, STRING, None, None, None, None, None) for col_name in self._column_names
                    ]
            except Exception as e:
                _logger.warning(f"Could not build dynamic description: {e}")

        return self._description

    def fetchone(self) -> Optional[Sequence[Any]]:
        """Fetch the next row from the result set"""
        if self._is_closed:
            raise ProgrammingError("ResultSet is closed")

        # Ensure we have at least one result
        self._ensure_results_available(1)

        if not self._cached_results:
            return None

        # Return and remove first result
        result = self._cached_results.pop(0)
        self._rownumber = (self._rownumber or 0) + 1
        return result

    def fetchmany(self, size: Optional[int] = None) -> List[Sequence[Any]]:
        """Fetch up to 'size' rows from the result set"""
        if self._is_closed:
            raise ProgrammingError("ResultSet is closed")

        fetch_size = size or self.arraysize

        # Ensure we have enough results
        self._ensure_results_available(fetch_size)

        # Return requested number of results
        results = self._cached_results[:fetch_size]
        self._cached_results = self._cached_results[fetch_size:]

        # Update row number
        self._rownumber = (self._rownumber or 0) + len(results)

        return results

    def fetchall(self) -> List[Sequence[Any]]:
        """Fetch all remaining rows from the result set"""
        if self._is_closed:
            raise ProgrammingError("ResultSet is closed")

        # Fetch all remaining results
        all_results = []

        try:
            # Ensure all results are available in cache by requesting a very large number
            # This will trigger getMore calls until all data is exhausted
            if not self._cache_exhausted and self._cursor_id != 0:
                self._ensure_results_available(float("inf"))

            # Now get everything from cache
            all_results.extend(self._cached_results)
            self._cached_results.clear()
            self._cache_exhausted = True

        except PyMongoError as e:
            self._errors.append({"error": str(e), "type": type(e).__name__})
            raise DatabaseError(f"Error fetching all results: {e}")

        # Update row number
        self._rownumber = (self._rownumber or 0) + len(all_results)

        return all_results

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def close(self) -> None:
        """Close the result set and free resources"""
        if not self._is_closed:
            self._is_closed = True
            self._command_result = None
            self._database = None
            self._cached_results.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class DictResultSet(ResultSet):
    """Result set that returns dictionaries instead of sequences"""

    def _format_result(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Override to return dictionary directly instead of converting to sequence"""
        return doc


# For backward compatibility
MongoResultSet = ResultSet
