# -*- coding: utf-8 -*-
import logging
from .base import Base
from .common import KeyWords, Tokens
from pyparsing import (
    CaselessKeyword,
    Opt,
    Group,
    ZeroOrMore,
    OneOrMore,
    one_of,
    delimited_list,
    ParseResults,
    ParserElement,
)
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)  # type: ignore


class DdlBase(Base):
    ParserElement.enablePackrat()

    _PROJECTION_PROJECTIONTYPE, _PROJECTION_NONKEYATTRIBUTES = map(
        CaselessKeyword,
        [
            "Projection.ProjectionType",
            "Projection.NonKeyAttributes",
        ],
    )

    (
        _PROVISIONEDTHROUGHPUT_READCAPACITYUNITS,
        _PROVISIONEDTHROUGHPUT_WRITECAPACITYUNITS,
        _BILLINGMODE,
        _STREAMSPECIFICATION_STREAMENABLED,
        _STREAMSPECIFICATION_STREAMVIEWTYPE,
        _SSESPECIFICATION_ENABLED,
        _SSESPECIFICATION_SSETYPE,
        _SSESPECIFICATION_KMSMASTERKEYID,
        _KMSMASTERKEYID,
        _TABLECLASS,
        _TAGS,
        _REPLICATION_GROUP,
    ) = map(
        CaselessKeyword,
        [
            "ProvisionedThroughput.ReadCapacityUnits",
            "ProvisionedThroughput.WriteCapacityUnits",
            "BillingMode",
            "StreamSpecification.StreamEnabled",
            "StreamSpecification.StreamViewType",
            "SSESpecification.Enabled",
            "SSESpecification.SSEType",
            "SSESpecification.KMSMasterKeyId",
            "KMSMasterKeyId",
            "TableClass",
            "Tags",
            "ReplicationGroup",
        ],
    )

    (
        _GLOBALSECONDARYINDEXES,
        _PROVISIONEDTHROUGHPUTOVERRIDE_READCAPACITYUNITS,
        _TABLECLASSOVERRIDE,
    ) = map(
        CaselessKeyword,
        [
            "GlobalSecondaryIndexes",
            "ProvisionedThroughputOverride.ReadCapacityUnits",
            "TableClassOverride",
        ],
    )

    _TABLE_OPTIONS = ZeroOrMore(
        Group(
            _PROVISIONEDTHROUGHPUT_READCAPACITYUNITS
            + Opt(KeyWords.EQUALS)
            + Tokens.INT_VALUE
            ^ _PROVISIONEDTHROUGHPUT_WRITECAPACITYUNITS
            + Opt(KeyWords.EQUALS)
            + Tokens.INT_VALUE
            ^ _BILLINGMODE
            + Opt(KeyWords.EQUALS)
            + one_of("PROVISIONED PAY_PER_REQUEST")
            ^ _STREAMSPECIFICATION_STREAMENABLED
            + Opt(KeyWords.EQUALS)
            + Tokens.BOOL_VALUE
            ^ _STREAMSPECIFICATION_STREAMVIEWTYPE
            + Opt(KeyWords.EQUALS)
            + one_of("NEW_IMAGE OLD_IMAGE NEW_AND_OLD_IMAGES KEYS_ONLY")
            ^ _SSESPECIFICATION_ENABLED + Opt(KeyWords.EQUALS) + Tokens.BOOL_VALUE
            ^ _SSESPECIFICATION_SSETYPE + Opt(KeyWords.EQUALS) + one_of("AES256 KMS")
            ^ _SSESPECIFICATION_KMSMASTERKEYID
            + Opt(KeyWords.EQUALS)
            + Tokens.KMSMASTERKEYID
            ^ _TABLECLASS
            + Opt(KeyWords.EQUALS)
            + one_of("STANDARD STANDARD_INFREQUENT_ACCESS")
            ^ _TAGS
            + Opt(KeyWords.EQUALS)
            + KeyWords.LPAR
            + Group(delimited_list(Tokens.TAG))("tags").set_name("tags")
            + KeyWords.RPAR
            ^ _REPLICATION_GROUP
            + KeyWords.LPAR
            + Group(delimited_list(Tokens.REGION_NAME))("replication_group").set_name(
                "replication_group"
            )
            + KeyWords.RPAR
        )("table_option").set_name("table_option")
    )("table_options").set_name("table_options")

    _INDEX_OPTIONS = ZeroOrMore(
        Group(
            _PROVISIONEDTHROUGHPUT_READCAPACITYUNITS
            + Opt(KeyWords.EQUALS)
            + Tokens.INT_VALUE
            ^ _PROVISIONEDTHROUGHPUT_WRITECAPACITYUNITS
            + Opt(KeyWords.EQUALS)
            + Tokens.INT_VALUE
            ^ _PROJECTION_PROJECTIONTYPE
            + Opt(KeyWords.EQUALS)
            + one_of("ALL KEYS_ONLY INCLUDE")
            ^ _PROJECTION_NONKEYATTRIBUTES
            + Opt(KeyWords.EQUALS)
            + KeyWords.LPAR
            + Group(delimited_list(Tokens.ATTRIBUTE_NAME))(
                "nonkey_attributes"
            ).set_name("nonkey_attributes")
            + KeyWords.RPAR
        )("index_option").set_name("index_option")
    )("index_options").set_name("index_options")

    _INDEX = Group(
        KeyWords.INDEX
        + Tokens.INDEX_NAME
        + Tokens.INDEX_TYPE
        + KeyWords.LPAR
        + delimited_list(OneOrMore(Group(Tokens.ATTRIBUTE_NAME + Tokens.KEY_TYPE)))(
            "attributes"
        ).set_name("attributes")
        + KeyWords.RPAR
        + _INDEX_OPTIONS
    )("index").set_name("index")

    def __init__(self, statement: str) -> None:
        super().__init__(statement)

    def _construct_attr_def(self, attr_name: str, data_type: str) -> Dict[str, str]:
        converted_data_type = None

        if data_type == "NUMERIC":
            converted_data_type = "N"
        elif data_type == "STRING":
            converted_data_type = "S"
        elif data_type == "BINARY":
            converted_data_type = "B"
        else:
            raise LookupError("Data type is invalid")

        return {"AttributeName": attr_name, "AttributeType": converted_data_type}

    def _construct_key_schema(self, attr_name: str, key_type: str) -> Dict[str, str]:
        converted_key_type = None
        if key_type == "PARTITION KEY" or key_type == "HASH":
            converted_key_type = "HASH"
        elif key_type == "SORT KEY" or key_type == "RANGE":
            converted_key_type = "RANGE"
        else:
            raise LookupError("Key schema type is invalid")

        return {"AttributeName": attr_name, "KeyType": converted_key_type}

    def _construct_index(self, index: ParseResults) -> Dict[str, Any]:
        index_ = {}
        index_name = index["index_name"]
        index_.update({"IndexName": index_name})

        attrs = index.get("attributes", None)
        if attrs:
            key_schema = []

            for attr in attrs:
                attr_name = attr["attribute_name"]
                key_type = attr["key_type"]

                key_schema.append(self._construct_key_schema(attr_name, key_type))
            index_.update({"KeySchema": key_schema})

        options = index["index_options"]
        index_.update(self._construct_options(options))
        return index_

    def _construct_options(self, options: List[Any]) -> Optional[Dict[str, Any]]:
        converted_ = None
        for option in options:
            if converted_ is None:
                converted_ = {}
            option_name_path = option[0]
            option_value = option[1]

            if isinstance(option_value, ParseResults):
                if (
                    option.get_name() == "index_option"
                    and option_value.get_name() == "nonkey_attributes"
                ):
                    option_value = [o for o in option_value]
                elif (
                    option.get_name() == "table_option"
                    and option_value.get_name() == "tags"
                ):
                    option_value = [
                        {"Key": o["tag_key"], "Value": o["tag_value"]}
                        for o in option_value
                    ]
                elif (
                    option.get_name() == "table_option"
                    and option_value.get_name() == "replication_group"
                ):
                    option_value = [{"RegionName": o} for o in option_value]

            self._parse_option_path(option_name_path, option_value, converted_)
        return converted_

    def _parse_option_path(
        self,
        option_name_path: str,
        option_value: Any,
        return_dict: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        if return_dict is None:
            return_dict = {}

        names = option_name_path.split(".")
        names_size = len(names)

        if names_size == 1:
            return_dict.update({names[0]: option_value})
        elif names_size == 2:
            if names[0] in return_dict:
                return_dict[names[0]].update({names[1]: option_value})
            else:
                return_dict.update({names[0]: {names[1]: option_value}})
        else:
            """Ignore the option"""
            pass

        return return_dict
