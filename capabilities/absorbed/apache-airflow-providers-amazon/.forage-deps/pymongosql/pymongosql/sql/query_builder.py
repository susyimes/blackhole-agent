# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .builder import ExecutionPlan

_logger = logging.getLogger(__name__)


@dataclass
class QueryExecutionPlan(ExecutionPlan):
    """Execution plan for MongoDB SELECT queries (query-only)."""

    filter_stage: Dict[str, Any] = field(default_factory=dict)
    projection_stage: Dict[str, Any] = field(default_factory=dict)
    column_aliases: Dict[str, str] = field(default_factory=dict)  # Maps field_name -> alias
    sort_stage: List[Dict[str, int]] = field(default_factory=list)
    limit_stage: Optional[int] = None
    skip_stage: Optional[int] = None
    # Aggregate pipeline support
    aggregate_pipeline: Optional[str] = None  # JSON string representation of pipeline
    aggregate_options: Optional[str] = None  # JSON string representation of options
    is_aggregate_query: bool = False  # Flag indicating this is an aggregate() call

    def to_dict(self) -> Dict[str, Any]:
        """Convert query plan to dictionary representation"""
        result = {
            "collection": self.collection,
            "filter": self.filter_stage,
            "projection": self.projection_stage,
            "sort": self.sort_stage,
            "limit": self.limit_stage,
            "skip": self.skip_stage,
        }

        # Add aggregate-specific fields if present
        if self.is_aggregate_query:
            result["is_aggregate_query"] = True
            result["aggregate_pipeline"] = self.aggregate_pipeline
            result["aggregate_options"] = self.aggregate_options

        return result

    def validate(self) -> bool:
        """Validate the query plan"""
        # For aggregate queries, collection is optional (unqualified aggregate syntax)
        # For regular queries, collection is required
        if self.is_aggregate_query:
            errors = []
        else:
            errors = self.validate_base()

        if self.limit_stage is not None and (not isinstance(self.limit_stage, int) or self.limit_stage < 0):
            errors.append("Limit must be a non-negative integer")

        if self.skip_stage is not None and (not isinstance(self.skip_stage, int) or self.skip_stage < 0):
            errors.append("Skip must be a non-negative integer")

        if errors:
            _logger.error(f"Query validation errors: {errors}")
            return False

        return True

    def copy(self) -> "QueryExecutionPlan":
        """Create a copy of this execution plan"""
        return QueryExecutionPlan(
            collection=self.collection,
            filter_stage=self.filter_stage.copy(),
            projection_stage=self.projection_stage.copy(),
            column_aliases=self.column_aliases.copy(),
            sort_stage=self.sort_stage.copy(),
            limit_stage=self.limit_stage,
            skip_stage=self.skip_stage,
            aggregate_pipeline=self.aggregate_pipeline,
            aggregate_options=self.aggregate_options,
            is_aggregate_query=self.is_aggregate_query,
        )


