"""
Spark configuration assembly with a layered override model.

Config priority (last wins):
  1. Base configs — shared across all Spark Connect backends
  2. Service-specific configs — per-backend adjustments (e.g., FTA, S3AG)
  3. Connection-level configs — from the DataZone connection's SparkConfiguration
  4. User-provided spark_conf — passed via sparkutils.init(spark_conf={...})
"""

import logging

from sagemaker_studio.utils._internal import InternalUtils
from sagemaker_studio.utils.spark.connection_resolver import _ensure_project

CATALOG_LIMIT = 7

_utils = InternalUtils()
_region = _utils._get_domain_region()
_stage = _utils._get_datazone_stage()

logger = logging.getLogger("SparkConnect")

DEFAULT_SPARK_PROPS = {
    "spark.hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
    "spark.sql.catalogImplementation": "hive",
    "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
}


def _get_account_id_from_arn(arn):
    return arn.split(":")[4]


def _generate_spark_catalog_spark_configs(account_id):
    return {
        "spark.sql.catalog.spark_catalog": "org.apache.iceberg.spark.SparkSessionCatalog",
        "spark.sql.catalog.spark_catalog.catalog-impl": "org.apache.iceberg.aws.glue.GlueCatalog",
        "spark.sql.catalog.spark_catalog.client.region": _region,
        "spark.sql.catalog.spark_catalog.glue.account-id": account_id,
        "spark.sql.catalog.spark_catalog.glue.id": account_id,
        "spark.sql.catalog.spark_catalog.glue.lakeformation-enabled": "true",
    }


def _generate_s3tables_spark_configs(proj):
    catalogs = proj.connection().catalogs
    conf = {}
    catalog_count = 0
    for catalog in catalogs:
        if catalog_count < CATALOG_LIMIT:
            if (
                catalog.type == "FEDERATED"
                and catalog.federated_catalog.get("ConnectionName") == "aws:s3tables"
            ):
                catalog_name = catalog.name
                conf[f"spark.sql.catalog.{catalog_name}"] = "org.apache.iceberg.spark.SparkCatalog"
                conf[f"spark.sql.catalog.{catalog_name}.catalog-impl"] = (
                    "org.apache.iceberg.aws.glue.GlueCatalog"
                )
                conf[f"spark.sql.catalog.{catalog_name}.warehouse"] = catalog.federated_catalog.get(
                    "Identifier"
                )
                conf[f"spark.sql.catalog.{catalog_name}.glue.id"] = catalog.id
                conf[f"spark.sql.catalog.{catalog_name}.glue.account-id"] = (
                    f"{_get_account_id_from_arn(catalog.resource_arn)}"
                )
                conf[f"spark.sql.catalog.{catalog_name}.glue.catalog-arn"] = catalog.resource_arn
                conf[f"spark.sql.catalog.{catalog_name}.client.region"] = _region
                conf[f"spark.sql.catalog.{catalog_name}.glue.lakeformation-enabled"] = "true"

                catalog_count += 1

    return conf


def _generate_glue_catalog_spark_configs(proj):
    """Add non-FEDERATED Glue catalogs (standard Data Catalog entries)."""
    catalogs = proj.connection().catalogs
    conf = {}
    catalog_count = 0
    for catalog in catalogs:
        if catalog_count >= CATALOG_LIMIT:
            break
        if catalog.type == "FEDERATED":
            continue
        catalog_name = catalog.spark_catalog_name
        conf[f"spark.sql.catalog.{catalog_name}"] = "org.apache.iceberg.spark.SparkCatalog"
        conf[f"spark.sql.catalog.{catalog_name}.catalog-impl"] = (
            "org.apache.iceberg.aws.glue.GlueCatalog"
        )
        conf[f"spark.sql.catalog.{catalog_name}.glue.id"] = catalog.id
        conf[f"spark.sql.catalog.{catalog_name}.glue.account-id"] = _get_account_id_from_arn(
            catalog.resource_arn
        )
        conf[f"spark.sql.catalog.{catalog_name}.glue.catalog-arn"] = catalog.resource_arn
        conf[f"spark.sql.catalog.{catalog_name}.client.region"] = _region
        conf[f"spark.sql.catalog.{catalog_name}.glue.lakeformation-enabled"] = "true"
        catalog_count += 1
    return conf


def apply_compatibility_mode_configs(spark_configs: dict) -> dict:
    """Apply Lake Formation compatibility mode configs for FTA-supported compute."""
    compatibility_spark_configs = {
        "spark.hadoop.fs.s3.credentialsResolverClass": "com.amazonaws.glue.accesscontrol.AWSLakeFormationCredentialResolver",
        "spark.hadoop.fs.s3.useDirectoryHeaderAsFolderObject": "true",
        "spark.hadoop.fs.s3.folderObject.autoAction.disabled": "true",
        "spark.sql.catalog.createDirectoryAfterTable.enabled": "true",
        "spark.sql.catalog.dropDirectoryBeforeTable.enabled": "true",
        "spark.sql.catalog.spark_catalog.glue.lakeformation-enabled": "true",
        "spark.sql.catalog.skipLocationValidationOnCreateTable.enabled": "true",
    }
    spark_configs.update(compatibility_spark_configs)
    return spark_configs


