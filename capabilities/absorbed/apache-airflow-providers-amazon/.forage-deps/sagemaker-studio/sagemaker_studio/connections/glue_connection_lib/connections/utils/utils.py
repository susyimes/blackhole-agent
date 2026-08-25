"""
Utility functions for Glue connection processing.
"""

import base64
import json
import logging
from typing import Any, Dict, Tuple, Union

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from ..constants import (
    CONNECTOR_TYPE,
    JDBC_CONNECTION_TYPES,
    ConnectionObjectKey,
    ConnectionPropertyKey,
)
from .jdbc_url import JdbcUrl

logger = logging.getLogger(__name__)


def get_vendor_from_url(full_url_to_use: str) -> Tuple[str, str, str]:
    """
    Extract vendor information from connection URL.

    Args:
        full_url_to_use: Database connection URL

    Returns:
        Tuple of (url, full_url, vendor_string) where:
        - url: simplified JDBC URL with vendor, host, and port
        - full_url: the original full URL passed in
        - vendor_string: the vendor name extracted from URL
    """
    jdbc_url = JdbcUrl.from_url(full_url_to_use)
    vendor_to_use = jdbc_url.get_vendor().value
    host = jdbc_url.get_host()
    port = jdbc_url.get_port()

    # Create simplified URL: jdbc:vendor://host:port
    url = f"jdbc:{vendor_to_use}://{host}:{port}"

    return url, full_url_to_use, vendor_to_use


def decrypt_encrypted_password(encrypted_password_field: str, kms_client: BaseClient) -> str:
    """
    Decrypt KMS-encrypted password with fallback to us-east-1.

    Args:
        encrypted_password_field: Base64-encoded encrypted password
        kms_client: Primary KMS client for decryption

    Returns:
        Decrypted plaintext password

    Raises:
        ValueError: If encrypted password field is empty
    """
    if not encrypted_password_field:
        raise ValueError("encrypted password field provided is null or empty")

    try:
        logger.debug("decrypted password done.")
        return _decrypt_string(encrypted_password_field, kms_client)
    except ClientError:
        logger.warning(
            "Second attempt to decrypt an encrypted password with us-east-1 as KMS region"
        )
        us_east_kms = boto3.client("kms", region_name="us-east-1")
        return _decrypt_string(encrypted_password_field, us_east_kms)


def _decrypt_string(encrypted_password_field: str, kms_client: BaseClient) -> str:
    """Internal decrypt function using specified KMS client."""
    logger.debug("Attempting to decrypt an encrypted password")
    decoded_bytes = base64.b64decode(encrypted_password_field)
    response = kms_client.decrypt(CiphertextBlob=decoded_bytes)  # type: ignore
    return response["Plaintext"].decode("utf-8")


def get_secret_options(
    option_map: Dict[str, Any], secrets_manager_client: BaseClient
) -> Dict[str, Any]:
    """Get secret options from Secrets Manager."""
    if "secretId" not in option_map:
        logger.debug("secretId is not provided.")
        return {}

    secret_id = str(option_map.get("secretId", ""))
    if not secret_id:
        raise ValueError("If secretId is provided, it cannot be empty.")

    try:
        response = secrets_manager_client.get_secret_value(SecretId=secret_id)  # type: ignore
        if response.get("SecretString"):
            logger.debug("got secrets options from secrets manager.")
            return json.loads(response["SecretString"])
        return {}
    except Exception as e:
        raise ValueError(f"Failed to retrieve or parse secret '{secret_id}': {str(e)}")


def get_connection_properties(connection: Dict[str, Any]) -> Dict[str, str]:
    """
    Get connection properties with V2 options resolved.

    Used by DynamicFrame. Merges ConnectionProperties and resolves V2 options
    if the connection is not legacy.

    Args:
        connection: AWS Glue Connection object

    Returns:
        Dictionary of connection properties

    Raises:
        ValueError: If connection is None
    """
    if connection is None:
        raise ValueError("Connection cannot be null for GlueConnectionWrapper")

    if not connection_properties_exist(connection):
        logger.debug("no connection/spark properties present.")
        return {}

    # Start with connection properties
    merged_map = dict(connection.get(ConnectionObjectKey.CONNECTION_PROPERTIES, {}))
    logger.debug("retrieved connection properties.")

    if not is_legacy_connection(connection):
        resolve_connection_v2_options(connection, merged_map)

    return merged_map


