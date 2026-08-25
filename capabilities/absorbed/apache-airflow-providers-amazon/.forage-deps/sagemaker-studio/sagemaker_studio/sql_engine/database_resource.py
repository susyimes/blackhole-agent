from dataclasses import dataclass, field
from typing import List


@dataclass
class DatabaseResource:
    """
    One item in the database resource tree (database, schema, table, or column).

    Represents a named resource discovered from metadata or SQL execution.
    The ``type`` indicates which kind of resource this is, and ``children`` lists
    the kinds of resources that can appear beneath this node in the hierarchy.

    Attributes:
      name: The resource identifier (e.g., ``"public"``, ``"users"``, ``"id"``).
      type: The resource kind (e.g., ``"DATABASE"``, ``"SCHEMA"``, ``"TABLE"``, ``"COLUMN"``).
      children: Ordered list of child resource kinds available under this node.
    """

    name: str = field()
    type: str = field()
    children: List[str] = field(default_factory=list)
