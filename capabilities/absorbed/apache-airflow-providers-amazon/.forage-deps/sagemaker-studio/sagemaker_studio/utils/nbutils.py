"""
Notebook utilities for managing notebook parameters.

Provides methods to retrieve and display notebook parameters.
Parameters are resolved in the following order:
1. Environment variables (namespaced with SMUS_NOTEBOOK_PARAM_ prefix)
2. Notebook metadata via DataZone API with notebook run ID (async execution)
3. Notebook metadata via DataZone API with notebook ID
4. Parameters cell in the local .ipynb file (fallback for exported notebooks)

Usage:
    from sagemaker_studio.utils import nbutils

    # Display all notebook parameters
    nbutils.parameters.show()

    # Get a specific parameter value
    value = nbutils.parameters.get('my_param')
"""

import ast
import json
import logging
import os
from typing import Any, Dict, Optional

import sagemaker_studio.utils

logger = logging.getLogger(__name__)

SMUS_NOTEBOOK_PARAM_PREFIX = "SAGEMAKER_NOTEBOOK_PARAMETER_"
_PARAMETERS_CELL_TAG = "parameters"
_INJECTED_PARAMETERS_CELL_TAG = "injected-parameters"


_NOT_LOADED = object()


class _NotebookMetadataReader:
    """Reads notebook ID and run ID from the SageMaker resource metadata file."""

    def __init__(self):
        self._metadata = _NOT_LOADED

    def _load_metadata(self) -> Optional[dict]:
        if self._metadata is not _NOT_LOADED:
            return self._metadata
        metadata_path = sagemaker_studio.utils.SAGEMAKER_METADATA_JSON_PATH
        if not os.path.exists(metadata_path):
            self._metadata = None
            return None
        try:
            with open(metadata_path, "r") as f:
                self._metadata = json.load(f)
            return self._metadata
        except Exception as e:
            logger.warning(f"Failed to read metadata file: {e}")
            self._metadata = None
            return None

    def get_notebook_id(self) -> Optional[str]:
        metadata = self._load_metadata()
        if not metadata:
            return None
        return metadata.get("NotebookId") or metadata.get("AdditionalMetadata", {}).get(
            "NotebookId"
        )

    def get_notebook_run_id(self) -> Optional[str]:
        metadata = self._load_metadata()
        if not metadata:
            return None
        return metadata.get("NotebookRunId") or metadata.get("AdditionalMetadata", {}).get(
            "NotebookRunId"
        )

    def get_domain_id(self) -> Optional[str]:
        metadata = self._load_metadata()
        if not metadata:
            return None
        return metadata.get("DomainId") or metadata.get("AdditionalMetadata", {}).get(
            "DataZoneDomainId"
        )

    def get_notebook_path(self) -> Optional[str]:
        metadata = self._load_metadata()
        if not metadata:
            return None
        return metadata.get("InputNotebookPath") or metadata.get("AdditionalMetadata", {}).get(
            "InputNotebookPath"
        )


_NOT_INITIALIZED = object()


class _DataZoneNotebookClient:
    """Thin wrapper around the DataZone API for notebook parameter operations."""

    def __init__(self):
        self._datazone_api = _NOT_INITIALIZED

    def _ensure_client(self):
        if self._datazone_api is not _NOT_INITIALIZED:
            return self._datazone_api
        try:
            from sagemaker_studio.sagemaker_studio_api import SageMakerStudioAPI

            api = SageMakerStudioAPI()
            self._datazone_api = api.datazone_api
        except Exception as e:
            logger.warning(f"Failed to initialize DataZone client: {e}")
            self._datazone_api = None
        return self._datazone_api

    def get_notebook_parameters(self, domain_id: str, notebook_id: str) -> Dict[str, str]:
        """
        Retrieve notebook parameters via GetNotebookWIP API.

        Accesses response.parameters from the notebook resource.

        Args:
            domain_id: The DataZone domain ID.
            notebook_id: The notebook ID.

        Returns:
            A dictionary of parameter name-value pairs.
        """
        client = self._ensure_client()
        if client is None:
            logger.warning("DataZone client is not available, cannot fetch notebook parameters")
            return {}
        try:
            response = client.get_notebook(domainIdentifier=domain_id, identifier=notebook_id)
            params = response.get("parameters", {})
            return _parse_parameters(params)
        except Exception as e:
            logger.warning(f"Failed to get notebook parameters from DataZone API: {e}")
            return {}

    def get_notebook_run_parameters(self, domain_id: str, run_id: str) -> Dict[str, str]:
        """
        Retrieve notebook parameters for a specific async run via GetNotebookRun API.

        Accesses response.parameters from the notebook run resource.

        Args:
            domain_id: The DataZone domain ID.
            run_id: The notebook run ID.

        Returns:
            A dictionary of parameter name-value pairs.
        """
        client = self._ensure_client()
        if client is None:
            logger.warning("DataZone client is not available, cannot fetch notebook run parameters")
            return {}
        try:
            response = client.get_notebook_run(domainIdentifier=domain_id, identifier=run_id)
            params = response.get("parameters", {})
            return _parse_parameters(params)
        except Exception as e:
            logger.warning(f"Failed to get notebook run parameters from DataZone API: {e}")
            return {}


