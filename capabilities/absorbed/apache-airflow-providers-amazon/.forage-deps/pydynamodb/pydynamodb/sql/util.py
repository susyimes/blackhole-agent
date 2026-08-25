# -*- coding: utf-8 -*-
import logging
from typing import Any, List

_logger = logging.getLogger(__name__)  # type: ignore


def flatten_list(lst: List[Any]) -> List[Any]:
    items = []
    for item in lst:
        if isinstance(item, list):
            if len(item) > 2 and item[0] == "[" and item[-1] == "]":
                items.append(
                    "[%s]" % (",".join(str(item[i]) for i in range(1, len(item) - 1)))
                )
                return items

            items.extend(flatten_list(item))
        else:
            items.append(item)
    return items
