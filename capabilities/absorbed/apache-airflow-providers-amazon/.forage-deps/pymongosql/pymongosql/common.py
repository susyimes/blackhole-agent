# -*- coding: utf-8 -*-
import logging
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

from .error import ProgrammingError

if TYPE_CHECKING:
    from .connection import Connection

_logger = logging.getLogger(__name__)  # type: ignore


class BaseCursor(metaclass=ABCMeta):
    DEFAULT_LIST_TABLES_LIMIT_SIZE: int = 100

    def __init__(
        self,
        connection: "Connection",
        mode: str = "standard",
        **kwargs,
    ) -> None:
        super().__init__()
        self._connection = connection
        self.mode = mode

    @property
    def connection(self) -> "Connection":
        return self._connection

    @property
    def description(
        self,
    ) -> Optional[List[Tuple[str, str, None, None, None, None, None]]]:
        return None

    @abstractmethod
    def execute(
        self,
        operation: str,
        parameters: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    ):
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def executemany(self, operation: str, seq_of_parameters: List[Union[Sequence[Any], Dict[str, Any]]]) -> None:
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError  # pragma: no cover

    def setinputsizes(self, sizes):
        """Does nothing by default"""
        pass

    def setoutputsize(self, size, column=None):
        """Does nothing by default"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class CursorIterator(metaclass=ABCMeta):
    DEFAULT_FETCH_SIZE: int = 1000

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.arraysize: int = kwargs.get("arraysize", self.DEFAULT_FETCH_SIZE)
        self._rownumber: Optional[int] = 0

    @property
    def arraysize(self) -> int:
        return self._arraysize

    @arraysize.setter
    def arraysize(self, value: int) -> None:
        if value <= 0:
            raise ValueError("arraysize must be positive")
        if value > self.DEFAULT_FETCH_SIZE:
            raise ProgrammingError(f"MaxResults is more than maximum allowed length {self.DEFAULT_FETCH_SIZE}.")
        self._arraysize = value

    @property
    def rownumber(self) -> Optional[int]:
        return self._rownumber

    @property
    def rowcount(self) -> int:
        """By default, return -1 to indicate that this is not supported."""
        return -1

    @abstractmethod
    def fetchone(self):
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def fetchmany(self):
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def fetchall(self):
        raise NotImplementedError  # pragma: no cover

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        else:
            return row

    def __iter__(self):
        return self
