"""
Constants for Glue Connection Library.
"""

from typing import Dict, List

# JDBC connection types that require JDBC-specific handling
JDBC_CONNECTION_TYPES = {
    "aurora",
    "mysql",
    "postgresql",
    "redshift",
    "sqlserver",
    "oracle",
    "jdbc",  # Generic JDBC type
}

# Connection type mappings for connector type determination
CONNECTOR_TYPE: Dict[str, List[str]] = {
    "jdbc": [
        "sqlserver",
        "postgresql",
        "oracle",
        "redshift",
        "mysql",
        "saphana",
        "teradata",
    ],
    "spark": [
        "snowflake",
        "mongodb",
        "documentdb",
        "dynamodb",
        "bigquery",
        "azuresql",
    ],
    "irc": [
        "workdayicebergrestcatalog",
        "databricksicebergrestcatalog",
        "snowflakeicebergrestcatalog",
        "icebergrestcatalog",
    ],
}

# Database type constants
POSTGRESQL = "postgresql"

# JDBC driver constants
POSTGRESQL_DRIVER = "org.postgresql.Driver"


class ConnectionObjectKey:
    """AWS Glue Connection object key constants.

    Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glue/client/get_connection.html#
    """

    CONNECTION_TYPE = "ConnectionType"
    CONNECTION_PROPERTIES = "ConnectionProperties"
    SPARK_PROPERTIES = "SparkProperties"
    NAME = "Name"
    AUTHENTICATION_CONFIGURATION = "AuthenticationConfiguration"


class SparkOptionsKey:
    """Connection options key constants (camelCase format from JDBCConf.as_map())."""

    USER = "user"
    PASSWORD = "password"
    VENDOR = "vendor"
    URL = "url"
    FULL_URL = "fullUrl"
    ENFORCE_SSL = "enforceSSL"
    CUSTOM_JDBC_CERT = "customJDBCCert"
    SKIP_CUSTOM_JDBC_CERT_VALIDATION = "skipCustomJDBCCertValidation"
    CUSTOM_JDBC_CERT_STRING = "customJDBCCertString"

    # Redshift-specific connection options
    AWS_IAM_ROLE = "aws_iam_role"
    TEMPORARY_AWS_ACCESS_KEY_ID = "temporary_aws_access_key_id"
    TEMPORARY_AWS_SECRET_ACCESS_KEY = "temporary_aws_secret_access_key"
    TEMPORARY_AWS_SESSION_TOKEN = "temporary_aws_session_token"
    FORWARD_SPARK_S3_CREDENTIALS = "forward_spark_s3_credentials"
    TEMPFORMAT = "tempformat"


class RedshiftOptionValues:
    """Redshift-specific option values."""

    TRUE = "true"
    AVRO_FORMAT = "AVRO"
    PARQUET_FORMAT = "PARQUET"


class ConnectionPropertyKey:
    """Connection property key constants matching AWS Glue ConnectionPropertyKey enum.

    Reference: https://docs.aws.amazon.com/AWSJavaSDK/latest/javadoc/com/amazonaws/services/glue/model/ConnectionPropertyKey.html
    """

    JDBC_ENFORCE_SSL = "JDBC_ENFORCE_SSL"
    SECRET_ID = "SECRET_ID"
    KAFKA_CLIENT_KEYSTORE_PASSWORD = "KAFKA_CLIENT_KEYSTORE_PASSWORD"
    KAFKA_CLIENT_KEY_PASSWORD = "KAFKA_CLIENT_KEY_PASSWORD"
    ENCRYPTED_PASSWORD = "ENCRYPTED_PASSWORD"
    PASSWORD = "PASSWORD"
    USERNAME = "USERNAME"
    CONNECTION_URL = "CONNECTION_URL"
    JDBC_CONNECTION_URL = "JDBC_CONNECTION_URL"
    CUSTOM_JDBC_CERT = "CUSTOM_JDBC_CERT"
    SKIP_CUSTOM_JDBC_CERT_VALIDATION = "SKIP_CUSTOM_JDBC_CERT_VALIDATION"
    CUSTOM_JDBC_CERT_STRING = "CUSTOM_JDBC_CERT_STRING"
