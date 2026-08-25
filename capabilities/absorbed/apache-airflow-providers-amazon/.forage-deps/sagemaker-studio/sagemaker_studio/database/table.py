from dataclasses import dataclass, field
from typing import List


@dataclass
class Column:
    """
    Represents a column within a database table.

    Attributes:
        name (str): The name of the column.
        type (str): The data type of the column.
    """

    name: str = field()
    type: str = field()


@dataclass
class Table:
    """
    Represents a table within a database.

    Attributes:
        name (str): The name of the table.
        database_name (str): The name of the database the table belongs to.
        catalog_id (str): The unique identifier of the catalog the table belongs to.
        location (str): The location of the table.
        columns (List[Column]): The list of columns in the table.
    """

    name: str = field()
    database_name: str = field()
    catalog_id: str = field()
    location: str = field()
    columns: List[Column] = field(default_factory=list)
