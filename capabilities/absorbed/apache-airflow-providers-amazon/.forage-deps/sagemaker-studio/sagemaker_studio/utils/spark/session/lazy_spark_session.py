"""
Lazy Spark Session Initialization.

This module provides lazy loading functionality for Spark sessions, delaying
initialization until the first attribute access.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError
from pyspark.errors.exceptions.connect import SparkConnectGrpcException
from pyspark.sql.connect.session import SparkSession as _SparkSession

from sagemaker_studio.utils.spark.connection_resolver import (
    _resolve_connection_and_create_session_manager,
)
from sagemaker_studio.utils.spark.session.spark_session_manager import SparkSessionManager

logger = logging.getLogger("SparkConnect")

_MAX_RECONNECT_ATTEMPTS = 3


class LazySparkSession:
    """
    Lazy initializer for SparkSession.

    This class handles the lazy loading of Spark sessions, delaying the actual
    session creation until the first attribute access.
    """

    def __init__(
        self,
        session_manager: SparkSessionManager = None,
        *,
        connection_name: str = None,
        config=None,
        spark_conf: dict = None,
    ):
        """
        Initialize the lazy Spark session.

        Args:
            session_manager: Pre-resolved session manager (if None, resolved lazily on first access).
            connection_name: Connection name for deferred resolution.
            config: ClientConfig for deferred resolution.
            spark_conf: User-supplied Spark config overrides (highest priority in merge order).
        """
        self._spark = None
        self._session_manager = session_manager
        self._reconnect_attempts = 0
        # Deferred resolution params — used only when session_manager is None.
        self._connection_name = connection_name
        self._config = config
        self._spark_conf = spark_conf

    # TO-DO: Handle race condition with user executed code.
    def _async_auto_mount_catalogs(self):
        logger.debug("Mounting catalogs..")
        catalogs = self._session_manager.project.connection().catalogs
        queries = [f"USE `{catalog.name}`" for catalog in catalogs]
        executor = ThreadPoolExecutor(max_workers=5)

        futures = []
        for query in queries:
            futures.append(executor.submit(self._spark.sql, query))

        def run_final_query():
            # Wait for all previous queries to complete
            for future in futures:
                future.result()
            # Run the final USE query
            return self._spark.sql("USE spark_catalog")

        executor.submit(run_final_query)
        logger.debug("Initiated catalogs automount.")

    def _get_spark(self):
        """Get or create the SparkSession."""

        if self._spark is None:
            try:
                logger.debug("Initializing SparkSession...")
                session_start_time = time.time()

                # Record session start time
                self._session_start_time = session_start_time

                # Resolve session manager lazily if not already set.
                # All network calls (GetNotebook, GetConnection) happen here,
                # not at sparkutils.init() time.
                if self._session_manager is None:
                    self._session_manager = _resolve_connection_and_create_session_manager(
                        connection_name=self._connection_name,
                        config=self._config,
                        spark_conf=self._spark_conf,
                    )

                if self._spark_conf:
                    self._session_manager.set_user_spark_conf(self._spark_conf)

                # Use the session manager to create the session
                self._spark = self._session_manager.create()

                # Log session creation metric
                try:
                    from sagemaker_studio.utils.loggerutils import log_session_metric

                    session_type = LazySparkSession._SESSION_TYPE_MAP.get(
                        type(self._session_manager).__name__,
                        type(self._session_manager).__name__,
                    )
                    log_session_metric(
                        metric_name="SessionCreated",
                        session_id=self._session_manager.get_session_id(),
                        duration_ms=int((time.time() - session_start_time) * 1000),
                        additional_properties={"SessionType": session_type},
                    )
                except Exception as e:
                    logger.error(f"Failed to log session creation metric: {e}")

                self._async_auto_mount_catalogs()
                logger.debug("SparkSession initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize SparkSession: {e}")
                raise
        return self._spark

    def __getattr__(self, name):
        """Delegate attribute access to the underlying SparkSession."""
        try:
            getattr(self._get_spark(), "version")
            # Reset counter on successful connection
            self._reconnect_attempts = 0
        except SparkConnectGrpcException:
            self._reconnect_attempts += 1
            if self._reconnect_attempts > _MAX_RECONNECT_ATTEMPTS:
                raise RuntimeError(
                    f"Spark session reconnection failed after {_MAX_RECONNECT_ATTEMPTS} attempts. "
                    "Please check your network/VPC endpoint configuration and restart the kernel."
                )
            import warnings

            warnings.warn(
                "Spark session connection lost (session may have been terminated or timed out). "
                f"Automatically creating a new session (attempt {self._reconnect_attempts}/{_MAX_RECONNECT_ATTEMPTS}).",
                stacklevel=2,
            )
            logger.warning(
                "SparkConnectGrpcException caught — session terminated or connection lost, creating a new session."
            )
            self.stop()
        except ClientError as e:
            # Athena: session in STOPPED state
            if (
                e.response["Error"]["Code"] == "InvalidRequestException"
                and "STOPPED state" in e.response["Error"]["Message"]
            ):
                self._reconnect_attempts += 1
                if self._reconnect_attempts > _MAX_RECONNECT_ATTEMPTS:
                    raise RuntimeError(
                        f"Spark session reconnection failed after {_MAX_RECONNECT_ATTEMPTS} attempts."
                    )
                logger.warning("Spark session is stopped, creating a new session.")
                self.stop()
            # EMR Serverless: session terminated (ResourceNotFoundException from get_session_endpoint)
            elif e.response["Error"]["Code"] == "ResourceNotFoundException":
                self._reconnect_attempts += 1
                if self._reconnect_attempts > _MAX_RECONNECT_ATTEMPTS:
                    raise RuntimeError(
                        f"Spark session reconnection failed after {_MAX_RECONNECT_ATTEMPTS} attempts."
                    )
                logger.warning("EMR Serverless session not found, creating a new session.")
                self.stop()
            # Glue: session not found or in illegal state
            elif e.response["Error"]["Code"] in (
                "EntityNotFoundException",
                "IllegalSessionStateException",
            ):
                self._reconnect_attempts += 1
                if self._reconnect_attempts > _MAX_RECONNECT_ATTEMPTS:
                    raise RuntimeError(
                        f"Spark session reconnection failed after {_MAX_RECONNECT_ATTEMPTS} attempts."
                    )
                logger.warning(
                    f"Glue session error ({e.response['Error']['Code']}), creating a new session."
                )
                self.stop()
            else:
                raise e
        return getattr(self._get_spark(), name)

    def __repr__(self):
        """Return string representation of the SparkSession."""
        try:
            return repr(self._get_spark())
        except Exception as e:
            logger.error(f"Error getting Spark representation: {e}")
            return f"<LazySparkSession (error: {e})>"

    @property
    def __class__(self):
        """Faking the class identity. Without this, instance type would be LazySparkSession"""
        return _SparkSession

    def stop(self):
        """Stop the SparkSession and clean up resources."""
        logger.info("Stopping lazy Spark session...")

        # Log session duration metric
        if "_session_start_time" in self.__dict__:
            try:
                session_duration_ms = int((time.time() - self._session_start_time) * 1000)
                from sagemaker_studio.utils.loggerutils import log_session_metric

                session_type = (
                    LazySparkSession._SESSION_TYPE_MAP.get(
                        type(self._session_manager).__name__,
                        type(self._session_manager).__name__,
                    )
                    if self._session_manager
                    else "unknown"
                )
                log_session_metric(
                    metric_name="SessionStopped",
                    session_id=(
                        self._session_manager.get_session_id() if self._session_manager else None
                    ),
                    duration_ms=session_duration_ms,
                    additional_properties={"SessionType": session_type},
                )
            except Exception as e:
                logger.error(f"Failed to log session stop metric: {e}")

        # Stop the session manager if it exists
        if self._session_manager:
            try:
                self._session_manager.stop()
            except Exception as e:
                logger.error(f"Error while stopping session manager: {e}")

        # Reset the Spark session reference
        self._spark = None

        logger.info("Stopped lazy Spark session")

    def get_athena_session_id(self):
        """Backward-compatible: returns session ID only for Athena sessions."""
        from sagemaker_studio.utils.spark.session.athena.athena_spark_session_manager import (
            AthenaSparkSessionManager,
        )

        if self._session_manager and isinstance(self._session_manager, AthenaSparkSessionManager):
            return self._session_manager.get_session_id()

    def get_session_id(self):
        """Get the session ID from the underlying session manager."""
        if self._session_manager:
            return self._session_manager.get_session_id()
        return None

    # Maps session manager class names to {SERVICE}_{PROTOCOL} identifiers.
    # Leaves room for future protocols like LIVY.
    _SESSION_TYPE_MAP = {
        "AthenaSparkSessionManager": "ATHENA_SPARK_CONNECT",
        "EMRServerlessSparkSessionManager": "EMR_SERVERLESS_SPARK_CONNECT",
        "GlueSparkSessionManager": "GLUE_SPARK_CONNECT",
        "EmrEc2SparkSessionManager": "EMR_EC2_SPARK_CONNECT",
        "EmrEksSparkSessionManager": "EMR_EKS_SPARK_CONNECT",
    }

    def get_session_info(self) -> dict | None:
        """Get session metadata (public API for kernel and external consumers).

        Returns a dict with session_id and session_type, or None if no active session.
        session_type is resolved via _SESSION_TYPE_MAP from the manager's class name.
        """
        if not self._session_manager:
            return None
        session_id = self._session_manager.get_session_id()
        if not session_id:
            return None
        manager_class = type(self._session_manager).__name__
        return {
            "session_id": session_id,
            "session_type": self._SESSION_TYPE_MAP.get(manager_class, manager_class),
        }
