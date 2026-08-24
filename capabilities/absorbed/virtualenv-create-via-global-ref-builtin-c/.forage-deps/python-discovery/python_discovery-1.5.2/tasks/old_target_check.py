"""Verify target-interpreter handling end to end; run inside a CI container with the target on PATH."""

from __future__ import annotations

import logging
import sys

from python_discovery import get_interpreter


def main(version: str, mode: str) -> None:
    handler = _RecordingHandler()
    logging.getLogger("python_discovery").addHandler(handler)
    info = get_interpreter(version)
    if mode == "discover":
        if info is None:
            msg = f"failed to discover Python {version}"
            raise SystemExit(msg)
        found = f"{info.version_info.major}.{info.version_info.minor}"
        if found != version:
            msg = f"discovered {found} at {info.executable} instead of {version}"
            raise SystemExit(msg)
        sys.stdout.write(f"discovered Python {version} at {info.executable}\n")
    else:
        if info is not None:
            msg = f"expected Python {version} to be rejected, discovered {info.executable}"
            raise SystemExit(msg)
        warnings = [record for record in handler.records if record.levelno == logging.WARNING]
        if not any("older than the minimum" in record.getMessage() for record in warnings):
            msg = f"no warning recorded while rejecting Python {version}"
            raise SystemExit(msg)
        sys.stdout.write(f"rejected Python {version} with a warning\n")


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
