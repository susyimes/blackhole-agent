# -*- coding: utf-8 -*-
import re
import json
from ..util import strtobool
from typing import TYPE_CHECKING, cast, Optional, Sequence, List

import pydynamodb
from pydynamodb.error import OperationalError, NotSupportedError
from ..sql.common import RESERVED_WORDS

import botocore
from sqlalchemy import exc, types, util, __version__
from sqlalchemy.engine import Engine, reflection
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.sql import crud
from sqlalchemy.sql.compiler import (
    IdentifierPreparer,
    DDLCompiler,
    GenericTypeCompiler,
    SQLCompiler,
)

if TYPE_CHECKING:
    from types import ModuleType


def _check_sqla_major_ver():  # pragma: no cover
    try:
        return tuple(int(x) for x in __version__.split("."))[0]
    except ValueError | Exception:
        raise NotSupportedError("Invalid SQLAlchemy version: %s" % __version__)


_SQLALCHEMY_MAJOR_VERSION = _check_sqla_major_ver()

if _SQLALCHEMY_MAJOR_VERSION > 2:
    from sqlalchemy.sql.compiler import InsertmanyvaluesSentinelOpts, _InsertManyValues


class DynamoDBJSON(types.JSON):
    """Custom JSON type for DynamoDB that handles SQLAlchemy 1.x compatibility."""

    def result_processor(self, dialect, coltype):
        string_process = self._str_impl.result_processor(dialect, coltype)
        json_deserializer = dialect._json_deserializer or json.loads

        def process(value):
            if value is None:
                return None

            if isinstance(value, dict) or isinstance(value, list):
                return value

            if isinstance(value, str) and _SQLALCHEMY_MAJOR_VERSION < 2:
                value = value.encode("utf-8")

            if string_process:
                value = string_process(value)
            return json_deserializer(value)

        return process


class DynamoDBIdentifierPreparer(IdentifierPreparer):
    reserved_words = RESERVED_WORDS


class DynamoDBDDLCompiler(DDLCompiler):
    def __init__(
        self,
        dialect,
        statement,
        schema_translate_map=None,
        compile_kwargs=None,
    ):
        exc.CompileError("DDL statement is not supported by DDB PartiQL.")


