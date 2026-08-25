# -*- coding: utf-8 -*-
from typing import TYPE_CHECKING, FrozenSet

from .error import *  # noqa

if TYPE_CHECKING:
    from .connection import Connection

__version__: str = "0.8.2"

# Globals https://www.python.org/dev/peps/pep-0249/#globals
apilevel: str = "2.0"
threadsafety: int = 3
paramstyle: str = "qmark"


class DBAPITypeObject(FrozenSet[str]):
    """Type Objects and Constructors

    https://www.python.org/dev/peps/pep-0249/#type-objects-and-constructors
    """

    def __eq__(self, other: object):
        if isinstance(other, frozenset):
            return frozenset.__eq__(self, other)
        else:
            return other in self

    def __ne__(self, other: object):
        if isinstance(other, frozenset):
            return frozenset.__ne__(self, other)
        else:
            return other not in self

    def __hash__(self):
        return frozenset.__hash__(self)


# https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.NamingRulesDataTypes.html
STRING: DBAPITypeObject = DBAPITypeObject(("STRING",))
BINARY: DBAPITypeObject = DBAPITypeObject(("STRING",))
BOOLEAN: DBAPITypeObject = DBAPITypeObject(
    (
        "BOOL",
        "NULL",
    )
)
NUMBER: DBAPITypeObject = DBAPITypeObject(("NUMBER",))
JSON: DBAPITypeObject = DBAPITypeObject(("STRING",))


def connect(*args, **kwargs) -> "Connection":
    from .connection import Connection
    from .superset_dynamodb.pydynamodb import SupersetCursor

    connector = kwargs.get("connector", None)
    if connector is not None and connector.lower() == "superset":
        kwargs.update({"cursor_class": SupersetCursor})

    return Connection(*args, **kwargs)
