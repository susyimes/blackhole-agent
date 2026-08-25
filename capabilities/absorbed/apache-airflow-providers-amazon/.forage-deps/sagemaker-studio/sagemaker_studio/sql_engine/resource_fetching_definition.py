from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal, Mapping, Optional, Sequence, Tuple, Union

ResourceKind = Literal["DATABASE", "SCHEMA", "TABLE", "COLUMN"]


class FetchMode(Enum):
    SQL_EXECUTION = auto()
    SQLALCHEMY_METADATA = auto()


class SQLAlchemyMetadataAction(Enum):
    GET_SCHEMA_NAMES = auto()
    GET_TABLE_NAMES = auto()
    GET_COLUMN_NAMES = auto()


Params = Union[Mapping[str, object], Sequence[object]]


@dataclass(frozen=True, slots=True)
class ResourceFetchingDefinition:
    """
    Plan describing how to fetch database resources.

    This dataclass encodes *what to fetch* and *how to fetch it* for a given
    level in a database hierarchy (e.g., databases → schemas → tables → columns).
    It acts like a small, discriminated union:

    - If ``mode`` is ``FetchMode.SQL_EXECUTION``: provide a parameterized SQL
      statement in ``sql`` (and optional ``sql_parameters``). The consumer will
      execute the SQL and interpret the first column of the result as resource
      names.

    - If ``mode`` is ``FetchMode.SQLALCHEMY_METADATA``: provide an
      ``sqlalchemy_action`` (e.g., list schemas/tables/columns). The consumer
      will use SQLAlchemy’s Inspector to enumerate resource names.

    Exactly **one** of ``sql`` or ``sqlalchemy_action`` must be set, consistent
    with ``mode``. This invariant is enforced in ``__post_init__``.

    Attributes:
      mode: How the resources should be fetched. Either
        ``FetchMode.SQL_EXECUTION`` or ``FetchMode.SQLALCHEMY_METADATA``.
      default_type: The resource kind produced by this definition
        (e.g., ``"DATABASE"``, ``"SCHEMA"``, ``"TABLE"``, ``"COLUMN"``).
      children: The allowed child resource kinds beneath each returned item
        (e.g., a table typically has ``("COLUMN",)``).
      sql: Parameterized SQL text to run when ``mode`` is
        ``FetchMode.SQL_EXECUTION``. Must be ``None`` otherwise.
      sql_parameters: Optional parameters for ``sql``. Typically a mapping
        (named parameters) or a sequence (positional).
      sqlalchemy_action: The metadata action to perform when ``mode`` is
        ``FetchMode.SQLALCHEMY_METADATA``. Must be ``None`` otherwise.
    """

    mode: FetchMode
    default_type: ResourceKind
    children: Tuple[ResourceKind, ...]
    sql: Optional[str] = None
    sql_parameters: Optional[Params] = None
    sqlalchemy_action: Optional[SQLAlchemyMetadataAction] = None

    def __post_init__(self) -> None:
        # Enforce invariants so impossible states are unrepresentable.
        if self.mode is FetchMode.SQL_EXECUTION:
            if self.sql is None:
                raise ValueError("SQL_EXECUTION mode requires `sql`.")
            if self.sqlalchemy_action is not None:
                raise ValueError("SQL_EXECUTION mode must not set `sqlalchemy_action`.")
        elif self.mode is FetchMode.SQLALCHEMY_METADATA:
            if self.sqlalchemy_action is None:
                raise ValueError("SQLALCHEMY_METADATA mode requires `sqlalchemy_action`.")
            if self.sql is not None:
                raise ValueError("SQLALCHEMY_METADATA mode must not set `sql`.")
        else:
            raise ValueError("Unknown mode: %s" % self.mode)

    # Factories
    @classmethod
    def from_sql_execution(
        cls,
        sql: str,
        *,
        default_type: ResourceKind,
        children: Sequence[ResourceKind] = (),
        sql_parameters: Optional[Params] = None,
    ) -> "ResourceFetchingDefinition":
        """Construct a SQL-execution definition.

        Args:
          sql: Parameterized SQL to execute. The first result column is treated
            as the resource name(s).
          default_type: Resource kind produced by this query.
          children: Child resource kinds available under each result.
          sql_parameters: Optional parameters for the SQL statement.

        Returns:
          A ``ResourceFetchingDefinition`` with ``mode=SQL_EXECUTION``.
        """
        return cls(
            mode=FetchMode.SQL_EXECUTION,
            default_type=default_type,
            children=tuple(children),
            sql=sql,
            sql_parameters=sql_parameters,
        )

    @classmethod
    def from_sqlalchemy_metadata(
        cls,
        action: SQLAlchemyMetadataAction,
        *,
        default_type: ResourceKind,
        children: Sequence[ResourceKind] = (),
    ) -> "ResourceFetchingDefinition":
        """Construct a SQLAlchemy-metadata definition.

        Args:
          action: The Inspector action to perform (e.g., list schemas/tables/columns).
          default_type: Resource kind produced by this action.
          children: Child resource kinds available under each result.

        Returns:
          A ``ResourceFetchingDefinition`` with ``mode=SQL_ALCHEMY_METADATA``.
        """
        return cls(
            mode=FetchMode.SQLALCHEMY_METADATA,
            default_type=default_type,
            children=tuple(children),
            sqlalchemy_action=action,
        )
