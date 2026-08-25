# -*- coding: utf-8 -*-
import logging
from abc import ABCMeta

from .common import QueryType, get_query_type
from .base import Base
from .ddl_create import DdlCreate
from .ddl_alter import DdlAlter
from .ddl_drop import DdlDrop
from .dml_insert import DmlInsert
from .dml_select import DmlSelect
from .dml_update import DmlUpdate
from .dml_delete import DmlDelete
from .util_sql import UtilListTables, UtilDescTable
from typing import Any, Dict, Tuple, Type, Optional

_logger = logging.getLogger(__name__)  # type: ignore


class SQLParser(metaclass=ABCMeta):
    def __init__(self, statement: str = "", parser_class: Base = None) -> None:
        self._statement = statement
        self._query_type = None
        self._query_category = None
        self._operation_type = None
        self._parser_class = parser_class
        self._parser = None

    @property
    def statement(self) -> str:
        return self._statement

    @property
    def query_type(self) -> Tuple[str, str, str]:
        if self._statement is None:
            raise ValueError("Statement is not specified")

        if self._query_type is not None:
            return self._query_type

        self._query_type = get_query_type(self._statement)
        return self._query_type

    @property
    def query_category(self) -> str:
        if self._query_category is not None:
            return self._query_category

        self._query_category = (
            self.query_type[0] if self.query_type is not None else None
        )
        return self._query_category

    @property
    def operation_type(self) -> str:
        if self._operation_type is not None:
            return self._operation_type

        self._operation_type = (
            self.query_type[1] if self.query_type is not None else None
        )
        return self._operation_type

    @property
    def parser(self) -> Base:
        if self._parser is None:
            if self._parser_class is None:
                self._parser = self._get_parse_class()(self.statement)
            else:
                self._parser = self._parser_class(self.statement)

        return self._parser

    def _get_parse_class(self) -> Optional[Type[Base]]:
        _parse_class: Optional[Type[Base]] = None
        if (
            self.query_type == QueryType.CREATE
            or self.query_type == QueryType.CREATE_GLOBAL
        ):
            _parse_class = DdlCreate
        elif self.query_type == QueryType.ALTER:
            _parse_class = DdlAlter
        elif (
            self.query_type == QueryType.DROP
            or self.query_type == QueryType.DROP_GLOBAL
        ):
            _parse_class = DdlDrop
        elif self.query_type == QueryType.SELECT:
            _parse_class = DmlSelect
        elif self.query_type == QueryType.INSERT:
            _parse_class = DmlInsert
        elif self.query_type == QueryType.UPDATE:
            _parse_class = DmlUpdate
        elif self.query_type == QueryType.DELETE:
            _parse_class = DmlDelete
        elif (
            self.query_type == QueryType.LIST
            or self.query_type == QueryType.LIST_GLOBAL
        ):
            _parse_class = UtilListTables
        elif (
            self.query_type == QueryType.DESC
            or self.query_type == QueryType.DESC_GLOBAL
        ):
            _parse_class = UtilDescTable

        return _parse_class

    def transform(self) -> Dict[str, Any]:
        assert self.parser is not None, "Parser not found."
        return self.parser.transform()
