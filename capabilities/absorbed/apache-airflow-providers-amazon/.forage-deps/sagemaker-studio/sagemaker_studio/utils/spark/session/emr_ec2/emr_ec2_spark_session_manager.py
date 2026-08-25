"""
EMR on EC2 Spark Connect Session Management.

This module provides the EmrEc2SparkSessionManager class that creates and returns
a configured SparkSession object connected to an EMR on EC2 cluster via Spark Connect.
"""

import logging
import os
import time
import traceback
import uuid

import boto3
from pyspark.sql.connect.session import SparkSession as _SparkSession

from sagemaker_studio.project import ClientConfig
from sagemaker_studio.utils._internal import InternalUtils
from sagemaker_studio.utils.loggerutils import sync_with_metrics
from sagemaker_studio.utils.spark.connection_resolver import _ensure_project
from sagemaker_studio.utils.spark.session.constants import SPARK_CONNECT_LOG_FILE
from sagemaker_studio.utils.spark.session.emr_ec2.interceptors import EmrEc2ChannelBuilder
from sagemaker_studio.utils.spark.session.spark_config_builder import (
    apply_compatibility_mode_configs,
    build_spark_configs,
    extract_connection_spark_configs,
    generate_s3_access_grants_configs,
)
from sagemaker_studio.utils.spark.session.spark_session_manager import SparkSessionManager

_parent_logger = logging.getLogger("SparkConnect")
SparkSessionManager.setup_logger(_parent_logger, SPARK_CONNECT_LOG_FILE)
logger = logging.getLogger("SparkConnect.EmrEc2")

_MODEL_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "boto3_models")
)
_POLL_INTERVAL = 15  # seconds
_MAX_POLL = 40  # ~10 min


def _parse_emr_cluster_arn(arn: str):
    """Parse an EMR cluster ARN into (cluster_id, region).

    ARN format: arn:aws:elasticmapreduce:{region}:{account}:cluster/{id}
    Returns (None, "") if the ARN is empty or malformed.
    """
    if not arn:
        return None, ""
    parts = arn.split(":")
    region = parts[3] if len(parts) > 3 else ""
    cluster_id = arn.split("/")[-1] if "/" in arn else None
    return cluster_id, region


