# -*- coding: utf-8 -*-
"""
Syntax of PartiQL
https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ql-reference.delete.html
------------------
DELETE FROM table
WHERE condition [RETURNING returnvalues]
<returnvalues>  ::= ALL OLD *

Sample SQL of Deleting:
------------------------
DELETE FROM "Music" WHERE "Artist" = 'Acme Band' AND "SongTitle" = 'PartiQL Rocks'

DELETE FROM "Music" WHERE "Artist" = 'Acme Band' AND "SongTitle" = 'PartiQL Rocks' RETURNING ALL OLD *
"""

import logging
from .dml_sql import DmlBase
from .common import KeyWords, Tokens
from pyparsing import (
    Forward,
    Opt,
)
from typing import Any, Dict

_logger = logging.getLogger(__name__)  # type: ignore


class DmlDelete(DmlBase):

    _DELETE_STATEMENT = (
        KeyWords.DELETE
        + KeyWords.FROM
        + Tokens.TABLE_NAME
        + KeyWords.WHERE
        + DmlBase._WHERE_CONDITIONS
        + Opt(DmlBase._RETURNING_CLAUSE)
    )("delete_statement").set_name("delete_statement")

    _DML_DELETE_EXPR = Forward()
    _DML_DELETE_EXPR <<= _DELETE_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return DmlDelete._DML_DELETE_EXPR

    def transform(self) -> Dict[str, Any]:
        table_name_ = self.root_parse_results["table"]

        table_ = '"%s"' % table_name_

        # Build the statement
        statement_ = "DELETE FROM {table} {where_conditions}"

        where_conditions = self.root_parse_results.get("where_conditions", None)
        if where_conditions is not None:
            where_conditions_ = self._construct_where_conditions(where_conditions)
        else:
            where_conditions_ = ""

        statement_ = statement_.format(
            table=table_, where_conditions=str(where_conditions_)
        )

        # Add RETURNING clause if present
        if "returning_clause" in self.root_parse_results:
            returning = self.root_parse_results["returning_clause"]
            return_content = returning.get("return_content", "").strip()
            statement_ += " RETURNING %s" % return_content

        request = {"Statement": statement_.strip()}
        return request
