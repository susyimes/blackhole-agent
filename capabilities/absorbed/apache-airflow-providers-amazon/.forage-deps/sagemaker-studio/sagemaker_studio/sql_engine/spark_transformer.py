from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer
from .resource_fetching_definition import ResourceFetchingDefinition


class SparkTransformer(DatabaseTransformer):
    """Database transformer for Spark SQL direct execution."""

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "spark"

    @staticmethod
    def get_required_fields() -> List[str]:
        return []

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("Spark transformer is for direct execution only")

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str], parents: Optional[Dict[str, str]] = None
    ) -> ResourceFetchingDefinition:
        raise NotImplementedError("Spark transformer is for direct execution only")
