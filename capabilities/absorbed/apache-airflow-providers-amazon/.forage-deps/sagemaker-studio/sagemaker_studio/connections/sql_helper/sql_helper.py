import abc
from dataclasses import asdict
from typing import Any, Dict, Optional

from sagemaker_studio.connections.connection import Connection


class SqlHelper(abc.ABC):
    """
    Abstract base class for SQL connection helpers.

    This class provides a common interface for transforming DataZone connection data
    into standardized SQL configuration formats.
    Each concrete implementation handles a specific database type (e.g., Athena, Redshift).
    """

    @staticmethod
    @abc.abstractmethod
    def to_sql_config(connection: Connection, **kwargs) -> Dict[str, Any]:
        """
        Transform DataZone connection data into SQL interface configuration.

        This method converts the DataZone connection data into a standardized format
        that can be consumed by SQL execution interfaces.

        Returns:
            Dict[str, Any]: Transformed configuration dictionary containing
                standardized SQL connection parameters.

        Raises:
            NotImplementedError: Must be implemented by concrete subclasses.
        """

    @staticmethod
    @abc.abstractmethod
    def get_connection_data(connection: Connection) -> Dict[str, Any]:
        connection_data = asdict(connection.data)
        connection_data["connection_creds"] = asdict(connection.connection_creds)
        return connection_data

    @staticmethod
    def get_glue_connection_property(
        connection_data: Dict[str, Any], property_name: str
    ) -> Optional[str]:
        """
        Retrieve a specific Glue connection property from the given connection data.

        This method safely navigates the nested AWS Glue connection structure to extract
        a property from the "connectionProperties" dictionary of the first physical endpoint.

        Args:
            connection_data (Dict[str, Any]): The connection metadata dictionary, expected
                to include a structure similar to:
                {
                    "physical_endpoints": [
                        {
                            "glueConnection": {
                                "connectionProperties": {
                                    "<property_name>": "<property_value>"
                                }
                            }
                        }
                    ]
                }
            property_name (str): The name of the property to retrieve from
                the Glue connection's "connectionProperties" section.

        Returns:
            Optional[str]: The value of the requested property if found, otherwise None.

        Raises:
            ValueError: If the connection_data structure is missing required fields
                or is malformed.
        """
        try:
            physical_endpoints = connection_data.get("physical_endpoints")
            if not physical_endpoints or not isinstance(physical_endpoints, list):
                raise ValueError("Missing or invalid 'physical_endpoints' in connection_data.")

            first_endpoint = physical_endpoints[0]
            if not isinstance(first_endpoint, dict):
                raise ValueError("Invalid endpoint structure in 'physical_endpoints' list.")

            glue_conn = first_endpoint.get("glueConnection", {})
            conn_props = glue_conn.get("connectionProperties", {})

            # Return the requested property value, if it exists
            return conn_props.get(property_name)

        except (AttributeError, IndexError, KeyError, TypeError) as e:
            raise ValueError(f"Invalid connection data format: {e}") from e
