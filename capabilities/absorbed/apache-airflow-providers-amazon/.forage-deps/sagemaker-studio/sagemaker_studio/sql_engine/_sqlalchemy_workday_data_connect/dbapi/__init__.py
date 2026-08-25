"""DB-API 2.0 interface for Workday Data Connect."""

from .connection import Connection  # noqa: F401
from .cursor import Cursor  # noqa: F401
from .exceptions import (  # noqa: F401
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    Warning,
)

apilevel = "2.0"
threadsafety = 2
paramstyle = "pyformat"


def connect(host, port, client_id, isu, token_endpoint, private_key, **kwargs):
    """Create a DB-API 2.0 connection to Workday Data Connect."""
    return Connection(
        host=host,
        port=port,
        client_id=client_id,
        isu=isu,
        token_endpoint=token_endpoint,
        private_key=private_key,
        **kwargs,
    )