class DynamoDBStatementCompiler(SQLCompiler):
    # DynamoDB can't guarantee the column orders of result
    # _textual_ordered_columns: bool = True
    _ordered_columns: bool = False

    def visit_column(
        self,
        column,
        add_to_result_map=None,
        include_table: bool = True,
        result_map_targets=(),
        ambiguous_table_name_map=None,
        **kwargs,
    ) -> str:
        return super().visit_column(
            column=column,
            add_to_result_map=add_to_result_map,
            include_table=False,
            result_map_targets=result_map_targets,
            ambiguous_table_name_map=ambiguous_table_name_map,
            kwargs=kwargs,
        )

    def visit_label(
        self,
        label,
        add_to_result_map=None,
        within_label_clause=False,
        within_columns_clause=False,
        render_label_as_label=None,
        result_map_targets=(),
        **kw,
    ):
        return super().visit_label(
            label=label,
            add_to_result_map=add_to_result_map,
            within_label_clause=within_label_clause,
            within_columns_clause=False,
            render_label_as_label=render_label_as_label,
            result_map_targets=result_map_targets,
            kw=kw,
        )

    def limit_clause(self, select, **kw):
        if hasattr(select, "_simple_int_clause"):
            limit_clause = select._limit_clause
            if limit_clause is not None and select._simple_int_clause(limit_clause):
                return f" LIMIT {self.process(limit_clause.render_literal_execute(), **kw)}"
        else:
            if select._limit_clause is not None:
                return " LIMIT " + self.process(select._limit_clause, **kw)
        return ""

    def visit_insert(self, insert_stmt, **kw):  # pragma: no cover
        # Compatible design for SQLAlchemy v1 and v2
        if _SQLALCHEMY_MAJOR_VERSION < 2:
            return self._visit_insert_v1(insert_stmt, **kw)
        return self._visit_insert_v2(insert_stmt, None, None, **kw)

    def _visit_insert_v1(self, insert_stmt, **kw):  # pragma: no cover
        compile_state = insert_stmt._compile_state_factory(insert_stmt, self, **kw)
        insert_stmt = compile_state.statement

        toplevel = not self.stack

        if toplevel:
            self.isinsert = True
            if not self.dml_compile_state:
                self.dml_compile_state = compile_state
            if not self.compile_state:
                self.compile_state = compile_state

        self.stack.append(
            {
                "correlate_froms": set(),
                "asfrom_froms": set(),
                "selectable": insert_stmt,
            }
        )

        crud_params = crud._get_crud_params(self, insert_stmt, compile_state, **kw)

        if (
            not crud_params
            and not self.dialect.supports_default_values
            and not self.dialect.supports_default_metavalue
            and not self.dialect.supports_empty_insert
        ):
            raise exc.CompileError(
                "The '%s' dialect with current database "
                "version settings does not support empty "
                "inserts." % self.dialect.name
            )

        preparer = self.preparer

        text = "INSERT "

        if insert_stmt._prefixes:
            text += self._generate_prefixes(insert_stmt, insert_stmt._prefixes, **kw)

        text += "INTO "
        table_text = preparer.format_table(insert_stmt.table)

        if insert_stmt._hints:
            _, table_text = self._setup_crud_hints(insert_stmt, table_text)

        if insert_stmt._independent_ctes:
            for cte in insert_stmt._independent_ctes:
                cte._compiler_dispatch(self, **kw)

        text += table_text

        if self.returning or insert_stmt._returning:
            returning_clause = self.returning_clause(
                insert_stmt, self.returning or insert_stmt._returning
            )

            if self.returning_precedes_values:
                text += " " + returning_clause
        else:
            returning_clause = None

        if insert_stmt.select is not None:
            raise exc.CompileError(
                "The '%s' dialect with current database "
                "version settings does not support "
                "select statement in insert." % self.dialect.name
            )
        else:
            insert_single_values_expr = ", ".join(
                ["'%s': %s" % (expr, value) for c, expr, value in crud_params]
            )
            text += " VALUE {%s}" % insert_single_values_expr
            if toplevel:
                self.insert_single_values_expr = insert_single_values_expr

        if insert_stmt._post_values_clause is not None:
            post_values_clause = self.process(insert_stmt._post_values_clause, **kw)
            if post_values_clause:
                text += " " + post_values_clause

        if returning_clause and not self.returning_precedes_values:
            text += " " + returning_clause

        if self.ctes and not self.dialect.cte_follows_insert:
            nesting_level = len(self.stack) if not toplevel else None
            text = (
                self._render_cte_clause(
                    nesting_level=nesting_level, include_following_stack=True
                )
                + text
            )

        self.stack.pop(-1)

        return text

    def _visit_insert_v2(
        self, insert_stmt, visited_bindparam=None, visiting_cte=None, **kw
    ):  # pragma: no cover
        compile_state = insert_stmt._compile_state_factory(insert_stmt, self, **kw)
        insert_stmt = compile_state.statement

        if visiting_cte is not None:
            kw["visiting_cte"] = visiting_cte
            toplevel = False
        else:
            toplevel = not self.stack

        if toplevel:
            self.isinsert = True
            if not self.dml_compile_state:
                self.dml_compile_state = compile_state
            if not self.compile_state:
                self.compile_state = compile_state

        self.stack.append(
            {
                "correlate_froms": set(),
                "asfrom_froms": set(),
                "selectable": insert_stmt,
            }
        )

        counted_bindparam = 0

        # reset any incoming "visited_bindparam" collection
        visited_bindparam = None

        # for positional, insertmanyvalues needs to know how many
        # bound parameters are in the VALUES sequence; there's no simple
        # rule because default expressions etc. can have zero or more
        # params inside them.   After multiple attempts to figure this out,
        # this very simplistic "count after" works and is
        # likely the least amount of callcounts, though looks clumsy
        if self.positional and visiting_cte is None:
            # if we are inside a CTE, don't count parameters
            # here since they wont be for insertmanyvalues. keep
            # visited_bindparam at None so no counting happens.
            # see #9173
            visited_bindparam = []

        crud_params_struct = crud._get_crud_params(
            self,
            insert_stmt,
            compile_state,
            toplevel,
            visited_bindparam=visited_bindparam,
            **kw,
        )

        if self.positional and visited_bindparam is not None:
            counted_bindparam = len(visited_bindparam)
            if self._numeric_binds:
                if self._values_bindparam is not None:
                    self._values_bindparam += visited_bindparam
                else:
                    self._values_bindparam = visited_bindparam

        crud_params_single = crud_params_struct.single_params

        if (
            not crud_params_single
            and not self.dialect.supports_default_values
            and not self.dialect.supports_default_metavalue
            and not self.dialect.supports_empty_insert
        ):
            raise exc.CompileError(
                "The '%s' dialect with current database "
                "version settings does not support empty "
                "inserts." % self.dialect.name
            )

        if compile_state._has_multi_parameters:
            if not self.dialect.supports_multivalues_insert:
                raise exc.CompileError(
                    "The '%s' dialect with current database "
                    "version settings does not support "
                    "in-place multirow inserts." % self.dialect.name
                )
            elif (
                self.implicit_returning or insert_stmt._returning
            ) and insert_stmt._sort_by_parameter_order:
                raise exc.CompileError(
                    "RETURNING cannot be determinstically sorted when "
                    "using an INSERT which includes multi-row values()."
                )
            crud_params_single = crud_params_struct.single_params
        else:
            crud_params_single = crud_params_struct.single_params

        preparer = self.preparer
        supports_default_values = self.dialect.supports_default_values

        text = "INSERT "

        if insert_stmt._prefixes:
            text += self._generate_prefixes(insert_stmt, insert_stmt._prefixes, **kw)

        text += "INTO "
        table_text = preparer.format_table(insert_stmt.table)

        if insert_stmt._hints:
            _, table_text = self._setup_crud_hints(insert_stmt, table_text)

        if insert_stmt._independent_ctes:
            self._dispatch_independent_ctes(insert_stmt, kw)

        text += table_text

        # look for insertmanyvalues attributes that would have been configured
        # by crud.py as it scanned through the columns to be part of the
        # INSERT
        use_insertmanyvalues = crud_params_struct.use_insertmanyvalues
        named_sentinel_params: Optional[Sequence[str]] = None
        add_sentinel_cols = None
        implicit_sentinel = False

        returning_cols = self.implicit_returning or insert_stmt._returning
        if returning_cols:
            add_sentinel_cols = crud_params_struct.use_sentinel_columns
            if add_sentinel_cols is not None:
                assert use_insertmanyvalues

                # search for the sentinel column explicitly present
                # in the INSERT columns list, and additionally check that
                # this column has a bound parameter name set up that's in the
                # parameter list.  If both of these cases are present, it means
                # we will have a client side value for the sentinel in each
                # parameter set.

                _params_by_col = {
                    col: param_names for col, _, _, param_names in crud_params_single
                }
                named_sentinel_params = []
                for _add_sentinel_col in add_sentinel_cols:
                    if _add_sentinel_col not in _params_by_col:
                        named_sentinel_params = None
                        break
                    param_name = self._within_exec_param_key_getter(_add_sentinel_col)
                    if param_name not in _params_by_col[_add_sentinel_col]:
                        named_sentinel_params = None
                        break
                    named_sentinel_params.append(param_name)

                if named_sentinel_params is None:
                    # if we are not going to have a client side value for
                    # the sentinel in the parameter set, that means it's
                    # an autoincrement, an IDENTITY, or a server-side SQL
                    # expression like nextval('seqname').  So this is
                    # an "implicit" sentinel; we will look for it in
                    # RETURNING
                    # only, and then sort on it.  For this case on PG,
                    # SQL Server we have to use a special INSERT form
                    # that guarantees the server side function lines up with
                    # the entries in the VALUES.
                    if (
                        self.dialect.insertmanyvalues_implicit_sentinel
                        & InsertmanyvaluesSentinelOpts.ANY_AUTOINCREMENT
                    ):
                        implicit_sentinel = True
                    else:
                        # here, we are not using a sentinel at all
                        # and we are likely the SQLite dialect.
                        # The first add_sentinel_col that we have should not
                        # be marked as "insert_sentinel=True".  if it was,
                        # an error should have been raised in
                        # _get_sentinel_column_for_table.
                        assert not add_sentinel_cols[0]._insert_sentinel, (
                            "sentinel selection rules should have prevented "
                            "us from getting here for this dialect"
                        )

                # always put the sentinel columns last.  even if they are
                # in the returning list already, they will be there twice
                # then.
                returning_cols = list(returning_cols) + list(add_sentinel_cols)

            returning_clause = self.returning_clause(
                insert_stmt,
                returning_cols,
                populate_result_map=toplevel,
            )

            if self.returning_precedes_values:
                text += " " + returning_clause

        else:
            returning_clause = None

        if insert_stmt.select is not None:
            # placed here by crud.py
            select_text = self.process(
                self.stack[-1]["insert_from_select"], insert_into=True, **kw
            )

            if self.ctes and self.dialect.cte_follows_insert:
                nesting_level = len(self.stack) if not toplevel else None
                text += " %s%s" % (
                    self._render_cte_clause(
                        nesting_level=nesting_level,
                        include_following_stack=True,
                    ),
                    select_text,
                )
            else:
                text += " %s" % select_text
        elif not crud_params_single and supports_default_values:
            text += " DEFAULT VALUES"
            if use_insertmanyvalues:
                self._insertmanyvalues = _InsertManyValues(
                    True,
                    self.dialect.default_metavalue_token,
                    cast("List[crud._CrudParamElementStr]", crud_params_single),
                    counted_bindparam,
                    sort_by_parameter_order=(insert_stmt._sort_by_parameter_order),
                    includes_upsert_behaviors=(
                        insert_stmt._post_values_clause is not None
                    ),
                    sentinel_columns=add_sentinel_cols,
                    num_sentinel_columns=(
                        len(add_sentinel_cols) if add_sentinel_cols else 0
                    ),
                    implicit_sentinel=implicit_sentinel,
                )
        elif compile_state._has_multi_parameters:
            text += " VALUES %s" % (
                ", ".join(
                    "(%s)" % (", ".join(value for _, _, value, _ in crud_param_set))
                    for crud_param_set in crud_params_struct.all_multi_params
                ),
            )
        else:
            insert_single_values_expr = ", ".join(
                [
                    "'%s': %s" % (expr, value)
                    for _, expr, value, _ in cast(
                        "List[crud._CrudParamElementStr]",
                        crud_params_single,
                    )
                ]
            )

            if use_insertmanyvalues:
                if (
                    implicit_sentinel
                    and (
                        self.dialect.insertmanyvalues_implicit_sentinel
                        & InsertmanyvaluesSentinelOpts.USE_INSERT_FROM_SELECT
                    )
                    # this is checking if we have
                    # INSERT INTO table (id) VALUES (DEFAULT).
                    and not (crud_params_struct.is_default_metavalue_only)
                ):
                    # if we have a sentinel column that is server generated,
                    # then for selected backends render the VALUES list as a
                    # subquery.  This is the orderable form supported by
                    # PostgreSQL and SQL Server.
                    embed_sentinel_value = True

                    render_bind_casts = (
                        self.dialect.insertmanyvalues_implicit_sentinel
                        & InsertmanyvaluesSentinelOpts.RENDER_SELECT_COL_CASTS
                    )

                    colnames = ", ".join(
                        f"p{i}" for i, _ in enumerate(crud_params_single)
                    )

                    if render_bind_casts:
                        # render casts for the SELECT list.  For PG, we are
                        # already rendering bind casts in the parameter list,
                        # selectively for the more "tricky" types like ARRAY.
                        # however, even for the "easy" types, if the parameter
                        # is NULL for every entry, PG gives up and says
                        # "it must be TEXT", which fails for other easy types
                        # like ints.  So we cast on this side too.
                        colnames_w_cast = ", ".join(
                            self.render_bind_cast(
                                col.type,
                                col.type._unwrapped_dialect_impl(self.dialect),
                                f"p{i}",
                            )
                            for i, (col, *_) in enumerate(crud_params_single)
                        )
                    else:
                        colnames_w_cast = colnames

                    text += (
                        f" SELECT {colnames_w_cast} FROM "
                        f"(VALUES ({insert_single_values_expr})) "
                        f"AS imp_sen({colnames}, sen_counter) "
                        "ORDER BY sen_counter"
                    )
                else:
                    # otherwise, if no sentinel or backend doesn't support
                    # orderable subquery form, use a plain VALUES list
                    embed_sentinel_value = False
                    text += f" VALUE {{{insert_single_values_expr}}}"

                self._insertmanyvalues = _InsertManyValues(
                    is_default_expr=False,
                    single_values_expr=insert_single_values_expr,
                    insert_crud_params=cast(
                        "List[crud._CrudParamElementStr]",
                        crud_params_single,
                    ),
                    num_positional_params_counted=counted_bindparam,
                    sort_by_parameter_order=(insert_stmt._sort_by_parameter_order),
                    includes_upsert_behaviors=(
                        insert_stmt._post_values_clause is not None
                    ),
                    sentinel_columns=add_sentinel_cols,
                    num_sentinel_columns=(
                        len(add_sentinel_cols) if add_sentinel_cols else 0
                    ),
                    sentinel_param_keys=named_sentinel_params,
                    implicit_sentinel=implicit_sentinel,
                    embed_values_counter=embed_sentinel_value,
                )

            else:
                text += f" VALUE {{{insert_single_values_expr}}}"

        if insert_stmt._post_values_clause is not None:
            post_values_clause = self.process(insert_stmt._post_values_clause, **kw)
            if post_values_clause:
                text += " " + post_values_clause

        if returning_clause and not self.returning_precedes_values:
            text += " " + returning_clause

        if self.ctes and not self.dialect.cte_follows_insert:
            nesting_level = len(self.stack) if not toplevel else None
            text = (
                self._render_cte_clause(
                    nesting_level=nesting_level,
                    include_following_stack=True,
                )
                + text
            )

        self.stack.pop(-1)

        return text

    def visit_update(self, update_stmt, **kw):
        return super().visit_update(update_stmt, **kw)

    def visit_delete(self, delete_stmt, **kw):
        return super().visit_delete(delete_stmt, **kw)


