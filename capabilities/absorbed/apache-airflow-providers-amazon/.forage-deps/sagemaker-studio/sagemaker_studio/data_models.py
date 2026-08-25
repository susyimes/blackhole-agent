from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from boto3 import Session


@dataclass
class BaseClientConfig:
    profile_name: Optional[str] = None
    region: Optional[str] = field(default=None)
    session: Optional[Session] = field(default=None)


@dataclass
class ClientConfig(BaseClientConfig):
    overrides: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.overrides = {
            "datazone": self.overrides.get("datazone", {}),
            "glue": self.overrides.get("glue", {}),
            "sagemaker": self.overrides.get("sagemaker", {}),
            "sagemaker_studio": self.overrides.get("sagemaker_studio", {}),
            "execution": self.overrides.get("execution", {}),
            "secretsmanager": self.overrides.get("secretsmanager", {}),
            "athena": self.overrides.get("athena", {}),
            "emr-serverless": self.overrides.get("emr-serverless", {}),
            "emr-containers": self.overrides.get("emr-containers", {}),
            "emr": self.overrides.get("emr", {}),
        }


class HttpMethod(Enum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    CONNECT = "CONNECT"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"
    PATCH = "PATCH"