def generate_s3_access_grants_configs(proj) -> dict:
    """Get S3 Access Grants spark configs if enabled for the project's tooling environment.

    Shared by the Glue, EMR Serverless and EMR on EC2 session managers. Checks
    enableS3AccessGrantsForTools in the tooling environment's provisionedResources,
    consistent with SageMakerStudioDataEngineeringSessions.

    Returns an empty dict when S3AG is disabled, absent, or the lookup fails, so
    callers can merge the result unconditionally.
    """
    try:
        default_env = proj._sagemaker_studio_api.project_api.get_project_default_environment(
            proj.domain_id, proj.id
        )
        provisioned_resources = default_env.get("provisionedResources", [])
        s3ag_enabled = any(
            r.get("name") == "enableS3AccessGrantsForTools" and r.get("value", "").lower() == "true"
            for r in provisioned_resources
        )
        if s3ag_enabled:
            logger.info("S3 Access Grants enabled for Spark configuration")
            return {
                "spark.hadoop.fs.s3.s3AccessGrants.enabled": "true",
                "spark.hadoop.fs.s3.s3AccessGrants.fallbackToIAM": "true",
            }
    except Exception as e:
        logger.warning(f"Failed to check S3 Access Grants status: {e}")
    return {}


def _generate_irc_spark_configs(proj):
    """Generate Spark catalog configs for every Iceberg REST Catalog connection.

    Covers all connection types listed in SUPPORTED_IRC_GLUE_CONNECTION_TYPES. Each
    connection resolves to one Spark catalog per entry in its SOURCE_CATALOG_LIST.
    """
    import json

    from sagemaker_studio.connections.connection import SUPPORTED_IRC_GLUE_CONNECTION_TYPES

    conf = {}
    connections = proj.connections
    for connection in connections:
        if connection.type not in SUPPORTED_IRC_GLUE_CONNECTION_TYPES:
            continue

        spark_catalog_configs = connection._spark_catalog_configs()
        # Returns None when the connection has no backing Glue connection.
        if not spark_catalog_configs:
            continue

        source_catalog_list = spark_catalog_configs.get("SOURCE_CATALOG_LIST")
        if not source_catalog_list:
            continue

        rest_uri = spark_catalog_configs["INSTANCE_URL"]
        access_token = spark_catalog_configs["ACCESS_TOKEN"]
        # Polaris backed catalogs (currently Workday) scope requests to a realm.
        # Vendors that do not use a realm simply omit TENANT_ID.
        realm = spark_catalog_configs.get("TENANT_ID")

        for catalog_name in json.loads(source_catalog_list):
            catalog_prefix = f"spark.sql.catalog.{catalog_name}"
            conf[catalog_prefix] = "org.apache.iceberg.spark.SparkCatalog"
            conf[f"{catalog_prefix}.type"] = "rest"
            conf[f"{catalog_prefix}.uri"] = rest_uri
            conf[f"{catalog_prefix}.warehouse"] = catalog_name
            conf[f"{catalog_prefix}.token"] = access_token
            conf[f"{catalog_prefix}.header.X-Iceberg-Access-Delegation"] = "vended-credentials"
            if realm:
                conf[f"{catalog_prefix}.header.Polaris-Realm"] = realm

    return conf


def generate_spark_configs(account_id):
    """Generate base Spark properties shared across all backends."""
    spark_props = DEFAULT_SPARK_PROPS.copy()
    proj = _ensure_project()
    spark_props.update(_generate_spark_catalog_spark_configs(account_id))
    spark_props.update(_generate_s3tables_spark_configs(proj))
    spark_props.update(_generate_glue_catalog_spark_configs(proj))
    spark_props.update(_generate_irc_spark_configs(proj))
    return spark_props


def build_spark_configs(
    account_id: str,
    service_configs: dict = None,
    connection_configs: dict = None,
    user_configs: dict = None,
) -> dict:
    """Assemble final Spark properties by merging configuration layers.

    Args:
        account_id: AWS account ID for catalog configuration.
        service_configs: Service-specific overrides (Athena, EMR Serverless, etc.).
        connection_configs: Connection-level SparkConfiguration properties.
        user_configs: User-provided spark_conf (highest priority).

    Returns:
        Merged Spark properties dict ready to pass to the session start API.
    """
    # Layer 1: Base configs (shared across all backends)
    configs = generate_spark_configs(account_id)

    # Layer 2: Service-specific configs
    if service_configs:
        configs.update(service_configs)

    # Layer 3: Connection-level configs
    if connection_configs:
        configs.update(connection_configs)

    # Layer 4: User-provided spark_conf (highest priority)
    if user_configs:
        configs.update(user_configs)

    return configs


def extract_connection_spark_configs(connection) -> dict:
    """Extract SparkConfiguration properties from a DataZone connection object.

    Looks for a classification entry named "SparkConfiguration" in the connection's
    configurations list and returns its properties dict.

    Args:
        connection: A resolved Connection object.

    Returns:
        Dict of spark config key-value pairs, or empty dict if none found.
    """
    try:
        configurations = getattr(connection, "_Connection__connection_data", {}).get(
            "configurations", []
        )
        if isinstance(configurations, list):
            for config in configurations:
                if config.get("classification") == "SparkConfiguration":
                    props = config.get("properties", {})
                    if props:
                        logger.info(f"Loaded {len(props)} connection-level spark configs")
                    return props
    except Exception as e:
        logger.warning(f"Error reading connection spark configs: {e}")
    return {}
