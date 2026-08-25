# -*- coding: utf-8 -*-

"""
Syntax of DDB table altering with SQL:
-------------------------------------
ALTER TABLE tbl_name (
    [col_name column_definition, ...]
    [alter_option [, alter_option] ...]
)
    [table_options]

alter_option: {
    CREATE INDEX [index_name] GLOBAL
        (col_name key_type, ...)
        [index_option] ...
    | UPDATE INDEX [index_name] GLOBAL
        [index_option] ...
    | DELETE INDEX [index_name] GLOBAL
    | CREATE REPLICA [region_name]
        [replica_option] ...
    | UPDATE REPLICA [region_name]
        [replica_option] ...
    | DELETE REPLICA [region_name]
}

key_type : {
    PARTITION KEY | SORT KEY | HASH | RANGE
}

index_option: {
    Projection.ProjectionType [=] {ALL | KEYS_ONLY | INCLUDE}
    | Projection.NonKeyAttributes [=] ('string', ...)
    | ProvisionedThroughput.ReadCapacityUnits [=] value
    | ProvisionedThroughput.WriteCapacityUnits [=] value
}

replica_option: {
    KMSMasterKeyId [=] value
    | ProvisionedThroughputOverride.ReadCapacityUnits [=] value
    | TableClassOverride [=] {STANDARD | STANDARD_INFREQUENT_ACCESS}
    | GlobalSecondaryIndexes [=] (
        index_name [ProvisionedThroughputOverride.ReadCapacityUnits [=] value],
        ...)
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
}

Sample SQL of Altering Table:
-----------------------------
ALTER TABLE Issues (
    IssueId numeric,
    Title string,
    CreateDate string,
    DueDate string,
    CREATE INDEX CreateDateIndex GLOBAL (
        CreateDate PARTITION KEY,
        IssueId SORT KEY
    )
        Projection.ProjectionType INCLUDE
        Projection.NonKeyAttributes (Description, Status)
        ProvisionedThroughput.ReadCapacityUnits 1
        ProvisionedThroughput.WriteCapacityUnits 1,
    UPDATE INDEX DueDateIndex GLOBAL
        ProvisionedThroughput.ReadCapacityUnits 10
        ProvisionedThroughput.WriteCapacityUnits 10,
    DELETE INDEX IssueIdIndex GLOBAL,
    CREATE REPLICA cn-north-1
        KMSMasterKeyId XXXXXXXX
        ProvisionedThroughputOverride.ReadCapacityUnits 1
        GlobalSecondaryIndexes (
            CreateDateIndex
            ProvisionedThroughputOverride.ReadCapacityUnits 1,
            DueDateIndex
            ProvisionedThroughputOverride.ReadCapacityUnits 1
        )
        TableClassOverride STANDARD,
    UPDATE REPLICA cn-northwest-1
        KMSMasterKeyId *********
        ProvisionedThroughputOverride.ReadCapacityUnits 10
        GlobalSecondaryIndexes (
            CreateDateIndex
            ProvisionedThroughputOverride.ReadCapacityUnits 10,
            DueDateIndex
            ProvisionedThroughputOverride.ReadCapacityUnits 10
        )
        TableClassOverride STANDARD_INFREQUENT_ACCESS,
    DELETE REPLICA cn-northwest-2
)
BillingMode PAY_PER_REQUEST
ProvisionedThroughput.ReadCapacityUnits 10
ProvisionedThroughput.WriteCapacityUnits 10
StreamSpecification.StreamEnabled True
StreamSpecification.StreamViewType NEW_AND_OLD_IMAGES
SSESpecification.Enabled True
SSESpecification.SSEType KMS
SSESpecification.KMSMasterKeyId $$$$$$$$
TableClass STANDARD_INFREQUENT_ACCESS
"""

import logging
from .ddl_sql import DdlBase
from .common import KeyWords, Tokens
from pyparsing import (
    Opt,
    Group,
    ZeroOrMore,
    delimited_list,
    one_of,
    Forward,
    ParseResults,
)
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)  # type: ignore