class DynamoDBTypeCompiler(GenericTypeCompiler):

    def visit_FLOAT(self, type_, **kw):
        return self.visit_REAL(type_, **kw)

    def visit_REAL(self, type_, **kw):
        return "DOUBLE"

    def visit_NUMERIC(self, type_, **kw):
        return self.visit_REAL(type_, **kw)

    def visit_DECIMAL(self, type_, **kw):
        return self.visit_REAL(type_, **kw)

    def visit_INTEGER(self, type_, **kw):
        return "INTEGER"

    def visit_SMALLINT(self, type_, **kw):
        return "INTEGER"

    def visit_BIGINT(self, type_, **kw):
        return "INTEGER"

    def visit_CLOB(self, type_, **kw):
        return self.visit_BINARY(type_, **kw)

    def visit_NCLOB(self, type_, **kw):
        return self.visit_BINARY(type_, **kw)

    def visit_JSON(self, type_, **kw):
        return "JSON"


class DynamoDBDialect(DefaultDialect):
    name = "dynamodb"
    driver = ""
    preparer = DynamoDBIdentifierPreparer
    statement_compiler = DynamoDBStatementCompiler
    ddl_compiler = DynamoDBDDLCompiler
    type_compiler = DynamoDBTypeCompiler
    default_paramstyle = pydynamodb.paramstyle
    supports_sane_rowcount = False
    supports_alter = False
    supports_pk_autoincrement = False
    supports_default_values = False
    supports_empty_insert = False
    supports_multivalues_insert = False
    supports_native_decimal = False
    supports_native_boolean = True
    supports_unicode_statements = True
    supports_unicode_binds = True
    supports_statement_cache = True
    returns_unicode_strings = True
    description_encoding = None
    postfetch_lastrowid = False

    # Custom type mapping for SQLAlchemy compatibility
    colspecs = {
        types.JSON: DynamoDBJSON,
    }

    _connect_options = {}  # type: ignore

    def __init__(
        self,
        json_serializer=None,
        json_deserializer=None,
        _json_serializer=None,
        _json_deserializer=None,
        **kwargs,
    ):
        DefaultDialect.__init__(self, **kwargs)
        if _json_serializer:
            json_serializer = _json_serializer
        if _json_deserializer:
            json_deserializer = _json_deserializer
        self._json_serializer = json_serializer
        self._json_deserializer = json_deserializer

    @classmethod
    def dbapi(cls):
        return pydynamodb

    @classmethod
    def import_dbapi(cls) -> "ModuleType":
        return pydynamodb

    def _raw_connection(self, connection):
        if isinstance(connection, Engine):
            return connection.raw_connection()
        return connection.connection

    def create_connect_args(self, url):
        # Connection string format:
        #   dynamodb://
        #   {aws_access_key_id}:{aws_secret_access_key}@dynamodb.{region_name}.amazonaws.com:443
        #   ?verify=false&...
        self._connect_options = self._create_connect_args(url)
        return [[], self._connect_options]

    def _create_connect_args(self, url):
        opts = {
            "aws_access_key_id": url.username if url.username else None,
            "aws_secret_access_key": url.password if url.password else None,
            "region_name": re.sub(
                r"^dynamodb\.([a-z0-9-]+)\.amazonaws\.(com|com.cn)$", r"\1", url.host
            ),
            "schema_name": url.database if url.database else "default",
        }
        opts.update(url.query)
        if "verify" in opts:
            verify = opts["verify"]
            try:
                verify = bool(strtobool(verify))
            except ValueError:
                # Probably a file name of the CA cert bundle to use
                pass
            opts.update({"verify": verify})

        return opts

    def do_ping(self, dbapi_connection):
        connection = dbapi_connection

        for attr_name in ("driver_connection", "dbapi_connection", "connection"):
            nested_connection = getattr(connection, attr_name, None)
            if nested_connection is not None:
                connection = nested_connection
                break

        test_connection = getattr(connection, "test_connection", None)
        if not callable(test_connection):
            return False

        try:
            return bool(test_connection())
        except Exception:
            return False

    def get_schema_names(self, connection, **kw):
        # DynamoDB does not have the concept of a schema
        return ["default"]

    @reflection.cache
    def _get_tables(self, connection, schema=None, **kw):
        raw_connection = self._raw_connection(connection)
        with raw_connection.driver_connection.cursor() as cursor:
            return cursor.list_tables()

    def _get_column_type(self, metadata, attribute_name) -> str:
        col_type = types.NullType

        for attr in metadata["AttributeDefinitions"]:
            if attr["AttributeName"] == attribute_name:
                type_ = attr["AttributeType"]
                if type_ == "S":
                    col_type = types.String
                elif type_ == "N":
                    col_type = types.Numeric
                elif type_ == "B":
                    col_type = types.BINARY
                else:
                    util.warn(f"Did not recognize type '{type_}'")
                    col_type = types.NullType
        return col_type()

    def has_table(self, connection, table_name, schema=None, **kw):
        try:
            columns = self.get_columns(connection, table_name, schema)
            return True if columns else False
        except exc.NoSuchTableError:
            return False

    @reflection.cache
    def get_columns(self, connection, table_name, schema=None, **kw):
        raw_connection = self._raw_connection(connection)
        with raw_connection.driver_connection.cursor() as cursor:
            try:
                metadata_ = cursor.get_table_metadata(table_name)

                columns = [
                    {
                        "name": c["AttributeName"],
                        "type": self._get_column_type(metadata_, c["AttributeName"]),
                        "nullable": False,
                        "default": None,
                        "autoincrement": False,
                        "comment": None,
                        "dialect_options": {},
                    }
                    for c in metadata_["KeySchema"]
                ]

                return columns
            except OperationalError as e:
                cause = e.__cause__
                if (
                    isinstance(cause, botocore.exceptions.ClientError)
                    and cause.response["Error"]["Code"] == "ResourceNotFoundException"
                ):
                    raise exc.NoSuchTableError(table_name) from e
                raise

    def get_table_names(self, connection, schema=None, **kw):
        return self._get_tables(connection, schema, **kw)

    def get_view_names(self, connection, schema=None, **kw):
        return []

    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        # DynamoDB has no support for foreign keys.
        return []  # pragma: no cover

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        # DynamoDB has no support for primary keys.
        return []  # pragma: no cover

    def get_indexes(self, connection, table_name, schema=None, **kw):
        # DynamoDB has no support for indexes.
        return []  # pragma: no cover

    def do_rollback(self, dbapi_connection):
        # No transactions for DynamoDB
        pass  # pragma: no cover

    def _check_unicode_returns(self, connection, additional_tests=None):
        # Requests gives back Unicode strings
        return True  # pragma: no cover

    def _check_unicode_description(self, connection):
        # Requests gives back Unicode strings
        return True  # pragma: no cover


class DynamoDBRestDialect(DynamoDBDialect):
    driver = "rest"
    supports_statement_cache = True
