# -*- coding: utf-8 -*-
import logging
import ast
from .sql.common import Functions
from datetime import datetime, date
from abc import ABCMeta, abstractmethod
from typing import Any, Callable, Dict, Optional, Set, List, Union, Type

_logger = logging.getLogger(__name__)  # type: ignore


class Serializer(metaclass=ABCMeta):
    def __init__(
        self,
        mapping: Optional[Dict[Any, Callable[[Optional[str]], Optional[Any]]]] = None,
    ) -> None:
        if mapping is None:
            self._mapping = self.get_default_converters()
        else:
            self._mapping = mapping

    @property
    def mapping(self) -> Dict[str, Callable[[Optional[str]], Optional[Any]]]:
        return self._mapping

    def _to_string(self, value: Optional[str], **kwargs) -> Optional[Dict[str, str]]:
        if value is None:
            return None
        return {"S": value}

    def _to_number(
        self, value: Optional[Union[int, float]], **kwargs
    ) -> Optional[Dict[str, str]]:
        if value is None:
            return None
        return {"N": str(value)}

    def _to_binary(self, value: Optional[bytes], **kwargs) -> Optional[Dict[str, str]]:
        if value is None:
            return None
        return {"B": value.decode()}

    def _to_set(
        self, value: Optional[Set[Any]], **kwargs
    ) -> Optional[Dict[str, List[str]]]:
        if value is None:
            return None

        value_ = next(iter(value))
        if isinstance(value_, type(1)) or isinstance(value_, type(1.0)):
            return {"NS": [str(v) for v in value]}
        elif isinstance(value_, type(b"")):
            return {"BS": [v.decode() for v in value]}
        else:
            return {"SS": [v for v in value]}

    def _to_map(
        self, value: Optional[Dict[str, Any]], **kwargs
    ) -> Optional[Dict[str, Any]]:
        if value is None:
            return None

        converted_ = {}
        for k, v in value.items():
            type_ = type(v)
            converted_[k] = self._mapping.get(type_, None)(v)
        return {"M": converted_}

    def _to_list(
        self, value: Optional[List[Any]], **kwargs
    ) -> Optional[Dict[str, Any]]:
        if value is None:
            return None

        converted_ = []
        for v in value:
            type_ = type(v)
            converted_.append(self._mapping.get(type_, None)(v))
        return {"L": converted_}

    def _to_null(self, value: Optional[Any], **kwargs) -> Optional[Dict[str, Any]]:
        return {"NULL": False if value else True}

    def _to_bool(self, value: Optional[bool], **kwargs) -> Optional[Dict[str, Any]]:
        return {"BOOL": value}

    def _to_datetime(
        self, value: Optional[Union[datetime, date]], **kwargs
    ) -> Optional[Dict[str, str]]:
        if value is None:
            return None

        return {"S": value.isoformat()}

    def _to_default(self, value: Optional[Any], **kwargs) -> Optional[Dict[str, Any]]:
        return {"S": str(value)}

    def get(self, type_: Type) -> Callable[[Optional[str]], Optional[Any]]:
        return self._mapping.get(type_, self._to_default)

    def get_default_converters(
        self,
    ) -> Dict[Type[Any], Callable[[Optional[str]], Optional[Any]]]:
        return {
            str: self._to_string,
            int: self._to_number,
            float: self._to_number,
            bytes: self._to_binary,
            set: self._to_set,
            dict: self._to_map,
            list: self._to_list,
            type(None): self._to_null,
            bool: self._to_bool,
            datetime: self._to_datetime,
            date: self._to_datetime,
        }


