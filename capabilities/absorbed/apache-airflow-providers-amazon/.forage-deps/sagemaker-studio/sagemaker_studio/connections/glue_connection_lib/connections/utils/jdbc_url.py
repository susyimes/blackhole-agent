"""
Complete JDBC URL parsing and generation utilities.
Migrated from Java JdbcUrl.java with full pattern support.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Pattern

from .jdbc_patterns import JDBC_PATTERNS, SQL_SERVER_INSTANCE_PATTERNS
from .jdbc_url_matcher_groups import JdbcUrlMatcherGroups
from .jdbc_vendor import JdbcVendor


@dataclass
class JdbcUrl:
    """Complete JDBC URL parser and generator."""

    vendor: JdbcVendor
    host: str = ""
    port: int = 0
    database: str = ""
    warehouse: str = ""
    account: str = ""
    user: str = ""
    role: str = ""
    application: str = ""
    instance: str = ""

    @classmethod
    def _try_patterns(cls, jdbc_url: str, patterns: Dict[str, Pattern]) -> Optional["JdbcUrl"]:
        """Try matching URL against a set of patterns."""
        for pattern_name, pattern in patterns.items():
            match = pattern.match(jdbc_url)
            if match:
                return cls._build_from_match(match)
        return None

    @classmethod
    def from_url(cls, base_url: str) -> "JdbcUrl":
        """Parse base URL and return JdbcUrl object."""
        # Try SQL Server instance patterns first
        if "sqlserver" in base_url and "instanceName" in base_url:
            result = cls._try_patterns(base_url, SQL_SERVER_INSTANCE_PATTERNS)
            if result:
                return result

        # Try regular patterns
        result = cls._try_patterns(base_url, JDBC_PATTERNS)
        if result:
            return result

        raise ValueError(f"Base URL {base_url} is not supported")

    @classmethod
    def _build_from_match(cls, match) -> "JdbcUrl":
        """Build JdbcUrl from regex match."""
        groups = match.groupdict()
        vendor_str = groups.get(JdbcUrlMatcherGroups.VENDOR.get_group_name(), "")

        # Convert vendor string to enum
        vendor = JdbcVendor.from_string(vendor_str)

        # Special handling for snowflake as the jdbc url does not contain host and port
        if vendor_str == "snowflake":
            return cls(
                vendor=vendor,
                account=groups.get(JdbcUrlMatcherGroups.ACCOUNT.get_group_name()),
                user=groups.get(JdbcUrlMatcherGroups.USER.get_group_name()),
                warehouse=groups.get(JdbcUrlMatcherGroups.WAREHOUSE.get_group_name()),
                database=groups.get(JdbcUrlMatcherGroups.SNOWFLAKE_DATABASE.get_group_name()),
                role=groups.get(JdbcUrlMatcherGroups.ROLE.get_group_name()),
            )
        else:
            pattern_str = match.re.pattern
            if vendor_str == "mongodb" and cls._is_mongo_atlas_pattern(pattern_str):
                # MongoDB Atlas - no port
                jdbc_url = cls(
                    vendor=vendor,
                    host=groups.get(JdbcUrlMatcherGroups.HOST.get_group_name(), ""),
                )
            else:
                # Standard handling for most vendors - with port
                jdbc_url = cls(
                    vendor=vendor,
                    host=groups.get(JdbcUrlMatcherGroups.HOST.get_group_name(), ""),
                    port=int(groups.get(JdbcUrlMatcherGroups.PORT.get_group_name())),
                )

            # Try to set database
            database_value = groups.get(JdbcUrlMatcherGroups.DATABASE.get_group_name())
            if database_value is None:
                # Oracle will have a Service / SID and not a Database group
                database_value = groups.get(JdbcUrlMatcherGroups.SERVICE_OR_SID.get_group_name())

            jdbc_url.database = database_value

            # SQL Server special handling
            if vendor_str == "sqlserver" and "instanceName" in match.string:
                jdbc_url.instance = groups.get(JdbcUrlMatcherGroups.INSTANCE_NAME.get_group_name())
            if vendor_str == "sqlserver" and "applicationName" in match.string:
                jdbc_url.application = groups.get(
                    JdbcUrlMatcherGroups.APPLICATION_NAME.get_group_name()
                )

            return jdbc_url

    @classmethod
    def _is_mongo_atlas_pattern(cls, pattern: str) -> bool:
        """Check if pattern is MongoDB Atlas pattern."""
        return pattern.lower().startswith("(?p<vendor>mongodb)\\+srv")

    @staticmethod
    def escape_db_name(vendor: JdbcVendor, db_name: str) -> str:
        """Escape database name for specific vendors."""
        if not db_name:
            return ""

        if vendor == JdbcVendor.SQLSERVER:
            if db_name.startswith("{") and db_name.endswith("}"):
                return db_name  # Already escaped
            return f"{{{db_name}}}"

        return db_name

    def get_connection_url(
        self,
        use_ssl: bool = False,
        use_domain_match: bool = False,
    ) -> str:
        """Generate connection URL with SSL and domain matching options."""
        # Note: domain_match_string is always empty in Scala code, so not included
        if self.vendor in (JdbcVendor.MYSQL, JdbcVendor.REDSHIFT, JdbcVendor.POSTGRESQL):
            return f"jdbc:{self.vendor.value}://{self.host}:{self.port}/{self.database}"

        elif self.vendor == JdbcVendor.SNOWFLAKE:
            url = f"jdbc:{self.vendor.value}://{self.account}.snowflakecomputing.com/?user={self.user}"
            if self.database:
                url += f"&db={self.database}"
            if self.role:
                url += f"&role={self.role}"
            if self.warehouse:
                url += f"&warehouse={self.warehouse}"
            return url

        elif self.vendor == JdbcVendor.ORACLE:
            if use_ssl:
                url = f"jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCPS)(HOST={self.host})(PORT={self.port}))"
                if self.database:
                    url += f"(CONNECT_DATA=(SERVICE_NAME={self.database}))"
                if use_domain_match:
                    if self.host.endswith("rds.amazonaws.com"):
                        domain_match_string = (
                            f"C=US,ST=Washington,L=Seattle,O=Amazon.com,OU=RDS,CN={self.host}"
                        )
                    else:
                        domain_match_string = f"CN={self.host}"
                    url += f'(SECURITY=(SSL_SERVER_CERT_DN="{domain_match_string}"))'
                url += ")"
                return url
            else:
                return f"jdbc:oracle:thin://@{self.host}:{self.port}/{self.database}"

        elif self.vendor == JdbcVendor.SQLSERVER:
            url_base = f"jdbc:sqlserver://{self.host}:{self.port};database={self.escape_db_name(JdbcVendor.SQLSERVER, self.database)}"

            if use_domain_match:
                return url_base + f";hostNameInCertificate={self.host}"

            if self.instance:
                url_base = f"jdbc:sqlserver://{self.host};instanceName={self.escape_db_name(JdbcVendor.SQLSERVER, self.instance)}:{self.port};database={self.escape_db_name(JdbcVendor.SQLSERVER, self.database)}"

            if self.application:
                url_base += f";applicationName={self.escape_db_name(JdbcVendor.SQLSERVER, self.application)}"

            return url_base

        elif self.vendor == JdbcVendor.MONGODB:
            if self.port != 0:
                return f"mongodb://{self.host}:{self.port}/{self.database}"
            else:
                return f"mongodb+srv://{self.host}/{self.database}"

        raise ValueError(f"URL generation not supported for {self.vendor}")

    def get_vendor(self) -> JdbcVendor:
        """Get the JDBC vendor."""
        return self.vendor

    def get_host(self) -> str:
        """Get the host."""
        return self.host

    def get_port(self) -> int:
        """Get the port."""
        return self.port

    def get_database(self) -> str:
        """Get the database name."""
        return self.database
