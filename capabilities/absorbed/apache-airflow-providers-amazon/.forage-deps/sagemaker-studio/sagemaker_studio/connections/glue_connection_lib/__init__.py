"""
Glue Connection Library.
Core interface for AWS Glue connection wrappers.
"""

from .connections.utils.secure_connection import sanitize_connection_for_logging
from .connections.wrapper.glue_connection_wrapper import GlueConnectionWrapper
from .connections.wrapper.glue_connection_wrapper_inputs import GlueConnectionWrapperInputs

__all__ = [
    "GlueConnectionWrapper",
    "GlueConnectionWrapperInputs",
    "sanitize_connection_for_logging",
]

__version__ = "0.1.0"