def resolve_connection_v2_options(
    connection: Dict[str, Any], connection_properties_map: Dict[str, str]
) -> None:
    """
    Resolve V2 connection options and add them to the properties map.

    This function modifies the connection_properties_map in-place by adding:
    1. Spark properties if present
    2. General V2 connection fields (secretId, authenticationType, connectionName)
    3. OAuth2 properties if applicable
    4. JDBC-related fields for JDBC connection types

    Args:
        connection: AWS Glue Connection object
        connection_properties_map: Dictionary to modify with resolved options
    """
    connection_type = connection.get(ConnectionObjectKey.CONNECTION_TYPE, "").lower()

    # 1. Add spark properties if present
    spark_properties = connection.get(ConnectionObjectKey.SPARK_PROPERTIES)
    if spark_properties:
        connection_properties_map.update(spark_properties)
        logger.debug("retrieved spark properties.")

    # 2. General handling for all V2 connections
    auth_config = connection.get(ConnectionObjectKey.AUTHENTICATION_CONFIGURATION, {})
    secret_id = None
    auth_type = None
    if auth_config:
        secret_id = auth_config.get("SecretArn")
        auth_type = auth_config.get("AuthenticationType")

        if secret_id:
            connection_properties_map.setdefault("secretId", secret_id)
        if auth_type:
            connection_properties_map.setdefault("authenticationType", auth_type)

        connection_name = connection.get(ConnectionObjectKey.NAME)
        if connection_name:
            connection_properties_map.setdefault("connectionName", connection_name)

    # Handle OAuth2 properties
    if auth_type == "OAUTH2":
        oauth2_props = auth_config.get("OAuth2Properties", {})
        oauth2_client_app = oauth2_props.get("OAuth2ClientApplication", {})
        client_id = oauth2_client_app.get("UserManagedClientApplicationClientId")
        if client_id:
            connection_properties_map.setdefault("clientId", client_id)

    # 3. Add JDBC-related fields for JDBC connection types
    if is_jdbc_connection_needed(connection_type):
        logger.debug("adding jdbc/mongodb options.")
        # For SSL
        connection_properties_map.setdefault(ConnectionPropertyKey.JDBC_ENFORCE_SSL, "false")
        # For secret ID (reuse the same secret_id from above)
        if secret_id:
            connection_properties_map.setdefault(ConnectionPropertyKey.SECRET_ID, secret_id)


def is_legacy_connection(connection: Dict[str, Any]) -> bool:
    """
    Check if connection uses legacy schema (version 1).

    Legacy connections don't have authenticationConfiguration field.
    Modern connections (v2) have authenticationConfiguration.

    Args:
        connection: AWS Glue Connection object

    Returns:
        True if legacy connection (schema v1), False if modern (schema v2)
    """
    is_legacy = connection.get(ConnectionObjectKey.AUTHENTICATION_CONFIGURATION) is None
    logger.debug(f"connection schema version: {1 if is_legacy else 2}.")
    return is_legacy


def connection_properties_exist(connection: Union[Dict[str, Any], None]) -> bool:
    """Check if connection has properties defined."""
    return bool(
        connection
        and (
            connection.get(ConnectionObjectKey.CONNECTION_PROPERTIES)
            or connection.get(ConnectionObjectKey.SPARK_PROPERTIES)
        )
    )


def is_jdbc_connection_needed(connection_type: str) -> bool:
    """Check if JDBC connection handling is needed."""
    connection_type_lower = connection_type.lower()

    if connection_type_lower in JDBC_CONNECTION_TYPES:
        return True

    if connection_type_lower in ("mongodb", "documentdb"):
        return True

    if connection_type_lower in CONNECTOR_TYPE["jdbc"]:
        return True

    return False