class Deserializer(metaclass=ABCMeta):
    def __init__(
        self,
        mapping: Optional[Dict[Any, Callable[[Optional[str]], Optional[Any]]]] = None,
    ) -> None:
        if mapping is None:
            self._mapping = self.get_default_converters()
        else:
            self._mapping = mapping

    @property
    def mapping(self) -> Dict[str, Callable[[Optional[str]], Optional[Any]]]:
        return self._mapping

    def _to_string(self, value: Optional[Any], **kwargs) -> Optional[Any]:
        function_ = kwargs.get("function", None)

        if function_ == Functions.DATE:
            return self._to_date(value, **kwargs)
        elif function_ == Functions.DATETIME:
            return self._to_datetime(value, **kwargs)
        elif function_ == Functions.SUBSTR or function_ == Functions.SUBSTRING:
            return self._to_substr(value, **kwargs)
        elif function_ == Functions.TRIM:
            return value.strip()
        elif function_ == Functions.LTRIM:
            return value.lstrip()
        elif function_ == Functions.RTRIM:
            return value.rstrip()
        elif function_ == Functions.UPPER:
            return value.upper()
        elif function_ == Functions.LOWER:
            return value.lower()
        elif function_ == Functions.REPLACE:
            return self._to_replace(value, **kwargs)
        else:
            return value

    def _to_date(self, value: Optional[Any], **kwargs) -> Optional[datetime]:
        function_params_ = kwargs.get("function_params", None)
        if function_params_ is None or len(function_params_) == 0:
            return date.fromisoformat(value)
        else:
            return datetime.strptime(value, function_params_[0]).date()

    def _to_datetime(self, value: Optional[Any], **kwargs) -> Optional[datetime]:
        function_params_ = kwargs.get("function_params", None)
        if function_params_ is None or len(function_params_) == 0:
            return datetime.fromisoformat(value)
        else:
            return datetime.strptime(value, function_params_[0])

    def _to_number(self, value: Optional[str], **kwargs) -> Optional[Union[int, float]]:
        if value is None:
            return None
        return ast.literal_eval(value)

    def _to_binary(self, value: Optional[str], **kwargs) -> Optional[bytes]:
        if value is None:
            return None
        return value

    def _to_string_set(
        self, value: Optional[List[str]], **kwargs
    ) -> Optional[Set[str]]:
        if value is None:
            return None
        return set([v for v in value])

    def _to_number_set(
        self, value: Optional[List[str]], **kwargs
    ) -> Optional[Set[float]]:
        if value is None:
            return None
        return set([float(v) for v in value])

    def _to_binary_set(
        self, value: Optional[List[str]], **kwargs
    ) -> Optional[Set[bytes]]:
        return self._to_string_set(value)

    def _to_map(
        self, value: Optional[Dict[str, Any]], **kwargs
    ) -> Optional[Dict[str, Any]]:
        if value is None:
            return None

        converted_ = {}
        for k, v in value.items():
            type_, value_ = next(iter(v.items()))
            converted_[k] = self._mapping.get(type_, None)(value_)
        return converted_

    def _to_list(self, value: Optional[List[Any]], **kwargs) -> Optional[List[Any]]:
        if value is None:
            return None

        coverted_ = []
        for v in value:
            type_, value_ = next(iter(v.items()))
            coverted_.append(self._mapping.get(type_, None)(value_))
        return coverted_

    def _to_null(self, value: Optional[bool], **kwargs) -> Optional[bool]:
        return None

    def _to_bool(self, value: Optional[bool], **kwargs) -> Optional[bool]:
        return value

    def _to_substr(self, value: Optional[str], **kwargs) -> Optional[str]:
        function_params_ = kwargs.get("function_params", None)
        if function_params_ is None or len(function_params_) == 0:
            return value
        elif len(function_params_) == 1:
            start = int(function_params_[0])
            return value[start:]
        else:
            start = int(function_params_[0])
            length = int(function_params_[1])
            end = start + length if start + length < len(value) else len(value)
            return value[start:end]

    def _to_replace(self, value: Optional[str], **kwargs) -> Optional[str]:
        function_params_ = kwargs.get("function_params", None)
        if function_params_ is None or len(function_params_) == 0:
            return value
        elif len(function_params_) == 1:
            return value.replace(function_params_[0], "")
        else:
            return value.replace(function_params_[0], function_params_[1])

    def _to_default(self, value: Optional[Any], **kwargs) -> Optional[str]:
        return value

    def get(self, type_: str) -> Callable[[Optional[str]], Optional[Any]]:
        return self._mapping.get(type_, self._to_default)

    def get_default_converters(
        self,
    ) -> Dict[Any, Callable[[Optional[str]], Optional[Any]]]:
        return {
            "S": self._to_string,
            "N": self._to_number,
            "B": self._to_binary,
            "SS": self._to_string_set,
            "NS": self._to_number_set,
            "BS": self._to_binary_set,
            "M": self._to_map,
            "L": self._to_list,
            "NULL": self._to_null,
            "BOOL": self._to_bool,
        }


class Converter(metaclass=ABCMeta):
    def __init__(
        self,
        serializer: Serializer,
        deserializer: Deserializer,
    ) -> None:
        self._serializer = serializer
        self._deserializer = deserializer

    @property
    def serializer(self) -> Serializer:
        return self._serializer

    @property
    def deserializer(self) -> Deserializer:
        return self._deserializer

    def get_serialize_converter(
        self, type_: str
    ) -> Callable[[Optional[str]], Optional[Any]]:
        return self._serializer.get(type_)

    def get_deserialize_converter(
        self, type_: str
    ) -> Callable[[Optional[str]], Optional[Any]]:
        return self._deserializer.get(type_)

    @abstractmethod
    def serialize(self, value: Optional[Any], **kwargs) -> Optional[Any]:
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def deserialize(self, value: Optional[Any], **kwargs) -> Optional[Any]:
        raise NotImplementedError  # pragma: no cover


class DefaultTypeConverter(Converter):
    def __init__(self) -> None:
        super().__init__(
            serializer=Serializer(),
            deserializer=Deserializer(),
        )

    def serialize(self, value: Optional[Any], **kwargs) -> Optional[Any]:
        type_ = type(value)
        converter = self.get_serialize_converter(type_)
        return converter(value, **kwargs)

    def deserialize(self, value: Optional[Any], **kwargs) -> Optional[Any]:
        type_, value_ = next(iter(value.items()))
        converter = self.get_deserialize_converter(type_)
        return converter(value_, **kwargs)