class MongoQueryBuilder:
    """Fluent builder for MongoDB queries with validation and readability"""

    def __init__(self):
        self._execution_plan = QueryExecutionPlan()
        self._validation_errors = []

    def collection(self, name: str) -> "MongoQueryBuilder":
        """Set the target collection"""
        if not name or not name.strip():
            self._add_error("Collection name cannot be empty")
            return self

        self._execution_plan.collection = name.strip()
        _logger.debug(f"Set collection to: {name}")
        return self

    def filter(self, conditions: Dict[str, Any]) -> "MongoQueryBuilder":
        """Add filter conditions"""
        if not isinstance(conditions, dict):
            self._add_error("Filter conditions must be a dictionary")
            return self

        self._execution_plan.filter_stage.update(conditions)
        _logger.debug(f"Added filter conditions: {conditions}")
        return self

    def project(self, fields: Union[Dict[str, int], List[str]]) -> "MongoQueryBuilder":
        """Set projection fields"""
        if isinstance(fields, list):
            # Convert list to projection dict
            projection = {field: 1 for field in fields}
        elif isinstance(fields, dict):
            projection = fields
        else:
            self._add_error("Projection must be a list of field names or a dictionary")
            return self

        self._execution_plan.projection_stage = projection
        _logger.debug(f"Set projection: {projection}")
        return self

    def sort(self, specs: List[Dict[str, int]]) -> "MongoQueryBuilder":
        """Add sort criteria.

        Only accepts a list of single-key dicts in the form:
            [{"field": 1}, {"other": -1}]

        This matches the output produced by the SQL parser (`sort_fields`).
        """
        if not isinstance(specs, list):
            self._add_error("Sort specifications must be a list of single-key dicts")
            return self

        for spec in specs:
            if not isinstance(spec, dict) or len(spec) != 1:
                self._add_error("Each sort specification must be a single-key dict, e.g. {'name': 1}")
                continue

            field, direction = next(iter(spec.items()))

            if not isinstance(field, str) or not field:
                self._add_error("Sort field must be a non-empty string")
                continue

            if direction not in [-1, 1]:
                self._add_error(f"Sort direction for field '{field}' must be 1 or -1")
                continue

            self._execution_plan.sort_stage.append({field: direction})
            _logger.debug(f"Added sort: {field} -> {direction}")

        return self

    def limit(self, count: int) -> "MongoQueryBuilder":
        """Set limit for results"""
        if not isinstance(count, int) or count < 0:
            return self

        self._execution_plan.limit_stage = count
        _logger.debug(f"Set limit to: {count}")
        return self

    def skip(self, count: int) -> "MongoQueryBuilder":
        """Set skip count for pagination"""
        if not isinstance(count, int) or count < 0:
            return self

        self._execution_plan.skip_stage = count
        _logger.debug(f"Set skip to: {count}")
        return self

    def column_aliases(self, aliases: Dict[str, str]) -> "MongoQueryBuilder":
        """Set column aliases mapping (field_name -> alias)"""
        if not isinstance(aliases, dict):
            self._add_error("Column aliases must be a dictionary")
            return self

        self._execution_plan.column_aliases = aliases
        _logger.debug(f"Set column aliases to: {aliases}")
        return self

    def where(self, field: str, operator: str, value: Any) -> "MongoQueryBuilder":
        """Add a where condition in a readable format"""
        condition = self._build_condition(field, operator, value)
        if condition:
            return self.filter(condition)
        return self

    def where_in(self, field: str, values: List[Any]) -> "MongoQueryBuilder":
        """Add a WHERE field IN (values) condition"""
        return self.filter({field: {"$in": values}})

    def where_between(self, field: str, min_val: Any, max_val: Any) -> "MongoQueryBuilder":
        """Add a WHERE field BETWEEN min AND max condition"""
        return self.filter({field: {"$gte": min_val, "$lte": max_val}})

    def where_like(self, field: str, pattern: str) -> "MongoQueryBuilder":
        """Add a WHERE field LIKE pattern condition"""
        # Convert SQL LIKE pattern to MongoDB regex
        regex_pattern = pattern.replace("%", ".*").replace("_", ".")
        return self.filter({field: {"$regex": regex_pattern, "$options": "i"}})

    def _build_condition(self, field: str, operator: str, value: Any) -> Optional[Dict[str, Any]]:
        """Build a MongoDB condition from field, operator, and value"""
        operator_map = {
            "=": "$eq",
            "!=": "$ne",
            "<": "$lt",
            "<=": "$lte",
            ">": "$gt",
            ">=": "$gte",
            "eq": "$eq",
            "ne": "$ne",
            "lt": "$lt",
            "lte": "$lte",
            "gt": "$gt",
            "gte": "$gte",
        }

        mongo_op = operator_map.get(operator.lower())
        if not mongo_op:
            self._add_error(f"Unsupported operator: {operator}")
            return None

        return {field: {mongo_op: value}}

    def _add_error(self, message: str) -> None:
        """Add validation error"""
        self._validation_errors.append(message)
        _logger.error(f"Query builder error: {message}")

    def validate(self) -> bool:
        """Validate the current query plan"""
        self._validation_errors.clear()

        # For aggregate queries, collection is optional (unqualified aggregate syntax)
        # For regular queries, collection is required
        if not self._execution_plan.is_aggregate_query and not self._execution_plan.collection:
            self._add_error("Collection name is required")

        # Add more validation rules as needed
        return len(self._validation_errors) == 0

    def get_errors(self) -> List[str]:
        """Get validation errors"""
        return self._validation_errors.copy()

    def build(self) -> QueryExecutionPlan:
        """Build and return the execution plan"""
        if not self.validate():
            error_summary = "; ".join(self._validation_errors)
            raise ValueError(f"Query validation failed: {error_summary}")

        return self._execution_plan

    def reset(self) -> "MongoQueryBuilder":
        """Reset the builder to start a new query"""
        self._execution_plan = QueryExecutionPlan()
        self._validation_errors.clear()
        return self

    def __str__(self) -> str:
        """String representation for debugging"""
        return (
            f"MongoQueryBuilder(collection={self._execution_plan.collection}, "
            f"filter={self._execution_plan.filter_stage}, "
            f"projection={self._execution_plan.projection_stage})"
        )
