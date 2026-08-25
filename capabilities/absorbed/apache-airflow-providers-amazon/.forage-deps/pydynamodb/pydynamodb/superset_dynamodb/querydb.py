# -*- coding: utf-8 -*-
import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from contextlib import closing
from abc import ABCMeta, abstractmethod
from typing import Tuple, Optional, Type, Any, List

from ..sql.common import DataTypes, QueryType, Functions
from ..sql.dml_select import DmlSelectColumn, DmlFunction
from ..model import Statement, Metadata
from ..util import synchronized
from ..error import NotSupportedError

_logger = logging.getLogger(__name__)  # type: ignore


DEFAULT_QUERYDB_TYPE = "sqlite"
DEFAULT_QUERYDB_URL = ":memory:"
DEFAULT_QUERYDB_LOAD_BATCH_SIZE = 200
DEFAULT_QUERYDB_EXPIRE_TIME = 300
DEFAULT_QUERYDB_PURGE_TIME = 86400


SUPPORTED_QUERYDB_CONFIG = {
    "querydb_type": ("PYDYNAMODB_QUERYDB_TYPE", DEFAULT_QUERYDB_TYPE),
    "querydb_class": ("PYDYNAMODB_QUERYDB_CLASS", None),
    "querydb_url": ("PYDYNAMODB_QUERYDB_URL", DEFAULT_QUERYDB_URL),
    "querydb_load_batch_size": (
        "PYDYNAMODB_QUERYDB_LOAD_BATCH_SIZE",
        DEFAULT_QUERYDB_LOAD_BATCH_SIZE,
    ),
    "querydb_expire_time": (
        "PYDYNAMODB_QUERYDB_EXPIRE_TIME",
        DEFAULT_QUERYDB_EXPIRE_TIME,
    ),
    "querydb_purge_enabled": (
        "PYDYNAMODB_QUERYDB_PURGE_ENABLED",
        "True",
    ),
    "querydb_purge_time": (
        "PYDYNAMODB_QUERYDB_PURGE_TIME",
        DEFAULT_QUERYDB_PURGE_TIME,
    ),
}


class QueryDBConfig:
    def __init__(
        self,
        db_type: str,
        db_class: str,
        db_url: str,
        load_batch_size: int = DEFAULT_QUERYDB_LOAD_BATCH_SIZE,
        expire_time: int = DEFAULT_QUERYDB_EXPIRE_TIME,
        purge_enabled: bool = True,
        purge_time: int = DEFAULT_QUERYDB_PURGE_TIME,
    ):
        self._db_type = db_type
        self._db_url = db_url
        self._db_class = db_class
        self._load_batch_size = load_batch_size
        self._expire_time = expire_time
        self._purge_enabled = purge_enabled
        self._purge_time = purge_time

    @property
    def db_type(self) -> str:
        return self._db_type

    @property
    def db_class(self) -> str:
        return self._db_class

    @property
    def db_url(self) -> str:
        return self._db_url

    @property
    def load_batch_size(self) -> int:
        return self._load_batch_size

    @property
    def expire_time(self) -> int:
        return self._expire_time

    @property
    def purge_enabled(self) -> int:
        return self._purge_enabled

    @property
    def purge_time(self) -> int:
        return self._purge_time


