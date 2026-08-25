# -*- coding: utf-8 -*-
import logging
import json
from datetime import datetime
from abc import ABCMeta, abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional, Tuple, cast

from .sql.common import DdbDataTypes, DataTypes, Functions, QueryType
from .sql.parser import SQLParser
from .converter import Converter
from .model import Metadata, ColumnInfo, Statements
from .error import OperationalError, DataError
from .util import RetryConfig, retry_api_call

if TYPE_CHECKING:
    from .connection import Connection

_logger = logging.getLogger(__name__)  # type: ignore


class BaseExecutor(metaclass=ABCMeta):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        self._connection: Optional["Connection"] = connection
        self._converter = converter
        self._statements = statements
        assert (
            self._statements and len(self._statements) > 0
        ), "Required statements not found."

        self._retry_config = retry_config
        self._next_token: Optional[str] = None
        self._metadata: Metadata = Metadata()
        self._is_predef_metadata: bool = False
        self._rows: Deque[Tuple[Any]] = deque()
        self._errors: List[Dict[str, str]] = []
        self._kwargs = kwargs
        self.pre_execute()

    @property
    def connection(self) -> "Connection":
        return self._connection

    @property
    def next_token(self) -> Optional[str]:
        return self._next_token

    @property
    def metadata(self) -> Metadata:
        return self._metadata

    @property
    def rows(self) -> Deque[Dict[str, Optional[Any]]]:
        return self._rows

    @property
    def errors(self) -> List[Dict[str, str]]:
        return self._errors

    def pre_execute(self) -> None:
        self.execute()

    @abstractmethod
    def execute(self) -> None:
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def process_rows(self, response: Dict[str, Any]) -> None:
        raise NotImplementedError  # pragma: no cover

    def post_execute(self):
        pass  # pragma: no cover

    def _dispatch_api_call(
        self, api_call_func, request: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            response = retry_api_call(
                api_call_func,
                config=self._retry_config,
                logger=_logger,
                **request,
            )
        except Exception as e:
            _logger.exception("Failed to execute statement.")
            raise OperationalError(*e.args) from e
        else:
            return cast(Dict[str, Any], response)

    def close(self) -> None:
        self._metadata = None
        self._rows = self._rows.clear()
        self._errors = self._errors.clear()
        self._next_token = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def dispatch_executor(
    connection: "Connection",
    converter: Converter,
    statements: Statements,
    retry_config: RetryConfig,
    is_transaction: bool = False,
    executor_class: BaseExecutor = None,
    **kwargs,
) -> Optional[BaseExecutor]:
    if statements is None or len(statements) == 0:
        return None

    _executor_class = (
        _get_executor_class(statements, is_transaction)
        if executor_class is None
        else executor_class
    )

    return _executor_class(connection, converter, statements, retry_config, **kwargs)


def _get_executor_class(statements: Statements, is_transaction: bool):
    if statements.query_type[0] == "DML":
        return _get_dml_executor_class(statements, is_transaction)
    elif statements.query_type == QueryType.CREATE:
        return DdlCreateExecutor
    elif statements.query_type == QueryType.ALTER:
        return DdlAlterExecutor
    elif statements.query_type == QueryType.DROP:
        return DdlDropExecutor
    elif statements.query_type == QueryType.LIST:
        return UtilListTablesExecutor
    elif statements.query_type == QueryType.DESC:
        return UtilDescTableExecutor
    elif statements.query_type == QueryType.CREATE_GLOBAL:
        return DdlCreateGlobalExecutor
    elif statements.query_type == QueryType.DROP_GLOBAL:
        return DdlDropGlobalExecutor
    elif statements.query_type == QueryType.LIST_GLOBAL:
        return UtilListGlobalTablesExecutor
    elif statements.query_type == QueryType.DESC_GLOBAL:
        return UtilDescGlobalTableExecutor
    else:
        raise LookupError(
            "Not support executor for query type: %s" % str(statements.query_type)
        )


def _get_dml_executor_class(statements: Statements, is_transaction: bool):
    if len(statements) > 1:
        if is_transaction:
            return DmlTransactionExecutor
        else:
            return DmlBatchExecutor
    else:
        return DmlStatementExecutor


class DmlStatementExecutor(BaseExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        self._statement = statements[0]
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        request = self._statement.api_request

        if self.next_token:
            request.update({"NextToken": self.next_token})

        response = self._dispatch_api_call(
            self.connection.client.execute_statement, request
        )

        try:
            self.process_rows(response)
        finally:
            self.post_execute()

    def process_rows(self, response: Dict[str, Any]) -> None:
        self._process_predef_metadata(self._statement.sql_parser)

        rows = response.get("Items", None)
        if rows is None:
            raise DataError("KeyError `Items`")

        processed_rows = []
        for row in rows:
            if self._is_predef_metadata:
                row_ = self._process_predef_row_item(row)
            else:
                row_ = self._process_undef_row_item(row)
            processed_rows.append(row_)

        self._rows.extend(processed_rows)
        self._next_token = response.get("NextToken", None)

    def _process_undef_row_item(self, row) -> Optional[Tuple]:
        row_ = {}
        for col, val in row.items():
            type_ = next(iter(val.keys()))
            val_ = self._converter.deserialize(val)
            col_index = self._process_metadata(col, type_)
            row_[col_index] = val_

        row__ = []
        for i in range(len(self._metadata)):
            row__.append(None)
        for i, v in row_.items():
            row__[i] = v

        return tuple(row__)

    def _process_metadata(self, col_name: str, type: str) -> int:
        type_ = DataTypes.STRING
        if type == DdbDataTypes.NULL or type == DdbDataTypes.BOOLEAN:
            type_ = DataTypes.BOOL
        elif type == DdbDataTypes.NUMBER:
            type_ = DataTypes.NUMBER

        if col_name not in self._metadata:
            self._metadata.update(ColumnInfo(col_name, col_name, type_code=type_))

        return self._metadata.index(col_name)

    def _process_predef_row_item(self, row) -> Optional[Tuple]:
        row_ = [None for _ in range(len(self.metadata))]
        for col, val in row.items():
            col_info = self.metadata.get(col, None)
            if col_info:
                if col_info.function:
                    val_ = self._converter.deserialize(
                        val,
                        function=col_info.function.name,
                        function_params=col_info.function.params,
                    )
                else:
                    val_ = self._converter.deserialize(val)
                index = self.metadata.index(col)
                row_[index] = val_

        return tuple(row_)

    def _process_predef_metadata(self, sql_parser: SQLParser) -> None:
        if sql_parser.query_type == QueryType.SELECT:
            if not sql_parser.parser.is_star_column:
                self._collect_column_info(sql_parser.parser.columns)
                self._is_predef_metadata = True
        else:
            self._is_predef_metadata = False

    def _collect_column_info(self, columns: List[Optional[Any]]) -> None:
        for column in columns:
            type_ = DataTypes.STRING
            if column.function is not None:
                function_name = column.function.name
                if (
                    function_name
                    in Functions.SUPPORTED_FUNTIONS[Functions.TYPE_CONVERSION]
                ):
                    type_ = function_name

            self._metadata.update(
                ColumnInfo(
                    column.result_name,
                    column.request_name,
                    column.alias,
                    function=column.function,
                    type_code=type_,
                )
            )


class DmlStatementDictExecutor(DmlStatementExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def _process_undef_row_item(self, row) -> Optional[Dict[str, Any]]:
        row_ = {}
        for col, val in row.items():
            val_ = self._converter.deserialize(val)
            row_[col] = val_

        return row_

    def _process_predef_row_item(self, row) -> Optional[Dict[str, Any]]:
        row_ = {}
        for col, val in row.items():
            col_info = self.metadata.get(col, None)
            if col_info:
                if col_info.function:
                    val_ = self._converter.deserialize(
                        val,
                        function=col_info.function.name,
                        function_params=col_info.function.params,
                    )
                else:
                    val_ = self._converter.deserialize(val)

                col_name_ = col if col_info.alias is None else col_info.alias
                row_[col_name_] = val_

        return row_


class DmlBatchExecutor(DmlStatementExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        request = {
            "Statements": [statement_.api_request for statement_ in self._statements]
        }

        response = self._dispatch_api_call(
            self.connection.client.batch_execute_statement, request
        )
        self.process_rows(response)
        self.post_execute()

    def process_rows(self, response: Dict[str, Any]) -> None:
        rows = response.get("Responses", None)
        if rows is None:
            raise DataError("KeyError `Responses` in BatchStatementResponse")

        processed_error_rows = []
        processed_rows = []
        for row in rows:
            error = row.get("Error", None)
            if error:
                processed_error_rows.append(
                    {
                        error.get("Code"): error.get("Message"),
                    }
                )
                continue

            item = row.get("Item", None)
            if item:
                row_ = self._process_undef_row_item(item)
                processed_rows.append(row_)

        self._errors.extend(processed_error_rows)
        self._rows.extend(processed_rows)
        self._next_token = response.get("NextToken", None)


class DmlTransactionExecutor(DmlBatchExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        request = {
            "TransactStatements": [
                statement_.api_request for statement_ in self._statements
            ]
        }

        if self.next_token:
            request.update({"ClientRequestToken": self.next_token})

        response = self._dispatch_api_call(
            self.connection.client.execute_transaction, request
        )
        self.process_rows(response)
        self.post_execute()


class DdlExecutor(BaseExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def process_rows(self, response: Dict[str, Any]) -> None:
        self.rows.extend(
            (k, json.dumps(v, default=self._handle_conversion))
            for k, v in response.items()
        )
        self._metadata.update(ColumnInfo("response_name", "response_name"))
        self._metadata.update(ColumnInfo("response_value", "response_value"))

    def _handle_conversion(self, val: Any) -> str:
        if isinstance(val, datetime):
            return str(val)
        else:
            return val


class DdlCreateExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(self.connection.client.create_table, request)
        self.process_rows(response)
        self.post_execute()


class DdlAlterExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(self.connection.client.update_table, request)
        self.process_rows(response)
        self.post_execute()


class DdlDropExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(self.connection.client.delete_table, request)
        self.process_rows(response)
        self.post_execute()


class DdlCreateGlobalExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(
            self.connection.client.create_global_table, request
        )
        self.process_rows(response)
        self.post_execute()


class DdlDropGlobalExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(
            self.connection.client.update_global_table, request
        )
        self.process_rows(response)
        self.post_execute()


class UtilListTablesExecutor(BaseExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        if self.next_token:
            request.update({"ExclusiveStartTableName": self.next_token})

        response = self._dispatch_api_call(self.connection.client.list_tables, request)
        self.process_rows(response)
        self.post_execute()

    def process_rows(self, response: Dict[str, Any]) -> None:
        tables = response.get("TableNames", None)
        if tables is None:
            raise DataError("KeyError `TableNames`")

        self._rows.extend((t) for t in tables)
        self._next_token = response.get("LastEvaluatedTableName", None)
        self._metadata.update(ColumnInfo("table_name", "table_name"))


class UtilDescTableExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(
            self.connection.client.describe_table, request
        )
        self.process_rows(response)
        self.post_execute()


class UtilListGlobalTablesExecutor(BaseExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        if self.next_token:
            request.update({"ExclusiveStartGlobalTableName": self.next_token})

        response = self._dispatch_api_call(
            self.connection.client.list_global_tables, request
        )
        self.process_rows(response)
        self.post_execute()

    def process_rows(self, response: Dict[str, Any]) -> None:
        tables = response.get("GlobalTables", None)
        if tables is None:
            raise DataError("KeyError `GlobalTables`")

        for table in tables:
            table_name = table["GlobalTableName"]
            regions = ",".join([r["RegionName"] for r in table["ReplicationGroup"]])
            self._rows.append((table_name, regions))

        self._next_token = response.get("LastEvaluatedGlobalTableName", None)
        self._metadata.update(ColumnInfo("table_name", "table_name"))
        self._metadata.update(ColumnInfo("region_names", "region_names"))


class UtilDescGlobalTableExecutor(DdlExecutor):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        retry_config: RetryConfig,
        **kwargs,
    ) -> None:
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            retry_config=retry_config,
            **kwargs,
        )

    def execute(self) -> None:
        statement_ = self._statements[0]
        request = statement_.api_request

        response = self._dispatch_api_call(
            self.connection.client.describe_global_table, request
        )
        self.process_rows(response)
