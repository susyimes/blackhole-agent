"""
Authentication for Workday Data Connect.

Contains DataServiceConfig and SDEAuth, which handle OAuth 2.0 JWT Bearer
authentication against Workday's token endpoint.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse

import jwt
import requests
from trino.auth import Authentication


class DataServiceConfig:
    """Configuration for Workday DataService connection."""

    def __init__(self, properties: Dict[str, str]):
        self._properties = properties
        self._validate()

    def _validate(self):
        required = ["token_endpoint", "client_id", "isu"]
        missing = [p for p in required if not self._properties.get(p)]
        if missing:
            raise ValueError(f"Missing required properties: {', '.join(missing)}")
        if not self._properties.get("private_key"):
            raise ValueError("'private_key' must be provided")

    @property
    def token_endpoint(self) -> str:
        return self._properties["token_endpoint"]

    @property
    def client_id(self) -> str:
        return self._properties["client_id"]

    @property
    def isu(self) -> str:
        return self._properties["isu"]

    @property
    def private_key(self) -> str:
        return self._properties["private_key"]

    @property
    def include_dataservice_path_prefix(self) -> bool:
        val = self._properties.get("include_path_prefix")
        if val is None:
            return True
        return val.lower() in ("true", "1", "yes")

    @property
    def host(self) -> str:
        return self._properties.get("host", "localhost")

    @property
    def port(self) -> int:
        val = self._properties.get("port")
        return int(val) if val else 443

    @property
    def catalog(self) -> str:
        return self._properties.get("catalog", "workday_core")

    @property
    def schema(self) -> str:
        return self._properties.get("schema", "public")

    @property
    def session_properties(self) -> dict:
        props_str = self._properties.get("session_properties", "")
        if not props_str:
            return {}
        result = {}
        for pair in props_str.split(","):
            if ":" in pair:
                key, value = pair.split(":", 1)
                result[key.strip()] = value.strip()
        return result


class SDEAuth(Authentication):
    """Workday DataService OAuth 2.0 JWT Bearer authentication handler."""

    def __init__(self, config: DataServiceConfig):
        self.config = config
        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def set_http_session(self, http_session):
        token = self.get_token()
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            tenant = decoded.get("tenant")
            if not tenant or not tenant.strip():
                raise ValueError("Tenant claim is missing or empty in access token")
        except Exception as e:
            raise Exception(f"Error parsing JWT access token: {e}")

        http_session.headers["Authorization"] = f"Bearer {token}"
        http_session.headers["X-Tenant"] = tenant
        http_session.headers["X-Trino-Extra-Credential"] = f"token={token}"

        original_request = http_session.request

        def intercepted_request(method, url, **kwargs):
            parsed = urlparse(url)
            netloc = f"{self.config.host}:{self.config.port}"

            should_add_prefix = (
                self.config.include_dataservice_path_prefix
                and not parsed.path.startswith("/dataservice")
            )
            path = "/dataservice" + parsed.path if should_add_prefix else parsed.path

            modified_url = urlunparse(parsed._replace(netloc=netloc, path=path))
            response = original_request(method, modified_url, **kwargs)

            if response.status_code == 401:
                try:
                    response.close()
                except Exception:
                    pass
                self._cached_token = None
                self._token_expires_at = None
                refreshed_token = self.get_token()
                http_session.headers["Authorization"] = f"Bearer {refreshed_token}"
                http_session.headers["X-Trino-Extra-Credential"] = f"token={refreshed_token}"
                response = original_request(method, modified_url, **kwargs)

            return response

        http_session.request = intercepted_request

    def get_token(self) -> str:
        if self._is_token_valid():
            return self._cached_token
        return self._refresh_token()

    def _is_token_valid(self) -> bool:
        if not self._cached_token or not self._token_expires_at:
            return False
        return datetime.now(timezone.utc) < (self._token_expires_at - timedelta(seconds=60))

    def _refresh_token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self.config.client_id,
            "sub": self.config.isu,
            "aud": self.config.token_endpoint,
            "iat": now,
            "exp": now + 300,
            "jti": str(uuid.uuid4()),
        }
        assertion = jwt.encode(payload, self.config.private_key, algorithm="RS256")

        resp = requests.post(
            self.config.token_endpoint,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=15,
        )

        if resp.status_code == 200:
            data = resp.json()
            self._cached_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return self._cached_token
        else:
            resp.raise_for_status()
