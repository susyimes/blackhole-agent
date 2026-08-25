"""
Athena-specific Spark Connect authentication interceptor.

Athena issues short-lived authentication tokens (via ``GetSessionEndpoint`` API)
that are valid for ~30 minutes.  This interceptor automatically refreshes the
token before it expires and injects it into each gRPC request.
"""

import datetime

from sagemaker_studio.utils.spark.session.base_interceptors import (
    BaseCustomChannelBuilder,
    BaseSparkConnectGRPCInterceptor,
    _TokenState,
)


class SparkConnectGRPCInterceptor(BaseSparkConnectGRPCInterceptor):

    def __init__(self, athena_session_id: str, athena_client):
        super().__init__(session_id=athena_session_id, logger_name="SparkConnect.Athena")
        self.athena = athena_client

    def _do_refresh_token(self) -> _TokenState:
        self.logger.debug(f"Refreshing token for session {self.session_id}")
        try:
            resp = self.athena.get_session_endpoint(SessionId=self.session_id)
            new_state = _TokenState(
                auth_token=resp["AuthToken"],
                expiration_time=resp["AuthTokenExpirationTime"]
                - datetime.timedelta(seconds=self._early_refresh_seconds),
            )
            self.logger.info(f"Next token refresh at {new_state.expiration_time}")
            return new_state
        except Exception as e:
            self.logger.error(
                f"Error while refreshing the Spark connect auth tokens "
                f"for session {self.session_id}: {e}"
            )
            raise


class CustomChannelBuilder(BaseCustomChannelBuilder):

    def __init__(self, athena_session_id: str, url: str, athena_client):
        super().__init__(url)
        self.athena_session_id = athena_session_id
        self.athena_client = athena_client

    def _create_interceptor(self):
        return SparkConnectGRPCInterceptor(self.athena_session_id, self.athena_client)
