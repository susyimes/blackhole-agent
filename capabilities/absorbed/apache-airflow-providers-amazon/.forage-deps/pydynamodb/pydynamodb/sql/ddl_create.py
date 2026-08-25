# -*- coding: utf-8 -*-
"""
Syntax of DDB table creation with SQL:
-------------------------------------
CREATE [GLOBAL] TABLE tbl_name
    [(create_definition, ...)]
    [table_options]

create_definition: {
    col_name column_definition
    | INDEX index_name index_type
        (col_name key_type, ...)
      [index_option] ...
}

column_definition: {
    data_type [key_type]
}

key_type : {
    PARTITION KEY | SORT KEY | HASH | RANGE
}

data_type: {
    NUMERIC | STRING | BINARY
}

index_type:
    {GLOBAL | LOCAL}

index_option: {
    Projection.ProjectionType [=] {ALL | KEYS_ONLY | INCLUDE}
    | Projection.NonKeyAttributes [=] ('string', ...)
    | ProvisionedThroughput.ReadCapacityUnits [=] value
    | ProvisionedThroughput.WriteCapacityUnits [=] value
}

table_options:
    table_option [[,] table_option] ...

table_option: {
    BillingMode [=] {PROVISIONED | PAY_PER_REQUEST}
    | ProvisionedThroughput.ReadCapacityUnits [=] value
    | ProvisionedThroughput.WriteCapacityUnits [=] value
    | StreamSpecification.StreamEnabled [=] {True | False}
    | StreamSpecification.StreamViewType [=] {NEW_IMAGE | OLD_IMAGE | NEW_AND_OLD_IMAGES | KEYS_ONLY}
    | SSESpecification.Enabled [=] {True | False}
    | SSESpecification.SSEType [=] {AES256 | KMS}
    | SSESpecification.KMSMasterKeyId [=] value
    | TableClass [=] {STANDARD | STANDARD_INFREQUENT_ACCESS}
    | Tags [=] (tags)
    | ReplicationGroup [=] ('string', ...)
}

tags:
    key:value, ...


Sample SQL of Creating Table:
-----------------------------
CREATE TABLE Issues (
    IssueId numeric PARTITION KEY,
    Title string SORT KEY,
    CreateDate string,
    DueDate string,
    INDEX CreateDateIndex GLOBAL (
        CreateDate PARTITION KEY,
        IssueId SORT KEY
    )
        Projection.ProjectionType INCLUDE
        Projection.NonKeyAttributes (Description, Status)
        ProvisionedThroughput.ReadCapacityUnits 1
        ProvisionedThroughput.WriteCapacityUnits 1,
    INDEX DueDateIndex GLOBAL (
        DueDate PARTITION KEY
    )
        Projection.ProjectionType ALL
        ProvisionedThroughput.ReadCapacityUnits 1
        ProvisionedThroughput.WriteCapacityUnits 1,
)
BillingMode PROVISIONED
ProvisionedThroughput.ReadCapacityUnits 1
ProvisionedThroughput.WriteCapacityUnits 1
StreamSpecification.StreamEnabled False
SSESpecification.Enabled False
TableClass STANDARD
Tags (name:Issue, usage:test)

CREATE GLOBAL TABLE Issues
    ReplicationGroup (us-east-1, us-west-2)
"""

import logging
from .common import KeyWords, Tokens
from .ddl_sql import DdlBase
from pyparsing import (
    Opt,
    Group,
    ZeroOrMore,
    OneOrMore,
    delimited_list,
    Forward,
)
from typing import Any, Dict

_logger = logging.getLogger(__name__)  # type: ignore


class DdlCreate(DdlBase):
    _ATTRIBUTE = Group(Tokens.ATTRIBUTE_NAME + Tokens.DATA_TYPE + Tokens.OPT_KEY_TYPE)(
        "attribute"
    ).set_name("attribute")

    _CREATE_TABLE_STATEMENT = (
        KeyWords.CREATE
        + Opt(KeyWords.GLOBAL)("global").set_name("global")
        + KeyWords.TABLE
        + Tokens.TABLE_NAME
        + Opt(
            KeyWords.LPAR
            + delimited_list(OneOrMore(_ATTRIBUTE))("attributes").set_name("attributes")
            + delimited_list(ZeroOrMore(DdlBase._INDEX))("indices").set_name("indices")
            + KeyWords.RPAR
        )
        + DdlBase._TABLE_OPTIONS
    )("create_statement").set_name("create_statement")

    _DDL_CREATE_EXPR = Forward()
    _DDL_CREATE_EXPR <<= _CREATE_TABLE_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return DdlCreate._DDL_CREATE_EXPR

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
        else:
            attr_def_ = []
            key_schema_ = []

            for attr in self.root_parse_results["attributes"]:
                attr_name = attr["attribute_name"]
                data_type = attr["data_type"]
                attr_def_.append(self._construct_attr_def(attr_name, data_type))

                key_type = attr["key_type"]
                if key_type != "":
                    key_schema_.append(self._construct_key_schema(attr_name, key_type))
            request.update({"AttributeDefinitions": attr_def_})

            request.update({"TableName": table_name_})
            request.update({"KeySchema": key_schema_})

            lsis_ = None
            gsis_ = None
            indices = self.root_parse_results["indices"]
            if indices is not None:
                for index in indices:
                    index_type = index["index_type"]

                    if index_type == "GLOBAL":
                        if gsis_ is None:
                            gsis_ = []
                        gsis_.append(self._construct_index(index))
                    elif index_type == "LOCAL":
                        if lsis_ is None:
                            lsis_ = []
                        lsis_.append(self._construct_index(index))
                    else:
                        raise LookupError("Index type is invalid")

            if lsis_ is not None:
                request.update({"LocalSecondaryIndexes": lsis_})
            if gsis_ is not None:
                request.update({"GlobalSecondaryIndexes": gsis_})

        table_options_ = self.root_parse_results["table_options"]
        if table_options_ is not None:
            converted_options = self._construct_options(table_options_)
            if converted_options is not None:
                request.update(converted_options)

        return request