def _parse_parameters(raw_parameters) -> Dict[str, str]:
    """Parse parameters, handling both dict and JSON string formats."""
    if isinstance(raw_parameters, dict):
        return {str(k): str(v) for k, v in raw_parameters.items()}
    if isinstance(raw_parameters, str):
        try:
            parsed = json.loads(raw_parameters)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass
    return {}


def _extract_parameters_from_notebook_file(notebook_path: str) -> Dict[str, str]:
    """
    Parse a local .ipynb file and extract parameters following the papermill convention.

    Looks for cells tagged with 'parameters' (default values) and
    'injected-parameters' (overridden values injected by papermill at execution time).
    If both exist, injected-parameters values take precedence.

    This is the fallback for exported notebooks that contain a parameters cell
    defining default parameter values as Python variable assignments.

    Args:
        notebook_path: Path to the .ipynb file.

    Returns:
        A dictionary of parameter name-value pairs.
    """
    if not notebook_path or not os.path.exists(notebook_path):
        return {}
    try:
        with open(notebook_path, "r") as f:
            nb = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read notebook file {notebook_path}: {e}")
        return {}

    params: Dict[str, str] = {}
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        tags = cell.get("metadata", {}).get("tags", [])
        if _PARAMETERS_CELL_TAG in tags:
            source = "".join(cell.get("source", []))
            params.update(_parse_parameter_assignments(source))
        if _INJECTED_PARAMETERS_CELL_TAG in tags:
            # Injected parameters override defaults
            source = "".join(cell.get("source", []))
            params.update(_parse_parameter_assignments(source))

    return params


def _strip_inline_comment(value: str) -> str:
    """Strip inline comment, respecting quoted strings."""
    if value and value[0] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[: end + 1]
    if "#" in value:
        return value[: value.index("#")].rstrip()
    return value


def _parse_parameter_assignments(source: str) -> Dict[str, str]:
    """
    Parse simple Python variable assignments from a parameters cell source.

    Handles patterns like:
        my_param = "hello"
        num_epochs = 10
        learning_rate = 0.01

    Args:
        source: The raw source code of the parameters cell.

    Returns:
        A dictionary of parameter name-value pairs (all values as strings).
    """
    params: Dict[str, str] = {}
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip type annotation (e.g. "learning_rate: float" -> "learning_rate")
            if ":" in key:
                key = key.split(":", 1)[0].strip()
            if not key.isidentifier():
                continue
            value = _strip_inline_comment(value)
            # Strip surrounding quotes if present
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            params[key] = value
    return params


