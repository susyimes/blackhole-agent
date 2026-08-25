# jsonParser.py
#
# Implementation of a simple JSON parser, returning a hierarchical
# ParseResults object support both list- and dict-style data access.
#
# Copyright 2006, by Paul McGuire
#
# Updated 8 Jan 2007 - fixed dict grouping bug, and made elements and
#   members optional in array and object collections
#
# Updated 9 Aug 2016 - use more current pyparsing constructs/idioms

import pyparsing as pp
from pyparsing import pyparsing_common as ppc


def make_keyword(kwd_str, kwd_value):
    return pp.Keyword(kwd_str).set_parse_action(pp.replace_with(kwd_value))


# set to False to return ParseResults
RETURN_PYTHON_COLLECTIONS = True

TRUE = make_keyword("true", True)
FALSE = make_keyword("false", False)
NULL = make_keyword("null", None)

LBRACK, RBRACK, LBRACE, RBRACE, COLON = map(pp.Suppress, "[]{}:")

jsonString = (pp.dbl_quoted_string() | pp.sgl_quoted_string).set_parse_action(
    pp.remove_quotes
)
jsonNumber = ppc.number().set_name("jsonNumber")

jsonObject = pp.Forward().set_name("jsonObject")
jsonValue = pp.Forward().set_name("jsonValue")

jsonElements = pp.DelimitedList(jsonValue).set_name(None)

jsonArray = pp.Group(
    LBRACK + pp.Optional(jsonElements) + RBRACK, aslist=RETURN_PYTHON_COLLECTIONS
).set_name("jsonArray")

jsonValue << (jsonString | jsonNumber | jsonObject | jsonArray | TRUE | FALSE | NULL)

memberDef = pp.Group(
    jsonString + COLON + jsonValue, aslist=RETURN_PYTHON_COLLECTIONS
).set_name("jsonMember")

jsonMembers = pp.DelimitedList(memberDef).set_name(None)
# jsonObject << pp.Dict(LBRACE + pp.Optional(jsonMembers) + RBRACE)
jsonObject << pp.Dict(
    LBRACE + pp.Optional(jsonMembers) + RBRACE, asdict=RETURN_PYTHON_COLLECTIONS
)

jsonComment = pp.cpp_style_comment
jsonObject.ignore(jsonComment)
