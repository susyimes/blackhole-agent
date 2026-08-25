# -*- coding: utf-8 -*-
import functools
import logging
import threading
from collections.abc import MutableMapping, MutableSequence
from typing import Any, Callable, Iterable, Dict

import tenacity
from tenacity import after_log, retry_if_exception, stop_after_attempt, wait_exponential

_logger = logging.getLogger(__name__)  # type: ignore


def synchronized(wrapped: Callable[..., Any]) -> Any:
    """The missing @synchronized decorator

    https://git.io/vydTA"""
    _lock = threading.RLock()

    @functools.wraps(wrapped)
    def _wrapper(*args, **kwargs):
        with _lock:
            return wrapped(*args, **kwargs)

    return _wrapper


# Copy from distutils.util to remove dependency
def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


def flatten_dict(
    d: Dict[str, Any], parent_key: str = "", separator: str = "."
) -> Dict[str, Any]:
    items = []
    for key, val in d.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(val, MutableMapping):
            items.extend(flatten_dict(val, new_key, separator=separator).items())
        elif isinstance(val, MutableSequence):
            for i, v in enumerate(val):
                new_list_key = "%s[%s]" % (new_key, str(i))
                if isinstance(v, MutableMapping):
                    items.extend(
                        flatten_dict(v, new_list_key, separator=separator).items()
                    )
                else:
                    items.append((new_list_key, v))
        else:
            items.append((new_key, val))
    return dict(items)


class RetryConfig:
    def __init__(
        self,
        exceptions: Iterable[str] = (
            "ThrottlingException",
            "TooManyRequestsException",
        ),
        attempt: int = 5,
        multiplier: int = 1,
        max_delay: int = 100,
        exponential_base: int = 2,
    ) -> None:
        self.exceptions = exceptions
        self.attempt = attempt
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.exponential_base = exponential_base


def retry_api_call(
    func: Callable[..., Any],
    config: RetryConfig,
    logger: logging.Logger = None,
    *args,
    **kwargs,
) -> Any:
    retry = tenacity.Retrying(
        retry=retry_if_exception(
            lambda e: (
                getattr(e, "response", {}).get("Error", {}).get("Code", None)
                in config.exceptions
                if e
                else False
            )
        ),
        stop=stop_after_attempt(config.attempt),
        wait=wait_exponential(
            multiplier=config.multiplier,
            max=config.max_delay,
            exp_base=config.exponential_base,
        ),
        after=after_log(logger, logger.level) if logger else None,  # type: ignore
        reraise=True,
    )
    return retry(func, *args, **kwargs)
