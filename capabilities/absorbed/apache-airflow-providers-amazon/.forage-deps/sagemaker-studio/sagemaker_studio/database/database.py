from dataclasses import dataclass, field
from typing import List

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker_studio.exceptions import AWSClientException

from .table import Column, Table


@dataclass
class Database:
    """
    Represents a database within SageMaker Unified Studio.

    Attributes:
        name (str): The name of the database.
        catalog_id (str): The unique identifier of the catalog the database belongs to.
        location_uri (str): The S3 location URI of the database.

    Args:
        name (str): The name of the database.
        catalog_id (str): The unique identifier of the catalog the database belongs to.
        location_uri (str): The S3 location URI of the database.
        domain_id (str): The unique identifier of the domain the database belongs to.
        project_id (str): The unique identifier of the project the database belongs to.
        glue_api (BaseClient): The Glue client.
    """

    name: str = field()
    catalog_id: str = field()
    location_uri: str = field()

    def __init__(
        self,
        name: str,
        catalog_id: str,
        location_uri: str,
        domain_id: str,
        project_id: str,
        glue_api: BaseClient,
    ):
        """
        Initializes a new instance of the Database class.

        Args:
            name (str): The name of the database.
            catalog_id (str): The unique identifier of the catalog the database belongs to.
            location_uri (str): The S3 location URI of the database.
            domain_id (str): The unique identifier of the domain the database belongs to.
            project_id (str): The unique identifier of the project the database belongs to.
            glue_api (BaseClient): The Glue client.
        """
        self.name = name
        self.catalog_id = catalog_id
        self.location_uri = location_uri
        self.domain_id = domain_id
        self.project_id = project_id
        self._glue_api: BaseClient = glue_api

    @property
    def tables(self) -> List[Table]:
        """
        Retrieves a list of all tables in the database.

        Returns:
            List[Table]: A list of Table objects.
        """
        try:
            tables_paginator = self._glue_api.get_paginator("get_tables")
            tables_page_iterator = tables_paginator.paginate(
                DatabaseName=self.name, CatalogId=self.catalog_id
            )
            database_tables: List[Table] = []
            for page in tables_page_iterator:
                for table in page.get("TableList", []):
                    storage_descriptor = table.get("StorageDescriptor", {})
                    database_tables.append(
                        Table(
                            name=table.get("Name"),
                            database_name=table.get("DatabaseName"),
                            catalog_id=table.get("CatalogId"),
                            location=storage_descriptor.get("Location", ""),
                            columns=[
                                Column(name=col["Name"], type=col["Type"])
                                for col in storage_descriptor["Columns"]
                            ],
                        )
                    )
            return database_tables
        except ClientError as e:
            raise RuntimeError(
                f"Encountered an error getting tables for database '{self.name}'",
                AWSClientException(e),
            )

    def table(self, name: str) -> Table:
        """
        Retrieves a specific table in the database given its name.

        Args:
            name (str): The name of the table.

        Returns:
            Table: The Table object.
        """
        try:
            get_table_response = self._glue_api.get_table(  # type: ignore
                Name=name, DatabaseName=self.name, CatalogId=self.catalog_id
            ).get("Table")
            storage_descriptor = get_table_response.get("StorageDescriptor", {})
            return Table(
                name=get_table_response.get("Name"),
                database_name=get_table_response.get("DatabaseName"),
                catalog_id=get_table_response.get("CatalogId"),
                location=storage_descriptor.get("Location", ""),
                columns=[
                    Column(name=col["Name"], type=col["Type"])
                    for col in storage_descriptor["Columns"]
                ],
            )
        except ClientError as e:
            raise AttributeError(f"Unable to access table '{name}': {AWSClientException(e)}")
        except Exception as e:
            raise RuntimeError(
                f"Encountered an error getting table '{name}' in database '{self.name}'",
                e,
            )
