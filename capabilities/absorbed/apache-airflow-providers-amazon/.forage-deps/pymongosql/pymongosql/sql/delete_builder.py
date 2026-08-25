# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict

from .builder import ExecutionPlan

_logger = logging.getLogger(__name__)


@dataclass
class DeleteExecutionPlan(ExecutionPlan):
    """Execution plan for DELETE operations against MongoDB."""

    filter_conditions: Dict[str, Any] = field(default_factory=dict)
    parameter_style: str = field(default="qmark")  # Parameter placeholder style: qmark (?) or named (:name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert delete plan to dictionary representation."""
        return {
            "collection": self.collection,
            "filter": self.filter_conditions,
        }

    def validate(self) -> bool:
        """Validate the delete plan."""
        errors = self.validate_base()

        # Note: filter_conditions can be empty for DELETE FROM <collection> (delete all)
        # which is valid, so we don't enforce filter presence

        if errors:
            _logger.error(f"Delete plan validation errors: {errors}")
            return False

        return True

    def copy(self) -> "DeleteExecutionPlan":
        """Create a copy of this delete plan."""
        return DeleteExecutionPlan(
            collection=self.collection,
            filter_conditions=self.filter_conditions.copy() if self.filter_conditions else {},
        )


class MongoDeleteBuilder:
    """Builder for constructing DeleteExecutionPlan objects."""

    def __init__(self) -> None:
        """Initialize the delete builder."""
        self._plan = DeleteExecutionPlan()

    def collection(self, collection: str) -> "MongoDeleteBuilder":
        """Set the collection name."""
        self._plan.collection = collection
        return self

    def filter_conditions(self, conditions: Dict[str, Any]) -> "MongoDeleteBuilder":
        """Set the filter conditions for the delete operation."""
        if conditions:
            self._plan.filter_conditions = conditions
        return self

    def build(self) -> DeleteExecutionPlan:
        """Build and return the DeleteExecutionPlan."""
        if not self._plan.validate():
            raise ValueError("Invalid delete plan")
        return self._plan
