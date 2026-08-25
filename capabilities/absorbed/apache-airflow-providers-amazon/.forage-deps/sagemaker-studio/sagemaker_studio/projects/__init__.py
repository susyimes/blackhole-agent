from typing import Optional

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio.exceptions import AWSClientException
from sagemaker_studio.projects.utils import find_default_tooling_environment


class ProjectService:
    """
    Provides methods for interacting with projects within SageMaker Unified Studio.

    Args:
        datazone_api (BaseClient): The DataZone client.
    """

    def __init__(self, datazone_api: BaseClient):
        """
        Initializes a new instance of the ProjectService class.

        Args:
            datazone_api (BaseClient): The DataZone client.
        """
        self.datazone_api = datazone_api

    def get_project_default_environment(
        self, domain_identifier: Optional[str], project_identifier: Optional[str]
    ) -> dict:
        """
        Retrieves the default tooling environment for the specified project.

        Args:
            domain_identifier (Optional[str]): The unique identifier of the domain.
            project_identifier (Optional[str]): The unique identifier of the project.

        Returns:
            dict: The default tooling environment information.

        Raises:
            ValueError: If the Tooling environment blueprint is not found or the
                default environment is not found.
        """
        try:
            tooling_blueprints = self.datazone_api.list_environment_blueprints(  # type: ignore
                domainIdentifier=domain_identifier,
                managed=True,
                name="Tooling",
                provider="Amazon SageMaker",
            ).get("items", [])

            if len(tooling_blueprints) > 0:
                tooling_env_blueprint = list(
                    filter(lambda blueprint: blueprint["name"] == "Tooling", tooling_blueprints)
                )[0]

                tooling_environments = self.datazone_api.list_environments(  # type: ignore
                    domainIdentifier=domain_identifier,
                    projectIdentifier=project_identifier,
                    environmentBlueprintIdentifier=tooling_env_blueprint.get("id"),
                ).get("items", [])

                default_environment = find_default_tooling_environment(tooling_environments)
                if default_environment:
                    return default_environment

            tooling_lite_blueprints = self.datazone_api.list_environment_blueprints(
                domainIdentifier=domain_identifier,
                managed=True,
                name="ToolingLite",
                provider="Amazon SageMaker",
            ).get("items", [])

            if len(tooling_lite_blueprints) > 0:
                tooling_lite_env_blueprint = tooling_lite_blueprints[0]

                tooling_lite_environments = self.datazone_api.list_environments(  # type: ignore
                    domainIdentifier=domain_identifier,
                    projectIdentifier=project_identifier,
                    environmentBlueprintIdentifier=tooling_lite_env_blueprint.get("id"),
                ).get("items", [])

                default_environment = find_default_tooling_environment(tooling_lite_environments)
                if default_environment:
                    return default_environment

            # Custom Blueprints as Tooling: resolve environment via IAM connection
            # when no managed Tooling/ToolingLite blueprint exists.
            # Try default.iam (EXPRESS) then project.iam (STANDARD).
            for connection_name in ("default.iam", "project.iam"):
                connections = self.datazone_api.list_connections(
                    domainIdentifier=domain_identifier,
                    projectIdentifier=project_identifier,
                    type="IAM",
                    name=connection_name,
                ).get("items", [])
                if connections:
                    env_id = connections[0].get("environmentId")
                    if env_id:
                        return self.datazone_api.get_environment(
                            domainIdentifier=domain_identifier,
                            identifier=env_id,
                        )

            raise ValueError(
                "No tooling environment could be resolved: no deployed Tooling/ToolingLite "
                "environment and no default IAM connection with an associated environment "
                "was found in this project."
            )

        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                raise ValueError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)

    def get_project_sagemaker_environment(
        self, domain_identifier: Optional[str], project_identifier: Optional[str]
    ) -> dict:
        """
        Retrieves the SageMaker environment for the specified project.

        Args:
            domain_identifier (Optional[str]): The unique identifier of the domain.
            project_identifier (Optional[str]): The unique identifier of the project.

        Returns:
            dict: The SageMaker environment information.

        Raises:
            ValueError: If the input parameters are invalid or the SageMaker environment is not found.
        """
        try:
            project_environments = self.datazone_api.list_environments(  # type: ignore
                domainIdentifier=domain_identifier,
                projectIdentifier=project_identifier,
                name="Tooling",
            ).get("items", [])
        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                raise ValueError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)

        sagemaker_environment = (
            project_environments[0]
            if project_environments
            else self.get_project_default_environment(
                domain_identifier=domain_identifier, project_identifier=project_identifier
            )
        )
        return sagemaker_environment

    def is_default_environment_present(
        self, domain_identifier: str, project_identifier: str, blueprint_name: str
    ) -> bool:
        """
        Checks if the default environment for the specified blueprint is present in the project.

        Args:
            domain_identifier (str): The unique identifier of the domain.
            project_identifier (str): The unique identifier of the project.
            blueprint_name (str): The name of the environment blueprint.

        Returns:
            bool: True if the default environment is present, False otherwise.

        Raises:
            ValueError: If the input parameters are invalid or the environment blueprint is not found.
        """
        try:
            blueprints = self.datazone_api.list_environment_blueprints(  # type: ignore
                domainIdentifier=domain_identifier,
                managed=True,
                name=blueprint_name,
                provider="Amazon SageMaker",
            ).get("items", [])
            if not blueprints:
                raise ValueError(f"{blueprint_name} environment blueprint not found")
            env_blueprint = blueprints[0]
            environments = self.datazone_api.list_environments(  # type: ignore
                domainIdentifier=domain_identifier,
                projectIdentifier=project_identifier,
                environmentBlueprintIdentifier=env_blueprint.get("id"),
            ).get("items", [])
            return len(environments) != 0
        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                raise ValueError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)
