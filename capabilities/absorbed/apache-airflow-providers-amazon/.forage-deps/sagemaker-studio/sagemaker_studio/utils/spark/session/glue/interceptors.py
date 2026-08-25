"""
Glue-specific Spark Connect authentication interceptor.

Glue issues short-lived authentication tokens (via ``GetSessionEndpoint`` API)
that are valid for ~30 minutes.  This interceptor automatically refreshes the
token before it expires and injects it into each gRPC request.  It also detects
terminated/invalid sessions and raises ``SparkConnectGrpcException`` so that
``LazySparkSession`` can trigger auto-recovery.
"""

import datetime

from sagemaker_studio.utils.spark.session.base_interceptors import (
    BaseCustomChannelBuilder,
    BaseSparkConnectGRPCInterceptor,
    _TokenState,
)


class SparkConnectGRPCInterceptor(BaseSparkConnectGRPCInterceptor):

    def __init__(
        self,
        glue_session_id: str,
        glue_client,
        initial_auth_token: str = None,
        initial_token_expiry=None,
    ):
        super().__init__(
            session_id=glue_session_id,
            initial_auth_token=initial_auth_token,
            initial_token_expiry=initial_token_expiry,
        )
        self.glue_client = glue_client

    def _do_refresh_token(self) -> _TokenState:
        self.logger.debug(f"Refreshing token for Glue session {self.session_id}")
        try:
            response = self.glue_client.get_session_endpoint(SessionId=self.session_id)
            # GetSessionEndpoint returns {SparkConnect: {Url, AuthToken, ...}}.
            endpoint_data = response.get("SparkConnect", response)

            # AuthTokenExpirationTime is an epoch timestamp (seconds since Unix epoch).
            token_expiry = endpoint_data["AuthTokenExpirationTime"]
            if not isinstance(token_expiry, datetime.datetime):
                token_expiry = datetime.datetime.fromtimestamp(
                    token_expiry, tz=datetime.timezone.utc
                )

            new_state = _TokenState(
                auth_token=endpoint_data["AuthToken"],
                expiration_time=token_expiry
                - datetime.timedelta(seconds=self._early_refresh_seconds),
            )
            self.logger.info(f"Next token refresh at {new_state.expiration_time}")
            return new_state
        except Exception as e:
            from botocore.exceptions import ClientError as _ClientError

            if not isinstance(e, _ClientError):
                self.logger.error(
                    f"Error while refreshing the Spark connect auth tokens "
                    f"for Glue session {self.session_id}: {e}"
                )
                raise

            error_code = e.response.get("Error", {}).get("Code", "")

            # Session gone or not in ready state — trigger auto-recovery
            if error_code in ("EntityNotFoundException", "IllegalSessionStateException"):
                from pyspark.errors.exceptions.connect import SparkConnectGrpcException

                self.logger.warning(
                    f"Glue session {self.session_id} is no longer available "
                    f"({error_code}). A new session will be created on next access."
                )
                raise SparkConnectGrpcException(
                    f"Glue session {self.session_id} terminated or not ready."
                ) from e

            # Transient service errors — retry once, then trigger auto-recovery
            if error_code in ("InternalServiceException", "OperationTimeoutException"):
                import time as _time

                self.logger.warning(
                    f"Glue GetSessionEndpoint returned {error_code} for session "
                    f"{self.session_id}, retrying once after 2s..."
                )
                _time.sleep(2)
                try:
                    response = self.glue_client.get_session_endpoint(SessionId=self.session_id)
                    endpoint_data = response.get("SparkConnect", response)
                    token_expiry = endpoint_data["AuthTokenExpirationTime"]
                    if not isinstance(token_expiry, datetime.datetime):
                        token_expiry = datetime.datetime.fromtimestamp(
                            token_expiry, tz=datetime.timezone.utc
                        )
                    new_state = _TokenState(
                        auth_token=endpoint_data["AuthToken"],
                        expiration_time=token_expiry
                        - datetime.timedelta(seconds=self._early_refresh_seconds),
                    )
                    self.logger.info(
                        f"Retry succeeded. Next token refresh at {new_state.expiration_time}"
                    )
                    return new_state
                except Exception:
                    # Retry failed — treat as session gone, trigger auto-recovery
                    from pyspark.errors.exceptions.connect import SparkConnectGrpcException

                    self.logger.warning(
                        f"Glue session {self.session_id} not recoverable after retry "
                        f"({error_code}). A new session will be created on next access."
                    )
                    raise SparkConnectGrpcException(
                        f"Glue session {self.session_id} not available ({error_code})."
                    ) from e

            # Non-recoverable errors (AccessDenied, InvalidInput, OperationNotSupported)
            self.logger.error(
                f"Error while refreshing the Spark connect auth tokens "
                f"for Glue session {self.session_id}: {error_code} - {e}"
            )
            raise


class CustomChannelBuilder(BaseCustomChannelBuilder):

    def __init__(
        self,
        glue_session_id: str,
        url: str,
        glue_client,
        initial_auth_token: str = None,
        initial_token_expiry=None,
    ):
        super().__init__(url)
        self.glue_session_id = glue_session_id
        self.glue_client = glue_client
        self.initial_auth_token = initial_auth_token
        self.initial_token_expiry = initial_token_expiry

    def _create_interceptor(self):
        return SparkConnectGRPCInterceptor(
            self.glue_session_id,
            self.glue_client,
            initial_auth_token=self.initial_auth_token,
            initial_token_expiry=self.initial_token_expiry,
        )
