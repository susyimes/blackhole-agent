"""An HTML form submits the entry list, not every named input.

A disabled control and an unchecked checkbox stay out. A select submits the
selected option, and a select with no selected attribute submits its first
option. A textarea newline stays a line feed in the entry list and becomes
percent-encoded CRLF in the urlencoded body. The clicked submitter is the
only button. multipart/form-data frames the same entries and omits the
dropped controls. An iso-8859-1 accept-charset is windows-1252, so a euro
sign is byte 0x80.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the constructor is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

MARKUP = """
<form id="pay" action="/pay" method="post" enctype="multipart/form-data" accept-charset="iso-8859-1">
  <input name="secret" value="nope" disabled>
  <fieldset disabled>
    <input name="buried" value="no">
    <legend><input name="legend" value="yes"></legend>
  </fieldset>
  <input type="checkbox" name="extra" value="1">
  <input type="checkbox" name="keep" checked>
  <select name="color">
    <option value="alpha">A</option>
    <option value="beta" selected>B</option>
  </select>
  <select name="plainpick"><option>alpha</option><option>beta</option></select>
  <select name="topping" multiple>
    <option value="a" selected>A</option>
    <option value="b">B</option>
    <option value="c" selected>C</option>
    <option value="d" selected disabled>D</option>
  </select>
  <textarea name="note">line1
line2</textarea>
  <input name="price" value="€">
  <input name="comment" dirname="comment.dir" value="hi">
  <input type="hidden" name="_charset_" value="nope">
  <input type="file" name="upload">
  <button name="other" value="no" type="submit">Other</button>
  <button name="go" value="send" type="submit">Send</button>
</form>
<input form="pay" name="outside" value="in">
<datalist id="hints"><input name="hint" value="hidden"></datalist>
"""


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.html_form_submission import build_form_submission
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        result = build_form_submission(MARKUP, form_id="pay", submitter_name="go")
    except Exception as exc:  # noqa: BLE001 - a broken constructor is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    entries = result.get("entries")
    rows = [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []
    names = [item.get("name") for item in rows]
    pairs = [(item.get("name"), item.get("value")) for item in rows if "value" in item]
    note = next((value for name, value in pairs if name == "note"), "")
    multipart = str(result.get("multipart") or "")
    urlencoded = str(result.get("urlencoded") or "")
    observed = {
        "ok": result.get("ok"),
        "encoding": result.get("encoding"),
        "enctype": result.get("enctype"),
        "names": names,
        "note": note,
        "pairs": pairs,
        "urlencoded": urlencoded,
        "plain": result.get("plain"),
        "multipart_has_color": 'name="color"' in multipart and "\r\n\r\nbeta\r\n" in multipart,
        "multipart_omits_secret": 'name="secret"' not in multipart and 'name="extra"' not in multipart,
        "multipart_euro": "\u0080" in multipart,
        "charset_pair": next((value for name, value in pairs if name == "_charset_"), ""),
    }
    passed = (
        observed["ok"] is True
        and observed["encoding"] == "windows-1252"
        and observed["enctype"] == "multipart/form-data"
        and names == [
            "legend",
            "keep",
            "color",
            "plainpick",
            "topping",
            "topping",
            "note",
            "price",
            "comment",
            "comment.dir",
            "_charset_",
            "upload",
            "go",
            "outside",
        ]
        and pairs[names.index("color")] == ("color", "beta")
        and pairs[names.index("plainpick")] == ("plainpick", "alpha")
        and [value for name, value in pairs if name == "topping"] == ["a", "c"]
        and note == "line1\nline2"
        and ("secret", "nope") not in pairs
        and ("extra", "1") not in pairs
        and ("buried", "no") not in pairs
        and ("other", "no") not in pairs
        and ("go", "send") in pairs
        and ("legend", "yes") in pairs
        and ("keep", "on") in pairs
        and ("outside", "in") in pairs
        and ("comment.dir", "ltr") in pairs
        and observed["charset_pair"] == "windows-1252"
        and "note=line1%0D%0Aline2" in urlencoded
        and "price=%80" in urlencoded
        and observed["multipart_has_color"] is True
        and observed["multipart_omits_secret"] is True
        and observed["multipart_euro"] is True
        and str(observed["plain"]).count("\r\n") >= 2
    )
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
