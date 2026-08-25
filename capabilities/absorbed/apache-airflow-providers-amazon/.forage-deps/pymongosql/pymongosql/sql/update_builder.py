# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict

from .builder import ExecutionPlan

_logger = logging.getLogger(__name__)


@dataclass
class UpdateExecutionPlan(ExecutionPlan):
    """Execution plan for UPDATE operations against MongoDB."""

    update_fields: Dict[str, Any] = field(default_factory=dict)  # Fields to update
    filter_conditions: Dict[str, Any] = field(default_factory=dict)  # Filter for documents to update
    parameter_style: str = field(default="qmark")  # Parameter placeholder style: qmark (?) or named (:name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert update plan to dictionary representation."""
        return {
            "collection": self.collection,
            "filter": self.filter_conditions,
            "update": {"$set": self.update_fields},
        }

    def validate(self) -> bool:
        """Validate the update plan."""
        errors = self.validate_base()

        if not self.update_fields:
            errors.append("Update fields are required")

        # Note: filter_conditions can be empty for UPDATE <collection> SET ... (update all)
        # which is valid, so we don't enforce filter presence

        if errors:
            _logger.error(f"Update plan validation errors: {errors}")
            return False

        return True

    def copy(self) -> "UpdateExecutionPlan":
        """Create a copy of this update plan."""
        return UpdateExecutionPlan(
            collection=self.collection,
            update_fields=self.update_fields.copy() if self.update_fields else {},
            filter_conditions=self.filter_conditions.copy() if self.filter_conditions else {},
        )

    def get_mongo_update_doc(self) -> Dict[str, Any]:
        """Get MongoDB update document using $set operator."""
        return {"$set": self.update_fields}


class MongoUpdateBuilder:
    """Builder for constructing UpdateExecutionPlan objects."""

    def __init__(self) -> None:
        """Initialize the update builder."""
        self._plan = UpdateExecutionPlan()

    def collection(self, collection: str) -> "MongoUpdateBuilder":
        """Set the collection name."""
        self._plan.collection = collection
        return self

    def update_fields(self, fields: Dict[str, Any]) -> "MongoUpdateBuilder":
        """Set the fields to update."""
        if fields:
            self._plan.update_fields = fields
        return self

    def filter_conditions(self, conditions: Dict[str, Any]) -> "MongoUpdateBuilder":
        """Set the filter conditions for the update operation."""
        if conditions:
            self._plan.filter_conditions = conditions
        return self

    def parameter_style(self, style: str) -> "MongoUpdateBuilder":
        """Set the parameter placeholder style."""
        self._plan.parameter_style = style
        return self

    def build(self) -> UpdateExecutionPlan:
        """Build and return the UpdateExecutionPlan."""
        if not self._plan.validate():
            raise ValueError("Invalid update plan")
        return self._plan
