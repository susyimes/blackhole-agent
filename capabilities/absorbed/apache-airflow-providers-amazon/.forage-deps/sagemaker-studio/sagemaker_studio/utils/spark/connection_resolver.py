"""
Connection resolution and session manager creation for Spark Connect.

Extracted from sparkutils to break the circular import between sparkutils
and lazy_spark_session. sparkutils imports LazySparkSession at module level,
and LazySparkSession needs _resolve_connection_and_create_session_manager at
runtime — keeping both in sparkutils created a cycle.
"""

import logging
import warnings
from functools import lru_cache

from sagemaker_studio.project import ClientConfig, Project
from sagemaker_studio.utils._internal import InternalUtils

logger = logging.getLogger()


def _resolve_connection_id_from_notebook(config: ClientConfig) -> str:
    """Resolve the default spark connection ID from notebook metadata.

    Delegates to InternalUtils._resolve_connection_id_from_notebook.
    """
    return InternalUtils()._resolve_connection_id_from_notebook(config)


@lru_cache(maxsize=1)
def _ensure_project():
    """Initialize Project on demand (cached singleton)."""
    return Project()


def _identify_service_from_props(connection) -> str:
    """Identify the backend service from the connection's props structure.

    Uses props-based identification (design doc Section 2.1):
    - sparkEmrProperties.computeArn contains "emr-serverless" → EMR_SERVERLESS
    - sparkEmrProperties.computeArn contains "emr-containers" → EMR_EKS
    - sparkEmrProperties.computeArn contains "elasticmapreduce" → EMR_EC2
    - sparkGlueProperties exists → GLUE
    - athenaProperties exists → ATHENA
    - Default → UNKNOWN (no recognized props)
    """
    try:
        conn_data = getattr(connection, "_Connection__connection_data", {})
        props = conn_data.get("props", {}) if isinstance(conn_data, dict) else {}

        # Check sparkEmrProperties.computeArn for EMR services
        compute_arn = props.get("sparkEmrProperties", {}).get("computeArn", "")
        if compute_arn:
            if "emr-serverless" in compute_arn:
                return "EMR_SERVERLESS"
            if "emr-containers" in compute_arn:
                return "EMR_EKS"
            if "elasticmapreduce" in compute_arn:
                return "EMR_EC2"
            logger.warning(f"Unrecognized computeArn pattern: {compute_arn}")
            return "UNKNOWN"

        # Check for Glue
        if "sparkGlueProperties" in props:
            return "GLUE"

        # Check for Athena
        if "athenaProperties" in props:
            return "ATHENA"

    except Exception as e:
        logger.warning(f"Error identifying service from props: {e}")

    logger.warning("No recognized props in SPARK_CONNECT connection")
    return "UNKNOWN"


