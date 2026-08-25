from dataclasses import dataclass, field
from typing import Optional

from botocore.exceptions import ClientError

from sagemaker_studio import ClientConfig
from sagemaker_studio.exceptions import AWSClientException
from sagemaker_studio.utils._internal import InternalUtils

from .sagemaker_studio_api import SageMakerStudioAPI


@dataclass
class Domain:
    """
    Represents a SageMaker Unified Studio domain. Domain allows a user to retrieve information about a SageMaker Unified Studio Domain,
    including its ID, name, domain execution role ARN, portal URL, and more.

    Attributes:
        id (Optional[str]): The unique identifier of the domain.
        root_domain_unit_id (str): The unique identifier of the root domain unit.
        name (str): The name of the domain.
        domain_execution_role (str): The IAM role ARN used for executing domain-level operations.
        status (str): The current status of the domain.
        portal_url (str): The URL of the domain's portal.

    Args:
        id (Optional[str]): The unique identifier of the domain.
        config (ClientConfig): The configuration settings for the SageMaker Unified Studio client.
    """

    id: Optional[str] = field()
    root_domain_unit_id: str = field()
    name: str = field()
    domain_execution_role: str = field()
    status: str = field()
    portal_url: str = field()

    def __init__(
        self,
        id: Optional[str] = None,
        config: ClientConfig = ClientConfig(),
    ):
        """
        Initializes a new instance of the Domain class. If a domain ID is not found within the environment,
        one must be supplied in order to initialize a Domain.

        Args:
            id (Optional[str]): The unique identifier of the domain.
            config (ClientConfig): The configuration settings for the SageMaker Unified Studio client.
        """
        self.id = id
        self._sagemaker_studio_api = SageMakerStudioAPI(config)
        self._utils = InternalUtils()
        self._initialize_domain()

    def _initialize_domain(self):
        if not self.id:
            domain_id_from_env = self._utils._get_domain_id()
            if not domain_id_from_env:
                raise ValueError("Domain ID not found in environment. Please specify a domain ID.")
            self.id = domain_id_from_env

        try:
            get_domain_result = self._sagemaker_studio_api.datazone_api.get_domain(
                identifier=self.id
            )
        except ClientError as e:
            raise AWSClientException(e)

        self.root_domain_unit_id = get_domain_result.get("rootDomainUnitId")
        self.name = get_domain_result.get("name")
        self.domain_execution_role = get_domain_result.get("domainExecutionRole")
        self.status = get_domain_result.get("status")
        self.portal_url = get_domain_result.get("portalUrl")

    @property
    def user_id(self) -> str:
        """
        Retrieves the user ID associated with the domain.

        Returns:
            str: The user ID.
        """
        return self._utils._get_user_id()
