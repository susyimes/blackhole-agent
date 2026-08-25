from dataclasses import dataclass, field
from typing import List, Optional

from sagemaker_studio.connections import ConnectionService
from sagemaker_studio.connections.connection import Connection
from sagemaker_studio.data_models import ClientConfig
from sagemaker_studio.execution.utils import RemoteExecutionUtils
from sagemaker_studio.sagemaker_studio_api import SageMakerStudioAPI
from sagemaker_studio.utils._internal import InternalUtils


@dataclass
class Project:
    """
    Represents a SageMaker Unified Studio project. Project allows a user to retrieve information about a project,
    including its connections, databases, tables, S3 paths, IAM roles, and more.

    Attributes:
        id (Optional[str]): The unique identifier of the project.
        name (Optional[str]): The name of the project.
        domain_id (Optional[str]): The unique identifier of the domain the project belongs to.
        project_status (str): The current status of the project.
        domain_unit_id (str): The unique identifier of the domain unit the project belongs to.
        project_profile_id (str): The unique identifier of the project profile.

    Args:
        name (Optional[str]): The name of the project.
        id (Optional[str]): The unique identifier of the project.
        domain_id (Optional[str]): The unique identifier of the domain the project belongs to.
        config (ClientConfig): The configuration settings for the SageMaker Unified Studio client.
    """

    id: Optional[str] = field()
    name: Optional[str] = field()
    domain_id: Optional[str] = field()
    project_status: str = field()
    domain_unit_id: str = field()
    project_profile_id: str = field()

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        domain_id: Optional[str] = None,
        config: ClientConfig = ClientConfig(),
    ):
        """
        Initializes a new Project instance. If a project ID is not found within the environment,
        a project ID must be supplied. Similarly, a domain ID must be supplied if not found
        within the environment.

        Args:
            name (Optional[str]): The name of the project.
            id (Optional[str]): The unique identifier of the project.
            domain_id (Optional[str]): The unique identifier of the domain the project belongs to.
            config (ClientConfig): The configuration settings for the SageMaker Unified Studio client.
        """
        self._utils = InternalUtils()
        self._sagemaker_studio_api = SageMakerStudioAPI(config)
        self.domain_id = domain_id
        self.name = name
        self.id = id
        self.config = config
        self._initialize_project()
        self.s3 = _ProjectS3Path(self)

    def _initialize_project(self):
        if not self.domain_id:
            domain_from_env = self._utils._get_domain_id()
            if not domain_from_env:
                raise ValueError("Domain ID not found in environment. Please specify a domain ID.")
            self.domain_id = domain_from_env

        if not self.id:
            self.id = self._utils._get_project_id(
                self._sagemaker_studio_api.datazone_api, self.domain_id, self.name
            )

        get_project_response = self._sagemaker_studio_api.datazone_api.get_project(
            identifier=self.id, domainIdentifier=self.domain_id
        )
        self._connection_service = ConnectionService(
            project_id=str(self.id),
            domain_id=str(self.domain_id),
            datazone_api=self._sagemaker_studio_api.datazone_api,
            glue_api=self._sagemaker_studio_api.glue_api,
            secrets_manager_api=self._sagemaker_studio_api.secrets_manager_api,
            kms_api=self._sagemaker_studio_api.kms_api,
            project_config=self.config,
        )
        self.name = get_project_response.get("name")
        self.project_status = get_project_response.get("projectStatus")
        self.project_profile_id = get_project_response.get("projectProfileId")
        self.domain_unit_id = get_project_response.get("domainUnitId")

        self._is_express_mode = self._check_express_mode()

    def _check_express_mode(self) -> bool:
        """Determine if the project uses express mode by checking for a default.iam connection."""
        default_iam_connections = self._sagemaker_studio_api.datazone_api.list_connections(
            domainIdentifier=self.domain_id,
            projectIdentifier=self.id,
            type="IAM",
            name="default.iam",
        ).get("items", [])

        return len(default_iam_connections) > 0

    def _get_iam_connection_name(self) -> str:
        """
        Determine IAM connection name based on domain mode.
        Returns 'default.iam' if domain is in EXPRESS mode,
        otherwise returns 'project.iam'.
        """
        return "default.iam" if self._is_express_mode else "project.iam"

    @property
    def kms_key_arn(self) -> str:
        """
        Retrieves the KMS key ARN associated with the project.

        Returns:
            str: The KMS key ARN.
        """
        return self._utils._get_project_kms_key_arn(
            project_api=self._sagemaker_studio_api.project_api,
            datazone_api=self._sagemaker_studio_api.datazone_api,
            domain_id=str(self.domain_id),
            project_id=self.id,
        )

    @property
    def mlflow_tracking_server_arn(self) -> str:
        """
        Retrieves the MLflow tracking server ARN associated with the project.

        Returns:
            str: The MLflow tracking server ARN.
        """
        return self._utils._get_mlflow_tracking_server_arn(
            datazone_api=self._sagemaker_studio_api.datazone_api,
            domain_id=str(self.domain_id),
            project_id=self.id,
        )

    def connection(
        self, name: Optional[str] = None, *, id: Optional[str] = None, type: Optional[str] = None
    ) -> Connection:
        """
        Retrieves a specific connection associated with the project by its name or ID.
        If no name or id is provided, it gets the default IAM connection based on domain mode.

        Args:
            name (Optional[str]): The name of the connection.
            id (Optional[str]): The ID of the connection.

        Returns:
            Connection: The Connection object.

        Raises:
            ValueError: If both name and id are provided.
        """
        if id is not None and name is not None:
            raise ValueError(
                "Cannot specify both 'name' and 'id' parameters. Use one or the other."
            )

        if id is not None:
            return self._connection_service.get_connection_by_id(connection_id=id)
        elif name is not None:
            return self._connection_service.get_connection_by_name(name=name)
        elif type is not None:
            return self._connection_service.get_connection_by_type(type=type)
        else:
            # No name or id provided, use domain-based selection
            connection_name = self._get_iam_connection_name()
            return self._connection_service.get_connection_by_name(name=connection_name)

    @property
    def connections(self) -> List[Connection]:
        """
        Retrieves a list of all connections associated with the project.
        The appropriate IAM connection based on domain mode is moved to index 0.

        Returns:
            List[Connection]: A list of Connection objects.
        """
        connections: List[Connection] = self._connection_service.list_connections()

        # Move the appropriate IAM connection to index 0 based on domain mode
        target_connection_name = self._get_iam_connection_name()
        target_connection_index = next(
            (i for i, conn in enumerate(connections) if conn.name == target_connection_name), -1
        )
        if target_connection_index != -1:
            target_connection = connections.pop(target_connection_index)
            connections.insert(0, target_connection)

        return connections

    @property
    def iam_role(self) -> str:
        """
        Retrieves the IAM role ARN associated with the project.
        Uses the appropriate IAM connection based on domain mode.

        Returns:
            str: The IAM role ARN.
        """
        if not hasattr(self, "_cached_iam_role"):
            project_iam_connection = self._get_iam_connection_name()
            connection = self.connection(name=project_iam_connection)
            project_role = connection.iam_role
            if not project_role:
                raise RuntimeError("Could not find project iam role")
            self._cached_iam_role = project_role
        return self._cached_iam_role

    @property
    def user_id(self) -> str:
        """
        Retrieves the user ID associated with the project.

        Returns:
            str: The user ID.
        """
        return self._utils._get_user_id()

    @property
    def shared_files(self) -> str:
        """
        Retrieves the path of shared files.

        Returns:
            str: The path of shared files.
        """
        try:
            connection = self.connection(name="default.s3_shared")
            if connection:
                return connection.data.s3_uri
            raise RuntimeError("No connection found for shared files.")
        except Exception as e:
            raise RuntimeError(
                f"Encountered an error getting the shared files path for project '{self.name}' in domain '{self.domain_id}'",
                e,
            )