class EmrEc2SparkSessionManager(SparkSessionManager):
    """
    Creates and returns a SparkSession connected to EMR on EC2 via Spark Connect.

    Lifecycle: start_session → poll until IDLE → get_session_endpoint →
    connect via gRPC with auth proxy interceptor.
    """

    def __init__(
        self,
        connection_name=None,
        config: ClientConfig = ClientConfig(),
        *,
        connection=None,
        spark_conf=None,
    ):
        """
        Initialize the EMR on EC2 Spark session manager.

        Args:
            connection_name (str): The connection name (backward compat, used if connection not provided).
            config (ClientConfig): Configuration for the client.
            connection: Pre-resolved Connection object (from sparkutils routing). Keyword-only.
            spark_conf: User-supplied Spark config overrides (highest priority in merge order).
        """
        self._connection = connection
        self.connection_name = connection_name
        self.config = config
        self.cluster_id = None
        self.emr_session_id = None
        self._spark_session = None
        self._emr_client = None
        self.resolved_connection_name = connection_name
        self.connection_spark_configs = {}
        if spark_conf:
            self.set_user_spark_conf(spark_conf)

    def _lazy_init(self):
        """Defer network calls and heavy initialization to first use."""
        self._utils = InternalUtils()

        self.project = _ensure_project()

        # Resolve connection and extract cluster_id and region from computeArn
        if self._connection is None:
            if self.connection_name:
                self._connection = self.project.connection(self.connection_name)
            else:
                raise ValueError(
                    "EmrEc2SparkSessionManager requires a connection or connection_name."
                )

        conn_data = getattr(self._connection, "_Connection__connection_data", {})
        props = conn_data.get("props", {}) if isinstance(conn_data, dict) else {}
        compute_arn = props.get("sparkEmrProperties", {}).get("computeArn", "")
        self.cluster_id, arn_region = _parse_emr_cluster_arn(compute_arn)
        if not self.cluster_id:
            raise ValueError("Could not resolve cluster_id from the connection's computeArn.")

        domain_region = self._utils._get_domain_region()
        self.region = arn_region if arn_region else domain_region

        logger.info(
            f"Resolved cluster_id={self.cluster_id}, region={self.region} from computeArn={compute_arn}"
        )

        self.connection_spark_configs = extract_connection_spark_configs(self._connection)
        self.resolved_connection_name = (
            getattr(self._connection, "name", None) or self.connection_name
        )

        # Endpoint URL is provided externally via ClientConfig (e.g., by the kernel for preprod).
        # The SDK itself never determines or exposes preprod endpoints.
        emr_override_config = self.config.overrides.get("emr", {})
        self.endpoint_url = emr_override_config.get("endpoint_url")

        self.sts_client = boto3.client("sts", region_name=self.region)
        self._emr_client = self._create_emr_client()

    def _create_emr_client(self):
        """
        Create EMR client with a private service model for session APIs.

        Uses botocore's extra_search_paths to load the local EMR service model.
        This is needed until the EMR session APIs are available in all boto3 versions
        that customers may have installed.
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

        return boto_session.client("emr", **client_kwargs)

    def create(self):
        """Create and return a SparkSession connected to EMR on EC2."""
        if self._spark_session is not None:
            logger.debug("SparkSession already exists, returning existing session")
            return self._spark_session

        try:
            logger.debug("Creating SparkSession connected to EMR on EC2...")
            os.environ["SPARK_CONNECT_MODE_ENABLED"] = "1"
            self._lazy_init()

            # Step 1-3: Start session, wait for IDLE, get endpoint (all metriced)
            user_id, spark_configs = self._build_session_params()
            session_id, spark_connect_url, endpoint_response = self._start_session(
                user_id, spark_configs
            )

            # Step 4: Create SparkSession with auth interceptor
            # Seed with initial token to avoid redundant API call on first gRPC request.
            credentials = endpoint_response.get("Credentials", {})
            username_password = credentials.get("UsernamePassword", {})
            channel_builder = EmrEc2ChannelBuilder(
                spark_connect_url,
                self.emr_session_id,
                self.cluster_id,
                self._emr_client,
                initial_auth_token=endpoint_response.get("AuthToken"),
                initial_token_expiry=endpoint_response.get("AuthTokenExpirationTime"),
                initial_username=username_password.get("Username"),
                initial_password=username_password.get("Password"),
            )
            logger.info("Creating SparkSession via Spark Connect...")
            self._spark_session = (
                _SparkSession.builder.channelBuilder(channel_builder)
                .appName("EmrEc2SparkSession")
                .getOrCreate()
            )
            logger.info("SparkSession created successfully")
            return self._spark_session

        except Exception as e:
            logger.error(f"Failed to create SparkSession: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.stop()
            raise

    def stop(self):
        """Stop the SparkSession and terminate the EMR on EC2 session."""
        logger.info(f"Stopping EMR on EC2 spark session {self.emr_session_id}...")

        if self._spark_session:
            try:
                self._spark_session.stop()
            except Exception as e:
                logger.error(f"Error stopping Spark session: {e}")
            finally:
                self._spark_session = None

        if self.emr_session_id:
            try:
                self._emr_client.terminate_session(
                    ClusterId=self.cluster_id, SessionId=self.emr_session_id
                )
                logger.info(f"Terminated EMR on EC2 session {self.emr_session_id}")
            except Exception as e:
                logger.error(f"Error terminating EMR on EC2 session {self.emr_session_id}: {e}")
            finally:
                self.emr_session_id = None

        logger.info("Stopped EMR EC2 spark session")

    def get_session_id(self):
        return self.emr_session_id

    def _get_service_specific_configs(self) -> dict:
        """Build EMR on EC2-specific spark configs (Layer 2).

        Includes OpenLineage configs for data lineage tracking (same as Glue,
        minus Glue-specific spark.glue.* keys).
        """
        configs = apply_compatibility_mode_configs({})

        # OpenLineage configs for data lineage (mirrors Glue session manager)
        try:
            configs.update(
                {
                    "spark.extraListeners": "io.openlineage.spark.agent.OpenLineageSparkListener",
                    "spark.openlineage.transport.type": "amazon_datazone_api",
                    "spark.openlineage.transport.domainId": self.project.domain_id,
                }
            )
            logger.info("OpenLineage configs added for EMR on EC2")
        except Exception as e:
            logger.warning(f"Failed to add OpenLineage configs: {e}")

        configs.update(self._get_s3_access_grants_configs())

        return configs

    def _get_s3_access_grants_configs(self) -> dict:
        """Get S3 Access Grants spark configs (shared implementation in spark_config_builder)."""
        return generate_s3_access_grants_configs(getattr(self, "project", None))

    def _build_session_params(self):
        """Build the parameters needed for start_session API call.

        Returns a tuple of (user_id, spark_configs) with all config layers merged.
        """
        user_id, account_id = self._get_user_id_account_id()
        service_configs = self._get_service_specific_configs()
        spark_configs = build_spark_configs(
            account_id=account_id,
            service_configs=service_configs,
            connection_configs=self.connection_spark_configs,
            user_configs=self._user_spark_conf,
        )
        return user_id, spark_configs

    @sync_with_metrics("_start_emr_ec2_session")
    def _start_session(self, user_id, spark_configs):
        """Start session, wait for IDLE, and get endpoint URL.

        Metrics capture the full lifecycle: API call + polling + endpoint retrieval.
        This matches the EMR on EKS and EMR Serverless patterns.
        """
        self._user_msg(f"Create session for connection: {self.resolved_connection_name}")

        resp = self._emr_client.start_session(
            ClusterId=self.cluster_id,
            ClientRequestToken=str(uuid.uuid4()),
            ExecutionRoleArn=self.project.iam_role,
            EngineConfigurations=[
                {"Classification": "spark-defaults", "Properties": spark_configs}
            ],
            Tags=[
                {"Key": "AmazonDataZoneSessionOwner", "Value": user_id},
                {"Key": "AmazonDataZoneProject", "Value": self.project.id},
            ],
        )
        session_id = resp["Id"]
        self.emr_session_id = session_id  # assign early so stop() can clean up on failure
        logger.info(f"Session started: {session_id} (state={resp['State']})")

        self._wait_for_idle(session_id)

        spark_connect_url, endpoint_response = self._get_spark_connect_url(session_id)
        self._user_msg(f"Session created for connection: {self.resolved_connection_name}.")

        return session_id, spark_connect_url, endpoint_response

    def _wait_for_idle(self, session_id):
        """Poll get_session until state is IDLE."""
        logger.info(f"Waiting for session {session_id} to become IDLE...")
        self._user_msg("Waiting for EMR on EC2 session to be ready...")
        for i in range(_MAX_POLL):
            resp = self._emr_client.get_session(ClusterId=self.cluster_id, SessionId=session_id)
            session = resp["Session"]
            state = session["State"]
            logger.debug(f"[{i + 1}/{_MAX_POLL}] State: {state}")

            if state == "IDLE":
                logger.info(f"Session {session_id} is IDLE (ready)")
                return
            elif state in ("FAILED", "TERMINATED", "TERMINATING"):
                reason = session.get("StateChangeReason", "unknown")
                raise RuntimeError(f"EMR on EC2 session {session_id} {state}: {reason}")

            time.sleep(_POLL_INTERVAL)

        raise RuntimeError(f"Timed out waiting for session {session_id} to become IDLE")

    def _get_spark_connect_url(self, session_id):
        """Get session endpoint and construct sc:// URL.

        Returns (url, endpoint_response) tuple so the caller can seed the
        initial auth token into the interceptor.
        """
        logger.debug("Getting session endpoint...")
        resp = self._emr_client.get_session_endpoint(
            ClusterId=self.cluster_id, SessionId=session_id
        )
        endpoint = resp["Endpoint"]
        logger.debug(f"Endpoint: {endpoint}")

        # Convert https://host to sc://host:443/;use_ssl=true
        if endpoint.startswith("https://"):
            host = endpoint.replace("https://", "")
            host = host.split("/")[0]
            url = f"sc://{host}:443/;use_ssl=true"
        else:
            url = endpoint

        logger.debug(f"Spark Connect URL: {url}")
        return url, resp
