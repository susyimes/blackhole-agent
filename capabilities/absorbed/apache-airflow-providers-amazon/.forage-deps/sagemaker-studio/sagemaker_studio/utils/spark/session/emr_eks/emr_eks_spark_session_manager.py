"""
EMR on EKS Spark Connect Session Management.

This module provides the EmrEksSparkSessionManager class that creates a
SPARK_CONNECT managed endpoint on an EMR on EKS virtual cluster and returns a
configured SparkSession connected to it via Spark Connect.
"""

import logging
import os
import time
import traceback
import uuid

import boto3
from pyspark.sql.connect.session import SparkSession as _SparkSession

from sagemaker_studio.project import ClientConfig, Project
from sagemaker_studio.utils._internal import InternalUtils
from sagemaker_studio.utils.loggerutils import sync_with_metrics
from sagemaker_studio.utils.spark.session.constants import SPARK_CONNECT_LOG_FILE
from sagemaker_studio.utils.spark.session.emr_eks.interceptors import EmrEksChannelBuilder
from sagemaker_studio.utils.spark.session.spark_config_builder import (
    apply_compatibility_mode_configs,
    build_spark_configs,
    extract_connection_spark_configs,
)
from sagemaker_studio.utils.spark.session.spark_session_manager import SparkSessionManager

_parent_logger = logging.getLogger("SparkConnect")
SparkSessionManager.setup_logger(_parent_logger, SPARK_CONNECT_LOG_FILE)
logger = logging.getLogger("SparkConnect.EmrEks")

_MODEL_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "boto3_models")
)
# Connection spark-defaults key carrying the EMR release label (set by the env add-on).
_SPARK_DEFAULTS_CLASSIFICATION = "spark-defaults"
_RELEASE_LABEL_KEY = "spark.emr.releaseLabel"
_POLL_INTERVAL = 5  # seconds
_MAX_POLL = 120  # max describe attempts (~10 min at _POLL_INTERVAL)
_SESSION_IDLE_TIMEOUT_MINUTES = 30


def _parse_emr_eks_arn(arn: str):
    """Parse an emr-containers ARN into (virtual_cluster_id, endpoint_id, region).

    ARN forms: arn:aws:emr-containers:{region}:{acct}:/virtualclusters/{vcId}[/endpoints/{epId}]
    Returns (None, None, "") if the ARN is empty or malformed.
    """
    if not arn:
        return None, None, ""
    parts = arn.split(":")
    region = parts[3] if len(parts) > 3 else ""
    resource = parts[5] if len(parts) > 5 else ""
    segments = resource.strip("/").split("/")
    vc_id = None
    ep_id = None
    if "virtualclusters" in segments:
        i = segments.index("virtualclusters")
        if i + 1 < len(segments):
            vc_id = segments[i + 1]
    if "endpoints" in segments:
        j = segments.index("endpoints")
        if j + 1 < len(segments):
            ep_id = segments[j + 1]
    return vc_id, ep_id, region


