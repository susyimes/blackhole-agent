"""HTML comments inside a list keep their closing marker across a blank line.

Absorbed markdown-it-py 4.0.0 ended the comment when the blank line was
outdented, then escaped the marker into a paragraph. The list fixture now
keeps the marker and leaves the trailing paragraph outside it. A blockquote
comment, a script block, a div that ends on a blank line, and an outdented
paragraph after an unclosed comment keep their places.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json


_LIST = "1. item\n\n    <!--\n    a\n\n    b\n    -->\n    c\n"
_QUOTE = "> <!--\n> a\n>\n> b\n> -->\n> c\n"
_DIV = "<div>\n\nparagraph\n"
_SCRIPT = "1. item\n\n    <script>\n    a\n\n    b\n    </script>\n    c\n"
_DEDENT = "1. item\n\n    <!--\n    a\n\nafter\n"
_PLAIN = "Hello\n"

_LIST_HTML = "<ol>\n<li>\n<p>item</p>\n <!--\n a\n\n b\n -->\n<p>c</p>\n</li>\n</ol>\n"
_QUOTE_HTML = "<blockquote>\n<!--\na\n\nb\n-->\n<p>c</p>\n</blockquote>\n"
_DIV_HTML = "<div>\n<p>paragraph</p>\n"
_SCRIPT_HTML = "<ol>\n<li>\n<p>item</p>\n <script>\n a\n\n b\n </script>\n<p>c</p>\n</li>\n</ol>\n"
_DEDENT_HTML = "<ol>\n<li>\n<p>item</p>\n <!--\n a\n\n</li>\n</ol>\n<p>after</p>\n"
_PLAIN_HTML = "<p>Hello</p>\n"


def observe() -> tuple[bool, dict]:
    observed: dict = {}
    try:
        from blackhole_agent.markdown_html_block import render_commonmark
    except Exception as exc:  # noqa: BLE001 - baseline without the renderer still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    documents = {
        "list_comment": _LIST,
        "blockquote_comment": _QUOTE,
        "div_blank": _DIV,
        "script_blank": _SCRIPT,
        "dedented_paragraph": _DEDENT,
        "plain": _PLAIN,
    }
    rendered: dict[str, str] = {}
    for name, document in documents.items():
        try:
            rendered[name] = render_commonmark(document)
        except Exception as exc:  # noqa: BLE001 - an unmet document stays observable
            observed[name] = {"error": type(exc).__name__, "detail": str(exc)[:240]}
            return False, observed
    observed.update(rendered)
    passed = (
        rendered["list_comment"] == _LIST_HTML
        and "--&gt;" not in rendered["list_comment"]
        and rendered["blockquote_comment"] == _QUOTE_HTML
        and rendered["div_blank"] == _DIV_HTML
        and "paragraph</div>" not in rendered["div_blank"]
        and rendered["script_blank"] == _SCRIPT_HTML
        and rendered["dedented_paragraph"] == _DEDENT_HTML
        and "-->" not in rendered["dedented_paragraph"]
        and rendered["plain"] == _PLAIN_HTML
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
