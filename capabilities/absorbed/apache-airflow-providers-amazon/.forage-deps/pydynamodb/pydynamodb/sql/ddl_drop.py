# -*- coding: utf-8 -*-
"""
Syntax of DDB table dropping with SQL:
DROP [GLOBAL] TABLE tbl_name
    [ReplicationGroup [=] ('string', ...)]

Sample SQL of Dropping Table:
-----------------------------
DROP TABLE Issues

DROP GLOBAL TABLE Issues
    ReplicationGroup (us-east-1, us-west-2)
"""

import logging
from .ddl_sql import DdlBase
from .common import KeyWords, Tokens
from pyparsing import Opt, Group, Forward, delimited_list
from typing import Any, Dict

_logger = logging.getLogger(__name__)  # type: ignore


class DdlDrop(DdlBase):
    _DROP_TABLE_STATEMENT = (
        KeyWords.DROP
        + Opt(KeyWords.GLOBAL)("global").set_name("global")
        + KeyWords.TABLE
        + Tokens.TABLE_NAME
        + Opt(
            DdlBase._REPLICATION_GROUP
            + Opt(KeyWords.EQUALS)
            + KeyWords.LPAR
            + Group(delimited_list(Tokens.REGION_NAME))("replication_group").set_name(
                "replication_group"
            )
            + KeyWords.RPAR
        )
    )("drop_statement").set_name("drop_statement")

    _DDL_DROP_EXPR = Forward()
    _DDL_DROP_EXPR <<= _DROP_TABLE_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return DdlDrop._DDL_DROP_EXPR

    def transform(self) -> Dict[str, Any]:
        if self.root_parse_results is None:
            raise ValueError("Statement was not parsed yet")

        request = {}
        is_global_table = (
            True if self.root_parse_results.get("global", None) is not None else False
        )
        table_name_ = self.root_parse_results["table"]

        if is_global_table:
            request.update({"GlobalTableName": table_name_})
            replication_group = self.root_parse_results["replication_group"]

            request.update(
                {
                    "ReplicaUpdates": [
                        {"Delete": {"RegionName": r}} for r in replication_group
                    ]
                }
            )
        else:
            request.update({"TableName": table_name_})

        return request
