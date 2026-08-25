# -*- coding: utf-8 -*-
from ..sql.dml_select import DmlSelect
from ..sql.common import KeyWords
from pyparsing import (
    Forward,
    SkipTo,
)
from typing import Any, Dict


class SupersetSelect(DmlSelect):
    _BASE_SELECT_STATEMENT = DmlSelect._SELECT_STATEMENT

    _INNER_SELECT_STATEMENT = (
        KeyWords.SELECT
        + SkipTo(KeyWords.FROM)("inner_columns").set_name("inner_columns")
        + KeyWords.FROM
        + KeyWords.LPAR
        + _BASE_SELECT_STATEMENT
        + KeyWords.RPAR
        + SkipTo(KeyWords.RPAR)("inner_exprs").set_name("inner_exprs")
    )("inner_select").set_name("inner_select")

    _OUTER_SELECT_STATEMENT = (
        KeyWords.SELECT
        + SkipTo(KeyWords.FROM)("outer_columns").set_name("outer_columns")
        + KeyWords.FROM
        + KeyWords.LPAR
        + (_INNER_SELECT_STATEMENT | _BASE_SELECT_STATEMENT)
        + KeyWords.RPAR
        + SkipTo(KeyWords.SEMICOLON)("outer_exprs").set_name("outer_exprs")
    )("outer_select").set_name("outer_select")

    _NESTED_SELECT_STATEMENT = (
        _OUTER_SELECT_STATEMENT | _INNER_SELECT_STATEMENT | _BASE_SELECT_STATEMENT
    )("nested_select_statement").set_name("nested_select_statement")

    _SUPERSET_SELECT_EXPR = Forward()
    _SUPERSET_SELECT_EXPR <<= _NESTED_SELECT_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)
        self._outer_columns = None
        self._outer_exprs = None
        self._inner_columns = None
        self._inner_exprs = None
        self._is_nested = False

    def preprocess(self) -> None:
        self._executed_statement = self._executed_statement.strip()
        if self._executed_statement[-1] != ";":
            self._executed_statement += ";"

    @property
    def outer_columns(self) -> str:
        return self._outer_columns

    @property
    def outer_exprs(self) -> str:
        return self._outer_exprs

    @property
    def inner_columns(self) -> str:
        return self._inner_columns

    @property
    def inner_exprs(self) -> str:
        return self._inner_exprs

    @property
    def is_nested(self) -> bool:
        return self._is_nested

    @property
    def syntax_def(self) -> Forward:
        return SupersetSelect._SUPERSET_SELECT_EXPR

    def transform(self) -> Dict[str, Any]:
        converted_ = super().transform()

        outer_columns = self.root_parse_results.get("outer_columns", None)
        if outer_columns is not None:
            self._outer_columns = outer_columns.strip()
            self._is_nested = True

        outer_exprs = self.root_parse_results.get("outer_exprs", None)
        if outer_exprs is not None:
            self._outer_exprs = outer_exprs.strip()

        inner_columns = self.root_parse_results.get("inner_columns", None)
        if inner_columns is not None:
            self._inner_columns = inner_columns.strip()

        inner_exprs = self.root_parse_results.get("inner_exprs", None)
        if inner_exprs is not None:
            self._inner_exprs = inner_exprs.strip()

        return converted_