def _create_session_manager(
    connection, connection_name, connection_id, config, is_explicit_choice=False, spark_conf=None
):
    """Route to the correct session manager based on connection type and props.

    Accepts both SPARK_CONNECT and SPARK connection types — DZ currently creates Glue
    connections with type=SPARK (not SPARK_CONNECT). The props-based service identification
    is the real routing signal, not the type string.

    Routing:
    - SPARK_CONNECT or SPARK type → identify service from props:
        - sparkEmrProperties.computeArn → EMR_SERVERLESS / EMR_EKS / EMR_EC2
        - sparkGlueProperties → GLUE
        - athenaProperties → ATHENA
        - Default → ATHENA
    - Unknown type:
        - If user explicitly chose this connection → raise error (don't silently give them Athena)
        - If no explicit choice (default path) → fall back to Athena
    """
    from sagemaker_studio.utils.spark.session.athena.athena_spark_session_manager import (
        AthenaSparkSessionManager,
    )
    from sagemaker_studio.utils.spark.session.emr_eks.emr_eks_spark_session_manager import (
        EmrEksSparkSessionManager,
    )
    from sagemaker_studio.utils.spark.session.emr_serverless.emr_serverless_spark_session_manager import (
        EMRServerlessSparkSessionManager,
    )
    from sagemaker_studio.utils.spark.session.glue.glue_spark_session_manager import (
        GlueSparkSessionManager,
    )

    def _raise_or_fallback_to_athena(msg, stacklevel=3):
        """Raise RuntimeError if user explicitly chose this connection, else fall back to Athena."""
        if is_explicit_choice:
            raise RuntimeError(msg)
        logger.warning(f"{msg} Falling back to Athena.")
        # Surface in notebook cell output so user is aware of the silent fallback.
        warnings.warn(f"{msg} Falling back to Athena Spark Connect.", stacklevel=stacklevel)
        return AthenaSparkSessionManager(config=config, spark_conf=spark_conf)

    def _validate_service(conn_type, service):
        """Validate the connection type and service combination. Raises on invalid configs."""
        if service == "UNKNOWN":
            raise RuntimeError(
                "Could not identify the Spark backend from the connection properties. "
                "Ensure the connection has valid athenaProperties, sparkEmrProperties, "
                "or sparkGlueProperties. Supported backends: Athena, EMR Serverless, EMR on EKS, EMR on EC2, Glue."
            )
        # SPARK type is only valid for Glue (DZ creates Glue connections with type=SPARK).
        if conn_type == "SPARK" and service != "GLUE":
            return _raise_or_fallback_to_athena(
                f"Connection type 'SPARK' is only supported for Glue connections. "
                f"Identified service '{service}' requires type 'SPARK_CONNECT'.",
                stacklevel=4,
            )
        return None

    conn_type = getattr(connection, "type", None)

    if conn_type in ("SPARK_CONNECT", "SPARK"):
        service = _identify_service_from_props(connection)
        logger.info(f"Connection type {conn_type}, identified service={service}")

        # Validate — raises or returns Athena fallback on invalid configs.
        fallback = _validate_service(conn_type, service)
        if fallback is not None:
            return fallback

        if service == "EMR_SERVERLESS":
            return EMRServerlessSparkSessionManager(
                connection=connection,
                connection_name=connection_name,
                config=config,
                spark_conf=spark_conf,
            )

        if service == "EMR_EKS":
            return EmrEksSparkSessionManager(
                connection=connection,
                connection_name=connection_name,
                config=config,
                spark_conf=spark_conf,
            )

        if service == "EMR_EC2":
            from sagemaker_studio.utils.spark.session.emr_ec2.emr_ec2_spark_session_manager import (
                EmrEc2SparkSessionManager,
            )

            return EmrEc2SparkSessionManager(
                connection=connection,
                connection_name=connection_name,
                config=config,
                spark_conf=spark_conf,
            )

        if service == "GLUE":
            return GlueSparkSessionManager(
                connection=connection,
                connection_name=connection_name,
                config=config,
                spark_conf=spark_conf,
            )

        if service == "UNKNOWN":
            raise RuntimeError(
                "Could not identify the Spark backend from the connection properties. "
                "Ensure the connection has valid athenaProperties or sparkEmrProperties "
                "with a recognized computeArn. Supported backends: Athena, EMR Serverless, EMR on EC2, EMR on EKS."
            )

        # Athena (default for SPARK_CONNECT)
        return AthenaSparkSessionManager(
            connection=connection,
            connection_name=connection_name,
            connection_id=connection_id,
            config=config,
            spark_conf=spark_conf,
        )

    # Unrecognized connection type for Spark Connect
    return _raise_or_fallback_to_athena(
        f"Connection type '{conn_type}' is not a recognized Spark Connect type. "
        "Verify that the connection type is SPARK_CONNECT or SPARK with the appropriate "
        "service properties (e.g., athenaProperties, sparkEmrProperties, sparkGlueProperties)."
    )


def get_spark_options(connection_name: str):
    """Get Spark options for a connection."""
    try:
        project = _ensure_project()
    except Exception as e:
        raise RuntimeError("Project is not initialized.") from e

    connection = project.connection(connection_name)
    return connection._spark_options()


def _resolve_connection_and_create_session_manager(
    connection_name: str = None,
    config: ClientConfig = None,
    spark_conf: dict = None,
):
    """Resolve the connection and create the appropriate session manager.

    Called lazily by LazySparkSession on first spark.* access. All network calls
    (GetNotebook, GetConnection) happen here, not at sparkutils.init() time.
    """
    import time

    config = config or ClientConfig()

    resolve_start = time.time()

    # Resolution priority: explicit name → notebook metadata → default Athena SPARK_CONNECT.
    connection_id = None
    is_explicit_choice = False
    if connection_name:
        logger.info(f"Resolving connection for connection_name={connection_name}")
        is_explicit_choice = True
    else:
        try:
            t0 = time.time()
            resolved_id = _resolve_connection_id_from_notebook(config)
            logger.info(f"Notebook metadata lookup took {int((time.time() - t0) * 1000)}ms")
            if resolved_id:
                connection_id = resolved_id
                is_explicit_choice = True
            else:
                logger.info("Falling back to default SPARK_CONNECT connection")
        except Exception as e:
            logger.warning(f"Notebook metadata lookup failed, falling back to default: {e}")

    project = _ensure_project()
    t0 = time.time()
    if connection_id:
        connection = project.connection(id=connection_id)
    elif connection_name:
        connection = project.connection(connection_name)
    else:
        connection = project.connection(type="SPARK_CONNECT")
    logger.info(f"Connection resolution took {int((time.time() - t0) * 1000)}ms")

    session_manager = _create_session_manager(
        connection,
        connection_name,
        connection_id,
        config,
        is_explicit_choice,
        spark_conf=spark_conf,
    )

    logger.info(
        f"Connection resolution and session manager creation took {int((time.time() - resolve_start) * 1000)}ms"
    )
    return session_manager
