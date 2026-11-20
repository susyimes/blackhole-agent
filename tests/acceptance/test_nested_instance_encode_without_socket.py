"""Local nested-instance encode must not load the network stack.

Controller replay of invoke_described_nested_instance_plane exited 1 because
the growth import loaded urllib.request and then _socket. Encoding caller
text does not need that module. This probe blocks socket, _socket, and
urllib.request before the import.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay this probe on baseline and
candidate source.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import sys


class _BlockedLoader(importlib.abc.Loader):
    def create_module(self, spec):  # noqa: ANN001
        return None

    def exec_module(self, module) -> None:  # noqa: ANN001
        raise ImportError(f"network stack blocked: {module.__name__}")


class _RefuseNetwork:
    def find_spec(self, fullname, path, target=None):  # noqa: ANN001
        if fullname in {"socket", "_socket", "urllib.request"} or fullname.startswith(
            "urllib.request."
        ):
            return importlib.machinery.ModuleSpec(fullname, _BlockedLoader())
        return None


def main() -> None:
    observed: dict[str, object] = {}
    passed = False
    sys.meta_path.insert(0, _RefuseNetwork())
    try:
        from blackhole_agent.capability_application_growth import (
            invoke_described_nested_instance_plane,
        )

        hello = invoke_described_nested_instance_plane(4, "Hello")
        other = invoke_described_nested_instance_plane(2, "xy")
        default = invoke_described_nested_instance_plane(3)
        refused = invoke_described_nested_instance_plane(3, 1)  # type: ignore[arg-type]
        observed = {
            "default": default,
            "hello": hello,
            "other": other,
            "refused": refused,
            "socket_loaded": "socket" in sys.modules or "_socket" in sys.modules,
            "urllib_request_loaded": "urllib.request" in sys.modules,
        }
        passed = (
            hello == "HELLO"
            and other == "XY"
            and default == "AB"
            and refused == ""
            and observed["socket_loaded"] is False
            and observed["urllib_request_loaded"] is False
        )
    except Exception as exc:  # noqa: BLE001 - baseline must report, not crash
        observed = {
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "socket_loaded": "socket" in sys.modules or "_socket" in sys.modules,
            "urllib_request_loaded": "urllib.request" in sys.modules,
        }
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
