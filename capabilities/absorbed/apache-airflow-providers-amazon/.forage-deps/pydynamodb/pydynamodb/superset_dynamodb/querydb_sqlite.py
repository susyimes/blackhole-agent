# -*- coding: utf-8 -*-
import logging
from datetime import datetime, date
from contextlib import closing
from typing import Any, Type

# Try to import sqlean first, fall back to native sqlite3
try:
    import sqlean as sqlite3

    _SQLEAN_INSTALLED = True
except ImportError:
    import sqlite3

    _SQLEAN_INSTALLED = False

from .querydb import QueryDB, QueryDBConfig
from ..model import Statement

_logger = logging.getLogger(__name__)  # type: ignore


def has_sqlean() -> bool:
    return _SQLEAN_INSTALLED


class SqliteFileQueryDB(QueryDB):
    def __init__(
        self,
        statement: Statement,
        config: QueryDBConfig,
        **kwargs,
    ) -> None:
        super().__init__(statement, config, **kwargs)
        self._connection = None

    @property
    def connection(self):
        if self._connection is None:
            # Enable extensions only if sqlean is available
            if _SQLEAN_INSTALLED:
                sqlite3.extensions.enable("math", "regexp", "stats", "text")

            self._connection = sqlite3.connect(
                self.config.db_url,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )

        return self._connection

    def type_conversion(self, type: Type[Any]) -> str:
        type_mapping = {
            str: "TEXT",
            int: "INTEGER",
            float: "REAL",
            bytes: "TEXT",
            bool: "INTEGER",
            datetime: "TIMESTAMP",
            date: "DATE",
        }

        return type_mapping.get(type, "TEXT")

    def has_table(self, table: str) -> bool:
        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "SELECT count(name) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            result = cursor.fetchone()
            if result and result == (1,):
                return True

        return False

    def purge(self) -> int:
        purged_count = super().purge()

        if purged_count > 0:
            self.connection.execute("VACUUM")

        return purged_count


class SqliteMemQueryDB(SqliteFileQueryDB):
    def __init__(
        self,
        statement: Statement,
        config: QueryDBConfig,
        **kwargs,
    ) -> None:
        kwargs.update({"cache_enabled": False})
        super().__init__(statement, config, **kwargs)
