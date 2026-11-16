"""Construct an HTML form entry list and its request body.

The regex field scrape in the browser session posts every named input,
including disabled controls and unchecked boxes, and it cannot see a
select, a textarea, or a control that points at the form with ``form=``.
``build_form_submission`` follows the HTML entry-list rules instead, then
encodes that list as urlencoded, multipart, and text/plain.

Output encoding matches ``serialize_html_form``: a windows-1252 label,
including the ``iso-8859-1`` alias, stays windows-1252, and every other
label is UTF-8. A static document has no selected files, so a file input
contributes one empty file entry.
"""

from __future__ import annotations

from typing import Mapping

from blackhole_agent.encoding_standard import encoding_name
from blackhole_agent.form_urlencoded import _crlf, serialize_html_form
from blackhole_agent.html5_document import parse_tree

_SUBMITTABLE = frozenset({"button", "input", "select", "textarea"})
_AUTO_DIR_TYPES = frozenset({"text", "search", "tel", "url", "email", "password"})
_URLENCODED = "application/x-www-form-urlencoded"
_MULTIPART = "multipart/form-data"
_PLAIN = "text/plain"


def build_form_submission(
    markup: str,
    *,
    form_id: str = "",
    submitter_name: str = "",
    coordinates: tuple[int, int] = (0, 0),
    overrides: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return the entry list and bodies for one form in ``markup``.

    ``submitter_name`` chooses the button. An empty name uses the first
    enabled submit button in tree order. ``overrides`` replaces a constructed
    string value, or appends a name the entry list did not contain.
    """

    if not isinstance(markup, str):
        raise TypeError("form markup must be a string")
    document = parse_tree(markup)
    parent: dict[int, object] = {}
    order: list[object] = []
    ids: dict[str, object] = {}

    def walk(node: object, owner: object | None) -> None:
        parent[id(node)] = owner
        order.append(node)
        if _local(node) and "id" in _attrib(node) and _attrib(node)["id"] not in ids:
            ids[_attrib(node)["id"]] = node
        for child in list(node):
            walk(child, node)

    walk(document, None)
    forms = [node for node in order if _local(node) == "form"]
    form = _choose_form(forms, ids, form_id)
    if form is None:
        return _fail("no-form")

    controls = [
        node
        for node in order
        if _local(node) in _SUBMITTABLE and _form_owner(node, parent, ids) is form
    ]
    submitter = _choose_submitter(controls, parent, submitter_name)
    label = _output_label(form)
    entries = _entry_list(controls, parent, submitter, label, coordinates)
    if overrides:
        entries = _apply_overrides(entries, overrides)
    pairs = _string_pairs(entries)
    urlencoded = serialize_html_form(pairs, encoding=label)
    plain = _plain_text(pairs)
    boundary, multipart = _multipart(entries, label)
    enctype = _enctype(form, submitter)
    method = _method(form, submitter)
    action = _action(form, submitter)
    if enctype == _MULTIPART:
        body = multipart
        content_type = f"{_MULTIPART}; boundary={boundary}"
    elif enctype == _PLAIN:
        body = _encode_text(plain, label)
        content_type = _PLAIN
    else:
        body = urlencoded.encode("utf-8")
        content_type = _URLENCODED
        enctype = _URLENCODED
    return {
        "ok": True,
        "error": "",
        "method": method,
        "action": action,
        "enctype": enctype,
        "encoding": label,
        "entries": entries,
        "urlencoded": urlencoded,
        "plain": plain,
        "multipart": multipart.decode("latin-1"),
        "boundary": boundary,
        "content_type": content_type,
        "body_bytes": body,
    }


def _fail(error: str) -> dict[str, object]:
    return {
        "ok": False,
        "error": error,
        "method": "",
        "action": "",
        "enctype": "",
        "encoding": "",
        "entries": [],
        "urlencoded": "",
        "plain": "",
        "multipart": "",
        "boundary": "",
        "content_type": "",
        "body_bytes": b"",
    }


def _choose_form(forms: list[object], ids: dict[str, object], form_id: str) -> object | None:
    if form_id:
        found = ids.get(form_id)
        if found is not None and _local(found) == "form":
            return found
        return None
    return forms[0] if forms else None


def _form_owner(node: object, parent: dict[int, object], ids: dict[str, object]) -> object | None:
    form_attr = _attrib(node).get("form")
    if form_attr is not None:
        found = ids.get(form_attr)
        if found is not None and _local(found) == "form":
            return found
        return None
    current = parent.get(id(node))
    while current is not None:
        if _local(current) == "form":
            return current
        current = parent.get(id(current))
    return None


def _choose_submitter(controls: list[object], parent: dict[int, object], name: str) -> object | None:
    candidates = [
        node
        for node in controls
        if _is_submit_button(node) and not _control_disabled(node, parent)
    ]
    if name:
        for node in candidates:
            if _attrib(node).get("name") == name:
                return node
        return None
    return candidates[0] if candidates else None


def _is_submit_button(node: object) -> bool:
    tag = _local(node)
    if tag == "input":
        return _input_type(node) in {"submit", "image"}
    if tag == "button":
        kind = _attrib(node).get("type", "submit").strip().lower()
        return kind in {"", "submit"}
    return False


def _is_button(node: object) -> bool:
    tag = _local(node)
    if tag == "button":
        return True
    return tag == "input" and _input_type(node) in {"submit", "image", "reset", "button"}


def _entry_list(
    controls: list[object],
    parent: dict[int, object],
    submitter: object | None,
    label: str,
    coordinates: tuple[int, int],
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for field in controls:
        if _skipped(field, parent, submitter):
            continue
        if _local(field) == "input" and _input_type(field) == "image":
            if field is not submitter:
                continue
            prefix = _attrib(field).get("name", "")
            if prefix:
                prefix += "."
            entries.append({"name": prefix + "x", "value": str(int(coordinates[0]))})
            entries.append({"name": prefix + "y", "value": str(int(coordinates[1]))})
            continue
        name = _attrib(field).get("name", "")
        if name == "":
            continue
        tag = _local(field)
        if tag == "select":
            for option in _selected_options(field):
                entries.append({"name": name, "value": _option_value(option)})
        elif tag == "input" and _input_type(field) in {"checkbox", "radio"}:
            entries.append({"name": name, "value": _attrib(field).get("value", "on")})
        elif tag == "input" and _input_type(field) == "file":
            entries.append(
                {
                    "name": name,
                    "filename": "",
                    "media_type": "application/octet-stream",
                    "body": "",
                }
            )
        elif tag == "input" and _input_type(field) == "hidden" and name.lower() == "_charset_":
            entries.append({"name": name, "value": label})
        else:
            value = _text(field) if tag == "textarea" else _attrib(field).get("value", "")
            entries.append({"name": name, "value": value})
        dirname = _attrib(field).get("dirname", "")
        if dirname and _auto_direction(field):
            entries.append({"name": dirname, "value": _direction(field, parent)})
    return entries


def _skipped(field: object, parent: dict[int, object], submitter: object | None) -> bool:
    if _has_ancestor(field, parent, "datalist"):
        return True
    if _control_disabled(field, parent):
        return True
    if _is_button(field) and field is not submitter:
        return True
    if _local(field) == "input" and _input_type(field) in {"checkbox", "radio"}:
        return "checked" not in _attrib(field)
    return False


def _control_disabled(node: object, parent: dict[int, object]) -> bool:
    if "disabled" in _attrib(node):
        return True
    current = parent.get(id(node))
    while current is not None:
        if _local(current) == "fieldset" and "disabled" in _attrib(current):
            legend = _first_legend_child(current)
            if legend is None or not _is_under(node, legend, parent):
                return True
        current = parent.get(id(current))
    return False


def _selected_options(select: object) -> list[object]:
    options = [node for node in _descendants(select) if _local(node) == "option"]
    marked = [node for node in options if "selected" in _attrib(node)]
    if not marked and "multiple" not in _attrib(select) and options:
        marked = [options[0]]
    return [node for node in marked if not _option_disabled(select, node)]


def _option_disabled(select: object, option: object) -> bool:
    if "disabled" in _attrib(option):
        return True
    for node in _descendants(select):
        if _local(node) != "optgroup" or "disabled" not in _attrib(node):
            continue
        if option in list(node):
            return True
    return False


def _option_value(option: object) -> str:
    if "value" in _attrib(option):
        return _attrib(option)["value"]
    return _text(option)


def _apply_overrides(
    entries: list[dict[str, str]],
    overrides: Mapping[str, str],
) -> list[dict[str, str]]:
    names = {entry["name"] for entry in entries}
    updated: list[dict[str, str]] = []
    for entry in entries:
        if "value" in entry and entry["name"] in overrides:
            updated.append({**entry, "value": str(overrides[entry["name"]])})
        else:
            updated.append(entry)
    for name, value in overrides.items():
        if name not in names:
            updated.append({"name": str(name), "value": str(value)})
    return updated


def _string_pairs(entries: list[dict[str, str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for entry in entries:
        if "filename" in entry:
            pairs.append((entry["name"], entry["filename"]))
        else:
            pairs.append((entry["name"], entry["value"]))
    return pairs


def _plain_text(pairs: list[tuple[str, str]]) -> str:
    lines = [f"{_crlf(name)}={_crlf(value)}\r\n" for name, value in pairs]
    return "".join(lines)


def _multipart(entries: list[dict[str, str]], label: str) -> tuple[str, bytes]:
    parts: list[bytes] = []
    for entry in entries:
        name = _escape_disposition(_encode_text(_crlf(entry["name"]), label))
        if "filename" in entry:
            filename = _escape_disposition(_encode_text(_crlf(entry["filename"]), label))
            media = entry.get("media_type", "application/octet-stream").encode("ascii", "replace")
            payload = entry.get("body", "").encode("latin-1")
            header = (
                b'Content-Disposition: form-data; name="'
                + name
                + b'"; filename="'
                + filename
                + b'"\r\nContent-Type: '
                + media
                + b"\r\n\r\n"
            )
            parts.append(header + payload)
            continue
        value = _encode_text(_crlf(entry["value"]), label)
        header = b'Content-Disposition: form-data; name="' + name + b'"\r\n\r\n'
        parts.append(header + value)
    number = 1
    blob = b"\r\n".join(parts)
    while True:
        boundary = f"----blackholeform{number:04d}"
        if boundary.encode("ascii") not in blob:
            break
        number += 1
    marker = boundary.encode("ascii")
    body = b"".join(b"--" + marker + b"\r\n" + part + b"\r\n" for part in parts)
    body += b"--" + marker + b"--\r\n"
    return boundary, body


def _escape_disposition(data: bytes) -> bytes:
    return data.replace(b"\r", b"%0D").replace(b"\n", b"%0A").replace(b'"', b"%22")


def _encode_text(text: str, label: str) -> bytes:
    codec = "cp1252" if label == "windows-1252" else "utf-8"
    encoded = bytearray()
    for char in text:
        try:
            encoded.extend(char.encode(codec))
        except UnicodeEncodeError:
            encoded.extend(f"&#{ord(char)};".encode("ascii"))
    return bytes(encoded)


def _output_label(form: object) -> str:
    raw = _attrib(form).get("accept-charset", "")
    for token in raw.split():
        name = encoding_name(token)
        if not name:
            continue
        if name == "windows-1252":
            return "windows-1252"
        return "UTF-8"
    return "UTF-8"


def _enctype(form: object, submitter: object | None) -> str:
    raw = _submitter_attr(submitter, "formenctype") or _attrib(form).get("enctype", "")
    folded = raw.strip().lower()
    if folded == _MULTIPART:
        return _MULTIPART
    if folded == _PLAIN:
        return _PLAIN
    return _URLENCODED


def _method(form: object, submitter: object | None) -> str:
    raw = _submitter_attr(submitter, "formmethod") or _attrib(form).get("method", "")
    folded = raw.strip().lower()
    if folded in {"post", "dialog"}:
        return folded
    return "get"


def _action(form: object, submitter: object | None) -> str:
    if submitter is not None and "formaction" in _attrib(submitter):
        return _attrib(submitter)["formaction"]
    return _attrib(form).get("action", "")


def _submitter_attr(submitter: object | None, name: str) -> str:
    if submitter is None:
        return ""
    return _attrib(submitter).get(name, "")


def _auto_direction(node: object) -> bool:
    tag = _local(node)
    if tag == "textarea":
        return True
    return tag == "input" and _input_type(node) in _AUTO_DIR_TYPES


def _direction(node: object, parent: dict[int, object]) -> str:
    current: object | None = node
    while current is not None:
        value = _attrib(current).get("dir", "").strip().lower()
        if value == "rtl":
            return "rtl"
        if value == "ltr":
            return "ltr"
        current = parent.get(id(current))
    return "ltr"


def _input_type(node: object) -> str:
    raw = _attrib(node).get("type", "text").strip().lower()
    return raw or "text"


def _first_legend_child(fieldset: object) -> object | None:
    for child in list(fieldset):
        if _local(child) == "legend":
            return child
    return None


def _has_ancestor(node: object, parent: dict[int, object], tag: str) -> bool:
    current = parent.get(id(node))
    while current is not None:
        if _local(current) == tag:
            return True
        current = parent.get(id(current))
    return False


def _is_under(node: object, ancestor: object, parent: dict[int, object]) -> bool:
    current = parent.get(id(node))
    while current is not None:
        if current is ancestor:
            return True
        current = parent.get(id(current))
    return False


def _descendants(node: object) -> list[object]:
    found: list[object] = []
    for child in list(node):
        found.append(child)
        found.extend(_descendants(child))
    return found


def _text(node: object) -> str:
    parts: list[str] = []
    text = getattr(node, "text", None)
    if text:
        parts.append(text)
    for child in list(node):
        parts.append(_text(child))
        tail = getattr(child, "tail", None)
        if tail:
            parts.append(tail)
    return "".join(parts)


def _attrib(node: object) -> dict[str, str]:
    raw = getattr(node, "attrib", None)
    if not raw:
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _local(node: object) -> str:
    tag = getattr(node, "tag", "")
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        tag = tag.rsplit("}", 1)[1]
    return tag.lower()
