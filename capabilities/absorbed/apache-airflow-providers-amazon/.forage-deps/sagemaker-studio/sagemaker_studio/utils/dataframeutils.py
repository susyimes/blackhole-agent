"""
DataFrame utilities for reading tables from various catalog types.
"""

import logging
from typing import Optional

import pandas as pd

from sagemaker_studio.utils.sqlutils import _ensure_project

logger = logging.getLogger()
logger.info("Importing dataframeutils")


def _detect_format_from_metadata(
    table_type: str,
    parameters: dict,
    input_format: str,
    serialization_library: str,
) -> str:
    """
    Detect table format from Glue table metadata components.

    Args:
        table_type: Glue table type
        parameters: Table parameters (normalized to lowercase keys)
        input_format: Storage descriptor input format
        serialization_library: SerDe serialization library

    Returns:
        str: Detected format ('iceberg', 'hudi', 'deltalake', 'parquet', 'orc',
             'json', 'csv_or_text', or 'unknown')
    """
    # Iceberg
    if (
        table_type == "ICEBERG"
        or parameters.get("table_type", "").lower() == "iceberg"
        or "iceberg" in serialization_library.lower()
    ):
        return "iceberg"

    # Hudi
    if (
        "hoodie.table.name" in parameters
        or "hudi" in input_format.lower()
        or "hudi" in serialization_library.lower()
    ):
        return "hudi"

    # Delta
    if (
        "delta.table.path" in parameters
        or "delta" in input_format.lower()
        or "delta" in serialization_library.lower()
        or "delta" in parameters.get("provider", "").lower()
    ):
        return "deltalake"

    # Parquet
    if "parquet" in input_format.lower() or "parquet" in serialization_library.lower():
        return "parquet"

    # ORC
    if "orc" in input_format.lower() or "orc" in serialization_library.lower():
        return "orc"

    # JSON
    if "json" in serialization_library.lower() or parameters.get("classification") == "json":
        return "json"

    # CSV / Text
    if input_format.lower().endswith("textinputformat"):
        return "csv_or_text"

    return "unknown"


def _get_glue_table_format(
    database: str, table: str, catalog_id: Optional[str] = None, region: Optional[str] = None
) -> str:
    """
    Determine the table format from Glue table metadata.

    Fetches table metadata from AWS Glue using boto3 and examines TableType,
    Parameters, and StorageDescriptor to identify the format. Checks for modern
    table formats (Iceberg, Hudi, Delta) as well as traditional formats
    (Parquet, ORC, JSON, CSV).

    Args:
        database: Database name
        table: Table name
        catalog_id: Optional catalog ID (AWS account ID)
        region: Optional AWS region for the Glue client

    Returns:
        str: Detected format ('iceberg', 'hudi', 'delta', 'parquet', 'orc', 'json',
             'csv_or_text', or 'unknown')
    """
    import boto3

    glue_client = boto3.client("glue", region_name=region) if region else boto3.client("glue")

    get_table_args = {"DatabaseName": database, "Name": table}
    if catalog_id:
        get_table_args["CatalogId"] = catalog_id

    try:
        response = glue_client.get_table(**get_table_args)
        table_metadata = response.get("Table", {})
    except Exception as e:
        logger.warning(
            f"Failed to retrieve table '{table}' from database '{database}': {str(e)}. "
            f"Returning 'unknown' format."
        )
        return "unknown"

    table_type = table_metadata.get("TableType", "")
    parameters = {k.lower(): v for k, v in table_metadata.get("Parameters", {}).items()}
    storage_descriptor = table_metadata.get("StorageDescriptor", {})
    input_format = storage_descriptor.get("InputFormat", "")
    serialization_library = storage_descriptor.get("SerdeInfo", {}).get("SerializationLibrary", "")

    return _detect_format_from_metadata(table_type, parameters, input_format, serialization_library)


