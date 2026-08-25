from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio.exceptions import AWSClientException

from ..database.database import Database


@dataclass
class Catalog:
    """
    Represents a catalog within SageMaker Unified Studio. A catalog is a container for
    databases and provides methods to retrieve information about those
    databases.

    Attributes:
        name (str): The name of the catalog.
        id (str): The unique identifier of the catalog.
        type (str): The type of the catalog.
        spark_catalog_name (str): The catalog name used for Spark, including its parent catalogs
        resource_arn (str): The Amazon Resource Name (ARN) of the catalog.
        domain_id (str): The ID of the domain this catalog belongs to.
        project_id (str): The ID of the project this catalog belongs to.
    """

    name: str = field()
    id: str = field()
    type: str = field()
    resource_arn: str = field()
    federated_catalog: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        name: str,
        id: str,
        type: str,
        spark_catalog_name: str,
        resource_arn: str,
        federated_catalog: Dict[str, Any],
        domain_id: str,
        project_id: str,
        glue_api: BaseClient,
        datazone_api: Optional[BaseClient] = None,
    ):
        """
        Initializes a new Catalog instance.

        Args:
            name (str): The name of the catalog.
            id (str): The unique identifier of the catalog.
            type (str): The type of the catalog.
            spark_catalog_name (str): The catalog name used for Spark, including its parent catalogs
            resource_arn (str): The Amazon Resource Name (ARN) of the catalog.
            domain_id (str): The ID of the domain this catalog belongs to.
            project_id (str): The ID of the project this catalog belongs to.
            glue_api (BaseClient): The Glue API client used for database operations.
            datazone_api (Optional[BaseClient]): The DataZone API client for environment queries.
        """
        self.name = name
        self.id = id
        self.type = type
        self.spark_catalog_name = spark_catalog_name
        self.resource_arn = resource_arn
        self.federated_catalog = federated_catalog
        self.domain_id = domain_id
        self.project_id = project_id
        self._glue_api = glue_api
        self._datazone_api = datazone_api

    def database(self, name: str) -> Database:
        """
        Retrieves a specific database in the catalog given its name.

        Args:
            name (str): The name of the database.

        Returns:
            Database: The Database object.
        """
        try:
            get_database_response = self._glue_api.get_database(Name=name, CatalogId=self.id).get("Database")  # type: ignore
            return Database(
                name=get_database_response.get("Name"),
                catalog_id=get_database_response.get("CatalogId"),
                location_uri=get_database_response.get("LocationUri"),
                domain_id=self.domain_id,
                project_id=self.project_id,
                glue_api=self._glue_api,
            )
        except ClientError as e:
            raise AttributeError(f"Unable to access database '{name}`: {AWSClientException(e)}'")
        except Exception as e:
            raise RuntimeError(f"Encountered an error getting database '{name}'", e)

    def _get_project_default_database_name(self) -> Optional[str]:
        """Get the project's default database name from environment provisioned resources."""
        if not self._datazone_api:
            return None

        try:
            environments = self._datazone_api.list_environments(
                domainIdentifier=self.domain_id, projectIdentifier=self.project_id
            )

            for env in environments.get("items", []):
                if "database" in env.get("name", "").lower():
                    env_details = self._datazone_api.get_environment(
                        domainIdentifier=self.domain_id, identifier=env["id"]
                    )

                    for resource in env_details.get("provisionedResources", []):
                        if resource.get("name") == "glueDBName":
                            return resource.get("value")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code not in ["ResourceNotFoundException", "AccessDeniedException"]:
                raise RuntimeError(
                    f"Failed to retrieve project default database: {AWSClientException(e)}"
                )

        return None

    @property
    def databases(self) -> List[Database]:
        """
        Retrieves a list of all databases in the catalog.

        In SMUS mode: Project default database is returned first.
        In Express mode: All databases sorted alphabetically.

        Returns:
            List[Database]: A list of Database objects.
        """
        try:
            databases_paginator = self._glue_api.get_paginator("get_databases")
            databases_page_iterator = databases_paginator.paginate(CatalogId=self.id)
            connection_databases: List[Database] = []
            for page in databases_page_iterator:
                for database in page.get("DatabaseList", []):
                    connection_databases.append(
                        Database(
                            name=database.get("Name"),
                            catalog_id=database.get("CatalogId"),
                            location_uri=database.get("LocationUri"),
                            domain_id=self.domain_id,
                            project_id=self.project_id,
                            glue_api=self._glue_api,
                        )
                    )

            # Move project default database to index 0 if it exists (SMUS only)
            default_db_name = self._get_project_default_database_name()
            if default_db_name:
                project_db_index = next(
                    (i for i, db in enumerate(connection_databases) if db.name == default_db_name),
                    -1,
                )
                if project_db_index > 0:
                    project_db = connection_databases.pop(project_db_index)
                    connection_databases.insert(0, project_db)

            return connection_databases
        except ClientError as e:
            raise RuntimeError("Encountered an error listing databases", AWSClientException(e))