class DdlAlter(DdlBase):
    _ATTRIBUTE = Group(Tokens.ATTRIBUTE_NAME + Tokens.DATA_TYPE)("attribute").set_name(
        "attribute"
    )

    _ALTER_INDEX = Group(
        KeyWords.CREATE("alter_ops") + DdlBase._INDEX
        ^ KeyWords.UPDATE("alter_ops")
        + Group(
            KeyWords.INDEX
            + Tokens.INDEX_NAME
            + Tokens.INDEX_TYPE
            + DdlBase._INDEX_OPTIONS
        )("index").set_name("index")
        ^ KeyWords.DELETE("alter_ops")
        + Group(KeyWords.INDEX + Tokens.INDEX_NAME + Tokens.INDEX_TYPE)(
            "index"
        ).set_name("index")
    )

    _REPLICA = Group(
        KeyWords.REPLICA
        + Tokens.REGION_NAME
        + Opt(
            ZeroOrMore(
                Group(
                    DdlBase._KMSMASTERKEYID
                    + Opt(KeyWords.EQUALS)
                    + Tokens.KMSMASTERKEYID
                    ^ DdlBase._PROVISIONEDTHROUGHPUTOVERRIDE_READCAPACITYUNITS
                    + Opt(KeyWords.EQUALS)
                    + Tokens.INT_VALUE
                    ^ DdlBase._TABLECLASSOVERRIDE
                    + Opt(KeyWords.EQUALS)
                    + one_of("STANDARD STANDARD_INFREQUENT_ACCESS")
                )("replica_option").set_name("replica_option")
                ^ Group(
                    DdlBase._GLOBALSECONDARYINDEXES
                    + KeyWords.LPAR
                    + delimited_list(
                        Group(
                            Tokens.INDEX_NAME
                            + DdlBase._PROVISIONEDTHROUGHPUTOVERRIDE_READCAPACITYUNITS
                            + Opt(KeyWords.EQUALS)
                            + Tokens.INT_VALUE
                        )("gsi").set_name("gsi")
                    )("gsis").set_name("gsis")
                    + KeyWords.RPAR
                )("replica_gsi_option").set_name("replica_gsi_option")
            )("replica_options").set_name("replica_options")
        )
    )("replica").set_name("replica")

    _ALTER_REPLICA = Group(
        KeyWords.CREATE("alter_ops") + _REPLICA
        ^ KeyWords.UPDATE("alter_ops") + _REPLICA
        ^ KeyWords.DELETE("alter_ops")
        + Group(KeyWords.REPLICA + Tokens.REGION_NAME)("replica").set_name("replica")
    )

    _ALTER_TABLE_STATEMENT = (
        KeyWords.ALTER
        + KeyWords.TABLE
        + Tokens.TABLE_NAME
        + KeyWords.LPAR
        + delimited_list(ZeroOrMore(_ATTRIBUTE))("attributes").set_name("attributes")
        + delimited_list(ZeroOrMore(_ALTER_INDEX))("indices").set_name("indices")
        + delimited_list(ZeroOrMore(_ALTER_REPLICA))("replicas").set_name("replicas")
        + KeyWords.RPAR
        + DdlBase._TABLE_OPTIONS
    )("alter_statement").set_name("alter_statement")

    _DDL_ALTER_EXPR = Forward()
    _DDL_ALTER_EXPR <<= _ALTER_TABLE_STATEMENT

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    @property
    def syntax_def(self) -> Forward:
        return DdlAlter._DDL_ALTER_EXPR

    def transform(self) -> Dict[str, Any]:
        if self.root_parse_results is None:
            raise ValueError("Statement was not parsed yet")

        request = {}
        attr_def_ = None

        for attr in self.root_parse_results["attributes"]:
            if attr_def_ is None:
                attr_def_ = []
            attr_name = attr["attribute_name"]
            data_type = attr["data_type"]
            attr_def_.append(self._construct_attr_def(attr_name, data_type))

        if attr_def_ is not None:
            request.update({"AttributeDefinitions": attr_def_})

        table_name_ = self.root_parse_results["table"]
        request.update({"TableName": table_name_})

        gsis_ = None
        indices = self.root_parse_results["indices"]
        if indices is not None:
            for index in indices:
                alter_ops = index["alter_ops"]
                index_type = index["index"]["index_type"]

                if index_type == "GLOBAL":
                    if gsis_ is None:
                        gsis_ = []

                    if alter_ops == "CREATE" or alter_ops == "UPDATE":
                        gsis_.append(
                            {
                                self._get_alter_operation(
                                    alter_ops
                                ): self._construct_index(index["index"])
                            }
                        )
                    elif alter_ops == "DELETE":
                        gsis_.append(
                            {
                                self._get_alter_operation(alter_ops): {
                                    "IndexName": index["index"]["index_name"]
                                }
                            }
                        )
                else:
                    raise LookupError("Index type is invalid")

        if gsis_ is not None:
            request.update({"GlobalSecondaryIndexUpdates": gsis_})

        replicas_ = None
        replicas = self.root_parse_results["replicas"]
        if replicas is not None:
            for replica in replicas:
                if replicas_ is None:
                    replicas_ = []
                alter_ops = replica["alter_ops"]

                if alter_ops == "CREATE" or alter_ops == "UPDATE":
                    replicas_.append(
                        {
                            self._get_alter_operation(
                                alter_ops
                            ): self._construct_replica(replica["replica"])
                        }
                    )
                elif alter_ops == "DELETE":
                    replicas_.append(
                        {
                            self._get_alter_operation(alter_ops): {
                                "RegionName": replica["replica"]["region_name"]
                            }
                        }
                    )

        if replicas_ is not None:
            request.update({"ReplicaUpdates": replicas_})

        table_options_ = self.root_parse_results["table_options"]
        if table_options_ is not None:
            converted_options = self._construct_options(table_options_)
            if converted_options is not None:
                request.update(converted_options)

        return request

    def _get_alter_operation(self, ops: str) -> Optional[str]:
        if ops is None:
            return None

        if ops.lower() == "CREATE".lower():
            return "Create"
        elif ops.lower() == "UPDATE".lower():
            return "Update"
        elif ops.lower() == "DELETE".lower():
            return "Delete"
        else:
            raise LookupError("Alter operation is invalid")

    def _construct_replica(self, replica: ParseResults) -> Dict[str, Any]:
        replicas_ = {}

        region_name = replica["region_name"]
        replicas_.update({"RegionName": region_name})

        replica_options = replica.get("replica_options")
        replica_options_ = None
        replica_gsi_option_ = None

        if replica_options is not None:
            for replica_option in replica_options:
                if replica_options_ is None:
                    replica_options_ = []

                if replica_option.get_name() == "replica_gsi_option":
                    replica_gsi_option_ = replica_option
                else:
                    replica_options_.append(replica_option)

        if replica_options_ is not None:
            converted_options_ = self._construct_options(replica_options_)
            if converted_options_ is not None:
                replicas_.update(converted_options_)

        if replica_gsi_option_ is not None:
            replicas_.update(
                {
                    "GlobalSecondaryIndexes": self._construct_replica_gsi(
                        replica_gsi_option_
                    )
                }
            )

        return replicas_

    def _construct_replica_gsi(
        self, replica_gsi_option: ParseResults
    ) -> Optional[Dict[str, Any]]:
        gsis = replica_gsi_option.get("gsis")
        gsis_ = None

        if gsis is not None:
            for gsi in gsis:
                index_name = gsi["index_name"]

                if len(gsi) == 3:
                    if gsis_ is None:
                        gsis_ = []

                    option_path_name = gsi[1]
                    option_value = gsi[2]
                    options = self._parse_option_path(option_path_name, option_value)
                    converted_ = {"IndexName": index_name}

                    if options is not None and len(options) > 0:
                        converted_.update(options)
                    gsis_.append(converted_)

        return gsis_
