"""
Base Spark Session Provider.

This module provides the abstract base class for all Spark session providers.
"""

import logging
import os
from abc import ABC, abstractmethod

from sagemaker_studio.utils._internal import InternalUtils

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

logger = logging.getLogger(__name__)


class SparkSessionManager(ABC):
    """
    Abstract base class for Spark session providers.

    This defines the interface that all Spark session providers must implement.
    """

    @staticmethod
    def setup_logger(logger: logging.Logger, log_file: str) -> None:
        """Configure *logger* with a file handler, falling back to console.

        Idempotent — skips if the logger already has handlers.
        """
        if logger.handlers:
            return
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(file_handler)
            logger.setLevel(logging.INFO)
        except (PermissionError, OSError) as e:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(console_handler)
            logger.setLevel(logging.INFO)
            logger.warning(f"Failed to create log file {log_file}: {e}.")

    @abstractmethod
    def create(self):
        """
        Create and return a SparkSession.

        Returns:
            SparkSession: A configured SparkSession object.
        """
        pass

    @abstractmethod
    def stop(self):
        """Stop the SparkSession and clean up resources."""
        pass

    @abstractmethod
    def get_session_id(self):
        pass

    _user_spark_conf: dict | None = None

    def set_user_spark_conf(self, spark_conf: dict | None):
        """Set user-supplied spark config overrides (from sparkutils.init or sparkutils.configure).

        Called by LazySparkSession before create(). These are the highest-priority
        configs — they override everything else.
        """
        self._user_spark_conf = spark_conf

    def _get_execution_role_arn(self):
        """Get the execution role ARN from the project's IAM connection."""
        return self.project.iam_role

    @staticmethod
    def _user_msg(msg):
        """Print a user-facing progress message (visible in notebook cell output)."""
        print(msg, flush=True)

    def _get_user_id_account_id(self):
        """Return (user_id, account_id), falling back to STS if env vars are missing."""
        _utils = InternalUtils()
        try:
            account_id = _utils._get_account_id()
            user_id = _utils._get_user_id()
        except (KeyError, EnvironmentError, RuntimeError, ValueError) as e:
            logger.warning("InternalUtils identity lookup failed, falling back to STS: %s", e)
            account_id = None
            user_id = None

        if not account_id or not user_id:
            response = self.sts_client.get_caller_identity()
            account_id = response["Account"]
            user_id = response["UserId"]
            tokens = user_id.split(":")
            if len(tokens) >= 2:
                return tokens[1], account_id
            else:
                raise RuntimeError("Invalid user id from STS caller identity.")

        return user_id, account_id
