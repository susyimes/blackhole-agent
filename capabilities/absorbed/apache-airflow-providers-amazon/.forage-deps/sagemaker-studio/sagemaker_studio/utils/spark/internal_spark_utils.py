"""Backward-compatibility shim — config logic now lives in spark_config_builder."""

# Re-exports for test backward compatibility
from sagemaker_studio import Project  # noqa: F401
from sagemaker_studio.utils.spark.session.spark_config_builder import CATALOG_LIMIT  # noqa: F401
from sagemaker_studio.utils.spark.session.spark_config_builder import _utils  # noqa: F401
from sagemaker_studio.utils.spark.session.spark_config_builder import logger  # noqa: F401
from sagemaker_studio.utils.spark.session.spark_config_builder import (  # noqa: F401
    DEFAULT_SPARK_PROPS,
    _generate_irc_spark_configs,
    _generate_s3tables_spark_configs,
    _generate_spark_catalog_spark_configs,
    _get_account_id_from_arn,
)
from sagemaker_studio.utils.spark.session.spark_config_builder import (  # noqa: F401
    _region as region,
)
from sagemaker_studio.utils.spark.session.spark_config_builder import _stage as stage  # noqa: F401
from sagemaker_studio.utils.spark.session.spark_config_builder import (  # noqa: F401
    generate_spark_configs,
)
