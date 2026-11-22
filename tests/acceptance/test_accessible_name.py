"""Accessible names that text content and placeholders get wrong.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("empty alt blocks title", "<img id='t' alt='' title='title' src='cat.png'>", "t", ""),
    ("missing alt uses title", "<img id='t' title='title' src='cat.png'>", "t", "title"),
    ("alt beats title", "<img id='t' alt='Cat' title='title'>", "t", "Cat"),
    ("src is not a name", "<img id='t' src='cat.png'>", "t", ""),
    (
        "labelledby keeps reference order",
        "<span id='b'>Beta</span><span id='a'>Alpha</span>"
        "<button id='t' aria-labelledby='b a'>ignored</button>",
        "t",
        "Beta Alpha",
    ),
    (
        "hidden reference is included",
        "<button id='t' aria-labelledby='h'>Visible</button><span id='h' hidden>Secret</span>",
        "t",
        "Secret",
    ),
    (
        "hidden descendant is skipped",
        "<button id='t'>A <span hidden>B</span> C</button>",
        "t",
        "A C",
    ),
    (
        "aria-hidden descendant is skipped",
        "<button id='t'>A <span aria-hidden='true'>B</span> C</button>",
        "t",
        "A C",
    ),
    (
        "inline display none is skipped",
        "<button id='t'>A <span style='color: red; display: none'>B</span> C</button>",
        "t",
        "A C",
    ),
    (
        "hidden reference keeps its hidden child",
        "<button id='t' aria-labelledby='el2'></button>"
        "<div id='el2' hidden><span hidden>hello</span></div>",
        "t",
        "hello",
    ),
    (
        "visible reference skips its hidden child",
        "<button id='t' aria-labelledby='el2'></button>"
        "<div id='el2'><span hidden>hello</span></div>",
        "t",
        "",
    ),
    (
        "label beats placeholder",
        "<label for='t'>Lab</label><input id='t' placeholder='ph' title='ti'>",
        "t",
        "Lab",
    ),
    (
        "aria-label beats the label",
        "<label for='t'>Lab</label><input id='t' aria-label='AL' placeholder='ph'>",
        "t",
        "AL",
    ),
    ("title beats placeholder", "<input id='t' title='ti' placeholder='ph'>", "t", "ti"),
    ("placeholder is the last text name", "<input id='t' placeholder='ph'>", "t", "ph"),
    (
        "second labelledby is not followed",
        "<span id='el1' aria-labelledby='el3'></span>"
        "<span id='el2' aria-labelledby='el1'></span>"
        "<span id='el3'> hello </span>",
        "el2",
        "",
    ),
    (
        "first labelledby is followed",
        "<span id='el1' aria-labelledby='el3'></span><span id='el3'> hello </span>",
        "el1",
        "hello",
    ),
    ("self reference uses content", "<button id='t' aria-labelledby='t'>Press</button>", "t", "Press"),
    (
        "self reference keeps its aria-label",
        "<a id='file'>Documentation.pdf</a>"
        "<span id='t' role='button' aria-label='Delete' aria-labelledby='t file'></span>",
        "t",
        "Delete Documentation.pdf",
    ),
    (
        "checkbox uses the label not the value",
        "<label for='t'>Agree</label><input id='t' type='checkbox' value='on'>",
        "t",
        "Agree",
    ),
    ("submit default", "<input id='t' type='submit'>", "t", "Submit"),
    ("submit value", "<input id='t' type='submit' value='Send'>", "t", "Send"),
    ("reset default", "<input id='t' type='reset'>", "t", "Reset"),
    ("image input empty alt submits", "<input id='t' type='image' alt=''>", "t", "Submit"),
    ("image input alt", "<input id='t' type='image' alt='Find'>", "t", "Find"),
    ("cell text is not its name", "<table><tr><td id='t'>Cell</td></tr></table>", "t", ""),
    ("cell title is its name", "<table><tr><td id='t' title='Head'>Cell</td></tr></table>", "t", "Head"),
    ("break becomes a space", "<button id='t'>A<br>B</button>", "t", "A B"),
    (
        "child aria-label replaces its text",
        "<button id='t'>A <span aria-label='B'>C</span></button>",
        "t",
        "A B",
    ),
    (
        "hidden label still names the control",
        "<label for='t' hidden>Secret</label><input id='t' placeholder='ph'>",
        "t",
        "Secret",
    ),
    (
        "visible label skips a hidden span",
        "<label for='t'>Visible <span hidden>no</span></label><input id='t'>",
        "t",
        "Visible",
    ),
    (
        "presentation prohibits the root name",
        "<span id='t' role='presentation' aria-label='Hello'>x</span>",
        "t",
        "",
    ),
    (
        "generic prohibits the root name",
        "<div id='t' role='generic' aria-label='Hello'>x</div>",
        "t",
        "",
    ),
    ("div aria-label", "<div id='t' aria-label='Hello'>x</div>", "t", "Hello"),
    ("div text is not its name", "<div id='t'>Hello</div>", "t", ""),
    ("heading uses its text", "<h1 id='t'>Title</h1>", "t", "Title"),
    (
        "aria-label collapses whitespace",
        "<button id='t' aria-label='  hello   world  '>no</button>",
        "t",
        "hello world",
    ),
    (
        "missing reference falls through",
        "<button id='t' aria-labelledby='missing' aria-label='OK'>no</button>",
        "t",
        "OK",
    ),
    (
        "one real reference wins",
        "<button id='t' aria-labelledby='missing real' aria-label='OK'>no</button>"
        "<span id='real'>Yes</span>",
        "t",
        "Yes",
    ),
    (
        "embedded textbox ignores its aria-label",
        "<label for='flash'><input type='checkbox' id='flash'>"
        "Flash the screen <span role='textbox' aria-label='number of times'>5</span> times</label>",
        "flash",
        "Flash the screen 5 times",
    ),
    (
        "wrapped control drops its own value",
        "<label>Flash the screen <input id='n' value='5'> times</label>",
        "n",
        "Flash the screen times",
    ),
    (
        "sole figcaption names the image",
        "<figure>\n  <img id='t'>\n  <figcaption>A cat</figcaption>\n</figure>",
        "t",
        "A cat",
    ),
    (
        "extra figure content blocks the caption",
        "<figure><img id='t'><p>extra</p><figcaption>A cat</figcaption></figure>",
        "t",
        "",
    ),
    (
        "empty alt blocks the figcaption",
        "<figure><img id='t' alt=''><figcaption>A cat</figcaption></figure>",
        "t",
        "",
    ),
    ("script text is not a name", "<button id='t'>OK<script>bad()</script></button>", "t", "OK"),
    (
        "select uses the label not the option",
        "<label for='s'>City</label><select id='s'><option>Paris</option></select>",
        "s",
        "City",
    ),
    (
        "legend names the fieldset",
        "<fieldset id='t'><legend>Group</legend><input></fieldset>",
        "t",
        "Group",
    ),
    (
        "caption names the table",
        "<table id='t'><caption>Data</caption><tr><td>1</td></tr></table>",
        "t",
        "Data",
    ),
    (
        "referenced presentation still contributes",
        "<button id='t' aria-labelledby='p'></button><span id='p' role='presentation'>Hello</span>",
        "t",
        "Hello",
    ),
    ("hidden root has no name", "<span id='t' hidden>Secret</span>", "t", ""),
    (
        "ancestor hidden root has no name",
        "<div hidden><span id='t'>Secret</span></div>",
        "t",
        "",
    ),
    ("spaces collapse", "<button id='t'>A   B</button>", "t", "A B"),
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.accessible_name import accessible_name
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    names: dict[str, str] = {}
    checks: dict[str, bool] = {}
    for label, markup, element_id, expected in _CASES:
        try:
            actual = accessible_name(markup, element_id)
        except Exception as exc:  # noqa: BLE001 - a raised name is an unmet outcome
            actual = f"error:{type(exc).__name__}:{exc}"
        names[label] = actual
        checks[label] = actual == expected
    return all(checks.values()), {"names": names, "checks": checks}


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
