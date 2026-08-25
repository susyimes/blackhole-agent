# -*- coding: utf-8 -*-
import logging
from .base import Base
from .common import KeyWords, Tokens
from pyparsing import Opt, Group, CaselessKeyword, ZeroOrMore, Forward
from typing import Any, Dict

_logger = logging.getLogger(__name__)  # type: ignore


class UtilBase(Base):
    def __init__(self, statement: str) -> None:
        super().__init__(statement)


"""
Syntax of list DDB tables:
{LIST | SHOW} [GLOBAL] TABLES
    [Limit [=] value]
    [RegionName [=] 'string']

Sample SQL of Listing Tables:
-----------------------------
LIST TABLES
SHOW TABLES Limit 10

LIST GLOBAL TABLES
    Limit 10
    RegionName us-west-1
"""


class UtilListTables(UtilBase):
    _REGION_NAME = CaselessKeyword("RegionName")

    _LIST_TABLES_STATEMENT = (
        (KeyWords.LIST | KeyWords.SHOW)
        + Opt(KeyWords.GLOBAL)("global").set_name("global")
        + KeyWords.TABLES
        + ZeroOrMore(
            Group(
                KeyWords.LIMIT
                + Opt(KeyWords.EQUALS)
                + Tokens.INT_VALUE("limit").set_name("limit")
                ^ _REGION_NAME + Opt(KeyWords.EQUALS) + Tokens.REGION_NAME
            )("option").set_name("option")
        )("options").set_name("options")
    )("list_tables_statement").set_name("list_tables_statement")

    _UTIL_LIST_TABLES_EXPR = Forward()
    _UTIL_LIST_TABLES_EXPR <<= _LIST_TABLES_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)
        self._limit = None

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def syntax_def(self) -> Forward:
        return UtilListTables._UTIL_LIST_TABLES_EXPR

    def transform(self) -> Dict[str, Any]:
        if self.root_parse_results is None:
            raise ValueError("Statement was not parsed yet")

        request = {}
        is_global_table = (
            True if self.root_parse_results.get("global", None) is not None else False
        )
        options = self.root_parse_results["options"]

        for option in options:
            limit_value = option.get("limit", None)
            region_name = option.get("region_name", None)

            if limit_value:
                self._limit = limit_value
                request.update({"Limit": limit_value})

            if is_global_table and region_name:
                request.update({"RegionName": region_name})

        return request


"""
Syntax of describe DDB table:
{DESC | DESCRIBE} [GLOBAL] tbl_name

Sample SQL of Describing Table:
-----------------------------
DESC Issues
DESCRIBE Issues

DESC GLOBAL Issues
"""


class UtilDescTable(UtilBase):
    _DESC_TABLE_STATEMENT = (
        (KeyWords.DESC | KeyWords.DESCRIBE)
        + Opt(KeyWords.GLOBAL)("global").set_name("global")
        + Tokens.TABLE_NAME
    )("desc_table_statement").set_name("desc_table_statement")

    _DESC_TABLE_EXPR = Forward()
    _DESC_TABLE_EXPR <<= _DESC_TABLE_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return UtilDescTable._DESC_TABLE_EXPR

    def transform(self) -> Dict[str, Any]:
        if self.root_parse_results is None:
            raise ValueError("Statement was not parsed yet")

        request = {}
        table_name = self.root_parse_results["table"]
        is_global_table = (
            True if self.root_parse_results.get("global", None) is not None else False
        )

        if is_global_table:
            request.update({"GlobalTableName": table_name})
        else:
            request.update({"TableName": table_name})

        return request
