import re
import uuid
from typing import Any, Dict, Optional

from boto3 import Session
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio._openapi.models import (
    GetExecutionRequest,
    ListExecutionsRequest,
    StartExecutionRequest,
    StopExecutionRequest,
)
from sagemaker_studio.exceptions import AWSClientException
from sagemaker_studio.execution.utils import ExecutionUtils, RemoteExecutionUtils
from sagemaker_studio.models.execution import (
    ConflictError,
    ErrorType,
    ExecutionClient,
    ExecutionConfig,
    InternalServerError,
    ResourceNotFoundError,
    SortBy,
    SortOrder,
    Status,
    ValidationError,
)
from sagemaker_studio.projects import ProjectService
from sagemaker_studio.utils._internal import InternalUtils

DEFAULT_INSTANCE_TYPE = "ml.m6i.xlarge"  # consistent with the default instance in the toolkit
FALLBACK_INSTANCE_TYPE = "ml.m5.xlarge"  # fallback instance type for regions without m6i support
DEFAULT_IMAGE_VERSION = "latest"  # default to latest image version


class RemoteExecutionClient(ExecutionClient):
    """
    A client for remote execution of notebooks.

    This class extends the ExecutionClient to provide functionality
    for executing notebooks on remote compute.

    Attributes:
        Inherits all attributes from ExecutionClient.

    Methods:
        Inherits all methods from ExecutionClient and may override or add new ones
        specific to remote execution.
    """

    kms_key_identifier: Optional[str]

    def __init__(
        self,
        datazone_api: BaseClient,
        project_api: ProjectService,
        config: ExecutionConfig,
    ):
        self._utils = InternalUtils()
        self.datazone_api: BaseClient = datazone_api
        self.project_api: ProjectService = project_api
        self.config: ExecutionConfig = config
        self.session = Session()
        self.domain_identifier = None
        self.project_identifier = None
        self.datazone_endpoint = None
        self.datazone_domain_region = None
        self.project_s3_path = None
        self.default_tooling_environment = None
        self.sagemaker_environment = None
        self.sagemaker_client = None
        self.ec2_client = None
        self.ssm_client = None
        self.security_group = None
        self.subnets = None
        self.user_role_arn = None
        self.kms_key_identifier = None

    """
    Retrieves detailed information about a specific execution.

    This method fetches the current state and details of an execution based on the provided
    execution identifier.

    Args:
        execution_id (str): The unique identifier of the execution to retrieve

    Returns:
        dict: A dictionary containing detailed information about the execution. The structure
        may include:
            {
                "execution_id": str,  # Unique identifier of the execution
                "status": str,  # Current status of the execution (e.g., 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'STOPPING', 'STOPPED')
                "start_time": int,  # timestamp in millis for when the execution started
                "end_time": int,  # timestamp in millis of when the execution ended (if applicable)
                "s3_path": str,  # S3 path where the execution outputs are stored
                "tags": List[dict],  # An array of Tag objects, each with a tag key and a value.
                "error_details": dict,  # Reason for failure (if status is 'FAILED')
            }

    Raises:
        ResourceNotFoundError: If the specified execution cannot be found.
        InternalServerError: For any server-side errors during the execution retrieval.
        RuntimeError: If there is error retrieving the execution details.

    Example:
        try:
            request = GetExecutionRequest(execution_id="exec-12345")
            execution_details = client.get_execution(request)
            print(f"Execution status: {execution_details['status']}")
            print(f"Start time: {execution_details['start_time']}")
        except ResourceNotFoundError:
            print("Execution not found")
        except ClientError as e:
            print(f"Error retrieving execution details: {str(e)}")

    Note:
        - The exact structure of the returned dictionary may vary based on the execution type
          and its current state.
        - Some fields in the returned dictionary might be None or missing if they are not
          applicable to the current state of the execution.
    """

    def get_execution(self, execution_id: str) -> dict:
        parameters = {"execution_id": execution_id}
        request = GetExecutionRequest(**parameters)
        return self._get_execution_internal(request)

    def _get_execution_internal(self, request: GetExecutionRequest) -> dict:
        self.__setup_execution_client()
        self.__validate_default_environment(self.default_tooling_environment)

        training_job_arn = "arn:aws:sagemaker:{0}:{1}:training-job/{2}".format(
            self.default_tooling_environment["awsAccountRegion"],
            self.default_tooling_environment["awsAccountId"],
            request.execution_id,
        )

        try:
            describe_training_job_response = self.sagemaker_client.describe_training_job(
                TrainingJobName=request.execution_id
            )
            execution_tags = []
            list_tags_paginator = self.sagemaker_client.get_paginator("list_tags")
            for page in list_tags_paginator.paginate(ResourceArn=training_job_arn):
                for tag in page.get("Tags", []):
                    if "Key" in tag and "Value" in tag:
                        execution_tags.append({"Key": tag["Key"], "Value": tag["Value"]})

            if (
                "CreationTime" not in describe_training_job_response
                or "TrainingJobStatus" not in describe_training_job_response
            ):
                raise RuntimeError(f"Error getting execution with id: {request.execution_id}")

            get_execution_response = {
                "execution_id": request.execution_id,
                "status": ExecutionUtils.map_training_job_status_to_status(
                    describe_training_job_response["TrainingJobStatus"]
                ).value,
                "start_time": (
                    ExecutionUtils.convert_timestamp_to_epoch_millis(
                        describe_training_job_response["TrainingStartTime"]
                    )
                    if "TrainingStartTime" in describe_training_job_response
                    else None
                ),
                "end_time": (
                    ExecutionUtils.convert_timestamp_to_epoch_millis(
                        describe_training_job_response["TrainingEndTime"]
                    )
                    if "TrainingEndTime" in describe_training_job_response
                    else None
                ),
                "s3_path": describe_training_job_response.get("ModelArtifacts", {}).get(
                    "S3ModelArtifacts", None
                ),
                "tags": execution_tags,
                "metricDefinitions": (
                    describe_training_job_response.get("AlgorithmSpecification", {}).get(
                        "MetricDefinitions", []
                    )
                    if "AlgorithmSpecification" in describe_training_job_response
                    else []
                ),
            }

            if "FailureReason" in describe_training_job_response:
                get_execution_response["error_details"] = {
                    "error_message": describe_training_job_response["FailureReason"],
                    "error_type": ErrorType.SERVER_ERROR,
                }

            return {
                key: value for (key, value) in get_execution_response.items() if value is not None
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            http_status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            if error_code == "ValidationException":
                if "Requested resource not found." in error_message and http_status_code == 400:
                    raise ResourceNotFoundError(
                        f"Execution with id {request.execution_id} not found."
                    )
                else:
                    raise InternalServerError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)

    """
    Retrieve a list of executions based on the provided request parameters.

    This method fetches a list of executions from the remote execution service
    using the criteria specified in the ListExecutionsRequest object.

    Args:
        start_time_after (Optional[int]): Filter executions starting after a specific time
        name_contains (Optional[str]): Filter executions whose name contains a specific string
        status (Optional[str]): Filter executions by their current status (e.g., 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'STOPPING', 'STOPPED')
        sort_order (Optional[str]): Order to return results (e.g., 'ASCENDING' or 'DESCENDING')
        sort_by (Optional[str]): Field to sort the results by (e.g., 'NAME', 'STATUS', 'START_TIME', 'END_TIME')
        next_token (Optional[str]): Token for pagination
        max_results (Optional[int]): Maximum number of results to return
        filter_by_tags (Optional[dict]): Filter executions containing specific tags

    Returns:
        dict: A dictionary containing the list of executions and metadata. Typical structure:
            {
                "executions": [
                    {
                        "id": str, # Unique identifier of the execution
                        "name": str, # Name of the execution
                        "status": str, # Current status of the execution (e.g., 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'STOPPING', 'STOPPED')
                        "start_time": int,  # timestamp in millis for when the execution started
                        "end_time": int,  # timestamp in millis of when the execution ended (if applicable)
                        "tags": List[dict],  # An array of Tag objects, each with a tag key and a value.
                    },
                ],
                "next_token": str,  # Token for retrieving the next page of results, if applicable
            }


    Raises:
        RuntimeError: If there's an issue with the execution service.
        ValueError:  If the input parameters are invalid.
        ClientError: For any other request-related errors during the execution retrieval.

    Example:
        request = ListExecutionsRequest(
            max_results=10,
            status="COMPLETED",
            name_contains="test",
            filter-by-tags={"AmazonDataZoneProject":"4a1w81w0jwrqmu"}
        )
        result = client.list_executions(request)
        for execution in result['executions']:
            print(f"Execution ID: {execution['id']}, Status: {execution['status']}")
    """

    def list_executions(
        self,
        start_time_after: Optional[int] = None,
        name_contains: Optional[str] = None,
        status: Optional[str] = None,
        sort_order: Optional[str] = None,
        sort_by: Optional[str] = None,
        next_token: Optional[str] = None,
        max_results: Optional[int] = None,
        filter_by_tags: Optional[dict] = None,
    ) -> dict:
        parameters = {}
        if start_time_after is not None:
            parameters["start_time_after"] = start_time_after
        if name_contains is not None:
            parameters["name_contains"] = name_contains
        if status is not None:
            parameters["status"] = status
        if sort_order is not None:
            parameters["sort_order"] = sort_order
        if sort_by is not None:
            parameters["sort_by"] = sort_by
        if next_token is not None:
            parameters["next_token"] = next_token
        if max_results is not None:
            parameters["max_results"] = max_results
        if filter_by_tags is not None:
            parameters["filter_by_tags"] = filter_by_tags
        request = ListExecutionsRequest(**parameters)
        return self._list_executions_internal(request)

    def _list_executions_internal(self, request: ListExecutionsRequest) -> dict:
        self.__setup_execution_client()
        try:
            search_args = {"Resource": "TrainingJob"}
            search_status = None
            if request.get("status"):
                search_status = ExecutionUtils.map_status_to_training_job_status(
                    Status(request.status)
                )
            if request.get("sort_by"):
                search_sort_by = ExecutionUtils.map_sort_by(SortBy(request.sort_by))
                search_args["SortBy"] = search_sort_by
            if request.get("sort_order"):
                search_sort_order = ExecutionUtils.map_sort_order(SortOrder(request.sort_order))
                search_args["SortOrder"] = search_sort_order
            search_expression = ExecutionUtils.create_sagemaker_search_expression_for_training(
                self.domain_identifier,
                self.project_identifier,
                request.get("start_time_after"),
                request.get("name_contains"),
                search_status,
                request.get("filter_by_tags"),
            )
            search_args["SearchExpression"] = search_expression
            # A recent change to project role now requires the SearchVisibilityCondition when using
            # the SageMaker Search API to enforce project-level access controls.
            search_args["VisibilityConditions"] = [
                {"Key": "Tags.AmazonDataZoneProject", "Value": self.project_identifier}
            ]
            if request.get("next_token"):
                search_args["NextToken"] = request.next_token
            search_response = self.sagemaker_client.search(
                MaxResults=request.get("max_results", 100), **search_args
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException":
                raise ValueError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)

        list_executions_response: dict = {"executions": []}
        if "Results" in search_response:
            for execution in search_response["Results"]:
                if "TrainingJob" in execution:
                    training_job = execution["TrainingJob"]
                    list_executions_response["executions"].append(
                        {
                            "id": training_job.get("TrainingJobName", "Unknown"),
                            "name": training_job.get("TrainingJobName", "Unknown"),
                            "status": (
                                ExecutionUtils.map_training_job_status_to_status(
                                    training_job["TrainingJobStatus"]
                                ).value
                                if "TrainingJobStatus" in training_job
                                else None
                            ),
                            "start_time": (
                                ExecutionUtils.convert_timestamp_to_epoch_millis(
                                    training_job["TrainingStartTime"]
                                )
                                if "TrainingStartTime" in training_job
                                else None
                            ),
                            "end_time": (
                                ExecutionUtils.convert_timestamp_to_epoch_millis(
                                    training_job["TrainingEndTime"]
                                )
                                if "TrainingEndTime" in training_job
                                else None
                            ),
                            "tags": training_job.get("Tags", None),
                        }
                    )
                else:
                    list_executions_response["executions"].append(
                        {
                            "id": "Unknown",
                            "name": "Unknown",
                            "status": "FAILED",
                            "start_time": None,
                            "end_time": None,
                        }
                    )
            list_executions_response["next_token"] = search_response.get("NextToken", None)
        return list_executions_response

    """
    Initiates a new execution based on the provided request parameters.

    This method starts a new execution on the remote compute using
    the configuration specified in the StartExecutionRequest object.

    Args:
        execution_name (str): A unique name for the execution
        input_config (Dict[str, Any]): Configuration for the input data for the execution
        domain_id (Optional[str]): DataZone domain ID. If provided, overrides config value
        project_id (Optional[str]): DataZone project ID. If provided, overrides config value
        domain_region (Optional[str]): DataZone domain region. If provided, overrides config value
        **kwargs: Additional parameters including:
            execution_type (str): The type of execution (e.g., 'NOTEBOOK')
            compute (Optional[str]): Configuration for the compute environment
            output_config (Optional[Dict[str, Any]]): Configuration for the outputs like output formats
            client_token (Optional[str]): A unique token to ensure idempotency
            termination_condition (Optional[Dict[str, Any]]): Condition for terminating the execution
            tags (Optional[Dict[str, Any]]): Tags related to the execution

    Returns:
        dict: A dictionary containing information about the started execution. Typical structure:
            {
                "execution_id": str,  # Unique identifier for the started execution
                "execution_name": str,  # Name of the execution
                "input_config":  dict,  # Configuration for the input data
                "output_config": dict,  # Configuration for the output data
                "compute": dict,  # Configuration for the compute environment
                "termination_condition":  dict,  # Condition for terminating the execution
                "tags": List[dict],  # List of tags associated with the execution
            }

    Raises:
        ValidationError: If the input parameters are invalid.
        RuntimeError: If there's an issue with the remote execution service.
        InternalServerError:  If there's an internal server error.

    Example:
        # Using config values (existing behavior)
        result = client.start_execution(
            execution_name="MyExecution",
            input_config={"notebook_config": {"input_path": "src/folder2/test.ipynb"}},
            execution_type="NOTEBOOK",
            output_config={"notebook_config": {"output_formats": ["NOTEBOOK", "HTML"]}},
            termination_condition={"max_runtime_in_seconds": 9000},
            compute={
                "instance_type": "ml.c5.xlarge",
                "image_details": {
                    # provide either ecr_uri or (image_name and image_version)
                    "image_name": "sagemaker-distribution-prod",
                    "image_version": "2.8",  // valid values - {2.6, 2.8, 2, 3.0, 3}
                    "ecr_uri": "123456123456.dkr.ecr.us-west-2.amazonaws.com/ImageName:latest"
                },
            },
            tags={}
        )

        # Using direct parameters (new behavior matching SageMakerNotebookOperator)
        result = client.start_execution(
            execution_name="notebook_task",
            input_config={"notebook_config": {"input_path": "path/to/notebook.ipynb"}},
            domain_id="dzd-example123456",
            project_id="example123456",
            domain_region="us-east-1",
            compute={"instance_type": "ml.c5.xlarge"}
        )
        print(f"Execution started with ID: {result.execution_id}")
    """

    def start_execution(
        self,
        execution_name: str,
        input_config: Dict[str, Any],
        domain_id: Optional[str] = None,
        project_id: Optional[str] = None,
        domain_region: Optional[str] = None,
        **kwargs,
    ) -> dict:
        # Convert underscores to hyphens in execution_name to meet regex validation
        execution_name = execution_name.replace("_", "-")

        parameters = {
            "execution_name": execution_name,
            "input_config": input_config,
            **kwargs,
        }

        request = StartExecutionRequest(**parameters)
        return self._start_execution_internal(request, domain_id, project_id, domain_region)

    def _start_execution_internal(
        self,
        request: StartExecutionRequest,
        domain_id: Optional[str] = None,
        project_id: Optional[str] = None,
        domain_region: Optional[str] = None,
    ):
        # Validate input parameters early
        if domain_id is not None:
            self.validate_domain_id(domain_id)
        if project_id is not None:
            self.validate_project_id(project_id)
        if domain_region is not None:
            self.validate_domain_region(domain_region)

        self.__setup_execution_client(domain_id, project_id, domain_region)
        self.validate_execution_name(request.execution_name)
        self.validate_input_config(request.input_config)
        self.validate_client_token(request.get("client_token"))
        self.__validate_default_environment(self.default_tooling_environment)
        self.__validate_stack()

        project_s3_path = self._utils._get_project_s3_path(
            project_api=self.project_api,
            datazone_api=self.datazone_api,
            domain_id=self.domain_identifier,
            project_id=self.project_identifier,
        )

        local_input_file_path = request.input_config.get("notebook_config", {}).get(
            "input_path", ""
        )
        is_git_project = RemoteExecutionUtils.is_git_project(
            self.default_tooling_environment.get("provisionedResources")
        )
        input_s3_location = RemoteExecutionUtils.pack_s3_path_for_input_file(
            project_s3_path,
            local_input_file_path,
            is_git_project,
        )
        local_full_input_file_path = RemoteExecutionUtils.pack_full_path_for_input_file(
            local_input_file_path
        )

        output_s3_location = RemoteExecutionUtils.pack_s3_path_for_output_file(
            project_s3_path,
            local_input_file_path,
            is_git_project,
        )

        project_root_pattern = r"^/?src/" if is_git_project else r"^/?shared/"
        input_relative_path = re.sub(project_root_pattern, "", local_input_file_path)
        project_s3_root = input_s3_location.replace(input_relative_path, "").rstrip("/")
        input = {"path": project_s3_root, "file": input_relative_path}
        output = ExecutionUtils.unpack_path_file(output_s3_location)

        execution_tags = [
            {"Key": "sagemaker-notebook-execution", "Value": "TRUE"},
            {"Key": "sagemaker-notebook-name", "Value": input["file"]},
        ]

        if request.get("tags"):
            execution_tags.extend(
                {"Key": key, "Value": value} for key, value in request.tags.to_dict().items()
            )

        if "compute" not in request:
            instance_type_info = self.__get_available_instance_type_with_info(DEFAULT_INSTANCE_TYPE)
            request["compute"] = {"instance_type": instance_type_info["instance_type"]}
            has_gpu = instance_type_info["has_gpu"]
        else:
            # User provided instance type - validate without fallback
            user_instance_type = request["compute"]["instance_type"]
            instance_type_info = self.__get_available_instance_type_with_info(
                user_instance_type, use_fallback=False
            )
            has_gpu = instance_type_info["has_gpu"]

        image_details = request.compute.get("image_details", {})
        if "ecr_uri" in image_details:
            ecr_uri = image_details["ecr_uri"]
        else:
            image_name_default = "sagemaker-distribution-prod"
            image_name: str = image_details.get("image_name", image_name_default)
            image_version: str = image_details.get("image_version", DEFAULT_IMAGE_VERSION)

            image_variant = "gpu" if has_gpu else "cpu"

            if image_name != image_name_default:
                # BYOI case, call describe-image-version api
                response = self.sagemaker_client.describe_image_version(
                    ImageName=image_name,
                    Version=int(image_details.get("image_version")),
                )
                ecr_uri = response.get("BaseImage")
            else:
                # using SMD image
                # validate image_version
                if not self.validate_image_version(image_version):
                    raise ValidationError(f"Invalid image version: {image_version}")
                # extract accountId from SSM public parameter
                account_id = self.ssm_client.get_parameter(
                    Name="/aws/service/sagemaker-distribution/ecr-account-id"
                )["Parameter"]["Value"]
                if account_id == "":
                    raise InternalServerError("Account ID not found in SSM parameter store")
                # construct ECR uri of this format: <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.<TLD>/sagemaker-distribution-prod:<TAG>
                # example: 123456123456.dkr.ecr.us-west-2.amazonaws.com/sagemaker-distribution-prod:3.0.0-cpu
                # get the region from the default environment
                region = self.default_tooling_environment["awsAccountRegion"]
                ecr_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{image_name}:{image_version}-{image_variant}"

        output_formats = (
            request.get("output_config", {})
            .get("notebook_config", {})
            .get("output_formats", ["NOTEBOOK"])
        )

        if "output_config" in request and "notebook_config" in request["output_config"]:
            request["output_config"]["notebook_config"]["output_formats"] = output_formats
        else:
            request["output_config"] = {"notebook_config": {"output_formats": output_formats}}
        output_formats_lowercase = [x.lower() for x in output_formats]
        # remove "notebook" from the list since the output from AstraHeadlessExecutionManager
        # is notebook by default. This list essentially only contains any additional output formats that need to be
        # passed to AstraHeadlessExecutionManager.
        if "notebook" in output_formats_lowercase:
            output_formats_lowercase.remove("notebook")

        try:
            kms_key_id = {}
            volume_kms_key_id = {}
            if self.kms_key_identifier is not None:
                kms_key_id = {"KmsKeyId": self.kms_key_identifier}
                volume_kms_key_id = {"VolumeKmsKeyId": self.kms_key_identifier}

            # Define environment variables for SM Training job
            environment_variables = {
                "SM_EFS_MOUNT_GID": "100",
                "SM_EFS_MOUNT_PATH": "/home/sagemaker-user",
                "SM_EFS_MOUNT_UID": "1000",
                "SM_ENV_NAME": "sagemaker-workflows-default-env",
                "SM_EXECUTION_INPUT_PATH": "/opt/ml/input/data/sagemaker_workflows",
                "SM_EXECUTION_SYSTEM_PATH": "/opt/ml/input/data/sagemaker_workflows_system",
                "SM_INPUT_NOTEBOOK_NAME": input["file"],
                "SM_JOB_DEF_VERSION": "1.0",
                "SM_KERNEL_NAME": "python3",
                "SM_OUTPUT_NOTEBOOK_NAME": output["file"],
                "SM_SKIP_EFS_SIMULATION": "true",
                # Required by connection magics
                "DataZoneDomainId": self.domain_identifier,
                "DataZoneProjectId": self.project_identifier,
                "DataZoneEndpoint": self.datazone_endpoint,
                "DataZoneDomainRegion": self.datazone_domain_region,
                "ProjectS3Path": self.project_s3_path,
                "InputNotebookPath": local_full_input_file_path,
                "SM_OUTPUT_FORMATS": (
                    ",".join(output_formats_lowercase) if output_formats_lowercase else ""
                ),
                # Full path got init script in SM training container is `"{SM_EXECUTION_INPUT_PATH}/${SM_INIT_SCRIPT}"`
                # The `sm_init_script.sh` is provided in SMD
                "SM_INIT_SCRIPT": "../../../../../etc/sagemaker-ui/workflows/sm_init_script.sh",
            }

            training_job_params = {
                "TrainingJobName": f"{request.execution_name}-{uuid.uuid4()}",
                "AlgorithmSpecification": {
                    "TrainingImage": ecr_uri,
                    "TrainingInputMode": "File",
                    "EnableSageMakerMetricsTimeSeries": False,
                    "ContainerEntrypoint": ["amazon_sagemaker_scheduler"],
                    "MetricDefinitions": [
                        {
                            "Name": "cells:complete",
                            "Regex": r".*Executing:.*?\|.*?\|\s+(\d+)\/\d+\s+\[",
                        },
                        {
                            "Name": "cells:total",
                            "Regex": r".*Executing:.*?\|.*?\|\s+\d+\/(\d+)\s+\[",
                        },
                    ],
                },
                "RoleArn": self.user_role_arn,
                "OutputDataConfig": {"S3OutputPath": output["path"], **kms_key_id},
                "ResourceConfig": {
                    "InstanceCount": 1,
                    "InstanceType": request.compute.get("instance_type", ""),
                    "VolumeSizeInGB": request.compute.get("volume_size_in_gb", 30),
                    **volume_kms_key_id,
                },
                "InputDataConfig": [
                    {
                        "ChannelName": "sagemaker_workflows",
                        "DataSource": {
                            "S3DataSource": {
                                "S3DataType": "S3Prefix",
                                "S3Uri": input["path"],
                                "S3DataDistributionType": "FullyReplicated",
                            }
                        },
                        "ContentType": "text/csv",
                        "CompressionType": "None",
                    }
                ],
                "HyperParameters": request.input_config.get("notebook_config", {}).get(
                    "input_parameters", {}
                )
                or {},
                "StoppingCondition": {
                    "MaxRuntimeInSeconds": request.get("termination_condition", {}).get(
                        "max_runtime_in_seconds", 86400
                    )
                },
                "EnableManagedSpotTraining": False,
                "EnableNetworkIsolation": False,
                "EnableInterContainerTrafficEncryption": True,
                "Environment": environment_variables,
                "RetryStrategy": {"MaximumRetryAttempts": 1},
                "Tags": execution_tags,
            }

            # Add VpcConfig only if both security_group and subnets are available
            if self.security_group is not None and self.subnets is not None:
                training_job_params["VpcConfig"] = {
                    "SecurityGroupIds": [self.security_group],
                    "Subnets": self.subnets,
                }

            create_training_job_response = self.sagemaker_client.create_training_job(
                **training_job_params
            )

            split_arn = create_training_job_response.get("TrainingJobArn").split(":training-job/")
            if len(split_arn) != 2:
                raise RuntimeError("Remote executionId not available")
            split_arn = create_training_job_response["TrainingJobArn"].split(":training-job/")

            if len(split_arn) != 2:
                raise RuntimeError("Remote executionId not available")

            # Convert the request object to a dictionary
            request_dict = request.to_dict()
            return {
                "execution_id": split_arn[1],
                **request_dict,
            }

        except ClientError as e:
            raise RuntimeError(f"Error starting remote execution: {AWSClientException(e)}")

    """
    Stops an ongoing execution based on the provided request parameters.

    This method attempts to stop a running execution. The behavior may vary depending on
    its current state.

    Args:
        execution_id (str): The unique identifier of the execution to stop

    Returns:
        None: This method doesn't return any value. The absence of an exception indicates
        that the stop request was successfully submitted.

    Raises:
        ConflictError: If the execution is already in a terminal state (e.g., STOPPED, FAILED).
        ResourceNotFoundError: If the specified execution cannot be found.
        ValidationError:  For any invalid input parameters.
        ClientError: For any other AWS SDK errors.

    Example:
        try:
            request = StopExecutionRequest(execution_id="exec-12345")
            client.stop_execution(request)
            print("Stop request for execution exec-12345 submitted successfully")
        except ConflictError as e:
            print(f"Failed to stop execution: {str(e)}")
        except ResourceNotFoundError:
            print("Execution not found")
    """

    def stop_execution(self, execution_id: str) -> None:
        parameters = {"execution_id": execution_id}
        request = StopExecutionRequest(**parameters)
        return self._stop_execution_internal(request)

    def _stop_execution_internal(self, request: StopExecutionRequest) -> None:
        self.__setup_execution_client()
        try:
            self.sagemaker_client.stop_training_job(
                TrainingJobName=request.execution_id,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            http_status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            if error_code == "ValidationException":
                if (
                    "The request was rejected because the training job is in status Stopped"
                    in error_message
                    and http_status_code == 400
                ):
                    raise ConflictError(
                        f"Execution with id {request.execution_id} is already stopped"
                    )
                elif (
                    "The request was rejected because the training job is in status Failed"
                    in error_message
                    and http_status_code == 400
                ):
                    raise ConflictError(
                        f"Execution with id {request.execution_id} is in Failed status and cannot be Stopped"
                    )
                elif "Requested resource not found." in error_message and http_status_code == 400:
                    raise ResourceNotFoundError(
                        f"Execution with id {request.execution_id} not found"
                    )
                else:
                    raise ValidationError(f"Invalid input parameters: {AWSClientException(e)}")
            else:
                raise AWSClientException(e)

        return

    def __set_sagemaker_environment(self):
        self.sagemaker_environment = self.project_api.get_project_sagemaker_environment(
            domain_identifier=self.domain_identifier,
            project_identifier=self.project_identifier,
        )
        return

    def __set_sagemaker_client(self):
        self.__validate_default_environment(self.sagemaker_environment)
        self.sagemaker_client = self.session.client(
            service_name="sagemaker",
            region_name=self.sagemaker_environment["awsAccountRegion"],
        )

    def __set_ec2client(self):
        self.ec2_client = self.session.client(
            service_name="ec2",
            region_name=self.sagemaker_environment["awsAccountRegion"],
        )

    def __set_ssmclient(self):
        self.ssm_client = self.session.client(
            service_name="ssm",
            region_name=self.sagemaker_environment["awsAccountRegion"],
        )

    def __set_default_tooling_environment(self):
        self.default_tooling_environment = self.project_api.get_project_default_environment(
            self.domain_identifier, self.project_identifier
        )
        return

    def __set_stack(self):
        self.__validate_default_environment(self.default_tooling_environment)
        provisioned_resources = self.default_tooling_environment["provisionedResources"]
        self.security_group = next(
            (
                resource["value"]
                for resource in provisioned_resources
                if resource["name"] == "securityGroup"
            ),
            None,
        )
        self.subnets = next(
            (
                resource["value"].split(",")
                for resource in provisioned_resources
                if resource["name"] == "privateSubnets"
            ),
            None,
        )
        self.user_role_arn = next(
            (
                resource["value"]
                for resource in provisioned_resources
                if resource["name"] == "userRoleArn"
            ),
            None,
        )
        self.kms_key_identifier = next(
            (
                resource["value"]
                for resource in provisioned_resources
                if resource["name"] == "kmsKeyArn"
            ),
            None,
        )
        return

    def __validate_default_environment(self, environment_summary: dict):
        if environment_summary is None:
            raise RuntimeError("Default environment not found")
        if "awsAccountRegion" not in environment_summary:
            raise RuntimeError("Default environment region not found")
        if "awsAccountId" not in environment_summary:
            raise RuntimeError("Default environment account not found")
        if "id" not in environment_summary:
            raise RuntimeError("Default environment id not found")
        if "provisionedResources" not in environment_summary:
            raise RuntimeError("Default environment provisioned resources not found")
        return

    def __setup_execution_client(
        self,
        domain_id: Optional[str] = None,
        project_id: Optional[str] = None,
        domain_region: Optional[str] = None,
    ):
        if self.domain_identifier is None:
            if domain_id:
                self.domain_identifier = domain_id
            else:
                self.domain_identifier = self.config.domain_identifier

        if self.project_identifier is None:
            if project_id:
                self.project_identifier = project_id
            else:
                self.project_identifier = self.config.project_identifier

        if not self.domain_identifier or not self.project_identifier:
            raise InternalServerError("Domain identifier and project identifier are required")

        if self.datazone_endpoint is None:
            self.datazone_endpoint = self.config.datazone_endpoint

        if self.datazone_domain_region is None:
            if domain_region:
                self.datazone_domain_region = domain_region
            else:
                self.datazone_domain_region = self.config.datazone_domain_region

        if self.project_s3_path is None:
            if domain_id and project_id:
                # Fetch project_s3_path dynamically using the provided domain_id and project_id
                self.project_s3_path = self._utils._get_project_s3_path(
                    project_api=self.project_api,
                    datazone_api=self.datazone_api,
                    domain_id=self.domain_identifier,
                    project_id=self.project_identifier,
                )
            else:
                self.project_s3_path = self.config.project_s3_path

        if self.default_tooling_environment is None:
            self.__set_default_tooling_environment()
        if self.sagemaker_environment is None:
            self.__set_sagemaker_environment()
        if self.sagemaker_client is None:
            self.__set_sagemaker_client()
        if self.ec2_client is None:
            self.__set_ec2client()
        if self.ssm_client is None:
            self.__set_ssmclient()
        if None in [
            self.security_group,
            self.subnets,
            self.user_role_arn,
            self.kms_key_identifier,
        ]:
            self.__set_stack()

        return

    @staticmethod
    def validate_execution_name(execution_name: str):
        if not re.match(r"^[a-zA-Z0-9]([-a-zA-Z0-9]){0,25}$", execution_name):
            raise ValidationError(
                f"Execution name {execution_name} does not match required pattern '^[a-zA-Z0-9]([-a-zA-Z0-9]){0, 25}$'"
            )

    @staticmethod
    def validate_input_config(input_config: dict):
        def validate_input_parameters(input_parameters):
            if not input_parameters:
                return
            if len(input_parameters) > 100:
                raise ValidationError(
                    "inputParameters in InputConfig notebookConfig cannot have more than 100 entries"
                )
            for key, value in input_parameters.items():
                if len(key) > 256:
                    raise ValidationError(
                        "The input parameters key length cannot exceed 256 characters."
                    )
                if len(value) > 2500:
                    raise ValidationError(
                        "The input parameters value length cannot exceed 2500 characters."
                    )

        if not input_config:
            raise ValidationError("InputConfig is required for remote execution")
        if "notebook_config" not in input_config:
            raise ValidationError("notebookConfig in InputConfig is required for remote execution")
        if "input_path" not in input_config["notebook_config"]:
            raise ValidationError(
                "'inputPath' in InputConfig notebookConfig is required for remote execution"
            )
        validate_input_parameters(input_config["notebook_config"].get("input_parameters"))

    @staticmethod
    def validate_client_token(client_token: Optional[str] = None):
        if client_token:
            raise ValidationError("Client (idempotency) token not supported")

    def __validate_stack(self):
        if self.user_role_arn is None:
            raise RuntimeError("Default stack use_role_arn not found")
        return

    def __get_available_instance_type_with_info(
        self, preferred_instance_type: str, use_fallback: bool = True
    ) -> Dict[str, Any]:
        """
        Get available instance type and its GPU info.
        Falls back to FALLBACK_INSTANCE_TYPE if preferred is not available.

        Args:
            preferred_instance_type (str): The preferred instance type
            use_fallback (bool): Whether to try fallback instance type if preferred unavailable

        Returns:
            dict: {
                "instance_type": str,  # The resolved instance type (with ml. prefix)
                "has_gpu": bool        # Whether the instance has GPU
            }

        Raises:
            ValidationError: If instance type is not available (and fallback is disabled or also unavailable)
        """

        def get_instance_info(instance_type: str) -> Optional[Dict[str, Any]]:
            """Helper to check if an instance type is available in the region."""
            try:
                # Remove 'ml.' prefix for EC2 API call
                ec2_type = instance_type
                if instance_type.startswith("ml."):
                    ec2_type = ".".join(instance_type.split(".")[1:])

                response = self.ec2_client.describe_instance_types(InstanceTypes=[ec2_type])

                if not response.get("InstanceTypes"):
                    return None

                instance_info = response["InstanceTypes"][0]
                has_gpu = bool(instance_info.get("GpuInfo", {}).get("Gpus"))

                return {"instance_type": instance_type, "has_gpu": has_gpu}

            except ClientError:
                return None

        # Try preferred instance type
        info = get_instance_info(preferred_instance_type)
        if info:
            return info

        # Try fallback instance type if user does not provide one
        if use_fallback:
            info = get_instance_info(FALLBACK_INSTANCE_TYPE)
            if info:
                return info

            # Both do not exist - raise error
            raise ValidationError(
                f"Neither the preferred instance type '{preferred_instance_type}' nor the fallback "
                f"instance type '{FALLBACK_INSTANCE_TYPE}' is available in the current region. "
                f"Please specify a valid instance type for this region."
            )
        else:
            raise ValidationError(
                f"Instance type '{preferred_instance_type}' is not available in the current region. Please specify a valid instance type for this region."
            )

    @staticmethod
    def validate_image_version(sem_ver: str):
        from packaging.version import InvalidVersion, Version

        # Allow "latest" as a valid version
        if sem_ver == "latest":
            return True

        try:
            # Parse the version using the packaging library
            parsed_version = Version(sem_ver)

            # Valid for any 3.x version (major version 3)
            if parsed_version.major == 3:
                return True

            # Since 2025 June, SMD switched to public images, valid versions are 2.6.x and above
            if parsed_version.major == 2 and (
                parsed_version.base_version == "2" or parsed_version.minor >= 6
            ):
                return True
            return False
        except InvalidVersion:
            raise ValidationError(f"Invalid image version {sem_ver}")

    @staticmethod
    def validate_domain_id(domain_id: str):
        """
        Validate DataZone domain ID format and constraints.

        Args:
            domain_id (str): The DataZone domain identifier to validate

        Raises:
            ValidationError: If the domain_id is invalid
        """
        if not domain_id:
            raise ValidationError("Domain ID cannot be empty")

        # DataZone domain IDs follow specific pattern: dzd[-_][a-zA-Z0-9_-]{1,36}
        if not re.match(r"^dzd[-_][a-zA-Z0-9_-]{1,36}$", domain_id):
            raise ValidationError(
                f"Invalid domain ID format: '{domain_id}'. "
                "Domain ID must follow the pattern 'dzd[-_][a-zA-Z0-9_-]{{1,36}}' "
                "(e.g., 'dzd-abc123', 'dzd_example-domain')"
            )

    @staticmethod
    def validate_project_id(project_id: str):
        """
        Validate DataZone project ID format and constraints.

        Args:
            project_id (str): The DataZone project identifier to validate

        Raises:
            ValidationError: If the project_id is invalid
        """
        if not project_id:
            raise ValidationError("Project ID cannot be empty")

        # DataZone project IDs follow pattern: [a-zA-Z0-9_-]{1,36}
        if not re.match(r"^[a-zA-Z0-9_-]{1,36}$", project_id):
            raise ValidationError(f"Invalid project ID: '{project_id}'. ")

    @staticmethod
    def validate_domain_region(domain_region: str):
        """
        Validate AWS region format for DataZone domain region.

        Args:
            domain_region (str): The AWS region to validate

        Raises:
            ValidationError: If the domain_region is invalid
        """
        if not domain_region:
            raise ValidationError("Domain region cannot be empty")

        # AWS region format validation: pattern covering all AWS regions with numbers
        # Pattern covers: us-east-1, eu-west-2, ap-southeast-1, us-gov-east-1, cn-north-1, etc.
        aws_region_pattern = r"^(us|eu|ap|sa|ca|af|me|il|cn|us-gov|us-iso|us-isob)-(north|south|east|west|central|northeast|northwest|southeast|southwest)-\d+$"

        if not re.match(aws_region_pattern, domain_region):
            raise ValidationError(
                f"Invalid AWS region format: '{domain_region}'. "
                "Region must follow AWS region naming convention (e.g., 'us-east-1', 'eu-west-2', 'ap-southeast-1')"
            )
