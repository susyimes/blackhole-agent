import logging

from sagemaker_studio.project import ClientConfig

logger = logging.getLogger()
logger.info("Importing sparkutils")

# Check if PySpark is available
try:
    from sagemaker_studio.utils.spark.session.lazy_spark_session import LazySparkSession

    _SPARK_AVAILABLE = True
except ImportError:
    _SPARK_AVAILABLE = False


def init(
    connection_name: str = None,
    config: ClientConfig = ClientConfig(),
    spark_conf: dict = None,
):
    if not _SPARK_AVAILABLE:
        raise RuntimeError("PySpark is not available.")

    # No network calls here — connection resolution is deferred to first spark.* access.
    # This keeps kernel startup decoupled from network (avoids VPC/PrivateLink timeout issues).
    logger.info(
        f"sparkutils.init() called, connection_name={connection_name}. "
        "Connection resolution deferred to first access."
    )
    return LazySparkSession(
        session_manager=None,
        connection_name=connection_name,
        config=config,
        spark_conf=spark_conf,
    )


# Re-export functions that were moved to connection_resolver to preserve the public API.
from sagemaker_studio.utils.spark.connection_resolver import get_spark_options  # noqa: F401, E402

logger.info("Finished importing sparkutils")
