"""Controller replay must keep the text that follows a non-UTF-8 byte.

Harvested loop stderr (2026-09-03, 2026-09-04, 2026-10-29) records
UnicodeDecodeError in subprocess._readerthread for bytes 0xD5 and 0xCE.
On this interpreter that drops stdout to None while the child exit code
stays 0. Prints JSON with boolean passed and nonempty observed. Exit 0
for both met and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import replay_validation_command

    marker = "KEPT" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="bh-transcript-") as directory:
        root = Path(directory)
        script = root / "emit_marker.py"
        script.write_bytes(
            b"import sys\n"
            b"sys.stdout.buffer.write(bytes([0xCE]))\n"
            b"sys.stdout.buffer.write(sys.argv[1].encode('ascii'))\n"
            b"sys.stdout.buffer.write(b'\\n')\n"
        )
        command = f'"{sys.executable}" "{script}" {marker}'
        result = replay_validation_command(root, command, timeout=30)
    transcript = str(result.get("stdout_tail") or "")
    observed = {
        "reproduced_exit_code": result.get("reproduced_exit_code"),
        "ok": result.get("ok"),
        "marker_kept": marker in transcript,
        "bad_byte_replaced": "\ufffd" in transcript,
    }
    passed = (
        observed["ok"] is True
        and observed["reproduced_exit_code"] == 0
        and observed["marker_kept"] is True
        and observed["bad_byte_replaced"] is True
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
