# -*- coding: utf-8 -*-
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .builder import ExecutionPlan

_logger = logging.getLogger(__name__)


@dataclass
class ViewExecutionPlan(ExecutionPlan):
    """Execution plan for view statements (CREATE VIEW, DROP VIEW)."""

    ddl_type: str = ""  # "create_view" or "drop_view"
    view_on: Optional[str] = None  # Source collection for CREATE VIEW
    pipeline: Optional[List[Dict[str, Any]]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "ddl_type": self.ddl_type,
            "collection": self.collection,
        }
        if self.ddl_type == "create_view":
            result["view_on"] = self.view_on
            result["pipeline"] = self.pipeline
        return result

    def validate(self) -> bool:
        errors = self.validate_base()

        if not self.ddl_type:
            errors.append("DDL type is required")

        if self.ddl_type == "create_view":
            if not self.view_on:
                errors.append("Source collection (ON) is required for CREATE VIEW")
            if self.pipeline is None:
                errors.append("Pipeline (AS) is required for CREATE VIEW")

        if errors:
            for err in errors:
                _logger.warning(f"View plan validation error: {err}")
            return False

        return True
