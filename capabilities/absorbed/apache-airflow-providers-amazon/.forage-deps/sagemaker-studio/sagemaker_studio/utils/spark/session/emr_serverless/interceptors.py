"""
EMR Serverless-specific Spark Connect authentication interceptor.

EMR Serverless issues short-lived authentication tokens (via ``GetSessionEndpoint``
API).  This interceptor automatically refreshes the token before it expires and
injects it into each gRPC request.  It also detects terminated/expired sessions
and raises ``SparkConnectGrpcException`` so that ``LazySparkSession`` can trigger
auto-recovery.
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
        emr_serverless_session_id: str,
        application_id: str,
        emr_serverless_client,
        initial_auth_token: str = None,
        initial_token_expiry=None,
    ):
        super().__init__(
            session_id=emr_serverless_session_id,
            initial_auth_token=initial_auth_token,
            initial_token_expiry=initial_token_expiry,
            logger_name="SparkConnect.EMRServerless",
        )
        self.application_id = application_id
        self.emr_serverless_client = emr_serverless_client

    def _do_refresh_token(self) -> _TokenState:
        self.logger.debug(f"Refreshing token for session {self.session_id}")
        try:
            resp = self.emr_serverless_client.get_session_endpoint(
                applicationId=self.application_id,
                sessionId=self.session_id,
            )
            new_state = _TokenState(
                auth_token=resp["authToken"],
                expiration_time=resp["authTokenExpiresAt"]
                - datetime.timedelta(seconds=self._early_refresh_seconds),
            )
            self.logger.info(f"Next token refresh at {new_state.expiration_time}")
            return new_state
        except Exception as e:
            from botocore.exceptions import ClientError as _ClientError

            if (
                isinstance(e, _ClientError)
                and e.response.get("Error", {}).get("Code") == "ResourceNotFoundException"
            ):
                from pyspark.errors.exceptions.connect import SparkConnectGrpcException

                self.logger.warning(
                    f"EMR Serverless session {self.session_id} is no longer available "
                    f"(terminated or expired). A new session will be created on next access."
                )
                raise SparkConnectGrpcException(
                    f"EMR Serverless session {self.session_id} terminated or expired."
                ) from e
            else:
                self.logger.error(
                    f"Error while refreshing the Spark connect auth tokens "
                    f"for session {self.session_id}: {e}"
                )
                raise


class CustomChannelBuilder(BaseCustomChannelBuilder):

    def __init__(
        self,
        emr_serverless_session_id: str,
        application_id: str,
        url: str,
        emr_serverless_client,
        initial_auth_token: str = None,
        initial_token_expiry=None,
    ):
        super().__init__(url)
        self.emr_serverless_session_id = emr_serverless_session_id
        self.application_id = application_id
        self.emr_serverless_client = emr_serverless_client
        self.initial_auth_token = initial_auth_token
        self.initial_token_expiry = initial_token_expiry

    def _create_interceptor(self):
        return SparkConnectGRPCInterceptor(
            self.emr_serverless_session_id,
            self.application_id,
            self.emr_serverless_client,
            initial_auth_token=self.initial_auth_token,
            initial_token_expiry=self.initial_token_expiry,
        )
