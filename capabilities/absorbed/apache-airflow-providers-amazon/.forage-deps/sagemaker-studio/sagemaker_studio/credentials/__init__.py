from dataclasses import dataclass
from datetime import datetime, timedelta

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio._openapi.models import GetDomainExecutionRoleCredentialsRequest
from sagemaker_studio.exceptions import AWSClientException
from sagemaker_studio.projects import ProjectService


@dataclass
class CredentialsVendingService:
    """
    Provides methods for retrieving AWS credentials for SageMaker Unified Studio projects and domains.

    Args:
        datazone_api (BaseClient): The DataZone client.
        project_api (ProjectService): The Project service.
    """

    def __init__(self, datazone_api: BaseClient, project_api: ProjectService):
        """
        Initializes a new instance of the CredentialsVendingService class.

        Args:
            datazone_api (BaseClient): The DataZone client.
            project_api (ProjectService): The Project service.
        """
        self.datazone_api: BaseClient = datazone_api
        self.project_api: ProjectService = project_api

    def get_project_default_iam_connection_credentials(
        self, domain_identifier: str, project_identifier: str
    ) -> dict:
        """
        Retrieves AWS credentials from the project's default IAM connection.

        Determines the appropriate IAM connection name based on domain mode
        (EXPRESS -> 'default.iam', STANDARD -> 'project.iam'), then calls
        GetConnection with withSecret=True to retrieve temporary credentials.

        Args:
            domain_identifier (str): The unique identifier of the domain.
            project_identifier (str): The unique identifier of the project.

        Returns:
            dict: A dictionary containing AWS credentials with keys:
                - accessKeyId (str)
                - secretAccessKey (str)
                - sessionToken (str)
                - expiration (str)
        """
        try:
            connection_id = self._get_default_iam_connection_id(
                domain_identifier=domain_identifier, project_identifier=project_identifier
            )
            connection_response = self.datazone_api.get_connection(  # type: ignore
                domainIdentifier=domain_identifier,
                identifier=connection_id,
                withSecret=True,
            )
            connection_credentials = connection_response.get("connectionCredentials")
            if not connection_credentials:
                raise ValueError("No credentials returned for default IAM connection")
            return {
                "accessKeyId": connection_credentials.get("accessKeyId", ""),
                "secretAccessKey": connection_credentials.get("secretAccessKey", ""),
                "sessionToken": connection_credentials.get("sessionToken", ""),
                "expiration": connection_credentials.get("expiration", ""),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                raise ValueError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise ValueError(
                    f"Unable to get IAM connection credentials: {AWSClientException(e)}"
                )

    def _get_default_iam_connection_id(
        self, domain_identifier: str, project_identifier: str
    ) -> str:
        """
        Determine the default IAM connection ID based on domain mode.
        Returns the connectionId for 'default.iam' (EXPRESS) or 'project.iam' (STANDARD).
        """
        connections = self.datazone_api.list_connections(  # type: ignore
            domainIdentifier=domain_identifier,
            projectIdentifier=project_identifier,
            type="IAM",
            name="default.iam",
        ).get("items", [])

        if not connections:
            connections = self.datazone_api.list_connections(  # type: ignore
                domainIdentifier=domain_identifier,
                projectIdentifier=project_identifier,
                type="IAM",
                name="project.iam",
            ).get("items", [])

        if not connections:
            raise ValueError("No default IAM connection found ('default.iam' or 'project.iam')")
        return connections[0].get("connectionId")

    def get_project_default_environment_credentials(
        self, domain_identifier: str, project_identifier: str
    ) -> dict:
        """
        Retrieves the credentials for the default environment of a project.

        .. deprecated::
            Use :meth:`get_project_default_iam_connection_credentials` instead.
            This method uses GetEnvironmentCredentials which is being removed.

        Args:
            domain_identifier (str): The unique identifier of the domain.
            project_identifier (str): The unique identifier of the project.

        Returns:
            dict: The AWS credentials for the default environment of the project.
        """
        # Delegate to the new connection-based method
        return self.get_project_default_iam_connection_credentials(
            domain_identifier=domain_identifier, project_identifier=project_identifier
        )

    def get_domain_execution_role_credential_in_space(self, domain_identifier: str):
        """
        Retrieves the domain execution role credentials for the specified domain.

        Args:
            domain_identifier (str): The unique identifier of the domain.

        Returns:
            dict: The AWS credentials for the domain execution role.
        """
        try:
            GetDomainExecutionRoleCredentialsRequest(domain_identifier)
        except Exception as e:
            raise e
        try:
            domain_exec_creds = self.datazone_api.get_domain_execution_role_credentials(  # type: ignore
                domainIdentifier=domain_identifier
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                raise ValueError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)
        return {
            "Version": 1,
            "AccessKeyId": domain_exec_creds.get("credentials", {}).get("accessKeyId", ""),
            "SecretAccessKey": domain_exec_creds.get("credentials", {}).get("secretAccessKey", ""),
            "SessionToken": domain_exec_creds.get("credentials", {}).get("sessionToken"),
            "Expiration": domain_exec_creds.get("credentials", {}).get(
                "expiration", datetime.now() + timedelta(minutes=20)
            ),
        }
