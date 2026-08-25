"""
EMR on EKS Spark Connect authentication interceptor.

The EMR on EKS auth proxy authenticates each gRPC request with a single
``x-aws-proxy-auth`` PASETO token (injected by the base interceptor). This
interceptor refreshes that token before expiry via the emr-containers
GetManagedEndpointSessionCredentials API and maps a terminated/expired
endpoint to SparkConnectGrpcException so LazySparkSession can auto-recover.
"""

import datetime

from sagemaker_studio.utils.spark.session.base_interceptors import (
    BaseCustomChannelBuilder,
    BaseSparkConnectGRPCInterceptor,
    _TokenState,
)


class EmrEksSparkConnectInterceptor(BaseSparkConnectGRPCInterceptor):
    """gRPC interceptor that refreshes the EMR on EKS auth-proxy token.

    Header injection (``x-aws-proxy-auth``) is handled by the base class, so no
    ``_with_metadata`` override is needed — EMR on EKS is token-only.
    """

    def __init__(
        self,
        virtual_cluster_id: str,
        endpoint_id: str,
        emr_client,
        execution_role_arn: str,
        initial_auth_token: str = None,
        initial_token_expiry=None,
    ):
        super().__init__(
            session_id=endpoint_id,
            initial_auth_token=initial_auth_token,
            initial_token_expiry=initial_token_expiry,
            logger_name="SparkConnect.EmrEks",
        )
        self.virtual_cluster_id = virtual_cluster_id
        self.endpoint_id = endpoint_id
        self.emr_client = emr_client
        self.execution_role_arn = execution_role_arn

    def _do_refresh_token(self) -> _TokenState:
        self.logger.debug(f"Refreshing token for EMR on EKS endpoint {self.endpoint_id}")
        try:
            resp = self.emr_client.get_managed_endpoint_session_credentials(
                virtualClusterIdentifier=self.virtual_cluster_id,
                endpointIdentifier=self.endpoint_id,
                executionRoleArn=self.execution_role_arn,
                credentialType="TOKEN",
            )
            new_state = _TokenState(
                auth_token=resp["credentials"]["token"],
                expiration_time=resp["expiresAt"]
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
                    f"EMR on EKS managed endpoint {self.endpoint_id} is no longer available "
                    f"(terminated or expired)."
                )
                raise SparkConnectGrpcException(
                    f"EMR on EKS managed endpoint {self.endpoint_id} terminated or expired."
                ) from e
            self.logger.error(
                f"Error refreshing EMR on EKS auth token for endpoint {self.endpoint_id}: {e}"
            )
            raise


class EmrEksChannelBuilder(BaseCustomChannelBuilder):
    """ChannelBuilder that attaches the EMR on EKS auth interceptor to the gRPC channel."""

    def __init__(
        self,
        url: str,
        virtual_cluster_id: str,
        endpoint_id: str,
        emr_client,
        execution_role_arn: str,
        initial_auth_token: str = None,
        initial_token_expiry=None,
    ):
        super().__init__(url)
        self.virtual_cluster_id = virtual_cluster_id
        self.endpoint_id = endpoint_id
        self.emr_client = emr_client
        self.execution_role_arn = execution_role_arn
        self.initial_auth_token = initial_auth_token
        self.initial_token_expiry = initial_token_expiry

    def _create_interceptor(self):
        return EmrEksSparkConnectInterceptor(
            self.virtual_cluster_id,
            self.endpoint_id,
            self.emr_client,
            self.execution_role_arn,
            initial_auth_token=self.initial_auth_token,
            initial_token_expiry=self.initial_token_expiry,
        )
