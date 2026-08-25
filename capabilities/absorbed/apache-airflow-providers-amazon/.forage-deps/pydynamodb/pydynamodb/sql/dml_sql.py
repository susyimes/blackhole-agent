# -*- coding: utf-8 -*-
import logging
from abc import ABCMeta
from .base import Base
from typing import Any, Dict, List, Optional
from .common import KeyWords, Tokens, escape_keyword
from .util import flatten_list
from pyparsing import (
    ParseResults,
    Word,
    CaselessKeyword,
    alphanums,
    nums,
    quoted_string,
    Group,
    ZeroOrMore,
    opAssoc,
    Opt,
    delimited_list,
    one_of,
    infix_notation,
    pyparsing_common as ppc,
    Combine,
    Regex,
)

_logger = logging.getLogger(__name__)  # type: ignore


class DmlBase(Base):
    def __escape_column(self, token: Any) -> str:
        return escape_keyword(token.get("column_name"))

    _CONSISTENT_READ, _RETURN_CONSUMED_CAPACITY = map(
        CaselessKeyword,
        [
            "ConsistentRead",
            "ReturnConsumedCapacity",
        ],
    )

    ATTR_NAME = (
        Opt('"') + Word(alphanums + "_-")("attr_name").set_name("attr_name") + Opt('"')
    )
    ATTR_ARRAY_NAME = ATTR_NAME + "[" + Word(nums) + "]"

    _COLUMN_NAME = (
        KeyWords.STAR
        ^ Combine(delimited_list(ATTR_NAME ^ ATTR_ARRAY_NAME, delim=".", combine=True))
    )("column_name").set_name("column_name")

    _ALIAS_NAME = Word(alphanums + "_-")("alias_name").set_name("alias_name")

    _COLUMN = _COLUMN_NAME.set_parse_action(__escape_column)

    _COLUMNS = delimited_list(
        Group(
            _COLUMN
            + ZeroOrMore(Group(KeyWords.ARITHMETIC_OPERATORS + _COLUMN))(
                "column_ops"
            ).set_name("column_ops")
        )
    )("columns").set_name("columns")

    _COLUMN_RVAL = (
        ppc.real() | ppc.signed_integer() | quoted_string | _COLUMN | KeyWords.QUESTION
    )("column_rvalue").set_name("column_rvalue")

    _WHERE_CONDITION = Group(
        (_COLUMN + KeyWords.COMPARISON_OPERATORS + _COLUMN_RVAL)
        ^ (
            _COLUMN
            + KeyWords.IN
            + Group(
                "["
                + delimited_list(_COLUMN_RVAL)("in_values_list").set_name(
                    "in_values_list"
                )
                + "]"
            )
        )
        ^ (_COLUMN + KeyWords.BETWEEN + _COLUMN_RVAL + KeyWords.AND + _COLUMN_RVAL)
        ^ (_COLUMN + KeyWords.IS + Tokens.PARTIQL_DATA_TYPE)
        ^ (_COLUMN + KeyWords.IS + KeyWords.NOT + Tokens.PARTIQL_DATA_TYPE)
        ^ (
            KeyWords.FUNCTION_ON_WHERE
            + "("
            + delimited_list(quoted_string)("function_params").set_name(
                "function_params"
            )
            + ")"
        )
        ^ (
            KeyWords.FUNCTION_WITH_OP_ON_WHERE
            + "("
            + delimited_list(quoted_string)("function_params").set_name(
                "function_params"
            )
            + ")"
            + KeyWords.COMPARISON_OPERATORS
            + _COLUMN_RVAL
        )
    )("where_condition").set_name("where_condition")

    _WHERE_CONDITIONS = infix_notation(
        _WHERE_CONDITION,
        [
            (KeyWords.NOT, 1, opAssoc.RIGHT),
            (one_of("AND OR", caseless=True), 2, opAssoc.LEFT),
            ((KeyWords.BETWEEN, KeyWords.AND), 3, opAssoc.RIGHT),
        ],
        lpar="(",
        rpar=")",
    )("where_conditions").set_name("where_expression")

    _RAW_SUPPORTED_OPTIONS = ZeroOrMore(
        Group(KeyWords.ORDER_BY + _COLUMN + Tokens.ORDER_BY_VALUE)(
            "raw_supported_option"
        ).set_name("raw_supported_option")
    )("raw_supported_options").set_name("raw_supported_options")

    _OPTIONS = ZeroOrMore(
        Group(
            KeyWords.LIMIT + Opt(KeyWords.EQUALS) + Tokens.INT_VALUE
            ^ _CONSISTENT_READ + Opt(KeyWords.EQUALS) + Tokens.BOOL_VALUE
            ^ _RETURN_CONSUMED_CAPACITY
            + Opt(KeyWords.EQUALS)
            + one_of("INDEXES TOTAL NONE")
        )("option").set_name("option")
    )("options").set_name("options")

    _RETURNING_CLAUSE = Group(
        KeyWords.RETURNING + Regex(r".*")("return_content").set_name("return_content")
    )("returning_clause").set_name("returning_clause")

    def __init__(self, statement: str) -> None:
        super().__init__(statement)
        self._parsed_where_conditions = []
        self._limit = None
        self._consistent_read = False
        self._return_consumed_capacity = "NONE"

    @property
    def where_conditions(self) -> List[Optional[str]]:
        return self._parsed_where_conditions

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def consistent_read(self) -> bool:
        return self._consistent_read

    @property
    def return_consumed_capacity(self) -> str:
        return self._return_consumed_capacity

    @property
    def syntax_def(self) -> None:
        return None

    def transform(self) -> Dict[str, Any]:
        return {"Statement": self._statement}

    def _construct_where_conditions(self, where_conditions: List[Any]) -> str:
        for condition in where_conditions:
            if not isinstance(condition, ParseResults):
                self._parsed_where_conditions.append(str(condition))
            else:
                function_ = condition.get("function", None)
                function_with_op_ = condition.get("function_with_op", None)
                if function_:
                    flatted_func_params = ",".join(condition["function_params"])
                    self._parsed_where_conditions.append(
                        "%s(%s)" % (function_, flatted_func_params)
                    )
                elif function_with_op_:
                    flatted_func_params = ",".join(condition["function_params"])
                    self._parsed_where_conditions.append(
                        "%s(%s) %s %s"
                        % (
                            function_with_op_,
                            flatted_func_params,
                            condition["comparison_operators"],
                            condition["column_rvalue"],
                        )
                    )
                else:
                    where_conditions_ = condition.as_list()
                    flatted_where = " ".join(
                        str(c) for c in flatten_list(where_conditions_)
                    )
                    self._parsed_where_conditions.append(flatted_where)

        return "WHERE %s" % " ".join(self.where_conditions)


class DmlFunction(metaclass=ABCMeta):
    def __init__(self, name: str, params: List[str] = None) -> None:
        self._name = name
        self._params = params

    @property
    def name(self) -> str:
        return self._name

    @property
    def params(self) -> List[str]:
        return self._params