class QueryDB(metaclass=ABCMeta):
    CACHE_TABLE = "QUERYDB_CACHES"

    def __init__(
        self,
        statement: Statement,
        config: QueryDBConfig,
        **kwargs,
    ) -> None:
        self._config = config
        self._statement = statement
        cache_enabled_ = kwargs.get("cache_enabled", None)
        self._cache_enabled = cache_enabled_ if cache_enabled_ is not None else True
        self._kwargs = kwargs
        self._query_id = None

    @property
    def statement(self) -> Statement:
        return self._statement

    @property
    def config(self) -> QueryDBConfig:
        return self._config

    @property
    def cache_enabled(self) -> bool:
        return self._cache_enabled

    @property
    def query_id(self) -> str:
        if self._query_id is None:
            sql_parser = self._statement.sql_parser
            if sql_parser.query_type == QueryType.SELECT:
                columns = ",".join([str(c) for c in sql_parser.parser.columns])
                hash_key = str(self._statement.api_request) + columns
                self._query_id = (
                    "_T" + hashlib.md5(hash_key.encode("utf-8")).hexdigest()
                )
            else:
                raise NotSupportedError

        return self._query_id

    @abstractmethod
    def connection(self):
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def type_conversion(self, type: Type[Any]) -> str:
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def has_table(self, table: str) -> bool:
        raise NotImplementedError  # pragma: no cover

    def rollback(self):
        if self.connection is not None:
            self.connection.rollback()

    def close(self):
        if self.connection is not None:
            if self.cache_enabled and self.config.purge_enabled:
                self.purge()
            self.connection.close()

    @synchronized
    def purge(self) -> int:
        purged_count = 0

        if self.config.purge_time < self.config.expire_time:
            return purged_count

        if not self.cache_enabled or not self.has_table(QueryDB.CACHE_TABLE):
            return purged_count

        _purge_period = datetime.now() - timedelta(seconds=self.config.purge_time)

        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "SELECT query_id FROM %s WHERE last_updated<=?" % QueryDB.CACHE_TABLE,
                (_purge_period,),
            )
            result = cursor.fetchall()
            purged_count = len(result)
            for r in result:
                try:
                    cursor.execute("DROP TABLE %s" % (r[0]))
                except Exception:
                    _logger.warning("Failed to drop query table.")

            if purged_count > 0:
                cursor.executemany(
                    "DELETE FROM %s WHERE query_id=?" % QueryDB.CACHE_TABLE, result
                )
        self.connection.commit()

        return purged_count

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @synchronized
    def init_cache_table(self) -> None:
        if not self.cache_enabled:
            return

        if not self.has_table(QueryDB.CACHE_TABLE):
            columns = []
            columns.append(
                "%s %s PRIMARY KEY" % ("query_id", self.type_conversion(str))
            )
            columns.append("%s %s" % ("statement", self.type_conversion(str)))
            columns.append("%s %s" % ("created", self.type_conversion(datetime)))
            columns.append("%s %s" % ("last_updated", self.type_conversion(datetime)))
            columns.append("%s %s" % ("queried_times", self.type_conversion(int)))
            self.connection.execute(
                "CREATE TABLE %s (%s)" % (QueryDB.CACHE_TABLE, ",".join(columns))
            )

    def get_cache(self) -> Optional[Tuple[Any]]:
        if not self.cache_enabled:
            return None

        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "SELECT statement, created, last_updated FROM %s WHERE query_id=?"
                % QueryDB.CACHE_TABLE,
                (self.query_id,),
            )
            return cursor.fetchone()

    def has_cache(self) -> bool:
        if not self.cache_enabled:
            return False

        if not self.has_table(QueryDB.CACHE_TABLE):
            return False

        cache_ = self.get_cache()
        if cache_ is None:
            return False

        if (datetime.now() - cache_[2]).seconds <= self.config.expire_time:
            return True

        return False

    @synchronized
    def add_cache(self) -> None:
        if not self.cache_enabled:
            return

        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "SELECT COUNT(query_id) FROM %s WHERE query_id=?" % QueryDB.CACHE_TABLE,
                (self.query_id,),
            )
            result = cursor.fetchone()
            if result is None or result == (0,):
                cursor.execute(
                    """INSERT INTO %s (query_id, statement,
                                    created, last_updated, queried_times
                        ) VALUES (?, ?, ?, ?, ?)
                    """ % QueryDB.CACHE_TABLE,
                    (
                        self.query_id,
                        str(self.statement.api_request),
                        datetime.now(),
                        datetime.now(),
                        0,
                    ),
                )
                self.connection.commit()

    @synchronized
    def set_cache_last_updated(self) -> None:
        if not self.cache_enabled:
            return

        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "UPDATE %s SET last_updated=? WHERE query_id=?" % QueryDB.CACHE_TABLE,
                (datetime.now(), self.query_id),
            )
            self.connection.commit()

    @synchronized
    def set_cache_queried_times(self) -> None:
        if not self.cache_enabled:
            return

        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                "UPDATE %s SET queried_times=queried_times+1 WHERE query_id=?"
                % QueryDB.CACHE_TABLE,
                (self.query_id,),
            )
            self.connection.commit()

    def _get_col_type(self, col_info: DmlSelectColumn) -> str:
        col_type = self.type_conversion(str)

        if col_info.type_code == DataTypes.BOOL or col_info.type_code == DataTypes.NULL:
            col_type = self.type_conversion(int)
        elif col_info.type_code == DataTypes.NUMBER:
            col_type = self.type_conversion(float)
        elif col_info.type_code == DataTypes.DATE:
            col_type = self.type_conversion(date)
        elif col_info.type_code == DataTypes.DATETIME:
            col_type = self.type_conversion(datetime)
        return col_type

    def _get_col_function(self, col_name: str, col_function: DmlFunction) -> str:
        _col_func = col_name
        if (
            col_function is not None
            and col_function.name
            in Functions.SUPPORTED_FUNTIONS[Functions.STRING_FUNCTION]
        ):
            if col_function.params is not None:
                _col_func = '%s("%s", %s)' % (
                    col_function.name,
                    col_name,
                    ",".join(
                        f'"{x}"' if isinstance(x, str) else str(x)
                        for x in col_function.params
                    ),
                )
            else:
                _col_func = '%s("%s")' % (col_function.name, col_name)

        return _col_func

    def _escape_col_name(self, col_name: str) -> str:
        return re.sub(r"[^\w]", "_", col_name)

    def _get_query_table_col_name(self, col_info: DmlSelectColumn) -> str:
        return (
            self._escape_col_name(col_info.name)
            if col_info.alias is None
            else col_info.alias
        )

    @synchronized
    def create_query_table(self, metadata: Metadata) -> None:
        columns_with_type = []

        for col_info in metadata:
            col_type = self._get_col_type(col_info)
            columns_with_type.append(
                '"%s" %s' % (self._get_query_table_col_name(col_info), col_type)
            )

        query_table_creation = "CREATE TABLE IF NOT EXISTS %s (%s)" % (
            self.query_id,
            ",".join(columns_with_type),
        )
        self.connection.execute(query_table_creation)
        self.add_cache()

    @synchronized
    def drop_query_table(self) -> None:
        if self.has_table(self.query_id):
            self.connection.execute("DROP TABLE %s" % (self.query_id))

    @synchronized
    def write_raw_data(
        self, metadata: Metadata, raw_data: Optional[List[Tuple[Any]]]
    ) -> None:
        columns = []
        values = []
        for col_info in metadata:
            columns.append('"' + self._get_query_table_col_name(col_info) + '"')
            values.append("?")

        self.connection.executemany(
            "INSERT INTO %s (%s) VALUES (%s)"
            % (self.query_id, ",".join(columns), ",".join(values)),
            [r for r in raw_data],
        )

        self.connection.commit()
        self.set_cache_last_updated()

    def _create_query_sql(self) -> str:
        parser = self.statement.sql_parser.parser
        query_sql = ""
        outer_columns = "*" if parser.outer_columns is None else parser.outer_columns
        outer_exprs = "" if parser.outer_exprs is None else parser.outer_exprs

        if parser.inner_columns is None:
            query_sql = "SELECT %s FROM %s %s" % (
                outer_columns,
                self.query_id,
                outer_exprs,
            )
        else:
            inner_columns = parser.inner_columns
            inner_exprs = "" if parser.inner_exprs is None else parser.inner_exprs

            query_sql = "SELECT %s FROM (SELECT %s FROM %s %s) %s" % (
                outer_columns,
                inner_columns,
                self.query_id,
                inner_exprs,
                outer_exprs,
            )

        return query_sql

    def query(self):
        query_sql = self._create_query_sql()
        with closing(self.connection.cursor()) as cursor:
            cursor.execute(query_sql)
            self.set_cache_queried_times()
            results = cursor.fetchall()
            desc = cursor.description
            return (desc, results)
