# -*- coding: utf-8 -*-
"""
Syntax of PartiQL
https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ql-reference.update.html
------------------
UPDATE  table
[SET | REMOVE]  path  [=  data] […]
WHERE condition [RETURNING returnvalues]
<returnvalues>  ::= [ALL OLD | MODIFIED OLD | ALL NEW | MODIFIED NEW] *

Sample SQL of Updating:
------------------------
UPDATE "Music"
SET AwardsWon=1
SET AwardDetail={'Grammys':[2020, 2018]}
WHERE Artist='Acme Band' AND SongTitle='PartiQL Rocks'
RETURNING ALL OLD *

UPDATE "Music"
REMOVE AwardDetail.Grammys[2]
WHERE Artist='Acme Band' AND SongTitle='PartiQL Rocks'
"""

import logging
from .dml_sql import DmlBase
from .json_parser import jsonArray, jsonObject
from .common import KeyWords, Tokens
from .util import flatten_list
from pyparsing import (
    Forward,
    Group,
    OneOrMore,
    Opt,
    Literal,
    ZeroOrMore,
)
from typing import Any, Dict

_logger = logging.getLogger(__name__)  # type: ignore


class DmlUpdate(DmlBase):

    _COMMA = Literal(",")

    _COLUMN_UPDATE_RVAL = (jsonObject | jsonArray | DmlBase._COLUMN_RVAL)(
        "column_update_rvalue"
    ).set_name("column_update_rvalue")

    _OPERATION_CONTENT = Group(
        DmlBase._COLUMN + KeyWords.EQUAL_TO + _COLUMN_UPDATE_RVAL
    )("op_content").set_name("op_content")

    _SET_OPERATION = Group(
        KeyWords.SET + _OPERATION_CONTENT + ZeroOrMore(_COMMA + _OPERATION_CONTENT)
    )("set_op").set_name("set_op")

    _REMOVE_OPERATION = Group(
        KeyWords.REMOVE + _OPERATION_CONTENT + ZeroOrMore(_COMMA + _OPERATION_CONTENT)
    )("remove_op").set_name("remove_op")

    _OPERATIONS = OneOrMore(_SET_OPERATION | _REMOVE_OPERATION)("operations").set_name(
        "operations"
    )

    _UPDATE_STATEMENT = (
        KeyWords.UPDATE
        + Tokens.TABLE_NAME
        + _OPERATIONS
        + KeyWords.WHERE
        + DmlBase._WHERE_CONDITIONS
        + Opt(DmlBase._RETURNING_CLAUSE)
    )("update_statement").set_name("update_statement")

    _DML_UPDATE_EXPR = Forward()
    _DML_UPDATE_EXPR <<= _UPDATE_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return DmlUpdate._DML_UPDATE_EXPR

    def transform(self) -> Dict[str, Any]:
        table_name_ = self.root_parse_results["table"]
        operations_ = self.root_parse_results["operations"]

        table_ = '"%s"' % table_name_

        operations_str = " ".join(str(c) for c in flatten_list(operations_.as_list()))

        where_conditions = self.root_parse_results.get("where_conditions", None)
        if where_conditions is not None:
            where_conditions_ = self._construct_where_conditions(where_conditions)
        else:
            where_conditions_ = ""

        # Build the statement
        statement_ = "UPDATE {table} {operations} {where_conditions}"

        statement_ = statement_.format(
            table=table_,
            operations=operations_str,
            where_conditions=where_conditions_,
        )

        # Add RETURNING clause if present
        if "returning_clause" in self.root_parse_results:
            returning = self.root_parse_results["returning_clause"]
            return_content = returning.get("return_content", "").strip()
            statement_ += " RETURNING %s" % return_content

        request = {"Statement": statement_.strip()}
        return request
