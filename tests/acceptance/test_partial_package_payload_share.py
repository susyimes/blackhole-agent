"""A versioned payload shares matching files when the trees are not identical.

Real absorbed slugs vendor ``name-version/``, not a directory named ``package``.
One extra or different file used to keep every identical path private. The
probe exits 0 either way and prints JSON with boolean passed and nonempty
observed.
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

        with tempfile.TemporaryDirectory(prefix="bh-partial-payload-") as tmp:
            root = Path(tmp)

            def write_slug(slug: str, notes: str, *, only: bool) -> None:
                payload = root / slug / "widget-1.2" / "sub"
                payload.mkdir(parents=True)
                (payload / "lib.py").write_text("LIB", encoding="utf-8")
                (root / slug / "widget-1.2" / "notes.txt").write_text(notes, encoding="utf-8")
                if only:
                    (root / slug / "widget-1.2" / "only_alpha.dat").write_text(
                        "ONLY", encoding="utf-8"
                    )
                hidden = root / slug / ".forage-deps"
                hidden.mkdir()
                (hidden / "secret.txt").write_text("SECRET", encoding="utf-8")
                (root / slug / "adapter.txt").write_text(f"{slug}-adapter", encoding="utf-8")

            write_slug("alpha", "ALPHA-NOTES", only=True)
            write_slug("beta", "BETA-NOTES", only=False)
            before = {
                slug: tree_digest(root / slug / "widget-1.2") for slug in ("alpha", "beta")
            }
            result = collapse_duplicate_package_payloads(root)
            after = {
                slug: tree_digest(root / slug / "widget-1.2") for slug in ("alpha", "beta")
            }
            alpha_lib = root / "alpha" / "widget-1.2" / "sub" / "lib.py"
            beta_lib = root / "beta" / "widget-1.2" / "sub" / "lib.py"
            alpha_notes = root / "alpha" / "widget-1.2" / "notes.txt"
            beta_notes = root / "beta" / "widget-1.2" / "notes.txt"
            alpha_secret = root / "alpha" / ".forage-deps" / "secret.txt"
            beta_secret = root / "beta" / ".forage-deps" / "secret.txt"
            alpha_only = root / "alpha" / "widget-1.2" / "only_alpha.dat"
            alpha_adapter = root / "alpha" / "adapter.txt"
            beta_adapter = root / "beta" / "adapter.txt"
            alpha_lib_stat = alpha_lib.stat()
            beta_lib_stat = beta_lib.stat()
            alpha_notes_stat = alpha_notes.stat()
            beta_notes_stat = beta_notes.stat()
            alpha_secret_stat = alpha_secret.stat()
            beta_secret_stat = beta_secret.stat()
            same_inode = (
                alpha_lib_stat.st_dev == beta_lib_stat.st_dev
                and alpha_lib_stat.st_ino == beta_lib_stat.st_ino
            )
            notes_private = (
                alpha_notes_stat.st_dev != beta_notes_stat.st_dev
                or alpha_notes_stat.st_ino != beta_notes_stat.st_ino
            )
            hidden_private = (
                alpha_secret_stat.st_dev != beta_secret_stat.st_dev
                or alpha_secret_stat.st_ino != beta_secret_stat.st_ino
            )
            observed = {
                "ok": result.get("ok"),
                "shared_slug_count": result.get("shared_slug_count"),
                "private_slugs": result.get("private_slugs"),
                "payloads": result.get("payloads"),
                "same_inode": same_inode,
                "notes_private": notes_private,
                "hidden_private": hidden_private,
                "only_alpha_present": alpha_only.is_file() and not (root / "beta" / "widget-1.2" / "only_alpha.dat").exists(),
                "only_alpha_nlink": alpha_only.stat().st_nlink,
                "bytes_held": (
                    alpha_lib.read_text(encoding="utf-8") == "LIB"
                    and beta_lib.read_text(encoding="utf-8") == "LIB"
                    and alpha_notes.read_text(encoding="utf-8") == "ALPHA-NOTES"
                    and beta_notes.read_text(encoding="utf-8") == "BETA-NOTES"
                    and alpha_secret.read_text(encoding="utf-8") == "SECRET"
                ),
                "adapters_held": [
                    alpha_adapter.read_text(encoding="utf-8"),
                    beta_adapter.read_text(encoding="utf-8"),
                ],
                "adapter_private": alpha_adapter.stat().st_ino != beta_adapter.stat().st_ino,
                "digests_held": before == after,
            }
            passed = bool(
                observed["ok"] is True
                and observed["same_inode"] is True
                and observed["notes_private"] is True
                and observed["hidden_private"] is True
                and observed["only_alpha_present"] is True
                and observed["only_alpha_nlink"] == 1
                and observed["bytes_held"] is True
                and observed["adapters_held"] == ["alpha-adapter", "beta-adapter"]
                and observed["adapter_private"] is True
                and observed["digests_held"] is True
                and observed["shared_slug_count"] == 2
                and observed["payloads"] == {"alpha": "widget-1.2", "beta": "widget-1.2"}
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
