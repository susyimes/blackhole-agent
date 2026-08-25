from typing import Any, Dict, List, Optional

from .database_transformer import DatabaseTransformer
from .resource_fetching_definition import ResourceFetchingDefinition


class DuckDBTransformer(DatabaseTransformer):
    """Database transformer for DuckDB local execution."""

    @classmethod
    def get_dialect(cls) -> Optional[str]:
        return "duckdb"

    @staticmethod
    def get_required_fields() -> List[str]:
        return []

    @staticmethod
    def to_sqlalchemy_config(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("DuckDB transformer is for local execution only")

    @staticmethod
    def get_resources_action(
        resource_type: Optional[str], parents: Dict[str, str]
    ) -> ResourceFetchingDefinition:
        raise NotImplementedError("DuckDB transformer is for local execution only")
