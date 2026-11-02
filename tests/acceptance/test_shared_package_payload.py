"""Identical absorbed package payloads share one file body.

The same probe runs against the previous milestone source and the candidate
source. It exits 0 either way and prints JSON with boolean passed plus a
nonempty observed object.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def outcome() -> dict[str, object]:
    observed: dict[str, object] = {}
    passed = False
    try:
        from blackhole_agent.capability_absorption import (
            collapse_duplicate_package_payloads,
            tree_digest,
        )

        with tempfile.TemporaryDirectory(prefix="bh-share-payload-") as tmp:
            root = Path(tmp)

            def write_tool(slug: str, payload: str, adapter: str) -> None:
                package = root / slug / "package"
                package.mkdir(parents=True)
                (package / "body.txt").write_text(payload, encoding="utf-8")
                (root / slug / "adapter.txt").write_text(adapter, encoding="utf-8")

            write_tool("alpha", "SAME", "alpha-adapter")
            write_tool("beta", "SAME", "beta-adapter")
            write_tool("gamma", "OTHER", "gamma-adapter")
            before = {slug: tree_digest(root / slug) for slug in ("alpha", "beta", "gamma")}
            result = collapse_duplicate_package_payloads(root)
            after = {slug: tree_digest(root / slug) for slug in ("alpha", "beta", "gamma")}
            alpha = root / "alpha" / "package" / "body.txt"
            beta = root / "beta" / "package" / "body.txt"
            gamma = root / "gamma" / "package" / "body.txt"
            alpha_stat = alpha.stat()
            beta_stat = beta.stat()
            gamma_stat = gamma.stat()
            observed = {
                "ok": result.get("ok"),
                "shared_slug_count": result.get("shared_slug_count"),
                "linked_files": result.get("linked_files"),
                "private_slugs": result.get("private_slugs"),
                "same_body": alpha_stat.st_dev == beta_stat.st_dev and alpha_stat.st_ino == beta_stat.st_ino,
                "gamma_private": gamma_stat.st_ino != alpha_stat.st_ino or gamma_stat.st_dev != alpha_stat.st_dev,
                "adapters": [
                    (root / "alpha" / "adapter.txt").read_text(encoding="utf-8"),
                    (root / "beta" / "adapter.txt").read_text(encoding="utf-8"),
                ],
                "digests_held": before == after,
                "bytes_held": alpha.read_text(encoding="utf-8") == "SAME" and gamma.read_text(encoding="utf-8") == "OTHER",
            }
            passed = bool(
                observed["ok"] is True
                and observed["shared_slug_count"] == 2
                and observed["same_body"] is True
                and observed["gamma_private"] is True
                and observed["adapters"] == ["alpha-adapter", "beta-adapter"]
                and observed["digests_held"] is True
                and observed["bytes_held"] is True
                and observed["private_slugs"] == ["gamma"]
            )
    except Exception as exc:
        observed = {"error": f"{type(exc).__name__}: {exc}"}
        passed = False
    return {"observed": observed, "passed": passed}


def main() -> int:
    print(json.dumps(outcome(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
