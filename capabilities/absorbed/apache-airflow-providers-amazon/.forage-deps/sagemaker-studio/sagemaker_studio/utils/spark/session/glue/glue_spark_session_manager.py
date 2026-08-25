"""
Glue Spark Session Management.

This module provides the GlueSparkSessionManager class that creates and returns
a configured SparkSession object connected to Glue via Spark Connect.
"""

import datetime
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
from sagemaker_studio.utils.spark.session.glue.interceptors import CustomChannelBuilder
from sagemaker_studio.utils.spark.session.spark_config_builder import (
    apply_compatibility_mode_configs,
    build_spark_configs,
    generate_s3_access_grants_configs,
)
from sagemaker_studio.utils.spark.session.spark_session_manager import SparkSessionManager

_parent_logger = logging.getLogger("SparkConnect")
SparkSessionManager.setup_logger(_parent_logger, SPARK_CONNECT_LOG_FILE)
logger = logging.getLogger("SparkConnect.Glue")


class GlueSparkSessionManager(SparkSessionManager):
    """
    Creates and returns a SparkSession object connected to Glue via Spark Connect.

    This class handles the creation of a Glue interactive session (SessionType=SPARK_CONNECT)
    and returns a configured SparkSession that can be used directly for Spark operations.
    """

    # CreateSession fields a user may override via ClientConfig.overrides["glue"].
    # Keys match the sparkGlueProperties names so a user override and the connection
    # default resolve through the same lookup. maxCapacity, securityConfiguration and
    # timeout are optional — they are only sent to CreateSession when configured.
    _CONFIGURABLE_SESSION_FIELDS = (
        "glueVersion",
        "workerType",
        "numberOfWorkers",
        "idleTimeout",
        "maxCapacity",
        "securityConfiguration",
        "timeout",
    )

    def __init__(
        self,
        connection_name=None,
        config: ClientConfig = ClientConfig(),
        *,
        connection=None,
        spark_conf: dict = None,
    ):
        """
        Initialize the Glue Spark session manager.

        Args:
            connection_name (str): The connection name (backward compat, used if connection not provided).
            config (ClientConfig): Configuration for the client. CreateSession fields
                (glueVersion, workerType, numberOfWorkers, idleTimeout, maxCapacity,
                securityConfiguration, timeout) may be overridden via config.overrides["glue"];
                these take precedence over the connection's sparkGlueProperties. Spark Connect
                guards still apply (glueVersion floored to 5.1, idleTimeout capped at 15 minutes).
                maxCapacity is mutually exclusive with workerType/numberOfWorkers in the Glue
                CreateSession API — when maxCapacity is configured, workerType and numberOfWorkers
                are omitted from the request.
            connection: Pre-resolved Connection object (from sparkutils routing). Keyword-only.
            spark_conf (dict): Optional custom Spark configuration. Values override defaults.
        """
        self._connection = connection
        self.connection_name = connection_name
        self.config = config
        self.spark_conf = spark_conf
        self.glue_session_id = None
        self._spark_session = None
        self.glue_client = None
        self.sts_client = None
        self.project = None

    def _lazy_init(self):
        _utils = InternalUtils()
        region = _utils._get_domain_region()

        glue_override_config = self.config.overrides.get("glue", {})
        glue_endpoint_url = glue_override_config.get("endpoint_url")

        # User-configurable CreateSession sizing fields, supplied via
        # ClientConfig.overrides["glue"]. These take precedence over the values
        # derived from the connection's sparkGlueProperties. Only the recognized
        # keys are picked up; everything else in the "glue" override (e.g.
        # endpoint_url) is ignored here.
        self._glue_session_overrides = {
            key: glue_override_config[key]
            for key in self._CONFIGURABLE_SESSION_FIELDS
            if key in glue_override_config
        }
        if self._glue_session_overrides:
            logger.info(f"User-supplied Glue session overrides: {self._glue_session_overrides}")

        # Load custom Glue service model (includes GetSessionEndpoint API
        # not yet in the public botocore model).
        import botocore.loaders
        import botocore.session

        model_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "boto3_models",
        )
        if os.path.isdir(model_path):
            loader = botocore.loaders.Loader(extra_search_paths=[model_path])
            botocore_session = botocore.session.get_session()
            botocore_session.register_component("data_loader", loader)
            import boto3 as _boto3

            custom_session = _boto3.Session(botocore_session=botocore_session)
        else:
            import boto3 as _boto3

            custom_session = _boto3.Session()

        glue_kwargs = {"region_name": region}
        if glue_endpoint_url:
            glue_kwargs["endpoint_url"] = glue_endpoint_url

        self.glue_client = custom_session.client("glue", **glue_kwargs)
        self.sts_client = boto3.client("sts", region_name=region)
        if self.project is None:
            self.project = _ensure_project()

        # Use pre-resolved connection if available, otherwise look up
        connection = self._connection
        if connection is None:
            if self.connection_name:
                connection = self.project.connection(self.connection_name)
            else:
                connection = self.project.connection(type="SPARK_CONNECT")

        # Extract Glue session properties from connection props
        conn_data = getattr(connection, "_Connection__connection_data", {})
        props = conn_data.get("props", {}) if isinstance(conn_data, dict) else {}
        self._glue_props = props.get("sparkGlueProperties", {})

        # Extract GlueDefaultArgument and SparkConfiguration from connection configurations
        # (same as sessions package connection_transformer.py).
        self._connection_default_arguments = {}
        self._connection_spark_configs = {}
        configurations = conn_data.get("configurations", []) if isinstance(conn_data, dict) else []
        for config in configurations:
            if isinstance(config, dict):
                if config.get("classification") == "GlueDefaultArgument":
                    self._connection_default_arguments = config.get("properties", {})
                elif config.get("classification") == "SparkConfiguration":
                    self._connection_spark_configs = config.get("properties", {})
        if self._connection_spark_configs:
            logger.info(
                f"Loaded {len(self._connection_spark_configs)} connection-level spark configs"
            )

        # Compatibility mode (FTA): same logic as sessions package —
        # if --enable-lakeformation-fine-grained-access is false or absent, apply compat configs.
        # NOTE: Glue Spark Connect does NOT support FGAC yet. Force compatibility mode ON
        # regardless of the connection setting (which may have FGAC enabled for Livy sessions
        # on the same connection with glueVersion=5.0).
        self._is_compatibility_mode = True

        # Extract glueConnectionNames (plural) from physicalEndpoints[0] for multi-subnet
        # failover — consistent with sessions package connection_transformer.py.
        physical_endpoints = (
            conn_data.get("physicalEndpoints", []) if isinstance(conn_data, dict) else []
        )
        if len(physical_endpoints) > 1:
            logger.warning(
                f"Connection has {len(physical_endpoints)} physicalEndpoints, using first endpoint only"
            )
        endpoint = physical_endpoints[0] if physical_endpoints else {}
        self._glue_connection_names = endpoint.get("glueConnectionNames", [])
        if self._glue_connection_names:
            logger.info(
                f"Resolved glueConnectionNames from physicalEndpoints[0]: {self._glue_connection_names}"
            )
        elif self._glue_props.get("glueConnectionName"):
            self._glue_connection_names = [self._glue_props["glueConnectionName"]]
            logger.debug(f"glueConnectionNames fallback to singular: {self._glue_connection_names}")
        else:
            logger.debug("No glueConnectionNames or glueConnectionName found")

        logger.info(
            f"Glue connection props: glueVersion={self._glue_props.get('glueVersion')}, "
            f"numberOfWorkers={self._glue_props.get('numberOfWorkers')}, "
            f"workerType={self._glue_props.get('workerType')}, "
            f"is_compatibility_mode={self._is_compatibility_mode}"
        )
        logger.debug("Successfully created Glue client")

    def create(self):
        """
        Create and return a SparkSession connected to Glue.

        Returns:
            SparkSession: A configured SparkSession object.
        """
        if self._spark_session is not None:
            logger.debug("SparkSession already exists, returning existing session")
            return self._spark_session

        try:
            logger.debug("Creating SparkSession connected to Glue...")
            os.environ["SPARK_CONNECT_MODE_ENABLED"] = "1"
            self._lazy_init()

            # Create Glue session and get Spark Connect URL
            self.glue_session_id, spark_endpoint_url, endpoint_response = self._start_glue_session()

            # Create custom channel builder with gRPC interceptor for auto-refreshing
            # Glue auth tokens. Seed with initial token to avoid redundant API call.
            # AuthTokenExpirationTime is an epoch timestamp (seconds since Unix epoch).
            initial_token_expiry = endpoint_response.get("AuthTokenExpirationTime")
            if initial_token_expiry is not None and not isinstance(
                initial_token_expiry, datetime.datetime
            ):
                initial_token_expiry = datetime.datetime.fromtimestamp(
                    initial_token_expiry, tz=datetime.timezone.utc
                )

            custom_channel_builder = CustomChannelBuilder(
                self.glue_session_id,
                spark_endpoint_url,
                self.glue_client,
                initial_auth_token=endpoint_response.get("AuthToken"),
                initial_token_expiry=initial_token_expiry,
            )

            # Create SparkSession
            self._spark_session = (
                _SparkSession.builder.channelBuilder(custom_channel_builder)
                .appName("GlueSparkSession")
                .getOrCreate()
            )

            logger.debug("SparkSession created successfully")
            return self._spark_session

        except Exception as e:
            logger.error(f"Failed to create SparkSession: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Clean up any orphaned Glue session
            self.stop()
            raise

    def stop(self):
        """Stop the SparkSession and terminate the Glue session."""
        logger.debug(f"Stopping Glue spark session {self.glue_session_id}...")

        # Stop Spark session first (graceful gRPC close)
        if self._spark_session:
            try:
                self._spark_session.stop()
            except Exception as e:
                logger.error(f"Error while stopping Spark session: {e}")
            finally:
                self._spark_session = None

        # Then terminate the server-side Glue session
        if self.glue_session_id:
            try:
                self._stop_glue_session(self.glue_session_id)
            except Exception as e:
                logger.error(f"Error while stopping Glue spark session {self.glue_session_id}: {e}")
            finally:
                self.glue_session_id = None

        logger.debug("Stopped Glue spark session")

    def get_session_id(self):
        return self.glue_session_id

    def _get_execution_role_arn(self):
        """Get the execution role ARN for the Glue session.

        Resolution order (same as sessions package connection_transformer.py):
        1. project.iam_role — resolves to environmentUserRole from the IAM connection
        2. Fallback: ExecutionRoleArn from resource-metadata.json (same as sessions
           package's EXECUTION_ROLE_ARN constant)
        """
        try:
            return self.project.iam_role
        except Exception as e:
            logger.warning(
                f"Failed to get project.iam_role, falling back to metadata ExecutionRoleArn: {e}"
            )
            _utils = InternalUtils()
            role_arn = _utils._get_field_from_environment("ExecutionRoleArn")
            if role_arn:
                return role_arn
            raise RuntimeError(
                "Could not resolve execution role from project IAM connection or metadata"
            ) from e

    @sync_with_metrics("_start_glue_session")
    def _start_glue_session(self):
        """Create a Glue interactive session and get Spark Connect URL."""
        try:
            logger.debug("Starting Glue Spark Connect session...")

            user_id = self.project.user_id
            account_id = self._get_account_id()

            # Build CreateSession request from connection props, allowing the user to
            # override the sizing fields via ClientConfig.overrides["glue"].
            # Resolution per field: user override > connection prop > built-in default.
            # Defaults align with sessions package where applicable.
            # glueVersion default is 5.1 — Spark Connect is only supported from Glue 5.1+.
            # number_of_workers=10, idle_timeout=15 (minutes) match sessions package.
            glue_version = self._resolve_session_field("glueVersion", "5.1")
            # Spark Connect requires Glue 5.1+. Silently bump if the resolved version
            # (connection or user-supplied) is older.
            _glue_version_bumped = False
            try:
                if float(glue_version) < 5.1:
                    logger.info(
                        f"Glue version {glue_version} does not support Spark Connect, bumping to 5.1"
                    )
                    _glue_version_bumped = True
                    glue_version = "5.1"
            except (ValueError, TypeError):
                pass
            worker_type = self._resolve_session_field("workerType", "G.1X")
            number_of_workers = self._resolve_session_field("numberOfWorkers", 10)
            idle_timeout = self._resolve_session_field("idleTimeout", 15)
            # Cap idle timeout to 15 min for interactive Spark Connect sessions
            # (consistent with EMR-S and Athena Spark Connect behavior). Applies to
            # user-supplied values too.
            if int(idle_timeout) > 15:
                idle_timeout = 15

            # Optional CreateSession fields — only sent when configured (user override
            # or connection prop). Default is None so unset fields are omitted from the
            # request rather than forcing a value.
            # - maxCapacity: DPU count; mutually exclusive with workerType/numberOfWorkers
            #   in the Glue CreateSession API, so those are dropped when this is set.
            # - securityConfiguration: name of a Glue security configuration (encryption).
            # - timeout: total session lifetime in minutes (distinct from idleTimeout).
            max_capacity = self._resolve_session_field("maxCapacity", None)
            security_configuration = self._resolve_session_field("securityConfiguration", None)
            session_timeout = self._resolve_session_field("timeout", None)

            # Build Glue service-specific configs
            service_configs = {}

            # Compatibility mode (FTA): apply LF compat configs when supported.
            # Version gate: FTA only supported for Glue >= 5.0 (same as sessions package).
            if self._is_fta_supported(glue_version):
                service_configs.update(apply_compatibility_mode_configs({}))
                logger.info("FTA supported — applying compatibility mode configs")
            else:
                logger.info("FTA not supported — skipping compatibility mode configs")

            # Merge OpenLineage configs for Glue >= 5.0 (same as sessions package).
            # Includes custom_environment_variables and JOB_NAME for parity.
            try:
                if float(glue_version) >= 5.0:
                    service_configs.update(
                        {
                            "spark.extraListeners": "io.openlineage.spark.agent.OpenLineageSparkListener",
                            "spark.openlineage.transport.type": "amazon_datazone_api",
                            "spark.openlineage.transport.domainId": self.project.domain_id,
                            "spark.openlineage.facets.custom_environment_variables": "[AWS_DEFAULT_REGION;GLUE_VERSION;GLUE_COMMAND_CRITERIA;GLUE_PYTHON_VERSION;]",
                            "spark.glue.accountId": account_id,
                        }
                    )
                    # JOB_NAME for interactive sessions (same as sessions package)
                    if user_id:
                        service_configs["spark.glue.JOB_NAME"] = (
                            f"Interactive/{self.project.id}/{user_id}"
                        )
                    logger.info("OpenLineage configs added for Glue >= 5.0")
            except (ValueError, TypeError):
                pass

            # Merge S3 Access Grants configs for Glue >= 5.0 — check DataZone environment
            # (consistent with sessions package which checks is_s3_ag_enabled_for_environment).
            try:
                if float(glue_version) >= 5.0:
                    s3ag_configs = self._get_s3_access_grants_configs()
                    if s3ag_configs:
                        service_configs.update(s3ag_configs)
                        logger.info("S3 Access Grants configs added for Glue >= 5.0")
            except (ValueError, TypeError):
                pass

            # Assemble final spark configs using build_spark_configs (consistent with EMR-S/Athena).
            spark_configs = build_spark_configs(
                account_id=account_id,
                service_configs=service_configs,
                connection_configs=self._connection_spark_configs,
                user_configs=self.spark_conf,
            )

            # --- DefaultArguments ---
            # Sessions package passes Livy-specific flags (--enable-spark-ui, --enable-glue-datacatalog,
            # --enable-auto-scaling, --datalake-formats). These are also passed for Spark Connect
            # sessions to maintain feature parity (Glue honors them regardless of session type).
            default_arguments = {
                "--enable-spark-live-ui": "true",
                "--enable-spark-ui": "true",
                "--enable-glue-datacatalog": "true",
                "--enable-auto-scaling": "true",
                "--datalake-formats": "iceberg",
            }

            # S3 log paths for Spark UI and system logs (same as sessions package).
            # Sessions package reads PROJECT_S3_PATH from resource-metadata.json;
            # SDK uses the Project.s3.root property for consistent access.
            project_s3_path = self.project.s3.root
            if project_s3_path:
                if project_s3_path.endswith("/"):
                    project_s3_path = project_s3_path[:-1]
                default_arguments["--spark-event-logs-path"] = (
                    f"{project_s3_path}/glue/glue-spark-events-logs/"
                )
                default_arguments["--spark-logs-s3-uri"] = (
                    f"{project_s3_path}/glue/glue-spark-system-logs/"
                )
            else:
                logger.warning(
                    "ProjectS3Path not found, skipping --spark-event-logs-path and --spark-logs-s3-uri"
                )

            # Glue expects spark configs via the --conf key in DefaultArguments.
            # Format: {"--conf": "spark.k1=v1 --conf spark.k2=v2 ..."}
            # This matches dict_to_string() in the sessions package.
            conf_value = " --conf ".join(f"{k}={v}" for k, v in spark_configs.items())
            default_arguments["--conf"] = conf_value

            # Merge connection-level GlueDefaultArgument properties into DefaultArguments
            # (same as sessions package: default_arguments.update(self.connection_details.default_arguments)).
            if self._connection_default_arguments:
                default_arguments.update(self._connection_default_arguments)
                logger.info("Connection-level GlueDefaultArgument merged into DefaultArguments")

            # Force FGAC off for Spark Connect sessions (not yet supported).
            # This overrides any connection-level setting that may have FGAC enabled for Livy.
            default_arguments["--enable-lakeformation-fine-grained-access"] = "false"

            # Session ID format: {project_id}-{uuid} — matches sessions package convention.
            new_session_id = f"{self.project.id}-{uuid.uuid4()}"

            # --- Glue connection names ---
            # Sessions package passes glueConnectionName(s) from connection props via
            # Connections param for VPC/network access. Uses glueConnectionNames (plural)
            # from physicalEndpoints[0] for multi-subnet failover.
            connections_list = self._glue_connection_names.copy()

            # RequestOrigin: interactive vs scheduled (same as sessions package).
            _utils2 = InternalUtils()
            metadata_exists = _utils2._get_field_from_environment("SpaceName") is not None
            request_origin = (
                "SageMakerUnifiedStudio_NotebookRun"
                if metadata_exists
                else "SageMakerUnifiedStudio_NotebookScheduledRun"
            )

            create_params = {
                "Id": new_session_id,
                "Role": self._get_execution_role_arn(),
                "Command": {"Name": "glueetl"},
                "GlueVersion": str(glue_version),
                "IdleTimeout": int(idle_timeout),
                # Spark Connect only: SessionType field not used by Livy sessions
                "SessionType": "SPARK_CONNECT",
                "DefaultArguments": default_arguments,
                "RequestOrigin": request_origin,
                "Tags": {
                    "AmazonDataZoneSessionOwner": user_id,
                    "AmazonDataZoneProject": self.project.id,
                },
            }

            # MaxCapacity is mutually exclusive with WorkerType/NumberOfWorkers in the
            # Glue CreateSession API. When the user/connection sets maxCapacity, send it
            # and omit the worker fields; otherwise use the worker-based sizing.
            if max_capacity is not None:
                create_params["MaxCapacity"] = float(max_capacity)
                logger.info(
                    f"Using MaxCapacity={create_params['MaxCapacity']} "
                    f"(WorkerType/NumberOfWorkers omitted)"
                )
            else:
                create_params["WorkerType"] = worker_type
                create_params["NumberOfWorkers"] = int(number_of_workers)

            # Optional pass-through fields — only included when configured.
            if security_configuration is not None:
                create_params["SecurityConfiguration"] = security_configuration
            if session_timeout is not None:
                create_params["Timeout"] = int(session_timeout)

            if connections_list:
                create_params["Connections"] = {"Connections": connections_list}

            create_response = self.glue_client.create_session(**create_params)
            session = create_response.get("Session", {})
            session_id = session.get("Id", new_session_id)
            logger.debug(f"Created Glue session: {session_id}")

            # Wait for session to be READY
            self._wait_for_glue_session(session_id)

            # Spark Connect only: Get endpoint URL and auth token via GetSessionEndpoint.
            # Livy sessions don't use this API — they communicate via REST.
            # Glue may return InternalServiceException or OperationTimeoutException transiently
            # when the Spark Connect endpoint is still initializing after session reaches READY.
            # Retry with backoff (consistent with integration doc section 6).
            logger.debug("Getting session endpoint URL and auth token...")
            raw_endpoint_response = self._get_session_endpoint_with_retry(session_id)

            # GetSessionEndpoint returns {SparkConnect: {Url, AuthToken, AuthTokenExpirationTime}}.
            # Unwrap the SparkConnect wrapper so downstream code can access fields directly.
            endpoint_response = raw_endpoint_response.get("SparkConnect", raw_endpoint_response)

            # Spark Connect only: Construct sc:// URL for gRPC channel.
            spark_connect_url = self._construct_spark_endpoint_url(endpoint_response)
            logger.debug("Successfully constructed Spark connect URL")

            if _glue_version_bumped:
                print(
                    f"Glue 5.1 session created for connection: {self.connection_name}.",
                    flush=True,
                )
            else:
                print(f"Session created for connection: {self.connection_name}.", flush=True)

            return session_id, spark_connect_url, endpoint_response

        except Exception as e:
            logger.error(f"Failed to create Glue Spark session: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _resolve_session_field(self, key, default):
        """Resolve a CreateSession sizing field with user override precedence.

        Resolution order: ClientConfig.overrides["glue"][key] (user)
        > connection sparkGlueProperties[key] > built-in default.

        Args:
            key: sparkGlueProperties field name (e.g. "workerType").
            default: built-in default if neither user nor connection supplies a value.
        """
        if key in self._glue_session_overrides:
            return self._glue_session_overrides[key]
        return self._glue_props.get(key, default)

    def _is_fta_supported(self, glue_version) -> bool:
        """Check if FTA (compatibility mode) is supported for this Glue session.

        Consistent with sessions package GlueSession._is_fta_supported:
        requires compatibility mode enabled AND glueVersion >= 5.0.
        """
        if not self._is_compatibility_mode:
            return False
        try:
            return float(glue_version) >= 5.0
        except (ValueError, TypeError):
            return False

    def _get_s3_access_grants_configs(self) -> dict:
        """Get S3 Access Grants spark configs (shared implementation in spark_config_builder)."""
        return generate_s3_access_grants_configs(getattr(self, "project", None))

    def _get_domain_id(self) -> str:
        """Get the DataZone domain ID for OpenLineage config.

        Deprecated: prefer self.project.domain_id directly.
        """
        return self.project.domain_id or ""

    def _construct_spark_endpoint_url(self, endpoint_response) -> str:
        """Construct the sc:// URL from GetSessionEndpoint response.

        Spark Connect only: Glue returns the URL already in sc:// format (e.g.,
        sc://s-xxx.sessions.glue.us-east-2.amazonaws.com).

        The auth token is URL-encoded because it contains base64 characters (=)
        that PySpark's URL parser splits on. PySpark will unquote it back when
        extracting parameters.
        """
        from urllib.parse import quote

        endpoint_url = endpoint_response["Url"]
        auth_token = endpoint_response["AuthToken"]

        # URL-encode the token: = becomes %3D, PySpark unquotes it back
        encoded_token = quote(auth_token, safe="")

        return f"{endpoint_url}:443/;use_ssl=true;x-aws-proxy-auth={encoded_token}"

    def _get_account_id(self):
        """Get the AWS account ID for catalog and session configuration."""
        _utils = InternalUtils()
        account_id = _utils._get_account_id()

        if not account_id:
            response = self.sts_client.get_caller_identity()
            account_id = response["Account"]

        return account_id

    def _get_user_id_account_id(self):
        """Deprecated: use self.project.user_id and self._get_account_id() directly."""
        return self.project.user_id, self._get_account_id()

    def _wait_for_glue_session(self, session_id, timeout=120, poll_interval=2):
        """Wait until Glue session is READY or timeout expires.

        Glue session states: PROVISIONING -> READY -> BUSY.
        Terminal states: FAILED, TIMEOUT, STOPPING, STOPPED.
        """
        logger.debug(f"Waiting for Glue session {session_id} to be ready...")
        print("Waiting for Glue session to be ready...", flush=True)
        start_time = time.time()
        last_state = None

        while True:
            try:
                response = self.glue_client.get_session(Id=session_id)
                session = response.get("Session", {})
                state = session.get("Status", "UNKNOWN")
                time_delta = time.time() - start_time

                if state != last_state:
                    logger.debug(f"Session {session_id} state: {state}, elapsed: {time_delta:.1f}s")
                    last_state = state

                if state in ("READY", "BUSY"):
                    logger.debug(f"Session {session_id} is ready.")
                    return True
                elif state in ("FAILED", "TIMEOUT", "STOPPING", "STOPPED"):
                    error_msg_detail = session.get("ErrorMessage", "Unknown")
                    error_msg = f"Session {session_id} failed with state {state}. Reason: {error_msg_detail}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                elif time_delta > timeout:
                    error_msg = (
                        f"Session {session_id} was not ready within the session start timeout."
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                time.sleep(poll_interval)
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"Error checking Glue session {session_id} status: {e}")
                raise

    def _get_session_endpoint_with_retry(self, session_id, max_retries=1, backoff=2):
        """Call GetSessionEndpoint with retry for transient errors.

        Glue may return InternalServiceException or OperationTimeoutException when the
        Spark Connect endpoint is still initializing after session reaches READY state.
        Retry once after 2s backoff before giving up (per integration doc section 6).
        If retry fails, the error propagates and create() calls stop() to clean up,
        then LazySparkSession will auto-recover by recreating the session.
        """
        from botocore.exceptions import ClientError

        retryable_codes = ("InternalServiceException", "OperationTimeoutException")
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return self.glue_client.get_session_endpoint(SessionId=session_id)
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code in retryable_codes and attempt < max_retries:
                    wait = backoff
                    request_id = e.response.get("ResponseMetadata", {}).get("RequestId", "unknown")
                    logger.warning(
                        f"GetSessionEndpoint returned {error_code} (attempt {attempt + 1}/{max_retries + 1}), "
                        f"RequestId={request_id}, retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
        raise last_error  # should not reach here

    def _stop_glue_session(self, session_id):
        """Stop a Glue session (same as sessions package — uses StopSession, not DeleteSession)."""
        try:
            response = self.glue_client.stop_session(Id=session_id)
            logger.debug(f"Stopped Glue session {session_id}")
            return response
        except Exception as e:
            logger.error(f"Error stopping Glue session {session_id}: {e}")
            raise
