"""A rendered adapter calls a constructor that needs a list and an integer.

The fixed trials (), a dict, a string, and an integer cannot build
Codec(chunks: list[str], times: int). The rendered adapter must print ABx
for encode("ab"), and introspection must list Codec.encode. A zero-argument
Codec still prints AB. An integer-only Codec still prints AB1.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PAIR_SOURCE = '''
class Codec:
    def __init__(self, chunks: list[str], times: int):
        if (
            not isinstance(chunks, list)
            or not chunks
            or any(not isinstance(item, str) or item == "" for item in chunks)
        ):
            raise TypeError("chunks")
        if type(times) is not int:
            raise TypeError("times")
        self.chunks = chunks
        self.times = times

    def encode(self, text):
        if not isinstance(text, str):
            raise TypeError("text")
        return (text.upper() + "".join(self.chunks)) * self.times
'''

ZERO_SOURCE = '''
class Codec:
    def encode(self, text):
        if not isinstance(text, str):
            raise TypeError("text")
        return text.upper()
'''

INT_SOURCE = '''
class Codec:
    def __init__(self, width):
        self.width = int(width)

    def encode(self, text):
        if not isinstance(text, str):
            raise TypeError("text")
        return text.upper() + str(self.width)
'''


def _run_adapter(source: str) -> dict:
    from blackhole_agent.capability_acquisition import AcquisitionSpec, synthesize_adapter_source

    spec = AcquisitionSpec(
        slug="bhcodec",
        name="Annotated codec",
        source=Path("."),
        import_name="bhcodec",
        callable_name="Codec.encode",
        requires=("text",),
        provides="codec_encode_output",
        probes=({"text": "ab"}, {"text": "cd"}),
        path_root=".",
    )
    rendered = synthesize_adapter_source(spec)
    with tempfile.TemporaryDirectory(prefix="bh-annotated-adapter-") as tmp:
        root = Path(tmp)
        (root / "bhcodec.py").write_text(source, encoding="utf-8")
        adapter = root / "acquisition_adapter.py"
        adapter.write_text(rendered, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(adapter)],
            input=json.dumps({"text": "ab"}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root,
            timeout=30,
            check=False,
        )
    payload = None
    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        payload = None
    output = payload.get("codec_encode_output") if isinstance(payload, dict) else None
    return {
        "exit_code": completed.returncode,
        "output": output,
        "stderr_tail": (completed.stderr or "")[-300:],
    }


def _reflect_pair() -> dict:
    from blackhole_agent.capability_foraging import detect_import_root, introspect_module

    with tempfile.TemporaryDirectory(prefix="bh-annotated-reflect-") as tmp:
        pkg = Path(tmp) / "pkg"
        pkg.mkdir()
        (pkg / "bhcodec.py").write_text(PAIR_SOURCE, encoding="utf-8")
        path_root, import_name = detect_import_root(pkg, "bhcodec")
        reflected = introspect_module(pkg, import_name, path_root, timeout=60)
    match = next(
        (
            item
            for item in reflected.get("candidates") or []
            if str(item.get("name") or "").endswith("Codec.encode")
        ),
        None,
    )
    return {
        "ok": bool(reflected.get("ok")),
        "error": str(reflected.get("error") or ""),
        "found": match is not None,
        "trial": "" if match is None else str(match.get("constructor_trial") or ""),
    }


_DONE_WHEN = (
    "A rendered Python acquisition adapter, given stdin text ab, writes "
    "codec_encode_output ABx for a constructor that requires list[str] and int. "
    "introspect_module includes Codec.encode with constructor trial list+int. "
    "The same adapter path writes AB for a zero-argument Codec and AB1 for an "
    "integer-only Codec."
)


def _false_capability_ids() -> list[str]:
    from blackhole_agent.capability_compounder import parse_outcome_contract

    parsed = parse_outcome_contract(_DONE_WHEN)
    return [
        str(item.get("arg") or "")
        for item in parsed.get("predicates") or []
        if item.get("kind") == "capability_exists"
    ]


def observe() -> tuple[bool, dict]:
    pair = _run_adapter(PAIR_SOURCE)
    zero = _run_adapter(ZERO_SOURCE)
    integer = _run_adapter(INT_SOURCE)
    reflected = _reflect_pair()
    false_ids = _false_capability_ids()
    observed = {
        "pair_exit": pair["exit_code"],
        "pair_output": pair["output"],
        "pair_stderr": pair["stderr_tail"],
        "zero_output": zero["output"],
        "integer_output": integer["output"],
        "reflected_found": reflected["found"],
        "reflected_trial": reflected["trial"],
        "reflected_error": reflected["error"],
        "false_capability_ids": false_ids,
    }
    passed = (
        pair["exit_code"] == 0
        and pair["output"] == "ABx"
        and zero["output"] == "AB"
        and integer["output"] == "AB1"
        and reflected["found"] is True
        and reflected["trial"] == "list+int"
        and false_ids == []
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:500]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
