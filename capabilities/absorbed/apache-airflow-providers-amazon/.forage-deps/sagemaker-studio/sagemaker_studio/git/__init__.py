from typing import Optional

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio._openapi.models import GetCloneUrlRequest
from sagemaker_studio.exceptions import AWSClientException
from sagemaker_studio.git.git_code_commit_client import GitCodeCommitClient
from sagemaker_studio.git.git_code_connections_client import GitCodeConnectionsClient
from sagemaker_studio.projects import ProjectService


class GitService:
    def __init__(self, datazone_api: BaseClient, project_api: ProjectService):
        self.datazone_api = datazone_api
        self.project_api = project_api
        self.domain_identifier: Optional[str] = None
        self.project_identifier: Optional[str] = None

    def get_clone_url(self, domain_identifier: str, project_identifier: str):
        try:
            GetCloneUrlRequest(
                project_identifier=project_identifier, domain_identifier=domain_identifier
            )
        except Exception as e:
            raise e
        self.domain_identifier = domain_identifier
        self.project_identifier = project_identifier
        git_client = self._resolve_client()
        repository_id = self._get_repository_id()
        if not repository_id:
            raise ValueError(
                "No git repository provisioned for this project. "
                "Custom tooling blueprints may not include git resources."
            )
        try:
            clone_url = git_client.get_clone_url(repository_id)
            return clone_url
        except ClientError as e:
            raise RuntimeError(
                f"Encountered error retrieving clone_url for project {project_identifier} in domain {domain_identifier}",
                AWSClientException(e),
            )
        except Exception as e:
            raise e

    def _resolve_client(self):
        connection_arn = self._get_connection_arn()
        if not connection_arn:
            if not self.domain_identifier or not self.project_identifier:
                raise ValueError("Domain and project identifiers cannot be None")
            return GitCodeCommitClient(
                self.project_api, self.datazone_api, self.domain_identifier, self.project_identifier
            )
        else:
            return GitCodeConnectionsClient(connection_arn)

    def _get_connection_arn(self):
        provisioned_resources = self._get_provisioned_resources()
        git_connection_arn_value = None
        for resource in provisioned_resources:
            if resource.get("name") == "gitConnectionArn":
                git_connection_arn_value = resource.get("value")
                break
        return git_connection_arn_value

    def _get_repository_id(self):
        provisioned_resources = self._get_provisioned_resources()
        repository_id = None
        # Tooling's provisioned resources will either have a codeRepositoryName parameter if
        # the project uses CodeCommit or a gitFullRepositoryId parameter if the project uses CodeConnections. Both
        # parameters cannot be present for the same project.
        for resource in provisioned_resources:
            if (
                resource.get("name") == "codeRepositoryName"
                or resource.get("name") == "gitFullRepositoryId"
            ):
                repository_id = resource.get("value")
                break
        return repository_id

    def _get_provisioned_resources(self):
        if not self.domain_identifier or not self.project_identifier:
            raise ValueError("Domain and project identifiers cannot be None")
        project_def_env = self.project_api.get_project_default_environment(
            domain_identifier=self.domain_identifier, project_identifier=self.project_identifier
        )
        if not project_def_env:
            raise ValueError("Project Default Environment Does Not Exist")
        provisioned_resources = project_def_env.get("provisionedResources", [])
        return provisioned_resources
