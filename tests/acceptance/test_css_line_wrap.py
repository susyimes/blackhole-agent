"""Wrap one inline into CSS Text line boxes.

A collapsible break between Han characters disappears, while a break between
Hangul or Latin letters becomes one space. Pre-wrap hangs a trailing space
unless that space fits before a preserved newline. Break-spaces keeps the
first space with the preceding glyph. A soft hyphen appears only when the
line breaks there. anywhere and break-word split the same overflowing word,
and only anywhere lowers min-content.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the wrapper still exits 0.
"""

from __future__ import annotations

import json
import sys


def _lines(result: object) -> list[tuple[str, object, object]] | None:
    if not isinstance(result, dict) or result.get("outcome") != "wrapped":
        return None
    rows = result.get("lines")
    if not isinstance(rows, list):
        return None
    packed: list[tuple[str, object, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        packed.append((row.get("text"), row.get("content_width"), row.get("width")))
    return packed


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_line_break import wrap_lines
    except Exception as exc:  # noqa: BLE001 - baseline without the wrapper still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = wrap_lines(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised wrap is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    def expect(name: str, lines: list[tuple[str, object, object]], minimum: object, maximum: object, **kwargs: object) -> None:
        result = keep(name, **kwargs)
        checks.append(_lines(result) == lines)
        checks.append(result.get("min_content") == minimum and result.get("max_content") == maximum)

    expect("han_join", [("長，在", 3, 3)], 2, 3, text="長，\n在", width=10)
    expect("han_wrap", [("長，", 2, 2), ("在", 1, 1)], 2, 3, text="長，在", width=2)
    expect("hangul_join", [("한 글", 3, 3)], 1, 3, text="한\n글", width=10)
    expect("latin_join", [("ab cd", 5, 5)], 2, 5, text="ab\ncd", width=10)
    expect("collapsed_blank", [("a b", 3, 3)], 1, 3, text="a\n\nb", width=10)
    expect("normal_newline", [("a", 1, 1)], 1, 1, text="a\n", width=4)
    expect("pre_newline", [("a", 1, 1), ("", 0, 0)], 1, 1, text="a\n", width=4, white_space="pre")

    expect(
        "pre_wrap_hang",
        [("abcd ", 4, 5), ("", 0, 0)],
        4,
        5,
        text="abcd \n",
        width=4,
        white_space="pre-wrap",
    )
    expect(
        "pre_wrap_fit",
        [("abc ", 4, 4), ("", 0, 0)],
        3,
        4,
        text="abc \n",
        width=4,
        white_space="pre-wrap",
    )
    expect("pre_wrap_end", [("abcd ", 4, 5)], 4, 4, text="abcd ", width=4, white_space="pre-wrap")
    expect(
        "break_spaces",
        [("ab ", 3, 3), (" c", 2, 2)],
        3,
        5,
        text="ab  c",
        width=2,
        white_space="break-spaces",
    )

    expect("overflow_normal", [("hello", 5, 5)], 5, 5, text="hello", width=3)
    expect("overflow_anywhere", [("hel", 3, 3), ("lo", 2, 2)], 1, 5, text="hello", width=3, overflow_wrap="anywhere")
    expect("overflow_break_word", [("hel", 3, 3), ("lo", 2, 2)], 5, 5, text="hello", width=3, overflow_wrap="break-word")
    expect("keep_all", [("字字", 2, 2), ("字", 1, 1)], 3, 3, text="字字字", width=2, word_break="keep-all")
    expect("han_letters", [("字字", 2, 2), ("字", 1, 1)], 1, 3, text="字字字", width=2)

    expect("shy_unused", [("abcd", 4, 4)], 3, 4, text="ab\u00adcd", width=10)
    expect("shy_used", [("ab\u2010", 3, 3), ("cd", 2, 2)], 3, 4, text="ab\u00adcd", width=3)
    expect("shy_suppressed", [("abcd", 4, 4)], 4, 4, text="ab\u00adcd", width=3, hyphens="none")

    expect("tab", [("a\tb", 5, 5)], 5, 5, text="a\tb", width=20, white_space="pre", tab_size=4)
    expect(
        "tab_under_half",
        [("a\t", 8, 8)],
        8,
        8,
        text="a\t",
        width=20,
        white_space="pre",
        tab_size=4,
        advances={"a": 3.75},
    )
    expect(
        "tab_exact_half",
        [("a\t", 4, 4)],
        4,
        4,
        text="a\t",
        width=20,
        white_space="pre",
        tab_size=4,
        advances={"a": 3.5},
    )

    expect("ellipsis_normal", [("……", 2, 2)], 2, 2, text="……", width=1)
    expect("ellipsis_loose", [("…", 1, 1), ("…", 1, 1)], 1, 2, text="……", width=1, line_break="loose")
    expect("small_kana", [("あゃ", 2, 2)], 2, 2, text="あゃ", width=1)
    expect("small_kana_loose", [("あ", 1, 1), ("ゃ", 1, 1)], 1, 2, text="あゃ", width=1, line_break="loose")
    expect("wavedash_zh", [("文", 1, 1), ("〜", 1, 1)], 1, 2, text="文〜", width=1, lang="zh")
    expect("wavedash_en", [("文〜", 2, 2)], 2, 2, text="文〜", width=1, lang="en")
    expect("wavedash_strict", [("文〜", 2, 2)], 2, 2, text="文〜", width=1, lang="zh", line_break="strict")

    cluster = keep("cluster", text="e\u0301x", width=1, overflow_wrap="anywhere")
    checks.append(_lines(cluster) == [("e\u0301", 1, 1), ("x", 1, 1)])
    checks.append(cluster.get("min_content") == 1)

    invalid = keep("bad_width", text="a", width=-1)
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("lines") is None)
    missing = keep("missing_text", text=None, width=1)
    checks.append(missing.get("outcome") == "invalid" and missing.get("lines") is None)

    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    """Write one ASCII JSON line. Isolated Windows runs use a GBK stdout."""

    try:
        line = json.dumps(payload, ensure_ascii=True)
    except Exception as exc:  # noqa: BLE001 - the probe must still emit a record
        line = json.dumps({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}})
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(line.encode("ascii") + b"\n")
        buffer.flush()
        return
    print(line)


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    _emit({"passed": bool(passed), "observed": observed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
