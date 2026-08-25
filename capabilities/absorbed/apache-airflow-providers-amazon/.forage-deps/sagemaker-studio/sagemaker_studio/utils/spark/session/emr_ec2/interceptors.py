"""
EMR on EC2 Spark Connect authentication interceptor.

Injects x-aws-proxy-auth (auth token) and authorization (session ID) headers
into every gRPC request. Refreshes the auth token before expiration via
EMR on EC2 GetSessionEndpoint API.
"""

import datetime
import logging

from sagemaker_studio.utils.spark.session.base_interceptors import (
    BaseCustomChannelBuilder,
    BaseSparkConnectGRPCInterceptor,
    _ClientCallDetails,
    _TokenState,
)


class EmrEc2SparkConnectInterceptor(BaseSparkConnectGRPCInterceptor):
    """gRPC interceptor that injects EMR on EC2 auth headers on every call."""

    def __init__(
        self,
        session_id: str,
        cluster_id: str,
        emr_client,
        initial_auth_token: str = None,
        initial_token_expiry=None,
        initial_username: str = None,
        initial_password: str = None,
    ):
        super().__init__(
            session_id=session_id,
            initial_auth_token=initial_auth_token,
            initial_token_expiry=initial_token_expiry,
        )
        self.logger = logging.getLogger("SparkConnect.EmrEc2")
        self.cluster_id = cluster_id
        self.emr_client = emr_client
        self._username = initial_username
        self._password = initial_password

    def _do_refresh_token(self) -> _TokenState:
        self.logger.debug(f"Refreshing token for EMR on EC2 session {self.session_id}")
        try:
            resp = self.emr_client.get_session_endpoint(
                ClusterId=self.cluster_id, SessionId=self.session_id
            )
            # Update username and password from the nested Credentials response
            credentials = resp.get("Credentials", {})
            username_password = credentials.get("UsernamePassword", {})
            self._username = username_password.get("Username")
            self._password = username_password.get("Password")
            new_state = _TokenState(
                auth_token=resp["AuthToken"],
                expiration_time=resp["AuthTokenExpirationTime"]
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
                    f"EMR on EC2 session {self.session_id} is no longer available "
                    f"(terminated or expired). A new session will be created on next access."
                )
                raise SparkConnectGrpcException(
                    f"EMR on EC2 session {self.session_id} terminated or expired."
                ) from e
            else:
                self.logger.error(
                    f"Error refreshing EMR on EC2 auth token for session {self.session_id}: {e}"
                )
                raise

    def _with_metadata(self, client_call_details):
        """Inject auth token, session ID, username, and password into gRPC metadata."""
        details = super()._with_metadata(client_call_details)
        metadata = dict(details.metadata)
        metadata["authorization"] = self.session_id
        if self._username:
            metadata["x-emr-username"] = self._username
        if self._password:
            metadata["x-emr-password"] = self._password
        return _ClientCallDetails(
            method=details.method,
            timeout=details.timeout,
            metadata=list(metadata.items()),
            credentials=details.credentials,
            wait_for_ready=details.wait_for_ready,
            compression=details.compression,
        )


class EmrEc2ChannelBuilder(BaseCustomChannelBuilder):
    """Custom ChannelBuilder that adds EMR on EC2 auth interceptor to the gRPC channel."""

    def __init__(
        self,
        url: str,
        session_id: str,
        cluster_id: str,
        emr_client,
        initial_auth_token: str = None,
        initial_token_expiry=None,
        initial_username: str = None,
        initial_password: str = None,
    ):
        super().__init__(url)
        self._emr_session_id = session_id
        self.cluster_id = cluster_id
        self.emr_client = emr_client
        self.initial_auth_token = initial_auth_token
        self.initial_token_expiry = initial_token_expiry
        self.initial_username = initial_username
        self.initial_password = initial_password

    def _create_interceptor(self):
        return EmrEc2SparkConnectInterceptor(
            self._emr_session_id,
            self.cluster_id,
            self.emr_client,
            initial_auth_token=self.initial_auth_token,
            initial_token_expiry=self.initial_token_expiry,
            initial_username=self.initial_username,
            initial_password=self.initial_password,
        )
