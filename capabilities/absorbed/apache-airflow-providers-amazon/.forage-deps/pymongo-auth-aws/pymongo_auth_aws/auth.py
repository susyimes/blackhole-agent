# Copyright 2020-present MongoDB, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MONGODB-AWS authentication support for PyMongo."""

import os
from functools import wraps

from base64 import standard_b64encode
from datetime import tzinfo, timedelta


import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from pymongo_auth_aws.errors import PyMongoAuthAwsError


"""MONGODB-AWS credentials."""


class AwsCredential:
    def __init__(self, username, password, token, refresh_needed=None):
        self.username = username
        self.password = password
        self.token = token
        self.refresh_needed = refresh_needed


_credential_buffer_seconds = 60
__cached_credentials = None
__use_cached_credentials = None


def get_use_cached_credentials():
    """Determine whether we are using cached credentials."""
    return __use_cached_credentials


def set_use_cached_credentials(value):
    """Set whether we are using cached credentials."""
    global __use_cached_credentials
    __use_cached_credentials = value


def get_cached_credentials():
    """Central point for accessing cached credentials."""
    global __cached_credentials
    creds = __cached_credentials
    if creds and creds.refresh_needed is not None:
        if creds.refresh_needed(_credential_buffer_seconds):
            creds = __cached_credentials = None
    return creds


def set_cached_credentials(credentials):
    """Central point for setting cached credentials."""
    global __cached_credentials
    if __use_cached_credentials:
        __cached_credentials = credentials


ZERO = timedelta(0)

# A Python 2.7-compliant UTC class (from stdlib docs).
# When we drop Python 2.7 support we can use `timezone.utc` instead.


class _UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO


utc = _UTC()


def aws_temp_credentials():
    """Construct temporary MONGODB-AWS credentials."""
    # Store the variable locally for safe threaded access.
    creds = get_cached_credentials()
    if creds:
        return creds

    try:
        session = boto3.Session()
        creds = session.get_credentials()
        # Use frozen credentials to prevent a race condition if there
        # is a refresh between property accesses.
        frozen = creds.get_frozen_credentials()
    except Exception:
        # If temporary credentials cannot be obtained then drivers MUST
        # fail authentication and raise an error.
        set_cached_credentials(None)
        raise PyMongoAuthAwsError("temporary MONGODB-AWS credentials could not be obtained")

    # The botocore Credentials object does not expose the expiration
    # directly, instead we use the refresh_needed method to determine
    # whether the credentials are expired.
    refresh_needed = getattr(creds, "refresh_needed", None)
    creds = AwsCredential(frozen.access_key, frozen.secret_key, frozen.token, refresh_needed)
    # Only cache credentials that need to be refreshed from
    # an external source.
    if refresh_needed is not None:
        set_cached_credentials(creds)
    return creds


_AWS4_HMAC_SHA256 = "AWS4-HMAC-SHA256"
_AWS_SERVICE = "sts"


def _get_region(sts_host):
    """Return the AWS region to use for the given host."""
    # Drivers must also validate that the host is greater than 0 and
    # less than or equal to 255 bytes per RFC 1035.
    if not sts_host or len(sts_host) > 255:
        raise PyMongoAuthAwsError("Server returned an invalid sts host: %s" % (sts_host,))

    parts = sts_host.split(".")
    if len(parts) == 1 or sts_host == "sts.amazonaws.com":
        return "us-east-1"  # Default

    # Check for empty labels (eg "invalid..host" or ".invalid.host").
    if not all(parts):
        raise PyMongoAuthAwsError("Server returned an invalid sts host: %s" % (sts_host,))

    return parts[1]


def _aws_auth_header(credentials, server_nonce, sts_host):
    """Signature Version 4 Signing Process to construct the authorization header"""
    region = _get_region(sts_host)

    request_parameters = "Action=GetCallerIdentity&Version=2011-06-15"
    encoded_nonce = standard_b64encode(server_nonce).decode("utf8")
    request_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(request_parameters)),
        "Host": sts_host,
        "X-MongoDB-Server-Nonce": encoded_nonce,
        "X-MongoDB-GS2-CB-Flag": "n",
    }
    request = AWSRequest(method="POST", url="/", data=request_parameters, headers=request_headers)
    boto_creds = Credentials(credentials.username, credentials.password, token=credentials.token)
    auth = SigV4Auth(boto_creds, "sts", region)
    auth.add_auth(request)
    final = {"a": request.headers["Authorization"], "d": request.headers["X-Amz-Date"]}
    if credentials.token:
        final["t"] = credentials.token
    return final


def _handle_credentials(func):
    @wraps(func)
    def inner(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception:
            set_cached_credentials(None)
            raise

    return inner


class AwsSaslContext(object):
    """MONGODB-AWS authentication support.

    :Parameters:
      - `credentials`: The :class:`AwsCredential` to use for authentication.
    """

    def __init__(self, credentials):
        self._credentials = credentials
        self._step = 0
        self._client_nonce = None

    def step(self, server_payload):
        """Step through the SASL conversation.

        :Parameters:
          - `server_payload`: The server payload (SASL challenge). Must be a
            bytes-like object.

        :Returns:
          The response payload for the next SASL step.

        :Raises:
          :class:`~pymongo_auth_aws.PyMongoAuthAwsError` on error.
        """
        self._step += 1
        if self._step == 1:
            return self._first_payload()
        elif self._step == 2:
            return self._second_payload(server_payload)
        else:
            raise PyMongoAuthAwsError("MONGODB-AWS failed: too many steps")
        pass

    @_handle_credentials
    def _first_payload(self):
        """Return the first SASL payload."""
        # If a username and password are not provided, drivers MUST query
        # a link-local AWS address for temporary credentials.
        if self._credentials.username is None:
            self._credentials = aws_temp_credentials()

        # Client first.
        client_nonce = os.urandom(32)
        self._client_nonce = client_nonce
        payload = {"r": self.binary_type()(client_nonce), "p": 110}
        return self.binary_type()(self.bson_encode(payload))

    @_handle_credentials
    def _second_payload(self, server_payload):
        """Return the second and final SASL payload."""
        if not server_payload:
            raise PyMongoAuthAwsError("MONGODB-AWS failed: server payload empty")

        server_payload = self.bson_decode(server_payload)
        server_nonce = server_payload["s"]
        if len(server_nonce) != 64 or not server_nonce.startswith(self._client_nonce):
            raise PyMongoAuthAwsError("Server returned an invalid nonce.")

        sts_host = server_payload["h"]
        payload = _aws_auth_header(self._credentials, server_nonce, sts_host)
        return self.binary_type()(self.bson_encode(payload))

    # Dependency injection:
    def binary_type(self):
        """Return the bson.binary.Binary type."""
        raise NotImplementedError

    def bson_encode(self, doc):
        """Encode a dictionary to BSON."""
        raise NotImplementedError

    def bson_decode(self, data):
        """Decode BSON to a dictionary."""
        raise NotImplementedError
