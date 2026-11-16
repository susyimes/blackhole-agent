"""Response bytes match Subresource Integrity metadata by the strongest hash.

A wrong sha256 beside a correct sha512 matches as sha512. A correct sha256
beside a wrong sha512 does not. Either of two sha512 hashes may match. Only
sha1, and blank metadata, match with nothing recognized. An uppercase SHA512
hash keeps a trailing question-mark option and still matches. A bare sha256
token is recognized and does not match. An unpadded sha512 hash does not
match the padded base64 encoding.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the checker is an unmet outcome, not a crash.
"""

from __future__ import annotations

import base64
import hashlib
import json


def _b64(algorithm: str, data: bytes) -> str:
    return base64.b64encode(hashlib.new(algorithm, data).digest()).decode("ascii")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.subresource_integrity import bytes_match_integrity
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    hello = b"hello"
    other = b"blackhole-sri-v1"
    sha256 = _b64("sha256", hello)
    sha384 = _b64("sha384", hello)
    sha512 = _b64("sha512", hello)
    wrong256 = _b64("sha256", other)
    wrong512 = _b64("sha512", other)
    try:
        strongest = bytes_match_integrity(hello, f"sha256-{wrong256} sha512-{sha512}")
        weaker = bytes_match_integrity(hello, f"sha256-{sha256} sha512-{wrong512}")
        either = bytes_match_integrity(hello, f"sha512-{wrong512} sha512-{sha512}")
        unknown = bytes_match_integrity(hello, "sha1-aaaaaaaa")
        empty = bytes_match_integrity(hello, "")
        blank = bytes_match_integrity(hello, " \n\t")
        upper = bytes_match_integrity(hello, f"SHA512-{sha512}?ignored=1")
        bare = bytes_match_integrity(hello, "sha256")
        skipped = bytes_match_integrity(hello, f"not-a-hash\nsha384-{sha384}")
        unpadded = bytes_match_integrity(hello, f"sha512-{sha512.rstrip('=')}")
    except Exception as exc:  # noqa: BLE001 - a broken checker is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed = {
        "strongest": strongest,
        "weaker": weaker,
        "either": either,
        "unknown": unknown,
        "empty": empty,
        "blank": blank,
        "upper": upper,
        "bare": bare,
        "skipped": skipped,
        "unpadded": unpadded,
    }
    passed = (
        strongest.get("match") is True
        and strongest.get("algorithm") == "sha512"
        and strongest.get("recognized") == 2
        and weaker.get("match") is False
        and weaker.get("algorithm") == "sha512"
        and either.get("match") is True
        and either.get("algorithm") == "sha512"
        and either.get("recognized") == 2
        and unknown.get("match") is True
        and unknown.get("recognized") == 0
        and unknown.get("algorithm") == ""
        and empty.get("match") is True
        and empty.get("recognized") == 0
        and blank.get("match") is True
        and blank.get("recognized") == 0
        and upper.get("match") is True
        and upper.get("algorithm") == "sha512"
        and upper.get("recognized") == 1
        and bare.get("match") is False
        and bare.get("algorithm") == "sha256"
        and bare.get("recognized") == 1
        and skipped.get("match") is True
        and skipped.get("algorithm") == "sha384"
        and skipped.get("recognized") == 1
        and unpadded.get("match") is False
        and unpadded.get("algorithm") == "sha512"
    )
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
