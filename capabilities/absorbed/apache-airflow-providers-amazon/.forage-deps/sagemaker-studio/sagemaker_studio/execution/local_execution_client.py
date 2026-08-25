import os
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests import Response
except Exception:
    pass

from sagemaker_studio._openapi.models import (
    GetExecutionRequest,
    ListExecutionsRequest,
    StartExecutionRequest,
    StopExecutionRequest,
)
from sagemaker_studio.data_models import HttpMethod
from sagemaker_studio.execution.utils import LocalExecutionUtils
from sagemaker_studio.models.execution import (
    ConflictError,
    ErrorType,
    ExecutionClient,
    ExecutionConfig,
    LocalExecutionStoppableStatuses,
    LocalExecutionTerminalStatusesWithOutputFiles,
    ServiceQuotaExceededError,
    Status,
    ThrottlingError,
)


class LocalExecutionClient(ExecutionClient):
    """
    A client for local execution of notebooks.

    This class extends the ExecutionClient to provide functionality
    for executing notebooks locally within the user's space.

    Attributes:
        Inherits all attributes from ExecutionClient.

    Methods:
        Inherits all methods from ExecutionClient and may override or add new ones
        specific to local execution.
    """

    def __init__(self, config: ExecutionConfig):
        self.xsrf = ""
        self.config: ExecutionConfig = config
        self.config.local = True

    """
    Retrieve information about a specific execution.
    This method fetches the details of an execution based on the provided request.

    Args:
        execution_id (str): The unique identifier of the execution to retrieve

    Returns:
        dict: A dictionary containing the execution details. It includes information such as:
            - execution_id: The unique identifier of the execution
            - status: The current status of the execution (e.g., 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'STOPPING', 'STOPPED')
            - start_time: The time when the execution started
            - end_time: The time when the execution ended (if applicable)
            - error_details: Details about any errors that occurred during execution (if applicable)
            - files: A list of output files associated with the execution (if applicable)

    Raises:
        ResourceNotFoundError: If the specified execution cannot be found.
        RequestError: For any other request-related errors during the execution retrieval.
        InternalServerError: For any server-side errors during the execution retrieval.

    Example:
        request = GetExecutionRequest(execution_id="exec-12345")
        execution_details = client.get_execution(request)
        print(f"Execution status: {execution_details['status']}")
    """

    def get_execution(self, execution_id: str) -> dict:
        parameters = {"execution_id": execution_id}
        request = GetExecutionRequest(**parameters)
        return self._get_execution_internal(request)

    def _get_execution_internal(self, request: GetExecutionRequest) -> dict:
        job_id: str = request.execution_id
        url: str = f"{LocalExecutionUtils.LOCAL_JOBS_SCHEDULER_URL}/{job_id}"

        try:
            job_data: dict = LocalExecutionUtils.fetch_data(url)

            if job_data["status"] in LocalExecutionTerminalStatusesWithOutputFiles.__members__:
                response = {
                    "execution_id": job_id,
                    "status": job_data["status"],
                    "start_time": job_data.get("start_time", None),
                    **(
                        {"end_time": job_data.get("end_time")}
                        if job_data.get("end_time") is not None
                        else {}
                    ),
                }

                if job_data["status"] == "FAILED":
                    response["error_details"] = {
                        "error_type": ErrorType.SERVER_ERROR,
                        "error_message": job_data.get("status_message", None),
                    }

                job_files = job_data["job_files"]
                if not job_data["downloaded"]:
                    LocalExecutionUtils.download_job_files(
                        LocalExecutionUtils.LOCAL_JOBS_SCHEDULER_URL, job_id
                    )
                    updated_job_data: dict = LocalExecutionUtils.fetch_data(url)
                    job_files = updated_job_data["job_files"]
                response["files"] = job_files

                return response
            else:
                return {
                    "execution_id": job_id,
                    "status": job_data["status"],
                    "start_time": job_data.get("start_time", None),
                    **(
                        {"end_time": job_data.get("end_time")}
                        if job_data.get("end_time") is not None
                        else {}
                    ),
                }
        except Exception as e:
            raise LocalExecutionUtils.get_api_error(e, "GetExecution", request.execution_id)

    """
    Retrieve a list of executions based on the provided request parameters.

    This method fetches a list of executions that match the criteria specified in the request.
    It can be used to query executions based on various filters, pagination, and sorting options.

    Args:
        start_time_after (Optional[int]): Filter executions starting after a specific time
        name_contains (Optional[str]): Filter executions whose name contains a specific string
        status (Optional[str]): Filter executions by their current status (e.g., 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'STOPPING', 'STOPPED')
        sort_order (Optional[str]): Order to return results (e.g., 'ASCENDING' or 'DESCENDING')
        sort_by (Optional[str]): Field to sort the results by (e.g., 'NAME', 'STATUS', 'START_TIME', 'END_TIME')
        next_token (Optional[str]): Token for pagination
        max_results (Optional[int]): Maximum number of results to return

    Returns:
        dict: A dictionary containing the list of executions and metadata. Typical structure:
            {
                "executions": [
                    {
                        "id": str,
                        "name": str,
                        "status": str,
                        "start_time": int,
                        "end_time": int
                    },
                    # ... more executions
                ],
                "next_token": str,  # Token for retrieving the next page of results, if applicable
            }

    Raises:
        RequestError: For any other request-related errors during the execution.
        InternalServerError: For any server-side errors during the execution retrieval.

    Example:
        request = ListExecutionsRequest(
            max_results=10,
            status="COMPLETED",
            sort_by="start_time",
            sort_order="DESCENDING"
        )
        result = client.list_executions(request)
        for execution in result["executions"]:
            print(f"Execution ID: {execution['execution_id']}, Status: {execution['status']}")

        if "next_token" in result:
            # Handle pagination
            next_request = ListExecutionsRequest(
                max_results=10,
                next_token=result["next_token"]
            )
            # ... make next request
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

        request = ListExecutionsRequest(**parameters)
        return self._list_executions_internal(request)

    def _list_executions_internal(self, request: ListExecutionsRequest) -> dict:
        try:
            search_sort_order = (
                "asc"
                if request.get("sort_order") and request.get("sort_order") == "ASCENDING"
                else "desc"
            )
            jupyter_scheduler_sort_by = LocalExecutionUtils.get_jupyter_scheduler_sort_by(
                sort_order=search_sort_order, sort_by=request.get("sort_by")
            )
            query_params = {
                "start_time": request.start_time_after if request.get("start_time_after") else None,
                "name": request.name_contains if request.get("name_contains") else None,
                "status": Status(request.status).value if request.get("status") else None,
                "sort_by": jupyter_scheduler_sort_by if jupyter_scheduler_sort_by else None,
                "next_token": request.next_token if request.get("next_token") else None,
                "max_items": request.max_results if request.get("max_results") else None,
            }
            query_params = {
                param_name: param_value
                for param_name, param_value in query_params.items()
                if param_value is not None
            }
            job_scheduler_list_response: dict = LocalExecutionUtils.fetch_data(
                LocalExecutionUtils.get_url_with_query_params(
                    base_url=LocalExecutionUtils.LOCAL_JOBS_SCHEDULER_URL,
                    params=query_params,
                )
            )
            jobs_data = job_scheduler_list_response.get("jobs", [])

            executions: List[Dict[str, Any]] = []
            for item in jobs_data:
                executions.append(
                    {
                        "id": item["job_id"],
                        "name": item["name"],
                        "status": item["status"],
                        "start_time": item.get("start_time", None),
                        **(
                            {"end_time": item.get("end_time")}
                            if item.get("end_time") is not None
                            else {}
                        ),
                    }
                )
            return {
                "executions": executions,
                **(
                    {"next_token": job_scheduler_list_response["next_token"]}
                    if "next_token" in job_scheduler_list_response
                    else {}
                ),
            }
        except Exception as e:
            raise LocalExecutionUtils.get_api_error(e, "ListExecutions")

    """
    Initiates a new execution in the user space based on the provided request parameters.

    Args:
        execution_name (str): A unique name for the execution
        execution_type (Optional[str]): The type of execution (e.g., 'NOTEBOOK')
        input_config (Dict[str, Any]): Configuration for the input data for the execution
        output_config (Optional[Dict[str, Any]]): Configuration for the outputs like output formats
        client_token (Optional[str]): A unique token to ensure idempotency

    Returns:
        dict: A dictionary containing information about the started execution. Typical structure:
            {
                "execution_id": str,  # Unique identifier for the started execution
                "execution_name": str,  # Name of the execution
                "input_config":  dict,  # Configuration for the input data
                "output_config": dict,  # Configuration for the output data
                "client_token": str,  # Client token used for idempotency
            }

    Raises:
        ThrottlingError: If starting the execution would exceed available CPU capacity on the instance.
        ServiceQuotaExceededError: If starting the execution would exceed the amount of EBS volume available on the instance.
        ConflictError: If a execution with the same client token already exists.
        RequestError: For any other request-related errors during the execution.
        InternalServerError: For any server-side errors during the execution.

    Example:
        request = StartExecutionRequest(
            execution_name="MyExecution-001",
            execution_type="NOTEBOOK",
            client_token="unique-token-123",
            input_config={
                "notebook_config": {
                    "input_path": "src/test.ipynb"
                }
            },
            output_config={
                "notebook_config" : {
                    "output_formats": ["NOTEBOOK", "HTML"]
                }
            }
        )
        result = client.start_execution(request)
        print(f"Execution started with ID: {result['execution_id']}")
        print(f"Current status: {result['status']}")
    """

    def start_execution(
        self,
        execution_name: str,
        input_config: Dict[str, Any] = {},
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
        return self._start_execution_internal(request)

    def _start_execution_internal(self, request: StartExecutionRequest) -> dict:
        import psutil

        self.xsrf = self.__set_cookies()
        load_avg_one_min = psutil.getloadavg()[0]
        num_cpus = psutil.cpu_count()
        if load_avg_one_min > num_cpus:
            print(f"Throttling {load_avg_one_min} > {num_cpus}")
            raise ThrottlingError("Not enough CPU capacity to start execution")
        bytes_free = LocalExecutionUtils.get_bytes_free(LocalExecutionUtils.SAGEMAKER_USER_HOME)
        bytes_needed = LocalExecutionUtils.get_bytes_needed(
            os.path.dirname(
                LocalExecutionUtils.SAGEMAKER_USER_HOME
                + "/"
                + request.input_config["notebook_config"]["input_path"]
            )
        )
        if bytes_needed > bytes_free:
            print(
                f"ServiceQuotaExceeded {LocalExecutionUtils.get_size_format(bytes_needed)} > "
                f"{LocalExecutionUtils.get_size_format(bytes_free)}"
            )
            raise ServiceQuotaExceededError(
                f"Not enough free space on EBS volume to start execution. "
                f"Please cleanup some older files from {LocalExecutionUtils.SAGEMAKER_USER_HOME}/jobs folder to free up "
                f"some space on EBS volume."
            )

        output_formats = (
            request.get("output_config", {})
            .get("notebook_config", {})
            .get("output_formats", ["NOTEBOOK"])
        )
        output_formats_lowercase = [
            output_format.lower().replace("notebook", "ipynb") for output_format in output_formats
        ]

        create_job_request = {
            "runtime_environment_name": "conda",
            "input_uri": request.input_config["notebook_config"]["input_path"],
            "name": request.execution_name,
            "package_input_folder": True,
            "output_formats": output_formats_lowercase,
        }
        if request.get("client_token"):
            create_job_request["idempotency_token"] = request.get("client_token")
        if request.input_config.get("notebook_config", {}).get("input_parameters", {}):
            create_job_request["parameters"] = request.input_config["notebook_config"][
                "input_parameters"
            ]
        params = {
            "headers": {
                "Content-Type": "application/json",
                "X-Xsrftoken": self.xsrf,
                "Cookie": f"_xsrf={self.xsrf}",
            },
            "method": HttpMethod.POST,
            "credentials": "include",
            "body": create_job_request,
        }

        try:
            start_execution_response: dict = LocalExecutionUtils.fetch_data(
                url=LocalExecutionUtils.LOCAL_JOBS_SCHEDULER_URL,
                params=params,
            )
            response = {
                "execution_id": start_execution_response["job_id"],
                "execution_name": request.execution_name,
                "input_config": {
                    "notebook_config": {
                        "input_path": request.input_config.notebook_config.input_path
                    },
                },
            }

            if request.input_config.notebook_config.get("input_parameters"):
                response["input_config"]["notebook_config"]["input_parameters"] = (
                    request.input_config.notebook_config.get("input_parameters")
                )
            if request.get("output_config"):
                response["output_config"] = request.output_config.to_dict()
            if "output_formats" not in request.get("output_config", {}).get("notebook_config", {}):
                response.setdefault("output_config", {}).setdefault("notebook_config", {})[
                    "output_formats"
                ] = ["NOTEBOOK"]
            if request.get("client_token"):
                response["client_token"] = request.client_token
            return response
        except Exception as e:
            raise LocalExecutionUtils.get_api_error(
                exception=e, api="StartExecution", reference_id=request.execution_name
            )

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
        RequestError: For any other request-related errors during the execution.
        ResourceNotFoundError: If the specified execution cannot be found.
        ConflictError: If the execution is already in a terminal state (e.g., Completed, Failed)
            or cannot be stopped for any other reason.
        InternalServerError: For any other unexpected errors during the execution of this method.
        RuntimeError: If the execution cannot be stopped due to an unexpected error.

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
        self.xsrf = self.__set_cookies()
        url = f"{LocalExecutionUtils.LOCAL_JOBS_SCHEDULER_URL}/{request.execution_id}"
        get_execution_status = self._get_execution_internal(
            GetExecutionRequest(execution_id=request.execution_id)
        ).get("status")
        if get_execution_status not in LocalExecutionStoppableStatuses.__members__:
            raise ConflictError(f"{request.execution_id} not running")

        try:
            LocalExecutionUtils.fetch_data(
                url=url,
                params={
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Xsrftoken": self.xsrf,
                        "Cookie": f"_xsrf={self.xsrf}",
                    },
                    "method": HttpMethod.PATCH,
                    "credentials": "include",
                    "body": {"status": "STOPPED"},
                },
            )
        except Exception as e:
            raise LocalExecutionUtils.get_api_error(e, "StopExecution", request.execution_id)

    def __set_cookies(self) -> str:
        if self.config.local:
            # Hit http://localhost:8888/jupyterlab/default endpoint should set the
            # cookies to be used in the subsequent request to scheduler jobs api.
            response: Response = requests.get(
                f"{LocalExecutionUtils.LOCAL_EXECUTION_HOST}/jupyterlab/default/lab"
            )
            if not response.ok:
                raise RuntimeError(f"HTTP error! Status: {response.status_code}")

            self.xsrf = ""
            xsrf_cookies = [
                cookie for cookie in response.cookies if cookie.name.startswith("_xsrf")
            ]
            if len(xsrf_cookies) == 1:
                self.xsrf = xsrf_cookies[0].value if xsrf_cookies[0].value else ""
            else:
                raise RuntimeError("XSRF cookie not found")
        else:
            raise RuntimeError("Remote execution not supported yet")

        return self.xsrf
