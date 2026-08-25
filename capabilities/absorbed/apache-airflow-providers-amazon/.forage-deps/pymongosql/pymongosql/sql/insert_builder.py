# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .builder import ExecutionPlan

_logger = logging.getLogger(__name__)


@dataclass
class InsertExecutionPlan(ExecutionPlan):
    """Execution plan for INSERT operations against MongoDB."""

    insert_documents: List[Dict[str, Any]] = field(default_factory=list)
    parameter_style: Optional[str] = None  # e.g., "qmark"
    parameter_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert insert plan to dictionary representation."""
        return {
            "collection": self.collection,
            "documents": self.insert_documents,
            "parameter_count": self.parameter_count,
        }

    def validate(self) -> bool:
        """Validate the insert plan."""
        errors = self.validate_base()

        if not self.insert_documents:
            errors.append("At least one document must be provided for insertion")

        if errors:
            _logger.error(f"Insert plan validation errors: {errors}")
            return False

        return True

    def copy(self) -> "InsertExecutionPlan":
        """Create a copy of this insert plan."""
        return InsertExecutionPlan(
            collection=self.collection,
            insert_documents=[doc.copy() for doc in self.insert_documents],
            parameter_style=self.parameter_style,
            parameter_count=self.parameter_count,
        )


class MongoInsertBuilder:
    """Fluent builder for INSERT execution plans."""

    def __init__(self):
        self._execution_plan = InsertExecutionPlan()
        self._validation_errors: List[str] = []

    def collection(self, name: str) -> "MongoInsertBuilder":
        """Set the target collection."""
        if not name or not name.strip():
            self._add_error("Collection name cannot be empty")
            return self

        self._execution_plan.collection = name.strip()
        _logger.debug(f"Set collection to: {name}")
        return self

    def insert_documents(self, documents: List[Dict[str, Any]]) -> "MongoInsertBuilder":
        """Set documents to insert (normalized from any syntax)."""
        if not isinstance(documents, list):
            self._add_error("Documents must be a list")
            return self

        if not documents:
            self._add_error("At least one document must be provided")
            return self

        self._execution_plan.insert_documents = documents
        _logger.debug(f"Set insert documents: {len(documents)} document(s)")
        return self

    def parameter_style(self, style: Optional[str]) -> "MongoInsertBuilder":
        """Set parameter binding style for tracking."""
        if style and style not in ["qmark", "named"]:
            self._add_error(f"Invalid parameter style: {style}")
            return self

        self._execution_plan.parameter_style = style
        _logger.debug(f"Set parameter style to: {style}")
        return self

    def parameter_count(self, count: int) -> "MongoInsertBuilder":
        """Set number of parameter placeholders to be bound."""
        if not isinstance(count, int) or count < 0:
            self._add_error("Parameter count must be a non-negative integer")
            return self

        self._execution_plan.parameter_count = count
        _logger.debug(f"Set parameter count to: {count}")
        return self

    def _add_error(self, message: str) -> None:
        """Add validation error."""
        self._validation_errors.append(message)
        _logger.error(f"Insert builder error: {message}")

    def validate(self) -> bool:
        """Validate the insert plan."""
        self._validation_errors.clear()

        if not self._execution_plan.collection:
            self._add_error("Collection name is required")

        if not self._execution_plan.insert_documents:
            self._add_error("At least one document must be provided")

        return len(self._validation_errors) == 0

    def get_errors(self) -> List[str]:
        """Get validation errors."""
        return self._validation_errors.copy()

    def build(self) -> InsertExecutionPlan:
        """Build and return the insert execution plan."""
        if not self.validate():
            error_summary = "; ".join(self._validation_errors)
            raise ValueError(f"Insert plan validation failed: {error_summary}")

        return self._execution_plan

    def reset(self) -> "MongoInsertBuilder":
        """Reset the builder to start a new insert plan."""
        self._execution_plan = InsertExecutionPlan()
        self._validation_errors.clear()
        return self

    def __str__(self) -> str:
        """String representation for debugging."""
        return (
            f"MongoInsertBuilder(collection={self._execution_plan.collection}, "
            f"documents={len(self._execution_plan.insert_documents)})"
        )
