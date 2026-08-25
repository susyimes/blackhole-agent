import json
import logging
import os
from typing import Optional

from botocore.client import BaseClient
from botocore.exceptions import ClientError

import sagemaker_studio.utils
from sagemaker_studio.exceptions import AWSClientException
from sagemaker_studio.projects import ProjectService


class InternalUtils:
    __instance = None

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super(InternalUtils, cls).__new__(cls)
        return cls.__instance

    def _get_domain_region(self) -> str:
        return self._get_field_from_environment("DataZoneDomainRegion")

    def _get_domain_id(self) -> str:
        return self._get_field_from_environment("DataZoneDomainId")

    def _get_account_id(self) -> Optional[str]:
        execution_role_arn = self._get_field_from_environment("ExecutionRoleArn")
        # Parse account ID from ARN format: arn:aws:iam::ACCOUNT_ID:role/...
        if execution_role_arn:
            parts = execution_role_arn.split(":")
            if len(parts) >= 5 and parts[0] == "arn" and parts[2] == "iam":
                account_id: str = parts[4]
                return account_id
            else:
                logging.warning(f"ExecutionRoleArn has unexpected format: {execution_role_arn}")
        else:
            logging.warning("ExecutionRoleArn not found in metadata")
        return None

    def _get_project_id(
        self,
        datazone_api: BaseClient,
        domain_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> str:
        if project_name and domain_id:
            project_paginator = datazone_api.get_paginator("list_projects")
            try:
                project_page_iterator = project_paginator.paginate(domainIdentifier=domain_id)
                for page in project_page_iterator:
                    for project in page.get("items", []):
                        if project.get("name") == project_name:
                            return project.get("id")

                raise RuntimeError(f"Project {project_name} not found")
            except ClientError as e:
                raise RuntimeError(
                    f"Encountered an error getting the project ID of project {project_name}",
                    AWSClientException(e),
                )
        elif not project_name:
            project_id_from_env = self._get_field_from_environment("DataZoneProjectId")
            if not project_id_from_env:
                raise ValueError(
                    "Project ID not found in environment. Please specify a project name."
                )
            return project_id_from_env
        elif project_name and not domain_id:
            raise ValueError("If specifying project name, a domain ID must also be specified.")
        else:
            raise RuntimeError("Encountered an error getting the project ID")

    def _get_datazone_environment_id(self) -> str:
        return self._get_field_from_environment("DataZoneEnvironmentId")

    def _get_user_id(self) -> str:
        user_id = self._get_field_from_environment("DataZoneUserId")
        if not user_id:
            raise RuntimeError("Encountered an error getting the current user ID")
        return user_id

    def _get_datazone_stage(self) -> str:
        return self._get_field_from_environment("DataZoneStage", default="prod")

    def _get_datazone_endpoint(self, region: str) -> str:
        dz_endpoint = self._get_field_from_environment("DataZoneEndpoint")
        if dz_endpoint:
            return dz_endpoint
        # Default to Prod Endpoint
        return f"https://datazone.{region}.api.aws"

    def _get_project_s3_path(
        self,
        project_api: ProjectService,
        datazone_api: BaseClient,
        domain_id: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> str:
        try:
            project_id = (
                project_id
                if project_id
                else self._get_project_id(datazone_api, domain_id, project_name)
            )
            self.__validate_domain_project_parameters(domain_id, project_id, project_name)

            default_tooling_environment_environment_summary = (
                self._get_default_tooling_environment_summary(
                    project_api=project_api,
                    datazone_api=datazone_api,
                    domain_id=str(domain_id),
                    project_id=project_id,
                )
            )
            default_tooling_environment_provisioned_resources = (
                default_tooling_environment_environment_summary.get("provisionedResources", [])
            )
            for resource in default_tooling_environment_provisioned_resources:
                if resource.get("name") == "s3BucketPath":
                    project_s3_path = resource.get("value")
                    return project_s3_path
            raise RuntimeError(
                f"s3BucketPath provisioned resource not found in default SageMaker Unified Studio tooling environment {default_tooling_environment_environment_summary.get('id')}"
            )
        except Exception as e:
            project_s3_path = self._get_field_from_environment("ProjectS3Path")
            if project_s3_path:
                return project_s3_path

            raise RuntimeError(
                f"Encountered an error getting the S3 path for project '{project_id}' in domain '{domain_id}'",
                e,
            )

    def _get_project_kms_key_arn(
        self,
        project_api: ProjectService,
        datazone_api: BaseClient,
        domain_id: str,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> str:
        try:
            project_id = (
                project_id
                if project_id
                else self._get_project_id(datazone_api, domain_id, project_name)
            )
            self._validate_project_parameters(project_id, project_name)
            default_tooling_environment_environment_summary = (
                self._get_default_tooling_environment_summary(
                    project_api=project_api,
                    datazone_api=datazone_api,
                    domain_id=domain_id,
                    project_id=project_id,
                )
            )
            default_tooling_environment_provisioned_resources = (
                default_tooling_environment_environment_summary.get("provisionedResources", [])
            )
            for resource in default_tooling_environment_provisioned_resources:
                if resource.get("name") == "kmsKeyArn":
                    return resource.get("value")

            raise RuntimeError(
                f"kmsKeyArn provisioned resource not found in default SageMaker Unified Studio tooling environment {default_tooling_environment_environment_summary.get('id')}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Encountered an error getting the project KMS key for project '{project_name}' in domain '{domain_id}'",
                e,
            )

    def _get_mlflow_tracking_server_arn(
        self,
        datazone_api: BaseClient,
        domain_id: str,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> str:
        project_id = (
            project_id
            if project_id
            else self._get_project_id(datazone_api, domain_id, project_name)
        )
        self._validate_project_parameters(project_id, project_name)

        sagemaker_studio_ml_experiments_environment_id = None
        try:
            environments_paginator = datazone_api.get_paginator("list_environments")
            environment_page_iterator = environments_paginator.paginate(
                domainIdentifier=domain_id, projectIdentifier=project_id
            )
            for page in environment_page_iterator:
                for environment in page.get("items", []):
                    if environment.get("name") == "MLExperiments":
                        sagemaker_studio_ml_experiments_environment_id = environment.get("id")

            if not sagemaker_studio_ml_experiments_environment_id:
                raise RuntimeError("MLExperiments environment not found")
        except Exception as e:
            raise RuntimeError("Encountered an error getting ML flow tracking server ARN", e)

        try:
            sagemaker_studio_ml_experiments_env_summary = datazone_api.get_environment(  # type: ignore
                domainIdentifier=domain_id,
                identifier=sagemaker_studio_ml_experiments_environment_id,
            )
            for resource in sagemaker_studio_ml_experiments_env_summary.get(
                "provisionedResources", []
            ):
                if resource.get("name") == "mlflowTrackingServerArn":
                    return resource.get("value")

            raise RuntimeError(
                "Could not find mlflowTrackingServerArn provisioned resource in MLExperiments environment"
            )
        except Exception as e:
            raise RuntimeError("Encountered an error getting ML flow tracking server ARN", e)

    def _get_field_from_environment(self, field: str, default: str = "") -> str:
        # Fetch this field from either the resource-metadata.json file in SageMaker Spaces, or
        # if the JSON does not exist, first look for a space environment variable with exact field name,
        # and if not there, look up as a MWAA environment variable `AIRFLOW__WORKFLOWS__{field}`
        if os.path.exists(sagemaker_studio.utils.SAGEMAKER_METADATA_JSON_PATH):
            try:
                return self._get_field_from_sagemaker_space_metadata_json(field)
            except Exception as e:
                logging.info(
                    f"An error occurred when fetching the {field} from resource-metadata JSON file: {e}"
                )
        # Look for a SM space environment variable first
        if field in os.environ:
            return os.environ[field]
        # then check if this is running in MWAA env
        if (
            field in sagemaker_studio.utils.SPACE_ENV_VARIABLES_TO_MWAA_ENV_VARIABLES
            and sagemaker_studio.utils.SPACE_ENV_VARIABLES_TO_MWAA_ENV_VARIABLES[field]
            in os.environ
        ):
            return os.environ[
                sagemaker_studio.utils.SPACE_ENV_VARIABLES_TO_MWAA_ENV_VARIABLES[field]
            ]
        return default

    def _get_field_from_sagemaker_space_metadata_json(self, field: str) -> str:
        try:
            with open(
                sagemaker_studio.utils.SAGEMAKER_METADATA_JSON_PATH, "r"
            ) as sagemaker_space_metadata_json:
                sagemaker_space_metadata = json.load(sagemaker_space_metadata_json)
                # Could be a top-level field within the JSON, or inside the AdditionalMetadata object
                return sagemaker_space_metadata.get(field) or sagemaker_space_metadata.get(
                    "AdditionalMetadata", {}
                ).get(field)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "JSON decoding error encountered when parsing resource-metadata file", e
            )
        except Exception as e:
            raise RuntimeError(
                "An unexpected error occurred when accessing SageMaker resource metadata", e
            )

    def _get_default_tooling_environment_summary(
        self, project_api: ProjectService, datazone_api: BaseClient, domain_id: str, project_id: str
    ):
        try:
            default_tooling_environment_id = project_api.get_project_default_environment(
                domain_identifier=domain_id, project_identifier=project_id
            ).get("id")

            if not default_tooling_environment_id:
                raise RuntimeError("Could not find default tooling environment ID")
            return datazone_api.get_environment(  # type: ignore
                domainIdentifier=domain_id, identifier=default_tooling_environment_id
            )
        except ClientError as e:
            raise RuntimeError(
                f"Encountered error getting project default tooling environment for project: {project_id} in domain {domain_id}",
                AWSClientException(e),
            )

    def _validate_project_parameters(
        self, project_id: Optional[str] = None, project_name: Optional[str] = None
    ) -> None:
        if not project_id and not project_name:
            raise ValueError("One of project_id or project_name must be provided.")

    def __validate_domain_project_parameters(
        self,
        domain_id: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ):
        if not domain_id:
            raise ValueError("domain_id must be provided.")
        self._validate_project_parameters(project_id, project_name)

    def _resolve_connection_id_from_notebook(self, config) -> str:
        """Resolve the default spark connection ID from notebook metadata.

        Reads NotebookId from the local resource-metadata.json file (same source as domain_id),
        then calls GetNotebook API to read notebook.metadata.defaultSparkConnectionId.
        Returns the connection ID string, or empty string if not found/not in notebook context.
        Raises on API/infrastructure errors so the caller can decide how to handle.
        """
        from sagemaker_studio.sagemaker_studio_api import SageMakerStudioAPI

        domain_id = self._get_domain_id()
        notebook_id = self._get_field_from_environment("NotebookId")

        if not domain_id or not notebook_id:
            logging.info("Missing domain_id or notebook_id, skipping notebook metadata lookup")
            return ""

        logging.info(f"Resolving connection from notebook_id={notebook_id}")
        api = SageMakerStudioAPI(config)
        response = api.datazone_api.get_notebook(
            domainIdentifier=domain_id,
            identifier=notebook_id,
        )
        metadata = response.get("metadata") or {}
        connection_id = metadata.get("defaultSparkConnectionId", "")
        if connection_id:
            logging.info(
                f"Resolved defaultSparkConnectionId from notebook metadata: {connection_id}"
            )
        else:
            logging.info("No defaultSparkConnectionId in notebook metadata")
        return connection_id
