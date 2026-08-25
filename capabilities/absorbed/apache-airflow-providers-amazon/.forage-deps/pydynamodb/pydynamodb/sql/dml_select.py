# -*- coding: utf-8 -*-
"""
Syntax of PartiQL
https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ql-reference.select.html
------------------
SELECT expression  [, ...]
FROM table[.index]
[ WHERE condition ] [ [ORDER BY key [DESC|ASC]] , ...]

Extension of PartiQL:
---------------------
Add Limit, ConsistentRead, ReturnConsumedCapacity options to the tailing
SELECT [expression | function(expression)] [alias]  [, ...]
FROM table[.index]
[ WHERE condition ]
[ [ORDER BY key [DESC|ASC]]
  [Limit value]
  [ConsistentRead {True|False}]
  [ReturnConsumedCapacity {INDEXES|TOTAL|NONE}]
...]

Sample SQL of Selecting:
------------------------
SELECT *
FROM "Issues"."CreateDateIndex"
WHERE IssueId IN [100, 300, 234]
AND Title = 'some title'
AND Content[0] >= 100
ORDER BY IssueId DESC
LIMIT 10
ConsistentRead False
ReturnConsumedCapacity NONE
"""

import logging
import re
from abc import ABCMeta
from collections import OrderedDict
from .dml_sql import DmlBase, DmlFunction
from .common import KeyWords, Tokens
from pyparsing import Opt, Forward, Group, ZeroOrMore, delimited_list, Regex
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)  # type: ignore


class DmlSelectColumn(metaclass=ABCMeta):
    def __init__(
        self,
        request_name: str,
        alias: str = None,
        result_name: str = None,
        function: DmlFunction = None,
    ) -> None:
        self._request_name = request_name
        self._alias = alias
        self._result_name = result_name
        self._function = function

    @property
    def request_name(self) -> str:
        return self._request_name

    @property
    def alias(self) -> str:
        return self._alias

    @alias.setter
    def alias(self, value: str) -> None:
        self._alias = value

    @property
    def result_name(self) -> str:
        if self._result_name is not None:
            return self._result_name

        if self.request_name is not None:
            self._result_name = self.request_name.split(".")[-1]
            self._result_name = self._result_name.replace('"', "")

        return self._result_name

    @property
    def function(self) -> DmlFunction:
        return self._function

    def __str__(self):
        return "(request_name: %s, alias: %s, result_name: %s, function: %s)" % (
            self.request_name,
            self.alias,
            self.result_name,
            self.function.name if self.function is not None else None,
        )

    __repr__ = __str__


