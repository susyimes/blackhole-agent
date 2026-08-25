from enum import Enum

AIRFLOW_PREFIX = "AIRFLOW__WORKFLOWS__"
SPACE_ENV_VARIABLES_TO_MWAA_ENV_VARIABLES = {
    "DataZoneDomainId": f"{AIRFLOW_PREFIX}DATAZONE_DOMAIN_ID",
    "DataZoneProjectId": f"{AIRFLOW_PREFIX}DATAZONE_PROJECT_ID",
    "DataZoneEndpoint": f"{AIRFLOW_PREFIX}DATAZONE_ENDPOINT",
    "ProjectS3Path": f"{AIRFLOW_PREFIX}PROJECT_S3_PATH",
    "DataZoneDomainRegion": f"{AIRFLOW_PREFIX}DATAZONE_DOMAIN_REGION",
}
SAGEMAKER_METADATA_JSON_PATH = "/opt/ml/metadata/resource-metadata.json"


class S3PathForProject(Enum):
    DATALAKE_CONSUMER_GLUE_DB = "/data/catalogs/"
    DATALAKE_ATHENA_WORKGROUP = "/sys/athena/"
    WORKFLOW_TEMP_STORAGE = "/workflows/tmp/"
    WORKFLOW_OUTPUT_LOCATION = "/workflows/output/"
    EMR_EC2_LOG_DEST = "/sys/emr"
    EMR_EC2_CERTS = "/sys/emr/certs"
    EMR_EC2_LOG_BOOTSTRAP = "/sys/emr/boot-strap"
    WORKFLOW_PROJECT_FILES_LOCATION = "/workflows/project-files/"
    WORKFLOW_CONFIG_FILES_LOCATION = "/workflows/config-files/"
