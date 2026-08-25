import os
import pathlib
import zipfile
from typing import Optional

from boto3 import Session

from sagemaker_studio.credentials import CredentialsVendingService
from sagemaker_studio.data_models import ClientConfig
from sagemaker_studio.execution.local_execution_client import LocalExecutionClient
from sagemaker_studio.execution.remote_execution_client import RemoteExecutionClient
from sagemaker_studio.git import GitService
from sagemaker_studio.models.execution import ExecutionClient, ExecutionConfig
from sagemaker_studio.projects import ProjectService
from sagemaker_studio.utils import SAGEMAKER_METADATA_JSON_PATH
from sagemaker_studio.utils._internal import InternalUtils


class SageMakerStudioAPI:
    """
    This class provides access to various APIs and services within SageMaker Unified Studio,
    such as DataZone, Glue, Project Service, Credentials Vending Service,
    Git Service, and Execution Clients.

    Args:
        config (ClientConfig): The configuration settings for the SageMaker Unified Studio client.
    """

    credentials_api: CredentialsVendingService
    project_api: ProjectService
    execution_client: Optional[ExecutionClient]
    git_api: GitService
    __instance = None

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super(SageMakerStudioAPI, cls).__new__(cls)
        return cls.__instance

    def __init__(self, config: ClientConfig = ClientConfig()):
        """
        Initializes a new instance of the SageMakerStudioAPI class.

        Args:
            config (ClientConfig): The configuration settings for the SageMaker Unified Studio client.
        """
        self.sagemaker_studio_config = config
        self._utils = InternalUtils()
        self.default_region: str = (
            self.sagemaker_studio_config.region or self._utils._get_domain_region() or "us-east-1"
        )
        models_path: str = self._set_boto3_models_path_env_var()

        space_aws_config_path = "/home/sagemaker-user/.aws/config"
        profile_name: Optional[str]
        if self.sagemaker_studio_config.profile_name:
            profile_name = self.sagemaker_studio_config.profile_name
        elif os.path.exists(space_aws_config_path) and os.path.exists(SAGEMAKER_METADATA_JSON_PATH):
            with open(space_aws_config_path, "r") as space_aws_config_config_file:
                space_aws_config_config = space_aws_config_config_file.read()
                domain_execution_role_creds_profile_name = "DomainExecutionRoleCreds"
                profile_name = (
                    domain_execution_role_creds_profile_name
                    if domain_execution_role_creds_profile_name in space_aws_config_config
                    else None
                )
        else:
            profile_name = None
        session = Session(region_name=self.default_region, profile_name=profile_name)
        self.default_session = self.sagemaker_studio_config.session or session
        self.default_session._loader.search_paths.extend([models_path])

        self.datazone_api = self._get_aws_client(
            "datazone", self.sagemaker_studio_config.overrides.get("datazone", {})
        )
        self.glue_api = self._get_aws_client(
            "glue", self.sagemaker_studio_config.overrides.get("glue", {})
        )
        self.secrets_manager_api = self._get_aws_client(
            "secretsmanager", self.sagemaker_studio_config.overrides.get("secretsmanager", {})
        )
        self.kms_api = self._get_aws_client(
            "kms", self.sagemaker_studio_config.overrides.get("kms", {})
        )
        self.project_api = ProjectService(self.datazone_api)
        self.credentials_api = CredentialsVendingService(self.datazone_api, self.project_api)
        self.git_api = GitService(self.datazone_api, self.project_api)

        execution_config = self._build_execution_config()
        if execution_config.domain_identifier and execution_config.project_identifier:
            if execution_config.local:
                self.execution_client = LocalExecutionClient(execution_config)
            else:
                self.execution_client = RemoteExecutionClient(
                    self.datazone_api, self.project_api, execution_config
                )
        else:
            self.execution_client = None

    def _build_execution_config(self):
        execution_overrides = self.sagemaker_studio_config.overrides.get("execution", {})
        execution_config = ExecutionConfig(**execution_overrides)

        # Use provided domain_id, project_id, domain_region OR fall back to env variables in MWAA or metadata file in Space
        execution_config.domain_identifier = (
            execution_overrides.get("domain_identifier") or self._utils._get_domain_id()
        )

        execution_config.project_identifier = execution_overrides.get(
            "project_identifier"
        ) or self._utils._get_project_id(self.datazone_api)

        execution_config.datazone_endpoint = execution_overrides.get(
            "datazone_endpoint"
        ) or self._utils._get_datazone_endpoint(self.default_region)

        execution_config.datazone_domain_region = (
            execution_overrides.get("datazone_domain_region") or self._utils._get_domain_region()
        )

        if (
            not execution_config.local
            and execution_config.domain_identifier
            and execution_config.project_identifier
        ):
            execution_config.project_s3_path = (
                self._utils._get_project_s3_path(
                    project_api=self.project_api,
                    datazone_api=self.datazone_api,
                    domain_id=execution_config.domain_identifier,
                    project_id=execution_config.project_identifier,
                )
                or ""
            )
        return execution_config

    def _get_aws_client(self, service_name: str, service_override_config: dict = {}):
        region_name: str = service_override_config.get("region", self.default_region)
        session: Session = service_override_config.get("session", self.default_session)
        endpoint_url: Optional[str] = None
        if service_name == "datazone":
            endpoint_url = self._utils._get_datazone_endpoint(self.default_region)
            override_url = service_override_config.get("endpoint_url")
            if override_url:
                endpoint_url = override_url
        else:
            region_name = os.getenv("AWS_REGION") or region_name
            override_region_name = service_override_config.get("region")
            if override_region_name:
                region_name = override_region_name
            endpoint_url = service_override_config.get("endpoint_url")

        if "environment" in service_override_config:
            region_name = service_override_config["environment"]["aws_region"]
            domain_identifier = service_override_config["environment"]["domain_identifier"]
            project_identifier = service_override_config["environment"].get(
                "project_identifier", ""
            )
            connection_credentials: dict = (
                self.credentials_api.get_project_default_iam_connection_credentials(
                    domain_identifier=domain_identifier,
                    project_identifier=project_identifier,
                )
            )
            access_key_id = connection_credentials["accessKeyId"]
            secret_access_key = connection_credentials["secretAccessKey"]
            session_token = connection_credentials["sessionToken"]

            return session.client(  # type: ignore
                service_name=service_name,
                region_name=region_name,
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                aws_session_token=session_token,
            )
        else:
            return session.client(  # type: ignore
                service_name=service_name, region_name=region_name, endpoint_url=endpoint_url
            )

    def _set_boto3_models_path_env_var(self):
        models_path: str = str(
            os.path.join(os.path.abspath(os.path.dirname(__file__)), "boto3_models")
        )
        if "sagemaker_studio.zip" in models_path:
            try:
                # current file path is
                # /tmp/sagemaker_studio.zip/sagemaker_studio/boto3_models
                # zip_path is
                # /tmp/sagemaker_studio.zip/
                zip_path = pathlib.Path(__file__).parent.parent.resolve()
                zip_parent_path = pathlib.Path(__file__).parent.parent.parent.resolve()
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    if "sagemaker_studio.zip" in str(zip_path):
                        # unzip to the parent directory of zip file
                        zip_ref.extractall(zip_parent_path)
                models_path = str(os.path.join(zip_parent_path, "sagemaker_studio/boto3_models"))
            except Exception:
                raise RuntimeError("Cannot apply additional boto3 models")
        os.environ["AWS_DATA_PATH"] = models_path
        return models_path