class EmrEksSparkSessionManager(SparkSessionManager):
    """
    Creates and returns a SparkSession connected to EMR on EKS via Spark Connect.

    Lifecycle: create_managed_endpoint -> poll until ACTIVE ->
    get_managed_endpoint_session_credentials -> connect via gRPC with auth proxy
    interceptor. stop() deletes the endpoint.
    """

    def __init__(
        self,
        connection_name=None,
        config: ClientConfig = ClientConfig(),
        *,
        connection=None,
        spark_conf: dict = None,
    ):
        """
        Initialize the EMR on EKS Spark session manager.

        Args:
            connection_name (str): The connection name (backward compat, used if connection not provided).
            config (ClientConfig): Configuration for the client.
            connection: Pre-resolved Connection object (from sparkutils routing). Keyword-only.
            spark_conf (dict): User-supplied Spark config, applied as endpoint spark-defaults.
        """
        self._connection = connection
        self.connection_name = connection_name
        self.config = config
        self.virtual_cluster_id = None
        self.endpoint_id = None
        self.release_label = None
        self.region = None
        self.endpoint_url = None
        self.resolved_connection_name = None
        self.connection_spark_configs = {}
        self._spark_session = None
        self._emr_client = None
        if spark_conf:
            self.set_user_spark_conf(spark_conf)

    def _lazy_init(self):
        """Defer network calls and heavy initialization to first use."""
        self._utils = InternalUtils()
        self.project = Project()

        connection = self._connection
        if connection is None:
            if self.connection_name:
                connection = self.project.connection(self.connection_name)
            else:
                raise ValueError(
                    "EmrEksSparkSessionManager requires a connection or connection_name."
                )

        conn_data = getattr(connection, "_Connection__connection_data", {})
        conn_data = conn_data if isinstance(conn_data, dict) else {}
        props = conn_data.get("props", {})
        spark_emr_props = props.get("sparkEmrProperties", {})
        compute_arn = spark_emr_props.get("computeArn", "")

        # computeArn identifies the virtual cluster; the endpoint is created per session.
        self.virtual_cluster_id, _, arn_region = _parse_emr_eks_arn(compute_arn)
        if not self.virtual_cluster_id:
            raise ValueError(
                "Could not resolve virtual_cluster_id from the connection's computeArn."
            )

        self.release_label = self._resolve_release_label(conn_data, spark_emr_props)
        self.region = arn_region or self._utils._get_domain_region()
        self.endpoint_url = self.config.overrides.get("emr-containers", {}).get("endpoint_url")
        self.sts_client = boto3.client("sts", region_name=self.region)
        self._emr_client = self._create_emr_client()
        self.resolved_connection_name = getattr(connection, "name", None) or self.connection_name
        self.connection_spark_configs = extract_connection_spark_configs(connection)
        logger.info(
            f"Resolved virtual_cluster_id={self.virtual_cluster_id}, "
            f"release_label={self.release_label}, region={self.region}"
        )

    def _resolve_release_label(self, conn_data: dict, spark_emr_props: dict) -> str:
        """Resolve the EMR release label from the connection's spark-defaults configuration.

        Reads ``spark.emr.releaseLabel`` from the ``spark-defaults`` configuration entry
        (populated by the environment add-on, same as the IdC connection). Raises if absent.
        """
        for cfg in conn_data.get("configurations", []) or []:
            if not isinstance(cfg, dict):
                continue
            if cfg.get("classification") == _SPARK_DEFAULTS_CLASSIFICATION:
                release_label = (cfg.get("properties") or {}).get(_RELEASE_LABEL_KEY)
                if release_label:
                    return release_label
        # Secondary location some connections may use.
        release_label = spark_emr_props.get("releaseLabel")
        if release_label:
            return release_label
        raise ValueError(
            f"Could not resolve {_RELEASE_LABEL_KEY} from the connection's "
            f"{_SPARK_DEFAULTS_CLASSIFICATION} configuration."
        )

    def _create_emr_client(self):
        """
        Create an emr-containers client with a private service model for SPARK_CONNECT APIs.

        Uses botocore's extra_search_paths to load the local model so the SPARK_CONNECT
        request/response fields are available until they ship in public boto3.
        """
        import botocore.loaders
        import botocore.session

        if os.path.isdir(_MODEL_PATH):
            loader = botocore.loaders.Loader(extra_search_paths=[_MODEL_PATH])
            botocore_sess = botocore.session.get_session()
            botocore_sess.register_component("data_loader", loader)
            boto_session = boto3.Session(botocore_session=botocore_sess)
        else:
            logger.warning(
                f"Custom boto3 model path not found: {_MODEL_PATH}; using default session"
            )
            boto_session = boto3.Session()

        client_kwargs = {"region_name": self.region}
        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url
        return boto_session.client("emr-containers", **client_kwargs)

    def create(self):
        """Create a managed endpoint and return a SparkSession connected to it."""
        if self._spark_session is not None:
            logger.debug("SparkSession already exists, returning existing session")
            return self._spark_session

        try:
            os.environ["SPARK_CONNECT_MODE_ENABLED"] = "1"
            self._lazy_init()

            # Step 1: Create endpoint, wait for ACTIVE, get URL + auth token
            kwargs = self._build_endpoint_params()
            spark_connect_url, token, token_expiry = self._create_managed_endpoint_session(kwargs)

            # Step 2: Create SparkSession with auth interceptor (seed initial token)
            channel_builder = EmrEksChannelBuilder(
                spark_connect_url,
                self.virtual_cluster_id,
                self.endpoint_id,
                self._emr_client,
                self.project.iam_role,
                initial_auth_token=token,
                initial_token_expiry=token_expiry,
            )

            logger.info("Creating SparkSession via Spark Connect...")
            self._user_msg("Connecting to Spark Connect server...")
            app_name = f"EmrEksSparkSession-{str(uuid.uuid4())[:8]}"
            self._spark_session = (
                _SparkSession.builder.channelBuilder(channel_builder)
                .appName(app_name)
                .getOrCreate()
            )

            logger.info("SparkSession created successfully")
            self._user_msg("Spark Connect session is ready.")
            return self._spark_session
        except Exception as e:
            logger.error(f"Failed to create SparkSession: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.stop()
            raise

    def _get_service_specific_configs(self) -> dict:
        """Build EMR on EKS-specific spark configs (Layer 2).

        Includes compatibility mode configs and OpenLineage for data lineage tracking
        (same as EC2/Glue, minus Glue-specific spark.glue.* keys).
        OpenLineage can be disabled via ClientConfig(overrides={"emr-containers": {"enable_open_lineage": False}}).
        """
        configs = apply_compatibility_mode_configs({})

        # OpenLineage configs for data lineage (mirrors EC2/Glue session manager)
        emr_containers_config = self.config.overrides.get("emr-containers", {})
        if emr_containers_config.get("enable_open_lineage", True):
            try:
                configs.update(
                    {
                        "spark.extraListeners": "io.openlineage.spark.agent.OpenLineageSparkListener",
                        "spark.openlineage.transport.type": "amazon_datazone_api",
                        "spark.openlineage.transport.domainId": self.project.domain_id,
                    }
                )
                logger.info("OpenLineage configs added for EMR on EKS")
            except Exception as e:
                logger.warning(f"Failed to add OpenLineage configs: {e}")
        else:
            logger.info("OpenLineage disabled via ClientConfig overrides")

        return configs

    def _build_endpoint_params(self):
        """Build the parameters needed for create_managed_endpoint API call.

        Returns a dict of kwargs ready for the API call. Spark configs are assembled
        using the standard 4-layer merge:
        base (account) → service (compatibility + OpenLineage) → connection → user.
        """
        user_id, account_id = self._get_user_id_account_id()

        # Assemble spark configs using build_spark_configs (consistent with EC2/Serverless)
        service_configs = self._get_service_specific_configs()
        spark_configs = build_spark_configs(
            account_id=account_id,
            service_configs=service_configs,
            connection_configs=self.connection_spark_configs,
            user_configs=self._user_spark_conf,
        )

        return dict(
            name=f"sc-endpoint-{str(uuid.uuid4())[:8]}",
            clientToken=str(uuid.uuid4()),
            type="SPARK_CONNECT",
            releaseLabel=self.release_label,
            executionRoleArn=self.project.iam_role,
            virtualClusterId=self.virtual_cluster_id,
            sessionIdleTimeoutInMinutes=_SESSION_IDLE_TIMEOUT_MINUTES,
            tags={
                "AmazonDataZoneProject": self.project.id,
                "AmazonDataZoneSessionOwner": user_id,
            },
            configurationOverrides={
                "applicationConfiguration": [
                    {"classification": "spark-defaults", "properties": spark_configs}
                ]
            },
        )

    @sync_with_metrics("_create_emr_eks_endpoint")
    def _create_managed_endpoint_session(self, kwargs):
        """Create a SPARK_CONNECT endpoint and return (sc_url, auth_token, token_expiry).

        Metrics are captured for the API call and endpoint lifecycle only.
        Config building is done upstream in _build_endpoint_params().
        """

        logger.info(f"Creating SPARK_CONNECT endpoint on virtual cluster {self.virtual_cluster_id}")
        self._user_msg(
            f"Creating Spark Connect session on EMR on EKS (virtual cluster: {self.virtual_cluster_id})..."
        )
        resp = self._emr_client.create_managed_endpoint(**kwargs)
        # Assign early so stop() can clean up even if waiting/connect fails.
        self.endpoint_id = resp["id"]
        self._user_msg(f"Endpoint created: {self.endpoint_id}. Waiting for ACTIVE state...")

        endpoint = self._wait_for_endpoint_active()
        host = endpoint.get("authProxyUrl") or endpoint.get("serverUrl")
        if not host:
            raise RuntimeError("Managed endpoint did not return authProxyUrl or serverUrl.")
        self._user_msg("Endpoint ACTIVE. Fetching session credentials...")

        creds_resp = self._emr_client.get_managed_endpoint_session_credentials(
            virtualClusterIdentifier=self.virtual_cluster_id,
            endpointIdentifier=self.endpoint_id,
            executionRoleArn=self.project.iam_role,
            credentialType="TOKEN",
        )
        token = creds_resp["credentials"]["token"]
        token_expiry = creds_resp.get("expiresAt")
        return self._to_sc_url(host), token, token_expiry

    def _wait_for_endpoint_active(self, max_poll=_MAX_POLL, poll_interval=_POLL_INTERVAL):
        """Poll describe_managed_endpoint until the endpoint is ACTIVE.

        Bounded by max_poll attempts (~max_poll * poll_interval seconds) to avoid
        an infinite loop if the endpoint never reaches a terminal state.
        """
        last_state = None
        for _ in range(max_poll):
            resp = self._emr_client.describe_managed_endpoint(
                virtualClusterId=self.virtual_cluster_id, id=self.endpoint_id
            )
            endpoint = resp["endpoint"]
            state = endpoint.get("state")
            if state != last_state:
                logger.info(f"Managed endpoint {self.endpoint_id} state: {state}")
                last_state = state

            if state == "ACTIVE":
                return endpoint
            if state in ("TERMINATED", "TERMINATED_WITH_ERRORS"):
                raise RuntimeError(
                    f"EMR on EKS managed endpoint {self.endpoint_id} reached {state}: "
                    f"{endpoint.get('stateDetails', '')}"
                )
            time.sleep(poll_interval)

        raise RuntimeError(
            f"Timed out waiting for managed endpoint {self.endpoint_id} to become ACTIVE "
            f"(last state={last_state})."
        )

    def stop(self):
        """Stop the SparkSession and delete the managed endpoint."""
        if self._spark_session:
            try:
                self._spark_session.stop()
            except Exception as e:
                logger.error(f"Error stopping Spark session: {e}")
            finally:
                self._spark_session = None

        if self.endpoint_id and self._emr_client:
            try:
                self._emr_client.delete_managed_endpoint(
                    id=self.endpoint_id, virtualClusterId=self.virtual_cluster_id
                )
                logger.info(f"Deleted managed endpoint {self.endpoint_id}")
            except Exception as e:
                logger.error(f"Error deleting managed endpoint {self.endpoint_id}: {e}")
            finally:
                self.endpoint_id = None

    def get_session_id(self):
        return self.endpoint_id

    @staticmethod
    def _to_sc_url(endpoint: str) -> str:
        """Convert an authProxyUrl/serverUrl to an sc:// Spark Connect URL."""
        host = endpoint
        for prefix in ("https://", "sc://"):
            if host.startswith(prefix):
                host = host[len(prefix) :]
        host = host.split("/")[0]
        if ":" not in host:
            host = f"{host}:443"
        return f"sc://{host}/;use_ssl=true"
