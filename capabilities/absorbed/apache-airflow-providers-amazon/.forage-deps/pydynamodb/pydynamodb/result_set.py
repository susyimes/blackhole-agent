# -*- coding: utf-8 -*-
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

from .converter import Converter
from .common import CursorIterator
from .model import Statements, Metadata
from .executor import BaseExecutor, dispatch_executor
from .executor import DmlStatementDictExecutor
from .error import ProgrammingError
from .util import RetryConfig

if TYPE_CHECKING:
    from .connection import Connection

_logger = logging.getLogger(__name__)  # type: ignore


class DynamoDBResultSet(CursorIterator):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        arraysize: int,
        retry_config: RetryConfig,
        is_transaction: bool = False,
        executor_class: BaseExecutor = None,
        **kwargs
    ) -> None:
        super().__init__(arraysize=arraysize)
        assert statements and len(statements) > 0, "Required statements not found."
        self._connection: Optional["Connection"] = connection
        self._arraysize = arraysize
        self._statements = statements
        self._executor = dispatch_executor(
            connection,
            converter,
            statements,
            retry_config,
            is_transaction,
            executor_class=executor_class,
            **kwargs
        )
        assert self._executor is not None, "Executor is not specified"

    @property
    def connection(self) -> "Connection":
        if self.is_closed:
            raise ProgrammingError("DynamoDBResultSet is closed.")
        return cast("Connection", self._connection)

    @property
    def errors(self) -> List[Dict[str, str]]:
        return self._executor.errors

    @property
    def metadata(self) -> Optional[Metadata]:
        return self._executor.metadata

    @property
    def rowcount(self) -> int:
        return len(self._executor.rows)

    @property
    def description(
        self,
    ) -> Optional[List[Tuple[str, str, None, None, None, None, None]]]:
        if self._executor.metadata is None:
            return None
        return [
            (
                (
                    column_info.alias
                    if column_info.alias is not None
                    else column_info.name
                ),
                column_info.type_code,
                None,
                None,
                None,
                None,
                None,
            )
            for column_info in self._executor.metadata
        ]

    def fetchone(
        self,
    ) -> Optional[Dict[Any, Optional[Any]]]:
        limit_ = self._statements.limit
        while len(self._executor.rows) == 0 and self._executor.next_token:
            if not limit_ or (limit_ and self._rownumber < limit_):
                self._executor.execute()
            else:
                break
        if not self._executor.rows:
            return None
        else:
            if self._rownumber is None:
                self._rownumber = 0
            if limit_ and self._rownumber >= limit_:
                self._executor.rows.clear()
                return None
            row = self._executor.rows.popleft()
            self._rownumber += 1
            return row

    def fetchmany(self, size: Optional[int] = None) -> List[Dict[Any, Optional[Any]]]:
        if not size or size <= 0:
            size = self._arraysize
        rows = []
        for _ in range(size):
            row = self.fetchone()
            if row:
                rows.append(row)
            else:
                break
        return rows

    def fetchall(self) -> List[Dict[Any, Optional[Any]]]:
        rows = []
        while True:
            row = self.fetchone()
            if row:
                rows.append(row)
            else:
                break
        return rows

    @property
    def is_closed(self) -> bool:
        return self._connection is None

    def close(self) -> None:
        self._connection = None
        self._executor = None
        self._rownumber = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class DynamoDBDictResultSet(DynamoDBResultSet):
    def __init__(
        self,
        connection: "Connection",
        converter: Converter,
        statements: Statements,
        arraysize: int,
        retry_config: RetryConfig,
        is_transaction: bool = False,
        executor_class: BaseExecutor = None,
        **kwargs
    ) -> None:
        assert (
            statements.query_type[0] == "DML" and len(statements) == 1
        ), "DictExecutor can only support single DML statement"
        super().__init__(
            connection=connection,
            converter=converter,
            statements=statements,
            arraysize=arraysize,
            retry_config=retry_config,
            is_transaction=is_transaction,
            executor_class=DmlStatementDictExecutor,
            **kwargs
        )
