# -*- coding: utf-8 -*-
"""
Syntax of PartiQL
https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ql-reference.insert.html
------------------
INSERT INTO table VALUE item

Sample SQL of Inserting:
------------------------
INSERT INTO "Music" value {'Artist' : 'Acme Band','SongTitle' : 'PartiQL Rocks'}
"""

import logging
from .dml_sql import DmlBase
from .common import KeyWords, Tokens
from pyparsing import Forward, Group, Regex
from typing import Any, Dict

_logger = logging.getLogger(__name__)  # type: ignore


class DmlInsert(DmlBase):

    # Parse everything inside curly brackets as a single string
    _ITEM = Group(
        KeyWords.LCURLYBRACKET
        + Regex(r"[^}]*")("item_content")
        + KeyWords.RCURLYBRACKET
    )("item").set_name("item")

    _INSERT_STATEMENT = (
        KeyWords.INSERT + KeyWords.INTO + Tokens.TABLE_NAME + KeyWords.VALUE + _ITEM
    )("insert_statement").set_name("insert_statement")

    _DML_INSERT_EXPR = Forward()
    _DML_INSERT_EXPR <<= _INSERT_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return DmlInsert._DML_INSERT_EXPR

    def transform(self) -> Dict[str, Any]:
        table_name_ = self.root_parse_results["table"]
        item_content_ = self.root_parse_results["item"]["item_content"]

        table_ = '"%s"' % table_name_
        item_ = "{%s}" % item_content_

        statement_ = "INSERT INTO {table} VALUE {item}"
        statement_ = statement_.format(
            table=table_,
            item=item_,
        )
        request = {"Statement": statement_.strip()}

        return request