def read_catalog_table(
    database: str,
    table: str,
    format: Optional[str] = None,
    catalog: Optional[str] = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Reads from a table in the Glue Data Catalog and returns a pandas DataFrame.

    AwsDataCatalog
    --------------
    Based on the desired format, delegate to the appropriate read_{format}
    function on the awswrangler library. This will take care of reading and converting
    the output to pandas using the S3 path derived from the table location.

    S3 Tables
    ---------
    S3 Tables is read using pyiceberg using the load_table and scan APIs. The
    scan API will pull in the data using pyarrow and the amount pulled in needs
    to be limited. By default Spiral limits to 20k rows which the API will default.
    The user can override this and also set it to None.

    Args:
        catalog: Catalog name/identifier (can be obtained from project.connection().catalog.name)
        database: Database name within the catalog
        table: Table name/identifier to read from
        format: Data format (e.g., 'parquet', 'csv', 'json') - required for AwsDataCatalog (NATIVE),
                ignored for S3Tables (Federated) as iceberg handles format internally
        **kwargs: Additional arguments passed to the underlying reader functions.
                 For S3Tables (Federated), you can pass 'limit' to control the maximum number
                 of rows to read (None for unlimited)

    Returns:
        pd.DataFrame: The table data as a pandas DataFrame

    Raises:
        Exception: If catalog type is not supported or table operations fail
    """
    import awswrangler as wr
    from pyiceberg.catalog import load_catalog

    project = _ensure_project()
    connection = project.connection()
    catalog_obj = connection.catalog(id=catalog)
    catalog_type = catalog_obj.type
    resource_arn = catalog_obj.resource_arn

    # Get region from connection's physical endpoints if available
    catalog_region = None
    if connection.physical_endpoints and len(connection.physical_endpoints) > 0:
        catalog_region = connection.physical_endpoints[0].aws_region
    # Fallback to extracting from resource ARN if not available from physical endpoints
    if not catalog_region and resource_arn:
        catalog_region = resource_arn.split(":")[3]

    if catalog_type == "NATIVE":
        detected_format = None  # Initialize to None
        table_info = None  # Initialize to None

        if format is None:
            # Try the original approach first using awswrangler's get_table_parameters
            try:
                table_info = wr.catalog.get_table_parameters(
                    database=database, table=table, catalog_id=catalog_obj.id
                )
                format = table_info.get("classification") if table_info else None
            except Exception as e:
                logger.warning(
                    f"Failed to get table parameters for {database}.{table}: {str(e)}. "
                    f"Will try alternative format detection."
                )
                format = None

            # If the original approach didn't work, fall back to the new detection method
            if format is None:
                try:
                    detected_format = _get_glue_table_format(
                        database=database,
                        table=table,
                        catalog_id=catalog_obj.id,
                        region=catalog_region,
                    )

                    # Map detected format to awswrangler reader function names
                    if detected_format in ["parquet", "orc", "json", "deltalake"]:
                        format = detected_format
                    elif detected_format == "csv_or_text":
                        format = "csv"
                    elif detected_format in ["iceberg", "hudi", "unknown"]:
                        format = "parquet"
                    else:
                        logger.warning(
                            f"Detected format '{detected_format}' for table {database}.{table} "
                            f"requires special handling. Falling back to 'parquet'."
                        )
                        format = "parquet"
                except Exception as e:
                    # If table metadata retrieval fails, set format to parquet
                    logger.warning(
                        f"Failed to detect format for table {database}.{table}: {str(e)}. "
                        f"Falling back to 'parquet'."
                    )
                    format = "parquet"

            if format is None:
                format = "parquet"

        table_location = wr.catalog.get_table_location(
            database=database, table=table, catalog_id=catalog_obj.id
        )
        reader_func_name = f"read_{format}"

        if not hasattr(wr.s3, reader_func_name):
            raise Exception(f"Unsupported format '{format}' for AwsDataCatalog")

        # For Hudi tables, append wildcard to read parquet files inside the folder
        if detected_format == "hudi" or format == "hudi":
            table_location = table_location.rstrip("/") + "/*.parquet"
        elif detected_format == "iceberg" or format == "iceberg":
            table_location = table_location + "/data/"
        # For Delta Lake tables, check if the actual location is in table parameters
        elif detected_format == "deltalake" or format == "deltalake":
            try:
                # If table_info wasn't retrieved earlier, fetch it now
                if table_info is None:
                    table_info = wr.catalog.get_table_parameters(
                        database=database, table=table, catalog_id=catalog_obj.id
                    )
                # Delta Lake stores the actual S3 path in the 'location' parameter
                if table_info and "location" in table_info:
                    table_location = table_info["location"]
                    logger.info(f"Using location parameter for table location: {table_location}")
            except Exception as e:
                logger.warning(f"Failed to get location parameter for Delta table: {str(e)}")

        # For JSON tables, ensure lines=True is set for JSONL/NDJSON format
        if (detected_format == "json" or format == "json") and "lines" not in kwargs:
            kwargs["lines"] = True

        reader = getattr(wr.s3, reader_func_name)
        wr_args = {"path": table_location, **kwargs}

        return reader(**wr_args)

    elif (
        catalog_type == "FEDERATED"
        and catalog_obj.federated_catalog.get("ConnectionName") == "aws:s3tables"
    ):
        catalog_region = resource_arn.split(":")[3]
        catalog_properties = {
            "type": "rest",
            "warehouse": catalog_obj.id,
            "uri": f"https://glue.{catalog_region}.amazonaws.com/iceberg",
            "rest.sigv4-enabled": "true",
            "rest.signing-name": "glue",
            "rest.signing-region": catalog_region,
        }

        cat = load_catalog(name=catalog, **catalog_properties)
        full_table_name = f"{database}.{table}"
        tbl = cat.load_table(full_table_name)
        scan_result = tbl.scan(**kwargs)
        arrow_table = scan_result.to_arrow()
        return arrow_table.to_pandas()

    else:
        error_msg = f"Unable to read from catalog. Catalog type '{catalog_type}' not supported."
        raise ValueError(error_msg)


def _parse_project_path_from_s3_root_path(project_id: str, s3_root: str) -> str:
    """
    Parse the project S3 root path based on project ID location.

    This function handles two main scenarios:
    1. Project ID is embedded in the bucket name (e.g., s3://project-abc123-bucket/shared)
    2. Project ID appears as a path component (e.g., s3://bucket/abc123/dev)

    Args:
        project_id: The project ID to search for
        s3_root: The full S3 root path from the project configuration

    Returns:
        str: Parsed S3 path based on project ID location:
             - If project ID is found in bucket name: returns s3://{bucket}
             - If project ID is found in path: returns path up to and including project ID
             - If project ID not found: returns original s3_root as fallback
    """
    s3_root = s3_root.rstrip("/")
    parts = s3_root.split("/")

    # Check if project ID is in the bucket name (parts[2])
    if len(parts) >= 3 and project_id in parts[2]:
        return f"s3://{parts[2]}"

    # Otherwise, keep removing prefixes until we find the project ID
    # Start from the end and work backwards
    while len(parts) > 3:  # Don't go below s3://bucket
        if parts[-1] == project_id:
            return "/".join(parts)
        parts = parts[:-1]  # Remove the last prefix

    # If project ID not found, return original s3_root as fallback
    return s3_root


def _determine_table_path(project, catalog_obj, database: str, table: str) -> str:
    """
    Determine the S3 path for writing a table based on the following priority:
    1. If database exists and has location_uri, use {database_location}/{table_name}
    2. If table exists and has location, use table location
    3. Otherwise, use project default S3 location

    If database doesn't exist, create it using project's default S3 location.

    Args:
        project: Project instance
        catalog_obj: Catalog object from connection
        database: Database name
        table: Table name

    Returns:
        str: S3 path to use for the table
    """
    import awswrangler as wr

    try:
        databases = catalog_obj.databases
        target_db = None
        for db in databases:
            if db.name == database:
                target_db = db
                break

        if target_db:
            if hasattr(target_db, "location_uri") and target_db.location_uri:
                db_location = target_db.location_uri.rstrip("/")
                final_path = f"{db_location}/{table}"
                return final_path
            else:
                try:
                    table_location = wr.catalog.get_table_location(
                        database=database, table=table, catalog_id=catalog_obj.id
                    )
                    if table_location:
                        return table_location
                except Exception:
                    pass
        else:
            project_root = _parse_project_path_from_s3_root_path(project.id, project.s3.root)
            db_location = f"{project_root}/catalog/{database}"
            _create_database_with_location(catalog_obj, database, db_location)

        project_root = _parse_project_path_from_s3_root_path(project.id, project.s3.root)
        final_path = f"{project_root}/catalog/{database}/{table}"
        return final_path

    except Exception:
        project_root = _parse_project_path_from_s3_root_path(project.id, project.s3.root)
        final_path = f"{project_root}/catalog/{database}/{table}"
        return final_path


def _ensure_database_exists(
    project, catalog_obj, database: str, user_path: Optional[str] = None
) -> None:
    """
    Ensure a database exists, creating it if necessary.

    If user_path is provided, derives database location from the user path.
    If user_path is None, uses the project's default S3 location.

    Args:
        project: Project instance
        catalog_obj: Catalog object from connection
        database: Database name to ensure exists
        user_path: Optional user-provided S3 path to derive database location from
    """

    try:
        databases = catalog_obj.databases
        for db in databases:
            if db.name == database:
                return
        if user_path is not None:
            db_location = user_path.rstrip("/")
        else:
            project_root = _parse_project_path_from_s3_root_path(project.id, project.s3.root)
            db_location = f"{project_root}/catalog/{database}"

        _create_database_with_location(catalog_obj, database, db_location)

    except Exception as e:
        raise AttributeError(f"Failed to ensure database '{database}' exists: {str(e)}")


def _create_database_with_location(catalog_obj, database: str, db_location: str) -> None:
    """
    Create a database if it doesn't exist using the specified S3 location.

    Args:
        catalog_obj: Catalog object from connection
        database: Database name to create
        db_location: S3 location to use for the database
    """
    import awswrangler as wr

    create_db_args = {"LocationUri": db_location}

    try:
        wr.catalog.create_database(
            name=database, database_input_args=create_db_args, catalog_id=catalog_obj.id
        )
    except Exception:
        # Database might already exist or creation failed
        # This is not critical - we'll proceed with the path anyway
        pass


def to_catalog_table(
    self: pd.DataFrame,
    database: str,
    table: str,
    format: Optional[str] = "parquet",
    catalog: Optional[str] = None,
    path: Optional[str] = None,
    **kwargs,
) -> None:
    """
    Writes a pandas DataFrame to S3 and creates a table in the Glue Data Catalog.

    The dataframe is written out to the S3 location determined by the following priority:
    1. If path is provided, use that location
    2. If database exists and has location_uri, use {database_location}/{table_name}
    3. If table exists and has location, use table location
    4. Otherwise, use project default S3 location

    If database doesn't exist, it will be created using the project's default S3 location.

    AwsDataCatalog
    --------------
    The actual write for the AwsDataCatalog (hive metastore) is performed by
    delegating to the awswrangler library.

    S3 Tables
    ---------
    S3 Tables is written out using Glue's IRC API. Using the Pandas dataframe, the
    arrow schema is created. If the table does not exist, a new table is created
    using the schema and if a table exists, the table is appended using pyiceberg.

    Args:
        self: Pandas DataFrame to write (automatically passed when called as df.to_catalog_table())
        database: Database name within the catalog
        table: Table name/identifier to write to
        format: Data format (e.g., 'parquet', 'csv', 'json') for AwsDataCatalog
        catalog: Catalog identifier (optional, uses default if None)
        path: S3 path to write data (optional, auto-determined if None)
        **kwargs: Additional arguments passed to the underlying writer functions

    Returns:
        None

    Raises:
        Exception: If catalog type is not supported or write operations fail
    """
    import awswrangler as wr
    import pyarrow as pa
    from pyiceberg.catalog import load_catalog
    from pyiceberg.exceptions import NoSuchNamespaceError, NoSuchTableError

    project = _ensure_project()
    connection = project.connection()

    catalog_obj = connection.catalog(id=catalog)
    catalog_type = catalog_obj.type
    resource_arn = catalog_obj.resource_arn

    if path is None:
        path = _determine_table_path(project, catalog_obj, database, table)

    _ensure_database_exists(project, catalog_obj, database, user_path=path)

    if catalog_type == "NATIVE":
        writer_func_name = f"to_{format}"

        if not hasattr(wr.s3, writer_func_name):
            raise Exception(f"Unsupported format '{format}' for AwsDataCatalog")

        writer = getattr(wr.s3, writer_func_name)
        wr_args = {
            "df": self,
            "path": path,
            "database": database,
            "table": table,
            "dataset": True,
            **kwargs,
        }
        if catalog:
            wr_args["catalog_id"] = catalog_obj.id

        result = writer(**wr_args)
        print("Write operation successful.")
        return result

    elif (
        catalog_type == "FEDERATED"
        and catalog_obj.federated_catalog.get("ConnectionName") == "aws:s3tables"
    ):
        catalog_region = resource_arn.split(":")[3]

        catalog_properties = {
            "type": "rest",
            "warehouse": catalog_obj.id,
            "uri": f"https://glue.{catalog_region}.amazonaws.com/iceberg",
            "rest.sigv4-enabled": "true",
            "rest.signing-name": "glue",
            "rest.signing-region": catalog_region,
        }

        cat = load_catalog(name=catalog, **catalog_properties)

        # Normalize column names to lowercase to match Hive/Glue behavior
        # This ensures compatibility between Arrow table and Iceberg table schemas
        normalized_df = self.copy()
        normalized_df.columns = [col.lower() for col in normalized_df.columns]

        arrow_table = pa.Table.from_pandas(normalized_df)

        # Normalize database and table names to lowercase to match Hive/Glue behavior
        normalized_database = database.lower()
        normalized_table = table.lower()
        full_table_name = f"{normalized_database}.{normalized_table}"

        try:
            iceberg_table = cat.load_table(full_table_name)
            result = iceberg_table.append(arrow_table)
            print("Write operation successful.")
            return result
        except NoSuchTableError:
            try:
                cat.create_table(full_table_name, schema=arrow_table.schema)
            except NoSuchNamespaceError:
                cat.create_namespace(normalized_database)
                cat.create_table(full_table_name, schema=arrow_table.schema)
            iceberg_table = cat.load_table(full_table_name)
            result = iceberg_table.append(arrow_table)
            print("Write operation successful.")
            return result

    else:
        error_msg = f"Unable to write to catalog. Catalog type '{catalog_type}' not supported."
        raise ValueError(error_msg)


# Monkey-patch pandas to add our custom methods
def _patch_pandas():
    """
    This allows users to use:
    - pandas.read_catalog_table() for reading from catalogs
    - df.to_catalog_table() for writing DataFrames to catalogs

    After importing dataframeutils, these methods become available directly on pandas.
    """
    import pandas as pd

    pd.read_catalog_table = read_catalog_table
    pd.DataFrame.to_catalog_table = to_catalog_table


_patch_pandas()
logger.info("Finished importing dataframeutils")