class DmlSelect(DmlBase):
    _FUNCTION_PARAMS = ZeroOrMore(
        KeyWords.COMMA
        + Tokens.QUOTED_STRING("function_param").set_name("function_param")
        | KeyWords.COMMA + Tokens.INT_VALUE("function_param").set_name("function_param")
    )("function_params").set_name("function_params")

    _COLUMN_WITH_FUNCTION = (
        KeyWords.FUNCTION_ON_COLUMN
        + KeyWords.LPAR
        + DmlBase._COLUMN_NAME
        + _FUNCTION_PARAMS
        + KeyWords.RPAR
    )

    _REQUEST_COLUMN = _COLUMN_WITH_FUNCTION | DmlBase._COLUMN_NAME

    _ALIAS = (
        Opt(KeyWords.SUPPRESS_QUOTE)
        + DmlBase._ALIAS_NAME
        + Opt(KeyWords.SUPPRESS_QUOTE)
    )

    _REQUEST_COLUMNS = delimited_list(
        Group(
            Opt(KeyWords.LPAR)
            + _REQUEST_COLUMN
            + ZeroOrMore(Group(KeyWords.ARITHMETIC_OPERATORS + _REQUEST_COLUMN))(
                "column_ops"
            ).set_name("column_ops")
            + Opt(KeyWords.RPAR)
            + Opt(~Regex("FROM", flags=re.IGNORECASE) + _ALIAS)
        )
    )("columns").set_name("columns")

    _SELECT_STATEMENT = (
        KeyWords.SELECT
        + _REQUEST_COLUMNS
        + KeyWords.FROM
        + Tokens.TABLE_NAME
        + Opt(KeyWords.DOT + Tokens.INDEX_NAME)
        + Opt(KeyWords.WHERE + DmlBase._WHERE_CONDITIONS)
        + Opt(DmlBase._RAW_SUPPORTED_OPTIONS)
        + Opt(DmlBase._OPTIONS)
    )("select_statement").set_name("select_statement")

    _DML_SELECT_EXPR = Forward()
    _DML_SELECT_EXPR <<= _SELECT_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)
        self._columns = []
        self._is_star_column = False

    @property
    def columns(self) -> List[Optional[DmlSelectColumn]]:
        return self._columns

    @property
    def is_star_column(self) -> bool:
        return self._is_star_column

    @property
    def syntax_def(self) -> Forward:
        return DmlSelect._DML_SELECT_EXPR

    def transform(self) -> Dict[str, Any]:
        table_name_ = self.root_parse_results["table"]
        index_name_ = self.root_parse_results.get("index_name", None)

        table_ = None
        if index_name_ is None:
            table_ = '"%s"' % table_name_
        else:
            table_ = '"%s"."%s"' % (table_name_, index_name_)

        columns_ = self._construct_columns(self.root_parse_results["columns"])

        where_conditions = self.root_parse_results.get("where_conditions", None)
        if where_conditions is not None:
            where_conditions_ = self._construct_where_conditions(where_conditions)
        else:
            where_conditions_ = ""

        raw_supported_options = self.root_parse_results.get("raw_supported_options", [])
        raw_supported_options_ = self._construct_raw_options(raw_supported_options)
        if raw_supported_options_ is not None:
            raw_supported_options_ = " ".join(raw_supported_options_)
        else:
            raw_supported_options_ = ""

        statement_ = "SELECT {columns} FROM {table} {where_conditions} {options}"
        statement_ = statement_.format(
            columns=columns_,
            table=table_,
            where_conditions=where_conditions_,
            options=raw_supported_options_,
        )
        request = {"Statement": statement_.strip()}

        options = self.root_parse_results.get("options", [])
        options_ = self._construct_options(options)
        if options_ is not None:
            request.update(options_)

        return request

    def _construct_columns(self, columns: List[Any]) -> str:
        columns_ = (
            OrderedDict()
        )  # Create a ordered dict to avoid duplicate column names
        for column in columns:
            if column["column_name"] == "*":
                self._is_star_column = True
                self._columns.clear()
                return "*"

            column_ = []
            column_.append(column["column_name"])

            for rcolumn in column["column_ops"]:
                column_.append(rcolumn["arithmetic_operators"])
                column_.append(rcolumn["column_name"])

            column__ = "".join(column_)
            columns_[column__] = (
                "_"  # Add a dummy value to avoid duplicate column names
            )

            function_ = column.get("function", None)
            column_function_ = None
            if function_:
                func_params_ = column["function_params"]
                if len(func_params_) > 0:
                    column_function_ = DmlFunction(
                        function_, params=[p for p in func_params_]
                    )
                else:
                    column_function_ = DmlFunction(function_)

            alias_ = column.get("alias_name", None)

            self._columns.append(
                DmlSelectColumn(column__, function=column_function_, alias=alias_)
            )
        columns_ = ",".join(columns_.keys())
        return columns_

    def _construct_raw_options(self, options: List[Any]) -> Optional[List[Any]]:
        converted_ = None
        for option in options:
            if converted_ is None:
                converted_ = []

            converted_.append(" ".join(str(o) for o in option))

        return converted_

    def _construct_options(self, options: List[Any]) -> Optional[Dict[str, Any]]:
        converted_ = None
        for option in options:
            if converted_ is None:
                converted_ = {}
            option_name = option[0]
            option_value = option[1]

            if option_name == "Limit":
                self._limit = option_value
                continue
            elif option_name == "ConsistentRead":
                self._consistent_read = option_value
            elif option_name == "ReturnConsumedCapacity":
                self._return_consumed_capacity = option_value

            converted_.update({option_name: option_value})

        return converted_
