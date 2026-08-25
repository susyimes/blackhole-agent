# -*- coding: utf-8 -*-
import logging
from typing import List, Optional, Any, Dict
from collections import OrderedDict
from .sql.dml_sql import DmlFunction
from .sql.base import Base
from .sql.common import QueryType
from .sql.parser import SQLParser
from .error import OperationalError

_logger = logging.getLogger(__name__)  # type: ignore


class ColumnInfo:
    def __init__(
        self,
        name: str,
        original: str,
        alias: str = None,
        function: DmlFunction = None,
        type_code: str = None,
        display_size: str = None,
        internal_size: str = None,
        precision: str = None,
        scale: str = None,
        null_ok: str = None,
    ) -> None:
        self._name = name
        self._original = original
        self._alias = alias
        self._function = function
        self._type_code = type_code
        self._display_size = display_size
        self._internal_size = internal_size
        self._precision = precision
        self._scale = scale
        self._null_ok = null_ok

    @property
    def name(self) -> str:
        return self._name

    @property
    def original(self) -> str:
        return self._original

    @property
    def alias(self) -> str:
        return self._alias

    @alias.setter
    def alias(self, value: str) -> None:
        self._alias = value

    @property
    def function(self) -> DmlFunction:
        return self._function

    @property
    def type_code(self) -> str:
        return self._type_code

    @type_code.setter
    def type_code(self, value: str) -> None:
        self._type_code = value

    @property
    def display_size(self) -> str:
        return self._display_size

    @display_size.setter
    def display_size(self, value: str) -> None:
        self._display_size = value

    @property
    def internal_size(self) -> str:
        return self._internal_size

    @internal_size.setter
    def internal_size(self, value: str) -> None:
        self._internal_size = value

    @property
    def precision(self) -> str:
        return self._precision

    @precision.setter
    def precision(self, value: str) -> None:
        self._precision = value

    @property
    def scale(self) -> str:
        return self._scale

    @scale.setter
    def scale(self, value: str) -> None:
        self._scale = value

    @property
    def null_ok(self) -> str:
        return self._null_ok

    @null_ok.setter
    def null_ok(self, value: str) -> None:
        self._null_ok = value

    def __str__(self) -> str:
        return "%s | %s | %s | %s | %s | %s | %s | %s | %s" % (
            self.name,
            self.original,
            self.alias,
            self.type_code,
            self.display_size,
            self.internal_size,
            self.precision,
            self.scale,
            self.null_ok,
        )


class Metadata:
    def __init__(self, column_infos: List[Optional[ColumnInfo]] = None) -> None:
        self._column_infos = OrderedDict()

        if column_infos is not None:
            for column_info in column_infos:
                self.append(column_info)

    def get(self, name: str, default: Any = None) -> ColumnInfo:
        return self._column_infos.get(name, default)

    def append(self, column_info: ColumnInfo) -> None:
        self.update(column_info)

    def update(self, column_info: ColumnInfo) -> None:
        self._column_infos.update({column_info.name: column_info})

    def clear(self) -> None:
        self._column_infos.clear()

    def index(self, key: str) -> int:
        return list(self._column_infos).index(key)

    def keys(self) -> List[str]:
        return self._column_infos.keys()

    def __len__(self):
        return len(self._column_infos.keys())

    def __getitem__(self, key: str) -> ColumnInfo:
        return self._column_infos[key]

    def __contains__(self, key: str):
        return key in self._column_infos

    def __next__(self):
        keys = list(self._column_infos)
        if self.__iterator_index < len(keys):
            ret = self._column_infos[keys[self.__iterator_index]]
            self.__iterator_index += 1
            return ret
        raise StopIteration

    def __iter__(self):
        self.__iterator_index = 0
        return self


class Statement:
    def __init__(self, operation: str, parser_class: Base = None) -> None:
        self._sql_parser = SQLParser(operation, parser_class=parser_class)
        self._api_request = self._sql_parser.transform()

    @property
    def sql_parser(self) -> SQLParser:
        return self._sql_parser

    @property
    def api_request(self) -> Optional[Dict[str, Any]]:
        return self._api_request


class Statements:
    def __init__(self, statements: List[Statement] = None) -> None:
        if statements is not None:
            for statement_ in statements:
                self._validate(statement_)
            self._statments = statements
        else:
            self._statments = []

        self._query_type = None
        self._query_category = None
        self._operation_type = None
        self._limit = None

    @property
    def query_type(self) -> QueryType:
        return self._query_type

    @property
    def query_category(self) -> str:
        return self._query_category

    @property
    def operation_type(self) -> str:
        return self._operation_type

    @property
    def limit(self) -> str:
        return self._limit

    def _validate(self, statement: Statement) -> bool:
        if statement is not None:
            query_type_ = statement.sql_parser.query_type
            query_category_ = statement.sql_parser.query_category
            operation_type_ = statement.sql_parser.operation_type
            if self._query_type is None:
                self._query_type = query_type_
                self._query_category = query_category_
                self._operation_type = operation_type_

                if (
                    self._query_type == QueryType.SELECT
                    or self._query_type == QueryType.LIST
                ):
                    self._limit = statement.sql_parser.parser.limit

                return True
            else:
                if query_category_ == "DML" and operation_type_ == self._query_type[1]:
                    return True
                elif query_category_ == "DDL" or query_category_ == "UTIL":
                    raise OperationalError("Not support batch DDL/Utility statements")
                else:
                    raise OperationalError(
                        "Not support both read and write operation statements in the request"
                    )

    def append(self, statement: Statement) -> None:
        if self._validate(statement):
            self._statments.append(statement)

    def extend(self, statements: "Statements") -> None:
        if statements is not None:
            for statement_ in statements:
                self.append(statement_)

    def clear(self) -> None:
        self._statments.clear()
        self._query_type = None

    def __len__(self):
        return len(self._statments)

    def __getitem__(self, key):
        return self._statments[key]

    def __next__(self):
        if self.__iterator_index < len(self._statments):
            ret = self._statments[self.__iterator_index]
            self.__iterator_index += 1
            return ret
        raise StopIteration

    def __iter__(self):
        self.__iterator_index = 0
        return self
