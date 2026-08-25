"""SQL query utilities for executing SQL in notebook environments."""

import re
from typing import List, Optional, TypedDict


# Type definitions
class QueryExecutionContext(TypedDict):
    """Represents the execution context for an Athena query."""

    catalog: Optional[str]
    database: Optional[str]


class SimpleContext(TypedDict, total=False):
    """Simple context without metadata (used internally)."""

    catalog: Optional[str]
    database: Optional[str]


def get_execution_context(sql_query: str) -> QueryExecutionContext:
    """Extract catalog and database execution context from SQL query.

    The function analyzes SQL in the following priority order:
    1. Special query context comments (/* @catalog: xyz, @database: abc */)
    2. USE CATALOG and USE DATABASE statements
    3. Fully qualified table names (catalog.database.table)

    Args:
        sql_query: SQL query string to analyze

    Returns:
        QueryExecutionContext with catalog and database

    Examples:
        >>> result = get_execution_context("USE CATALOG my_catalog; USE DATABASE my_db; SELECT * FROM table")
        >>> result["catalog"]
        'my_catalog'
        >>> result["database"]
        'my_db'

        >>> result = get_execution_context("SELECT * FROM table")
        >>> result["catalog"]
        None
    """
    if not sql_query or not isinstance(sql_query, str):
        return {"catalog": None, "database": None}

    normalized_sql = sql_query.strip()

    # Priority 1: Check for context comments
    comment_context = _extract_from_context_comment(normalized_sql)
    if comment_context.get("catalog") or comment_context.get("database"):
        return {
            "catalog": comment_context.get("catalog"),
            "database": comment_context.get("database"),
        }

    # Priority 2: Check for USE statements
    use_context = _extract_from_use_statements(normalized_sql)
    if use_context.get("catalog") or use_context.get("database"):
        return {"catalog": use_context.get("catalog"), "database": use_context.get("database")}

    # Priority 3: Extract from fully qualified table names
    table_contexts = _extract_all_qualified_table_names(normalized_sql)
    if table_contexts:
        table_context = table_contexts[0]
        return {"catalog": table_context.get("catalog"), "database": table_context.get("database")}

    return {"catalog": None, "database": None}


def _extract_from_context_comment(sql: str) -> SimpleContext:
    """Extract catalog and database from special query context comments.

    Format: /* @catalog: catalog_name, @database: database_name */

    Args:
        sql: SQL query string

    Returns:
        SimpleContext with catalog and/or database
    """
    context: SimpleContext = {
        "catalog": None,
        "database": None,
    }

    # Match comment blocks with @catalog or @database annotations
    comment_regex = r"/\*([^*]|\*(?!/))*\*/"
    matches = re.finditer(comment_regex, sql)

    if not matches:
        return context

    for match in matches:
        comment_text = match.group(0)

        # Extract catalog
        catalog_match = re.search(r"@catalog\s*:\s*([a-zA-Z0-9_-]+)", comment_text, re.IGNORECASE)
        if catalog_match and not context.get("catalog"):
            context["catalog"] = catalog_match.group(1).strip()

        # Extract database
        database_match = re.search(r"@database\s*:\s*([a-zA-Z0-9_-]+)", comment_text, re.IGNORECASE)
        if database_match and not context.get("database"):
            context["database"] = database_match.group(1).strip()

        # If both found, we can return early
        if context.get("catalog") and context.get("database"):
            return context

    return context


def _extract_from_use_statements(sql: str) -> SimpleContext:
    """Extract catalog and database from USE CATALOG and USE DATABASE statements.

    Args:
        sql: SQL query string

    Returns:
        SimpleContext with catalog and/or database
    """
    context: SimpleContext = {
        "catalog": None,
        "database": None,
    }

    # Remove comments and string literals to avoid false matches
    sql_without_comments = _remove_comments_and_strings(sql)

    # Match USE CATALOG statement (case insensitive)
    catalog_match = re.search(
        r"USE\s+CATALOG\s+([a-zA-Z0-9_-]+)", sql_without_comments, re.IGNORECASE
    )
    if catalog_match:
        context["catalog"] = catalog_match.group(1).strip()

    # Match USE DATABASE statement (case insensitive)
    database_match = re.search(
        r"USE\s+(?:DATABASE\s+)?([a-zA-Z0-9_-]+)", sql_without_comments, re.IGNORECASE
    )
    if database_match and not catalog_match:
        # Only set database if it's not part of a catalog statement
        context["database"] = database_match.group(1).strip()
    elif database_match and catalog_match:
        # If we have a catalog, look for database specifically
        db_only_match = re.search(
            r"USE\s+DATABASE\s+([a-zA-Z0-9_-]+)", sql_without_comments, re.IGNORECASE
        )
        if db_only_match:
            context["database"] = db_only_match.group(1).strip()

    return context