class NotebookParameters:
    """
    Provides methods to retrieve and display notebook parameters.

    Parameters are resolved using a layered approach:
    1. Environment variables (SMUS_NOTEBOOK_PARAM_ prefix)
    2. DataZone notebook metadata with run ID (async execution)
    3. DataZone notebook metadata with notebook ID
    4. Parameters cell in the local .ipynb file (exported notebooks)
    """

    _UNRESOLVED = object()

    def __init__(self, notebook_path: Optional[str] = None):
        self._metadata_reader = _NotebookMetadataReader()
        self._dz_client = _DataZoneNotebookClient()
        self._explicit_path = notebook_path
        self._notebook_path_cache = self._UNRESOLVED

    @property
    def _notebook_path(self) -> Optional[str]:
        if self._notebook_path_cache is self._UNRESOLVED:
            self._notebook_path_cache = (
                self._explicit_path or self._metadata_reader.get_notebook_path()
            )
        return self._notebook_path_cache

    @staticmethod
    def _try_parse_json(value: Any) -> Any:
        """Attempt to parse a string value as JSON, recursively deserializing
        string values within dicts and lists.

        If the value is a string that represents a JSON object, array,
        or other JSON literal, return the parsed result. Otherwise
        return the original value unchanged.

        Handles values wrapped in extra surrounding quotes (single or
        double) which may come from the DataZone API.

        Also handles Python-style literals (e.g. single-quoted strings,
        lists with single quotes like ``['a', 'b']``) via
        ``ast.literal_eval`` as a fallback.

        For dicts, each string value is recursively deserialized so that
        nested JSON-encoded strings (e.g. ``"true"`` → ``True``,
        ``"[1, 2]"`` → ``[1, 2]``) are automatically parsed.
        """
        if not isinstance(value, str):
            # Recursively deserialize string values inside dicts and lists
            if isinstance(value, dict):
                return {k: NotebookParameters._try_parse_json(v) for k, v in value.items()}
            if isinstance(value, list):
                return [NotebookParameters._try_parse_json(item) for item in value]
            return value
        stripped = value.strip()
        # Strip surrounding quotes that may wrap a JSON payload
        if (stripped.startswith("'") and stripped.endswith("'")) or (
            stripped.startswith('"') and stripped.endswith('"')
        ):
            stripped = stripped[1:-1]
        try:
            parsed = json.loads(stripped)
            return NotebookParameters._try_parse_json(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        # Fall back to original value without stripping
        try:
            parsed = json.loads(value)
            return NotebookParameters._try_parse_json(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        # Fall back to ast.literal_eval for Python-style literals
        # (e.g. "['chess', 'gaming']" or "{'key': 'value'}")
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (dict, list, tuple)):
                return NotebookParameters._try_parse_json(parsed)
            return parsed
        except (ValueError, SyntaxError):
            return value

    def get(self, name: str, default: Any = None) -> Any:
        """
        Get the value of a notebook parameter by name.

        Resolution order:
        1. Check environment variables (SMUS_NOTEBOOK_PARAM_{name}).
           If found, return immediately.
        2. If metadata file has notebook ID and run ID, get parameters
           for that run from DataZone API and return.
        3. If metadata file has notebook ID (no run ID), get parameters
           for the notebook from DataZone API and return.
        4. If metadata file / notebook ID not available, attempt to find
           a parameters cell in the local .ipynb file.
        5. Otherwise return default.

        If the resolved value is a JSON-encoded string (e.g. a dict or
        list), it is automatically parsed into the corresponding Python
        object before being returned.

        Args:
            name: The parameter name.
            default: Value to return if the parameter is not found.

        Returns:
            The parameter value, automatically parsed from JSON when
            applicable, or the default value if not found.
        """
        # Step 1: Check namespaced environment variable
        env_key = f"{SMUS_NOTEBOOK_PARAM_PREFIX}{name}"
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return self._try_parse_json(env_value)

        # Step 2 & 3: Try DataZone API
        domain_id = self._metadata_reader.get_domain_id()
        notebook_id = self._metadata_reader.get_notebook_id()
        run_id = self._metadata_reader.get_notebook_run_id()

        if domain_id and notebook_id and run_id:
            # Step 2: notebook ID + run ID exist
            params = self._dz_client.get_notebook_run_parameters(
                domain_id=domain_id,
                run_id=run_id,
            )
            if name in params:
                return self._try_parse_json(params[name])
        elif domain_id and notebook_id:
            # Step 3: notebook ID exists, no run ID
            params = self._dz_client.get_notebook_parameters(
                domain_id=domain_id,
                notebook_id=notebook_id,
            )
            if name in params:
                return self._try_parse_json(params[name])

        # Step 4: Fall back to parameters cell in local .ipynb
        if self._notebook_path:
            cell_params = _extract_parameters_from_notebook_file(self._notebook_path)
            if name in cell_params:
                return self._try_parse_json(cell_params[name])

        return default

    def show(self) -> Dict[str, str]:
        """
        Display all notebook parameters from all available sources.

        Collects parameters following the same resolution order as get():
        1. DataZone API (run-level or notebook-level)
        2. Parameters cell in local .ipynb file
        3. Environment variables with SMUS_NOTEBOOK_PARAM_ prefix

        Later sources override earlier ones, so env vars have highest precedence.

        Returns:
            A dictionary of all parameter name-value pairs.
        """
        all_params: Dict[str, str] = {}

        # Lowest precedence: parameters cell
        if self._notebook_path:
            cell_params = _extract_parameters_from_notebook_file(self._notebook_path)
            all_params.update(cell_params)

        # Middle precedence: DataZone API
        domain_id = self._metadata_reader.get_domain_id()
        notebook_id = self._metadata_reader.get_notebook_id()
        run_id = self._metadata_reader.get_notebook_run_id()

        if domain_id and notebook_id and run_id:
            api_params = self._dz_client.get_notebook_run_parameters(
                domain_id=domain_id,
                run_id=run_id,
            )
            all_params.update(api_params)
        elif domain_id and notebook_id:
            api_params = self._dz_client.get_notebook_parameters(
                domain_id=domain_id,
                notebook_id=notebook_id,
            )
            all_params.update(api_params)

        # Highest precedence: environment variables
        for key, value in os.environ.items():
            if key.startswith(SMUS_NOTEBOOK_PARAM_PREFIX):
                param_name = key[len(SMUS_NOTEBOOK_PARAM_PREFIX) :]
                all_params[param_name] = value

        return all_params


# Module-level singleton for convenient access: nbutils.parameters.get(...) / nbutils.parameters.show()
parameters = NotebookParameters()

logger.info("Finished importing nbutils")
