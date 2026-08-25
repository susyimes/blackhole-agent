import json
import os
import re
import urllib
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests import Response
except Exception:
    pass

from sagemaker_studio.data_models import HttpMethod
from sagemaker_studio.models.execution import (
    ConflictError,
    InternalServerError,
    ProblemJsonError,
    RequestError,
    ResourceNotFoundError,
    SortBy,
    SortOrder,
    Status,
)
from sagemaker_studio.utils import S3PathForProject


class ExecutionUtils:

    @staticmethod
    def map_sort_by(sort_by: SortBy):
        search_sort_by = "TrainingStartTime"
        if sort_by == SortBy.NAME:
            search_sort_by = "TrainingJobName"
        elif sort_by == SortBy.STATUS:
            search_sort_by = "TrainingJobStatus"
        elif sort_by == SortBy.START_TIME:
            search_sort_by = "TrainingStartTime"
        elif sort_by == SortBy.END_TIME:
            search_sort_by = "TrainingEndTime"
        return search_sort_by

    @staticmethod
    def map_sort_order(sort_order: SortOrder):
        if sort_order == SortOrder.ASCENDING:
            return "Ascending"
        elif sort_order == SortOrder.DESCENDING:
            return "Descending"
        else:
            raise RuntimeError(f"Invalid sort order defined: {sort_order}")

    @staticmethod
    def map_training_job_status_to_status(training_job_status: str):
        if training_job_status == "InProgress":
            return Status.IN_PROGRESS
        elif training_job_status == "Completed":
            return Status.COMPLETED
        elif training_job_status == "Failed":
            return Status.FAILED
        elif training_job_status == "Stopping":
            return Status.STOPPING
        elif training_job_status == "Stopped":
            return Status.STOPPED
        else:
            raise RuntimeError(f"Invalid training job status defined: {training_job_status}")

    @staticmethod
    def map_status_to_training_job_status(input_job_status: Status):
        if input_job_status == Status.IN_PROGRESS:
            return "InProgress"
        elif input_job_status == Status.COMPLETED:
            return "Completed"
        elif input_job_status == Status.FAILED:
            return "Failed"
        elif input_job_status == Status.STOPPING:
            return "Stopping"
        elif input_job_status == Status.STOPPED:
            return "Stopped"
        else:
            raise RuntimeError(f"Invalid input job status defined: {input_job_status}")

    @staticmethod
    def unpack_path_file(path_file: str):
        split_path_file = path_file.split("/")
        if len(split_path_file) < 2:
            raise ValueError(f"Path and filename required: {path_file})")

        path = split_path_file[0 : len(split_path_file) - 1]
        file = split_path_file[-1]

        return {"path": "/".join(path), "file": file}

    @staticmethod
    def convert_timestamp_to_epoch_millis(timestamp: datetime):
        #  convert to milliseconds
        return int(timestamp.timestamp() * 1000)

    @staticmethod
    def create_sagemaker_search_expression_for_training(
        domain_identifier: str,
        project_identifier: str,
        start_time_after: Optional[int] = None,
        name_contains: Optional[str] = None,
        search_status: Optional[str] = None,
        filter_by_tags: Optional[Dict[str, str]] = None,
    ):
        filters: List[Dict[str, Any]] = [
            {"Name": "Tags.sagemaker-notebook-execution", "Operator": "Equals", "Value": "TRUE"},
            {
                "Name": "Tags.AmazonDataZoneProject",
                "Operator": "Equals",
                "Value": project_identifier,
            },
            {"Name": "Tags.AmazonDataZoneDomain", "Operator": "Equals", "Value": domain_identifier},
        ]

        if name_contains:
            filters.append(
                {"Name": "TrainingJobName", "Operator": "Contains", "Value": name_contains}
            )
        if start_time_after:
            filters.append(
                {
                    "Name": "TrainingStartTime",
                    "Operator": "GreaterThanOrEqualTo",
                    "Value": datetime.fromtimestamp(start_time_after / 1000.0).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
            )
        if search_status:
            filters.append(
                {"Name": "TrainingJobStatus", "Operator": "Equals", "Value": search_status}
            )
        if filter_by_tags:
            for tag_key, tag_value in filter_by_tags.items():
                filters.append(
                    {"Name": f"Tags.{tag_key}", "Operator": "Equals", "Value": tag_value}
                )

        return {"Filters": filters} if filters else {}


class LocalExecutionUtils:
    LOCAL_EXECUTION_HOST = "http://localhost:8888"
    LOCAL_JOBS_SCHEDULER_URL = f"{LOCAL_EXECUTION_HOST}/jupyterlab/default/scheduler/jobs"
    SAGEMAKER_USER_HOME = "/home/sagemaker-user"

    @staticmethod
    def download_job_files(jobs_url: str, job_id: str, redownload: bool = False):
        download_url = f"{jobs_url}/{job_id}/download_files?redownload={redownload}"
        try:
            response: Response = requests.get(download_url)
            if not response.ok:
                raise RuntimeError(f"Network response was not ok: {response.text}")
            print(f"Downloaded the output files of job {job_id} successfully.")
        except Exception as e:
            raise RuntimeError(f"Exception occurred when downloading output files of {job_id}: {e}")

    @staticmethod
    def fetch_data(url: str, params: dict = {}) -> dict:
        body = headers = None
        method = HttpMethod.GET

        if "headers" in params:
            headers = params["headers"]
        if "body" in params:
            body = json.dumps(params["body"])
        if "method" in params:
            method = params["method"]

        response: Response
        if method == HttpMethod.GET:
            response = requests.get(url, headers=headers)
        elif method == HttpMethod.POST:
            response = requests.post(url, data=body, headers=headers)
        elif method == HttpMethod.PATCH:
            response = requests.patch(url, data=body, headers=headers)

        if response.status_code == 204:
            return {}
        if response.ok:
            return response.json()

        content_type = response.headers.get("content-type")
        if content_type == "application/problem+json" and "content-length" in response.headers:
            error = response.json()
            if "detail" in error:
                raise ProblemJsonError(error)

        error_message = json.loads(response.text).get("message")
        if error_message is None:
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                error_message = str(e)

        raise RequestError(error_message, response=response)

    @staticmethod
    def get_url_with_query_params(base_url: str, params: dict):
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def get_jupyter_scheduler_sort_by(sort_order: str, sort_by: Optional[str] = None):
        request_sort_by = "start_time"
        if sort_by:
            request_sort_by = LocalExecutionUtils.map_sort_by(SortBy(sort_by))
        return sort_order + "(" + request_sort_by + ")"

    @staticmethod
    def map_sort_by(sort_by: SortBy):
        search_sort_by = "start_time"
        if sort_by == SortBy.NAME:
            search_sort_by = "name"
        elif sort_by == SortBy.STATUS:
            search_sort_by = "status"
        elif sort_by == SortBy.END_TIME:
            search_sort_by = "end_time"
        return search_sort_by

    @staticmethod
    def get_api_error(exception: Exception, api: str, reference_id: Optional[str] = None):
        general_message = f"An error occurred during {api}"
        if reference_id:
            general_message += f" for {reference_id}"

        if isinstance(exception, RequestError):
            http_status_code = exception.response.status_code
            if http_status_code == 404:
                return ResourceNotFoundError(
                    f"{general_message}: {exception.response.reason}: {exception}"
                )
            elif http_status_code == 409:
                return ConflictError(f"{general_message}: Execution with token already exists")
            else:
                return InternalServerError(
                    f"{general_message}: {exception.response.reason}: {exception}"
                )
        else:
            return InternalServerError(f"{general_message}: An unknown error occurred: {exception}")

    @staticmethod
    def get_bytes_free(folder: str):
        try:
            stats = os.statvfs(folder)
            return stats.f_bsize * stats.f_bavail
        except Exception as e:
            print(f"Unable to get free size of folder {folder}")
            print(e)
            return 0

    @staticmethod
    def get_bytes_needed(file_path: str):
        total_folder_bytes = LocalExecutionUtils.get_folder_bytes(file_path)
        # jupyterlab scheduler makes 2 copies of the input folder
        return 2 * total_folder_bytes

    @staticmethod
    def get_folder_bytes(folder: str):
        total_bytes = 0
        for root, dirs, files in os.walk(folder):
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    total_bytes += os.path.getsize(file_path)
                except Exception:
                    print(
                        f"Warning: Unable to get size of file {file_path}, continuing to check other files..."
                    )
        return total_bytes

    @staticmethod
    def get_size_format(b, factor=1024, suffix="B"):
        """
        Scale bytes to its proper byte format
        e.g:
            1253656 => '1.20MB'
            1253656678 => '1.17GB'
        """
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
            if b < factor:
                return f"{b:.2f}{unit}{suffix}"
            b /= factor
        return f"{b:.2f}Y{suffix}"


class RemoteExecutionUtils:

    @staticmethod
    def is_git_project(provisioned_resources: list):
        storage_type = "S3"
        for resource in provisioned_resources:
            if resource.get("name") in ["gitConnectionArn", "codeRepositoryName"]:
                storage_type = "Git"
                break
        return storage_type == "Git"

    @staticmethod
    def pack_s3_path_for_input_file(
        project_s3_path: str, local_file_path: str, is_git_project: bool
    ) -> str:
        """Given the project s3 path, and path to the local input file,
        Generate the s3 path for the input file.
        An example of local_file_path will be like `src/getting_started.ipynb`, since for remote execution,
        this input path will be the same as it for local execution.
        We will need to strip the leading `src`.

        """

        project_s3_path = project_s3_path.rstrip("/")
        if is_git_project:
            local_file_path = re.sub(r"^/?src/", "", local_file_path)
        else:  # S3
            project_s3_path = project_s3_path.replace(
                "/dev", "/shared"
            )  # replace with 'shared' if there's 'dev'
            local_file_path = re.sub(r"^/?shared/", "", local_file_path)
            return f"{project_s3_path}/{local_file_path}"
        return f"{project_s3_path}{S3PathForProject.WORKFLOW_PROJECT_FILES_LOCATION.value}{local_file_path}"

    @staticmethod
    def pack_s3_path_for_output_file(
        project_s3_path: str, local_input_file_path: str, is_git_project: bool
    ) -> str:
        """Given the project s3 path, the local input file path, generate the s3 path for the output file s3 location.
        An example of local_input_file_path will be like `src/getting_started.ipynb`,
        the output s3 location will be like `s3://<project-s3-path>/workflows/output/_getting_started.ipynb`

        Args:
            project_s3_path (str): the project s3 path
            local_input_file_path (str): the local input file path
            is_git_storage (bool): if the project is git

        Returns:
            str: output file s3 location
        """
        project_s3_path = project_s3_path.rstrip("/")
        if is_git_project:
            local_input_file_path = re.sub(r"^/?src/", "", local_input_file_path)
        else:  # S3
            local_input_file_path = re.sub(r"^/?shared/", "", local_input_file_path)
        directory, file_name = os.path.split(local_input_file_path)
        output_file_path = os.path.join(directory, f"_{file_name}")

        return (
            f"{project_s3_path}{S3PathForProject.WORKFLOW_OUTPUT_LOCATION.value}{output_file_path}"
        )

    @staticmethod
    def pack_full_path_for_input_file(local_input_file_path: str) -> str:
        cleaned_path = local_input_file_path.lstrip("/")
        return os.path.join(LocalExecutionUtils.SAGEMAKER_USER_HOME, cleaned_path)