def _extract_all_qualified_table_names(sql: str) -> List[SimpleContext]:
    """Extract all catalog and database references from fully qualified table names.

    Format: catalog.database.table or database.table
    Supports quoted identifiers: "catalog"."database"."table" or `catalog/path`.`database`.`table`

    Args:
        sql: SQL query string

    Returns:
        List of SimpleContext objects for all contexts found
    """
    contexts: List[SimpleContext] = []

    # Remove comments and string literals to avoid false matches
    cleaned_sql = _remove_comments_and_strings(sql)

    # Pattern for identifiers: can be quoted with backticks, double quotes, or unquoted
    # Backticks can contain any character (including /, -, etc. for S3 catalog paths)
    # Double quotes can contain special chars
    # Unquoted must be alphanumeric with underscores/hyphens
    identifier_pattern = r'(?:`([^`]+)`|"([^"]+)"|([a-zA-Z0-9_-]+))'

    # Dot separator with optional whitespace
    dot_separator = r"\s*\.\s*"

    # DDL keywords that work with databases
    database_ddl = (
        r"CREATE\s+(?:OR\s+REPLACE\s+)?DATABASE|ALTER\s+DATABASE|DROP\s+DATABASE|"
        r"USE\s+DATABASE|SHOW\s+DATABASES"
    )

    # DDL keywords that work with tables
    table_ddl = (
        r"FROM|JOIN|INTO|UPDATE|CREATE\s+(?:EXTERNAL\s+|OR\s+REPLACE\s+)?TABLE|"
        r"ALTER\s+TABLE|DROP\s+TABLE|TRUNCATE\s+TABLE"
    )

    # Match three-part names: catalog.database.table (for tables)
    three_part_table_pattern = (
        rf"(?:{table_ddl})\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
        rf"{identifier_pattern}{dot_separator}{identifier_pattern}{dot_separator}{identifier_pattern}"
    )
    three_part_table_matches = re.finditer(three_part_table_pattern, cleaned_sql, re.IGNORECASE)

    for match in three_part_table_matches:
        # Extract the identifier from whichever capture group matched (backtick, quote, or unquoted)
        catalog = (match.group(1) or match.group(2) or match.group(3)).strip()
        database = (match.group(4) or match.group(5) or match.group(6)).strip()
        contexts.append({"catalog": catalog, "database": database})

    # Match two-part names for database DDL: `catalog/path`.database
    two_part_database_pattern = (
        rf"(?:{database_ddl})\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
        rf"{identifier_pattern}{dot_separator}{identifier_pattern}"
    )
    two_part_database_matches = re.finditer(two_part_database_pattern, cleaned_sql, re.IGNORECASE)

    for match in two_part_database_matches:
        # For database DDL, the format is catalog.database (not database.table)
        catalog = (match.group(1) or match.group(2) or match.group(3)).strip()
        database = (match.group(4) or match.group(5) or match.group(6)).strip()
        contexts.append({"catalog": catalog, "database": database})

    # If we found any contexts, return them
    if contexts:
        return contexts

    # Match two-part table names: database.table (assuming no catalog)
    two_part_table_pattern = (
        rf"(?:{table_ddl})\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
        rf"{identifier_pattern}{dot_separator}{identifier_pattern}"
    )
    two_part_table_matches = re.finditer(two_part_table_pattern, cleaned_sql, re.IGNORECASE)

    for match in two_part_table_matches:
        # Extract the identifier from whichever capture group matched
        database = (match.group(1) or match.group(2) or match.group(3)).strip()
        contexts.append(
            {
                "catalog": None,
                "database": database,
            }
        )

    return contexts


def _remove_comments(sql: str) -> str:
    """Remove SQL comments from a query string.

    Args:
        sql: SQL query string

    Returns:
        SQL string without comments
    """
    # Remove multi-line comments /* ... */
    result = re.sub(r"/\*([^*]|\*(?!/))*\*/", " ", sql)
    # Remove single-line comments -- ...
    result = re.sub(r"--[^\r\n]*", " ", result)
    return result


def _remove_comments_and_strings(sql: str) -> str:
    """Remove SQL comments and string literals to avoid false matches.

    Note: In Athena/SQL, double quotes are used for identifiers, not strings.
    Single quotes are for string literals.

    Args:
        sql: SQL query string

    Returns:
        Cleaned SQL string
    """
    result = _remove_comments(sql)
    # Remove string literals (single quotes only - double quotes are for identifiers in SQL)
    result = re.sub(r"'([^']|\\')*'", " ", result)
    return result
