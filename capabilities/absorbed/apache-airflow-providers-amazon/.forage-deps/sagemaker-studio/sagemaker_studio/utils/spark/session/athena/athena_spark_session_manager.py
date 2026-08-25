"""
Athena Spark Session Management.

This module provides the AthenaSparkSessionManager class that creates and returns
a configured SparkSession object connected to Athena.
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
from sagemaker_studio.utils.spark.session.athena.interceptors import CustomChannelBuilder
from sagemaker_studio.utils.spark.session.constants import SPARK_CONNECT_LOG_FILE
from sagemaker_studio.utils.spark.session.spark_config_builder import (
    apply_compatibility_mode_configs,
    build_spark_configs,
    extract_connection_spark_configs,
)
from sagemaker_studio.utils.spark.session.spark_session_manager import SparkSessionManager

_parent_logger = logging.getLogger("SparkConnect")
SparkSessionManager.setup_logger(_parent_logger, SPARK_CONNECT_LOG_FILE)
logger = logging.getLogger("SparkConnect.Athena")


class AthenaSparkSessionManager(SparkSessionManager):
    """
    Creates and returns a SparkSession object connected to Athena.

    This class handles the creation of an Athena session and returns a configured
    SparkSession that can be used directly for Spark operations.
    """

    def __init__(
        self,
        connection_name=None,
        connection_id=None,
        config: ClientConfig = ClientConfig(),
        spark_conf=None,
        *,
        connection=None,
    ):
        """
        Initialize the Athena Spark session.

        Args:
            connection_name (str, optional): Connection name for lookup by name.
            connection_id (str, optional): Connection ID resolved from notebook metadata.
                If both are None, falls back to the default SPARK_CONNECT connection.
            config (ClientConfig, optional): Client configuration overrides.
            spark_conf (dict, optional): Additional Spark configuration properties.
                These will be merged with the default configs, with user values taking precedence.
            connection: Pre-resolved Connection object (from connection_resolver routing). Keyword-only.
        """
        self._connection = connection
        self.connection_name = connection_name
        self.connection_id = connection_id
        self.config = config
        if spark_conf:
            self.set_user_spark_conf(spark_conf)
        self.workgroup_name = None
        self.athena_session_id = None
        self._spark_session = None
        self.athena_client = None
        self.sts_client = None

    def _lazy_init(self):
        _utils = InternalUtils()
        region = _utils._get_domain_region()

        athena_override_config = self.config.overrides.get("athena", {})
        athena_endpoint_url = athena_override_config.get("endpoint_url")

        if athena_endpoint_url:
            self.athena_client = boto3.client(
                "athena",
                region_name=region,
                endpoint_url=athena_endpoint_url,
            )
        else:
            self.athena_client = boto3.client("athena", region_name=region)

        self.sts_client = boto3.client("sts", region_name=region)
        self.project = Project()

        # Use pre-resolved connection if available, otherwise look up
        connection = self._connection
        if connection is None:
            if self.connection_id:
                logger.info(f"Resolving connection by id={self.connection_id}")
                connection = self.project.connection(id=self.connection_id)
            elif self.connection_name:
                logger.info(f"Resolving connection by name={self.connection_name}")
                connection = self.project.connection(self.connection_name)
            else:
                logger.info("Resolving default SPARK_CONNECT connection")
                connection = self.project.connection(type="SPARK_CONNECT")
        self.workgroup_name = connection.data.workgroup_name
        logger.info(
            f"Resolved workgroup_name={self.workgroup_name} for connection type={getattr(connection, 'type', 'unknown')}"
        )
        self.connection_spark_configs = extract_connection_spark_configs(connection)
        logger.debug("Successfully created Athena client")

    def create(self):
        """
        Create and return a SparkSession connected to Athena.

        Returns:
            SparkSession: A configured SparkSession object.
        """
        if self._spark_session is not None:
            logger.debug("SparkSession already exists, returning existing session")
            return self._spark_session

        try:
            logger.debug("Creating SparkSession connected to Athena...")
            os.environ["SPARK_CONNECT_MODE_ENABLED"] = "1"
            self._lazy_init()

            # Prepare session parameters (outside metrics)
            user_id, account_id = self._get_user_id_account_id()
            service_configs = apply_compatibility_mode_configs({})
            spark_properties = build_spark_configs(
                account_id=account_id,
                service_configs=service_configs,
                connection_configs=self.connection_spark_configs,
                user_configs=self._user_spark_conf,
            )

            # Get Athena session and Spark Connect URL
            self.athena_session_id, spark_endpoint_url = self._start_athena_session(
                self.workgroup_name, user_id, spark_properties
            )

            # Import and create custom channel builder
            custom_channel_builder = CustomChannelBuilder(
                self.athena_session_id, spark_endpoint_url, self.athena_client
            )

            # Create SparkSession
            self._spark_session = (
                _SparkSession.builder.channelBuilder(custom_channel_builder)
                .appName("AthenaSparkSession")
                .getOrCreate()
            )

            logger.debug("SparkSession created successfully")
            return self._spark_session

        except Exception as e:
            logger.error(f"Failed to create SparkSession: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def stop(self):
        """Stop the SparkSession and terminate the Athena session."""
        logger.debug(f"Stopping Athena spark session {self.athena_session_id}...")

        # Terminate Athena session if it exists
        if self.athena_session_id:
            try:
                self._terminate_athena_session(self.athena_session_id)
            except Exception as e:
                logger.error(
                    f"Error while terminating Athena spark session {self.athena_session_id}: {e}"
                )
            finally:
                self.athena_session_id = None

        # Stop Spark session if it exists
        if self._spark_session:
            try:
                self._spark_session.stop()
            except Exception as e:
                logger.error(f"Error while stopping Spark session: {e}")
            finally:
                self._spark_session = None

        logger.debug("Stopped Athena spark session")

    def get_session_id(self):
        return self.athena_session_id

    @sync_with_metrics("_start_athena_session")
    def _start_athena_session(self, athena_wg_name, user_id, spark_properties):
        """Get Athena Spark Connect URL for the given workgroup."""
        client_token = str(uuid.uuid4())

        try:
            # 1. Start Athena session
            logger.debug(f"Creating Athena Spark session for workgroup: {athena_wg_name}")

            start_session_response = self.athena_client.start_session(
                WorkGroup=athena_wg_name,
                EngineConfiguration={
                    "Classifications": [{"Name": "spark-defaults", "Properties": spark_properties}]
                },
                SessionIdleTimeoutInMinutes=15,
                ClientRequestToken=client_token,
                Tags=[
                    {"Key": "AmazonDataZoneSessionOwner", "Value": user_id},
                    {"Key": "AmazonDataZoneProject", "Value": self.project.id},
                ],
            )
            session_id = start_session_response["SessionId"]
            logger.debug(f"Created Athena Spark session with id: {session_id}")

            # 2. Wait for Athena session to start
            self._wait_for_athena_session(session_id)

            # 3. Get auth token
            logger.debug("Getting session endpoint URL and auth token...")
            get_session_endpoint_response = self.athena_client.get_session_endpoint(
                SessionId=session_id
            )

            # 4. Construct spark connect url
            spark_connect_url = self._construct_spark_endpoint_url(get_session_endpoint_response)
            logger.debug("Successfully constructed Spark connect URL")
            return session_id, spark_connect_url

        except Exception as e:
            logger.error(f"Failed to create Athena Spark session: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _construct_spark_endpoint_url(self, get_session_endpoint_response) -> str:
        # Change url schema from https to sc
        endpoint_url = get_session_endpoint_response["EndpointUrl"]
        auth_token = get_session_endpoint_response["AuthToken"]
        if endpoint_url.startswith("https://"):
            endpoint_url = endpoint_url.replace("https://", "sc://", 1)

        return f"{endpoint_url}:443/;use_ssl=true;x-aws-proxy-port=15002;x-aws-force-h2=true;x-aws-proxy-auth={auth_token}"

    def _wait_for_athena_session(self, session_id, timeout=120, poll_interval=2):
        """
        Wait until Athena session is started or timeout expires.
        """
        logger.debug(f"Waiting for Athena session {session_id} to be ready...")
        start_time = time.time()

        while True:
            try:
                response = self.athena_client.get_session(SessionId=session_id)
                state = response["Status"]["State"]
                time_delta = time.time() - start_time

                logger.debug(f"Session {session_id} state: {state}, elapsed: {time_delta:.1f}s")

                if state in ("CREATED", "IDLE", "BUSY"):
                    logger.debug(f"Session {session_id} is ready.")
                    return True
                elif state in ("FAILED", "TERMINATED", "TERMINATING"):
                    reason = response["Status"].get("StateChangeReason", "Unknown")
                    error_msg = f"Session {session_id} failed with state {state}. Reason: {reason}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                elif time_delta > timeout:
                    error_msg = (
                        f"Session {session_id} was not ready within the session start timeout."
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                time.sleep(poll_interval)
            except Exception as e:
                logger.error(f"Error checking session status: {e}")
                raise

    def _terminate_athena_session(self, session_id):
        """Terminate an Athena session."""
        try:
            response = self.athena_client.terminate_session(SessionId=session_id)
            logger.debug(f"Terminated session {session_id}")
            return response
        except Exception as e:
            logger.error(f"Error terminating session : {e}")
            raise
