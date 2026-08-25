from typing import Any, Dict

from boto3 import Session
from botocore.client import BaseClient

from sagemaker_studio.credentials import CredentialsVendingService
from sagemaker_studio.projects import ProjectService


class GitCodeCommitClient:
    def __init__(
        self,
        project_api: ProjectService,
        datazone_api: BaseClient,
        domain_identifier: str,
        project_identifier: str,
    ):
        self.project_api = project_api
        self.datazone_api = datazone_api
        self.domain_identifier = domain_identifier
        self.project_identifier = project_identifier
        self.credentials_api = CredentialsVendingService(datazone_api, project_api)

    def get_clone_url(self, repository_id: str) -> Dict[str, Any]:
        code_commit_client = self._get_client()
        response = code_commit_client.get_repository(repositoryName=repository_id)
        return {"cloneUrl": response.get("repositoryMetadata", {}).get("cloneUrlHttp")}

    def _get_client(self):
        if self.domain_identifier is None or self.project_identifier is None:
            raise ValueError("Domain and project identifiers cannot be None")
        project_default_env = self.project_api.get_project_default_environment(
            domain_identifier=self.domain_identifier, project_identifier=self.project_identifier
        )
        region_name = project_default_env.get("awsAccountRegion", "")

        connection_credentials = (
            self.credentials_api.get_project_default_iam_connection_credentials(
                domain_identifier=self.domain_identifier,
                project_identifier=self.project_identifier,
            )
        )
        access_key_id = connection_credentials["accessKeyId"]
        secret_access_key = connection_credentials["secretAccessKey"]
        session_token = connection_credentials["sessionToken"]
        session: Session = Session(region_name)
        return session.client(
            service_name="codecommit",
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
        )
