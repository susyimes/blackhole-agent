import logging
from dataclasses import dataclass
from typing import List

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.data_models import ClientConfig
from sagemaker_studio.exceptions import AWSClientException

logger = logging.getLogger(__name__)

_DEFAULT_SPARK_CONNECT_CONNECTION_NAMES = [
    "default.athena.spark",
    "serverless.spark",
]


@dataclass
class ConnectionService:
    """
    Provides methods for interacting with connections within a SageMaker Unified Studio project.

    Args:
        project_id (str): The unique identifier of the project.
        domain_id (str): The unique identifier of the domain.
        datazone_api (BaseClient): The DataZone client.
        glue_api (BaseClient): The Glue client.
    """

    def __init__(
        self,
        project_id: str,
        domain_id: str,
        datazone_api: BaseClient,
        glue_api: BaseClient,
        secrets_manager_api: BaseClient,
        kms_api: BaseClient,
        project_config: ClientConfig,
    ):
        """
        Initializes a new instance of the ConnectionService class.

        Args:
            project_id (str): The unique identifier of the project.
            domain_id (str): The unique identifier of the domain.
            datazone_api (BaseClient): The DataZone client.
            glue_api (BaseClient): The Glue client.
            kms_api (BaseClient): The KMS client.
        """
        self.project_id = project_id
        self.domain_id = domain_id
        self.datazone_api = datazone_api
        self.glue_api = glue_api
        self.secrets_manager_api = secrets_manager_api
        self.project_config = project_config
        self.kms_api = kms_api

    def get_connection_by_name(self, name: str) -> Connection:
        """
        Retrieves a connection by its name.

        Args:
            name (str): The name of the connection.

        Returns:
            Connection: The connection object.

        Raises:
            AttributeError: If no connection is found with the specified name.
            RuntimeError: If the user does not have access to the connection.
        """
        connection_list_response = self.datazone_api.list_connections(  # type: ignore
            domainIdentifier=self.domain_id, projectIdentifier=self.project_id, name=name
        )
        connections = connection_list_response.get("items", [])
        if connections:
            try:
                connection_response = self.datazone_api.get_connection(  # type: ignore
                    domainIdentifier=self.domain_id,
                    identifier=connections[0].get("connectionId"),
                    withSecret=True,
                )
                connection_instance = Connection(
                    connection_data=connection_response,
                    glue_api=self.glue_api,
                    datazone_api=self.datazone_api,
                    secrets_manager_api=self.secrets_manager_api,
                    kms_api=self.kms_api,
                    project_config=self.project_config,
                )
                return connection_instance
            except ClientError as e:
                raise RuntimeError(f"Unable to access connection '{name}', {AWSClientException(e)}")
        raise AttributeError(f"No connection found with name '{name}'")

    def get_connection_by_id(self, connection_id: str) -> Connection:
        """
        Retrieves a connection by its ID.

        Args:
            connection_id (str): The ID of the connection.

        Returns:
            Connection: The connection object.

        Raises:
            ClientError: If the user does not have access to the connection or if the connection is not found.
        """
        try:
            connection_response = self.datazone_api.get_connection(  # type: ignore
                domainIdentifier=self.domain_id,
                identifier=connection_id,
                withSecret=True,
            )
            connection_instance = Connection(
                connection_data=connection_response,
                glue_api=self.glue_api,
                datazone_api=self.datazone_api,
                secrets_manager_api=self.secrets_manager_api,
                kms_api=self.kms_api,
                project_config=self.project_config,
            )
            return connection_instance
        except ClientError as e:
            # Re-raise the ClientError with additional context
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            raise ClientError(
                error_response={"Error": {"Code": error_code, "Message": error_message}},
                operation_name=e.operation_name,
            ) from e

    def get_connection_by_type(self, type: str) -> Connection:
        """
        Retrieves a connection by its type.

        For SPARK_CONNECT, prefers the Athena connection (identified by athenaProperties in props)
        as the default fallback. Falls back to the first connection if no Athena connection is found.

        Args:
            type (str): The type of the connection.

        Returns:
            Connection: The connection object.

        Raises:
            AttributeError: If no connection is found with the specified type.
            RuntimeError: If the user does not have access to the connection.
        """
        connection_list_response = self.datazone_api.list_connections(  # type: ignore
            domainIdentifier=self.domain_id, projectIdentifier=self.project_id, type=type
        )
        connections = connection_list_response.get("items", [])
        if connections:
            connection_id = connections[0].get("connectionId")
            if type == "SPARK_CONNECT":
                athena_candidates = [
                    c for c in connections if "athenaProperties" in c.get("props", {})
                ]
                if athena_candidates:
                    # Tiebreaker: prefer the well-known default name if present among candidates
                    default = next(
                        (
                            c
                            for c in athena_candidates
                            if c.get("name") in _DEFAULT_SPARK_CONNECT_CONNECTION_NAMES
                        ),
                        athena_candidates[0],
                    )
                    connection_id = default.get("connectionId")
                    logger.info(
                        f"Resolved default Athena Spark Connect connection: id={connection_id}, name={default.get('name')}"
                    )
                else:
                    logger.info(
                        f"No Athena connection (athenaProperties) found among {len(connections)} SPARK_CONNECT connections, using first: id={connection_id}"
                    )
            try:
                connection_response = self.datazone_api.get_connection(  # type: ignore
                    domainIdentifier=self.domain_id,
                    identifier=connection_id,
                    withSecret=True,
                )
                connection_instance = Connection(
                    connection_data=connection_response,
                    glue_api=self.glue_api,
                    datazone_api=self.datazone_api,
                    secrets_manager_api=self.secrets_manager_api,
                    kms_api=self.kms_api,
                    project_config=self.project_config,
                )
                return connection_instance
            except ClientError as e:
                raise RuntimeError(
                    f"Unable to access connection '{connection_id}', {AWSClientException(e)}"
                )
        raise AttributeError(f"No connection found with type '{type}'")

    def list_connections(self) -> List[Connection]:
        """
        Retrieves a list of all connections in the project.

        Returns:
            List[Connection]: A list of connection objects.
        """
        connection_info_list: List[Connection] = []
        next_token = None
        first_call = True
        try:
            while next_token is not None or first_call:
                first_call = False
                params = {"domainIdentifier": self.domain_id, "projectIdentifier": self.project_id}
                if next_token:
                    params["nextToken"] = next_token
                connection_list_response = self.datazone_api.list_connections(**params)  # type: ignore
                connections = connection_list_response.get("items", [])
                for connection in connections:
                    connection_instance = Connection(
                        connection_data=connection,
                        glue_api=self.glue_api,
                        datazone_api=self.datazone_api,
                        secrets_manager_api=self.secrets_manager_api,
                        kms_api=self.kms_api,
                        project_config=self.project_config,
                    )
                    connection_info_list.append(connection_instance)
                next_token = connection_list_response.get("nextToken")
        except ClientError as e:
            raise RuntimeError(
                f"Encountered an error while listing connections for project: {self.project_id} in domain: {self.domain_id}, {AWSClientException(e)}"
            )

        return connection_info_list
