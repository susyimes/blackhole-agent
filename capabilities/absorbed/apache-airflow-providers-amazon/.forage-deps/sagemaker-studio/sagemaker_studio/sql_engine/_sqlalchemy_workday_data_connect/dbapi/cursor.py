"""DB-API 2.0 Cursor wrapping a trino cursor."""


class Cursor:
    """Thin wrapper around a trino cursor exposing DB-API 2.0 interface."""

    def __init__(self, trino_cursor):
        self._cursor = trino_cursor

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def arraysize(self):
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value):
        self._cursor.arraysize = value

    def execute(self, operation, parameters=None):
        return self._cursor.execute(operation, parameters)

    def executemany(self, operation, seq_of_parameters):
        return self._cursor.executemany(operation, seq_of_parameters)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchmany(self, size=None):
        if size is None:
            size = self.arraysize
        return self._cursor.fetchmany(size)

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    def setinputsizes(self, sizes):
        pass

    def setoutputsize(self, size, column=None):
        pass

    def __iter__(self):
        return iter(self._cursor)

    def __next__(self):
        return next(self._cursor)
