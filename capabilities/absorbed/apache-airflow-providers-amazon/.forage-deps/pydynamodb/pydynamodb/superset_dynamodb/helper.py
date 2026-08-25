# -*- coding: utf-8 -*-
import os
import logging
import importlib
from abc import ABCMeta
from typing import Optional, Union

from .querydb import (
    QueryDBConfig,
    QueryDB,
    SUPPORTED_QUERYDB_CONFIG,
    DEFAULT_QUERYDB_TYPE,
    DEFAULT_QUERYDB_URL,
    DEFAULT_QUERYDB_LOAD_BATCH_SIZE,
    DEFAULT_QUERYDB_EXPIRE_TIME,
    DEFAULT_QUERYDB_PURGE_TIME,
)
from ..model import Statement
from ..util import strtobool
from ..error import NotSupportedError, OperationalError
from .querydb_sqlite import SqliteMemQueryDB, SqliteFileQueryDB

_logger = logging.getLogger(__name__)  # type: ignore


class QueryDBHelper(metaclass=ABCMeta):
    @staticmethod
    def create(statement: Statement, config: QueryDBConfig = None, **kwargs) -> QueryDB:
        if config is None:
            _config = QueryDBHelper.get_default_config(**kwargs)
        else:
            _config = config

        _query_db_class = None
        if _config.db_type.lower() == DEFAULT_QUERYDB_TYPE:
            _query_db_class = (
                SqliteMemQueryDB
                if _config.db_url.lower() == DEFAULT_QUERYDB_URL
                else SqliteFileQueryDB
            )
        else:
            if _config.db_class:
                db_apis = _config.db_class.split(":")
                if len(db_apis) == 2:
                    _query_db_module = importlib.import_module(db_apis[0])
                    _query_db_class = getattr(_query_db_module, db_apis[1])
                else:
                    raise OperationalError("QueryDB class is invalid.")
            else:
                raise NotSupportedError("QueryDB class is not specified.")

        _query_db = _query_db_class(statement, _config, **kwargs)
        if _query_db is None:
            raise OperationalError("QueryDB is not specified.")
        else:
            return _query_db

    @staticmethod
    def get_default_config(**kwargs):
        db_type = QueryDBHelper.get_config_value("querydb_type", **kwargs)
        db_url = QueryDBHelper.get_config_value("querydb_url", **kwargs)
        db_class = QueryDBHelper.get_config_value("querydb_class", **kwargs)
        load_batch_size = QueryDBHelper.get_config_value(
            "querydb_load_batch_size", **kwargs
        )
        expire_time = QueryDBHelper.get_config_value("querydb_expire_time", **kwargs)
        purge_enabled = QueryDBHelper.get_config_value(
            "querydb_purge_enabled", **kwargs
        )
        purge_time = QueryDBHelper.get_config_value("querydb_purge_time", **kwargs)

        _db_type = db_type if db_type is not None else DEFAULT_QUERYDB_TYPE
        _db_url = db_url if db_url is not None else DEFAULT_QUERYDB_URL
        _db_class = db_class
        _load_batch_size = (
            int(load_batch_size)
            if load_batch_size is not None
            else DEFAULT_QUERYDB_LOAD_BATCH_SIZE
        )
        _expire_time = (
            int(expire_time) if expire_time is not None else DEFAULT_QUERYDB_EXPIRE_TIME
        )
        _purge_enabled = strtobool(purge_enabled) if purge_enabled is not None else True
        _purge_time = (
            int(purge_time) if purge_time is not None else DEFAULT_QUERYDB_PURGE_TIME
        )

        return QueryDBConfig(
            _db_type,
            _db_class,
            _db_url,
            load_batch_size=_load_batch_size,
            expire_time=_expire_time,
            purge_enabled=_purge_enabled,
            purge_time=_purge_time,
        )

    @staticmethod
    def get_config_value(config_name: str, **kwargs) -> Optional[Union[str, int]]:
        if config_name in kwargs:
            return kwargs[config_name]
        else:
            if config_name in SUPPORTED_QUERYDB_CONFIG:
                env_name, default_val = SUPPORTED_QUERYDB_CONFIG[config_name]
                env_val = os.getenv(env_name, None)
                if env_val is None:
                    return default_val
                else:
                    return env_val
            else:
                return None
