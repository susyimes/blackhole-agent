# -*- coding: utf-8 -*-
import logging
import time
from boto3.session import Session
from botocore.config import Config
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from .converter import Converter
from .cursor import BaseCursor, Cursor
from .error import NotSupportedError
from .util import RetryConfig, retry_api_call

if TYPE_CHECKING:
    from botocore.client import BaseClient

_logger = logging.getLogger(__name__)


class Connection:
    _SESSION_PASSING_ARGS: List[str] = [
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "region_name",
        "botocore_session",
        "profile_name",
    ]
    _CLIENT_PASSING_ARGS: List[str] = [
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "config",
        "api_version",
        "use_ssl",
        "verify",
        "endpoint_url",
    ]

    def __init__(
        self,
        region_name: Optional[str] = None,
        profile_name: Optional[str] = None,
        role_arn: Optional[str] = None,
        role_session_name: str = f"PyDynamoDB-session-{int(time.time())}",
        external_id: Optional[str] = None,
        serial_number: Optional[str] = None,
        token_code: Optional[str] = None,
        principal_arn: Optional[str] = None,
        saml_assertion: Optional[str] = None,
        web_identity_token: Optional[str] = None,
        provider_id: Optional[str] = None,
        duration_seconds: int = 3600,
        session: Optional[Session] = None,
        config: Optional[Config] = None,
        converter: Optional[Converter] = None,
        retry_config: Optional[RetryConfig] = None,
        cursor_class: Type[BaseCursor] = Cursor,
        cursor_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        self._kwargs = {
            **kwargs,
            "role_arn": role_arn,
            "role_session_name": role_session_name,
            "external_id": external_id,
            "serial_number": serial_number,
            "token_code": token_code,
            "principal_arn": principal_arn,
            "saml_assertion": saml_assertion,
            "web_identity_token": web_identity_token,
            "provider_id": provider_id,
            "duration_seconds": duration_seconds,
        }

        self.region_name = region_name
        self.profile_name = profile_name
        self.config: Optional[Config] = config if config else Config()

        if session:
            self._session = session
        else:
            creds = None
            if role_arn and saml_assertion:
                creds = self._assume_role_with_saml(
                    profile_name=self.profile_name,
                    region_name=self.region_name,
                    role_arn=role_arn,
                    principal_arn=principal_arn,
                    saml_assertion=saml_assertion,
                    duration_seconds=duration_seconds,
                )
            elif role_arn and web_identity_token:
                creds = self._assume_role_with_web_identity(
                    profile_name=self.profile_name,
                    region_name=self.region_name,
                    role_arn=role_arn,
                    role_session_name=role_session_name,
                    web_identity_token=web_identity_token,
                    provider_id=provider_id,
                    duration_seconds=duration_seconds,
                )
            elif role_arn:
                creds = self._assume_role(
                    profile_name=self.profile_name,
                    region_name=self.region_name,
                    role_arn=role_arn,
                    role_session_name=role_session_name,
                    external_id=external_id,
                    serial_number=serial_number,
                    token_code=token_code,
                    duration_seconds=duration_seconds,
                )
            elif serial_number:
                creds = self._get_session_token(
                    profile_name=self.profile_name,
                    region_name=self.region_name,
                    serial_number=serial_number,
                    duration_seconds=duration_seconds,
                )

            if creds:
                self.profile_name = None
                self._kwargs.update(
                    {
                        "aws_access_key_id": creds["AccessKeyId"],
                        "aws_secret_access_key": creds["SecretAccessKey"],
                        "aws_session_token": creds["SessionToken"],
                    }
                )
            self._session = Session(
                region_name=self.region_name,
                profile_name=self.profile_name,
                **self._session_kwargs,
            )

        self._client = self._session.client(
            "dynamodb",
            region_name=self.region_name,
            config=self.config,
            **self._client_kwargs,
        )

        self._converter = converter
        self._retry_config = retry_config if retry_config else RetryConfig()
        self.cursor_class = cursor_class
        self.cursor_kwargs = cursor_kwargs if cursor_kwargs else {}
        self._cursor_pool = []
        self._autocommit = True
        self._in_transaction = False

    def _assume_role(
        self,
        profile_name: Optional[str],
        region_name: Optional[str],
        role_arn: str,
        role_session_name: str,
        external_id: Optional[str],
        serial_number: Optional[str],
        token_code: Optional[str],
        duration_seconds: int,
    ) -> Dict[str, Any]:
        session = Session(
            region_name=region_name, profile_name=profile_name, **self._session_kwargs
        )
        client = session.client(
            "sts", region_name=region_name, config=self.config, **self._client_kwargs
        )
        request = {
            "RoleArn": role_arn,
            "RoleSessionName": role_session_name,
            "DurationSeconds": duration_seconds,
        }
        if external_id:
            request.update(
                {
                    "ExternalId": external_id,
                }
            )
        if serial_number:
            request.update(
                {
                    "SerialNumber": serial_number,
                    "TokenCode": token_code,
                }
            )

        response = client.assume_role(**request)
        creds: Dict[str, Any] = response["Credentials"]
        return creds

    def _assume_role_with_saml(
        self,
        profile_name: Optional[str],
        region_name: Optional[str],
        role_arn: str,
        principal_arn: str,
        saml_assertion: str,
        duration_seconds: int,
    ) -> Dict[str, Any]:
        session = Session(
            region_name=region_name, profile_name=profile_name, **self._session_kwargs
        )
        client = session.client(
            "sts", region_name=region_name, config=self.config, **self._client_kwargs
        )

        # Resolve the issue which plus sign will be replaced to space by url.parse_qsl
        saml_assertion = saml_assertion.replace(" ", "+")

        request = {
            "RoleArn": role_arn,
            "PrincipalArn": principal_arn,
            "SAMLAssertion": saml_assertion,
            "DurationSeconds": duration_seconds,
        }

        response = client.assume_role_with_saml(**request)
        creds: Dict[str, Any] = response["Credentials"]
        return creds

    def _assume_role_with_web_identity(
        self,
        profile_name: Optional[str],
        region_name: Optional[str],
        role_arn: str,
        role_session_name: str,
        web_identity_token: str,
        provider_id: Optional[str],
        duration_seconds: int,
    ) -> Dict[str, Any]:
        session = Session(
            region_name=region_name, profile_name=profile_name, **self._session_kwargs
        )
        client = session.client(
            "sts", region_name=region_name, config=self.config, **self._client_kwargs
        )
        request = {
            "RoleArn": role_arn,
            "RoleSessionName": role_session_name,
            "DurationSeconds": duration_seconds,
            "WebIdentityToken": web_identity_token,
        }

        if provider_id:
            request.update(
                {
                    "ProviderId": provider_id,
                }
            )

        response = client.assume_role_with_web_identity(**request)
        creds: Dict[str, Any] = response["Credentials"]
        return creds

    def _get_session_token(
        self,
        profile_name: Optional[str],
        region_name: Optional[str],
        serial_number: Optional[str],
        duration_seconds: int,
    ) -> Dict[str, Any]:
        session = Session(profile_name=profile_name, **self._session_kwargs)
        client = session.client(
            "sts", region_name=region_name, config=self.config, **self._client_kwargs
        )
        token_code = input("Enter the MFA code: ")
        request = {
            "DurationSeconds": duration_seconds,
            "SerialNumber": serial_number,
            "TokenCode": token_code,
        }
        response = client.get_session_token(**request)
        creds: Dict[str, Any] = response["Credentials"]
        return creds

    @property
    def _session_kwargs(self) -> Dict[str, Any]:
        return {
            k: v for k, v in self._kwargs.items() if k in self._SESSION_PASSING_ARGS
        }

    @property
    def _client_kwargs(self) -> Dict[str, Any]:
        return {k: v for k, v in self._kwargs.items() if k in self._CLIENT_PASSING_ARGS}

    @property
    def session(self) -> Session:
        return self._session

    @property
    def client(self) -> "BaseClient":
        return self._client

    @property
    def autocommit(self) -> bool:
        return self._autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        try:
            if not self._autocommit and value:
                self._autocommit = True
                for cursor_ in self.cursor_pool:
                    cursor_.flush()
        finally:
            self._autocommit = value

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    @in_transaction.setter
    def in_transaction(self, value: bool) -> bool:
        self._in_transaction = False

    @property
    def cursor_pool(self) -> List[Optional[BaseCursor]]:
        return self._cursor_pool

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def cursor(self, cursor: Optional[Type[BaseCursor]] = None, **kwargs) -> BaseCursor:
        kwargs.update(self.cursor_kwargs)
        if not cursor:
            cursor = self.cursor_class
        converter = kwargs.pop("converter", self._converter)
        if not converter:
            converter = cursor.get_default_converter()
        cursor_ = cursor(
            connection=self,
            converter=converter,
            retry_config=kwargs.pop("retry_config", self._retry_config),
            **kwargs,
        )

        self._cursor_pool.append(cursor_)
        return cursor_

    def close(self) -> None:
        self._session = None
        self._client = None
        self._autocommit = True
        self._in_transaction = False
        self.cursor_pool.clear()

    def begin(self) -> None:
        self._autocommit = False
        self._in_transaction = True

    def commit(self) -> None:
        try:
            if self._in_transaction:
                for cursor_ in self.cursor_pool:
                    cursor_.execute_transaction()
        finally:
            self._autocommit = True
            self._in_transaction = False

    def rollback(self) -> None:
        raise NotSupportedError

    def test_connection(self) -> bool:
        request: Dict[str, Any] = {"Limit": 1}

        try:
            retry_api_call(
                self._client.list_tables,
                config=self._retry_config,
                logger=_logger,
                **request,
            )
        except Exception as e:
            _logger.exception("Failed to connect database: %s" % repr(e))
            return False
        else:
            return True