class _ProjectS3Path:
    """
    Provides access to the S3 paths associated with the project.

    Args:
        project (Project): The Project instance.
    """

    def __init__(self, project: Project):
        """
        Initializes a new instance of the _ProjectS3Path class.

        Args:
            project (Project): The Project instance.
        """
        self._project = project

    @property
    def root(self) -> str:
        """
        Retrieves the S3 path of the project root directory.

        Returns:
            str: The S3 path of the project root directory.
        """
        return self._get_project_s3_path()

    @property
    def datalake_consumer_glue_db(self) -> str:
        """
        Retrieves the S3 path of the DataLake consumer Glue DB directory.

        Returns:
            str: The S3 path of the DataLake consumer Glue DB directory.
        """
        blueprint_name = "DataLake"
        blueprint_path = "/data/catalogs/"
        return self._get_path(blueprint_name, blueprint_path)

    @property
    def datalake_athena_workgroup(self) -> str:
        """
        Retrieves the S3 path of the DataLake Athena workgroup directory.

        Returns:
            str: The S3 path of the DataLake Athena workgroup directory.
        """
        blueprint_name = "DataLake"
        blueprint_path = "/sys/athena/"

        return self._get_path(blueprint_name, blueprint_path)

    @property
    def workflow_output_directory(self) -> str:
        """
        Retrieves the S3 path of the workflows output directory.

        Returns:
            str: The S3 path of the workflows output directory.
        """
        blueprint_name = "Workflows"
        blueprint_path = "/workflows/output/"

        return self._get_path(blueprint_name, blueprint_path)

    @property
    def workflow_temp_storage(self) -> str:
        """
        Retrieves the S3 path of the workflows temp storage directory.

        Returns:
            str: The S3 path of the workflows temp storage directory.
        """
        blueprint_name = "Workflows"
        blueprint_path = "/workflows/tmp/"

        return self._get_path(blueprint_name, blueprint_path)

    @property
    def emr_ec2_log_destination(self) -> str:
        """
        Retrieves the S3 path of the EMR EC2 log destination directory.

        Returns:
            str: The S3 path of the EMR EC2 log destination directory.
        """
        blueprint_name = "EmrOnEc2"
        blueprint_path = "/sys/emr"

        return self._get_path(blueprint_name, blueprint_path)

    @property
    def emr_ec2_certificates(self) -> str:
        """
        Retrieves the S3 path of the EMR EC2 log bootstrap directory.

        Returns:
            str: The S3 path of the EMR EC2 log bootstrap directory.
        """
        blueprint_name = "EmrOnEc2"
        blueprint_path = "/sys/emr/certs"

        return self._get_path(blueprint_name, blueprint_path)

    @property
    def emr_ec2_log_bootstrap(self) -> str:
        """
        Retrieves the S3 path of the EMR EC2 log bootstrap directory.

        Returns:
            str: The S3 path of the EMR EC2 log bootstrap directory.
        """
        blueprint_name = "EmrOnEc2"
        blueprint_path = "/sys/emr/boot-strap"

        return self._get_path(blueprint_name, blueprint_path)

    def workflow_script_path(self, local_script_path: str) -> str:
        """
        Retrieves the S3 path of a script file.

        Args:
            local_script_path (str): The path to the local script file.

        Returns:
            str: The S3 path of the script file.
        """
        return RemoteExecutionUtils.pack_s3_path_for_input_file(self.root, local_script_path)

    def environment_path(self, environment_id: str) -> str:
        """
        Retrieves the S3 path of a specific environment.

        Args:
            environment_id (str): The unique identifier of the environment.

        Returns:
            str: The S3 path of the specified environment.
        """
        environment_id = environment_id.strip("/")
        # Check if the environment exists
        self._project._sagemaker_studio_api.datazone_api.get_environment(
            domainIdentifier=self._project.domain_id, identifier=environment_id
        )

        return f"{self._get_project_s3_path()}/{environment_id}"

    def _get_path(self, blueprint_name, blueprint_path):
        # Check if the environment for this path exists
        if self._project._sagemaker_studio_api.project_api.is_default_environment_present(
            domain_identifier=self._project.domain_id,  # type: ignore
            project_identifier=self._project.id,  # type: ignore
            blueprint_name=blueprint_name,
        ):
            s3_path = self._get_project_s3_path()
            return f"{s3_path}{blueprint_path}"
        else:
            raise RuntimeError(
                f"Could not find environment for {blueprint_name} blueprint needed for fetching s3 "
                f"path"
            )

    def _get_project_s3_path(self):
        return self._project._utils._get_project_s3_path(
            project_api=self._project._sagemaker_studio_api.project_api,
            datazone_api=self._project._sagemaker_studio_api.datazone_api,
            domain_id=str(self._project.domain_id),
            project_id=self._project.id,
        )
