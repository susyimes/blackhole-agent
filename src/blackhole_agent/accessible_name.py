"""Compute an accessible name from a document fragment.

Accname 1.2 chooses the name. HTML-AAM supplies the host-language steps for
the elements handled here. A hidden element contributes only when an
``aria-labelledby`` reference or a ``label`` traversal directly includes it.
An ``img`` with an empty ``alt`` does not fall through to ``title`` or to a
``figcaption``. A text control uses its label before ``title``, and ``title``
before ``placeholder``.

Shadow trees, CSS pseudo-elements, and author stylesheets are outside this
computation. Hidden means the ``hidden`` attribute, ``aria-hidden="true"``,
or an inline style of ``display: none``, ``visibility: hidden``,
``visibility: collapse``, or ``content-visibility: hidden``, on the element
or an ancestor. ``script``, ``style``, and ``template`` are hidden. Missing
submit and reset labels use the English strings ``Submit`` and ``Reset``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blackhole_agent.html5_document import parse_tree

_CONTENT_OWNERS = frozenset(
    {
        "a",
        "caption",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "label",
        "legend",
        "option",
        "summary",
    }
)
_LABELABLE = frozenset({"button", "meter", "output", "progress", "select", "textarea"})
_PROHIBITED = frozenset(
    {
        "caption",
        "code",
        "deletion",
        "emphasis",
        "generic",
        "insertion",
        "mark",
        "none",
        "paragraph",
        "presentation",
        "strong",
        "subscript",
        "suggestion",
        "superscript",
        "term",
        "time",
    }
)
_TEXT_INPUTS = frozenset({"email", "number", "password", "search", "tel", "text", "url"})
_SKIPPED = frozenset({"script", "style", "template"})
_WHITESPACE = "\t\n\f\r "


@dataclass
class _Doc:
    ids: dict[str, object]
    parents: dict[int, object]
    elements: list[object]
    stack: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class _Flags:
    referenced: bool = False
    in_labelledby: bool = False
    in_content: bool = False
    allow_hidden: bool = False
    user_root: bool = False
    skip: object | None = None


def accessible_name(markup: str, element_id: str) -> str:
    """Return the flat accessible name of the element with ``element_id``.

    A missing id returns an empty string. The root is hidden unless a caller
    reached it through ``aria-labelledby`` or a label, so asking for a hidden
    element directly returns an empty string.
    """

    if not isinstance(markup, str) or not isinstance(element_id, str):
        raise TypeError("markup and element_id must be strings")
    if not element_id:
        return ""
    document = _Doc(ids={}, parents={}, elements=[])
    _index(parse_tree(markup), None, document)
    target = document.ids.get(element_id)
    if target is None:
        return ""
    return _alternative(target, document, _Flags(user_root=True))


def _index(node: object, parent: object | None, document: _Doc) -> None:
    document.parents[id(node)] = parent
    if _is_element(node):
        document.elements.append(node)
        element_id = _attrib(node).get("id")
        if element_id and element_id not in document.ids:
            document.ids[element_id] = node
    for child in list(node):
        _index(child, node, document)


def _alternative(node: object, document: _Doc, flags: _Flags) -> str:
    if id(node) in document.stack:
        return ""
    document.stack.add(id(node))
    try:
        return _compute(node, document, flags)
    finally:
        document.stack.discard(id(node))


def _compute(node: object, document: _Doc, flags: _Flags) -> str:
    if flags.skip is not None and node is flags.skip:
        return ""
    if not _is_element(node):
        return ""
    if not flags.allow_hidden and _hidden(node, document):
        return ""
    if flags.user_root and _explicit_role(node) in _PROHIBITED:
        return ""
    if _local(node) == "br":
        return "\n"

    if not flags.in_labelledby:
        labelled = _labelledby(node, document, flags)
        if labelled:
            return labelled

    if flags.in_content and node is not flags.skip and _embedded_kind(node):
        return _flat(_embedded_value(node))

    aria = _flat(_attrib(node).get("aria-label", ""))
    if aria and not (flags.in_content and _embedded_kind(node)):
        return aria

    handled, host = _host(node, document, flags)
    if handled:
        return host
    if flags.referenced or flags.in_content or _local(node) in _CONTENT_OWNERS:
        content = _content(node, document, flags)
        if content:
            return content
    return _flat(_attrib(node).get("title", ""))


def _labelledby(node: object, document: _Doc, flags: _Flags) -> str:
    refs = _idrefs(node, document, "aria-labelledby")
    if not refs:
        return ""
    parts: list[str] = []
    for target in refs:
        child = _Flags(
            referenced=True,
            in_labelledby=True,
            allow_hidden=_hidden(target, document),
            skip=flags.skip,
        )
        if target is node:
            document.stack.discard(id(node))
            try:
                parts.append(_alternative(node, document, child))
            finally:
                document.stack.add(id(node))
        else:
            parts.append(_alternative(target, document, child))
    return _flat(" ".join(part for part in parts if part))


def _host(node: object, document: _Doc, flags: _Flags) -> tuple[bool, str]:
    local = _local(node)
    if local == "img":
        return True, _img_name(node, document, flags)
    if local == "input":
        return True, _input_name(node, document, flags)
    if local == "textarea":
        return True, _text_control_name(node, document, flags)
    if local == "select":
        return True, _label_or_title(node, document, flags)
    if local == "button":
        labelled = _labels_text(node, document, flags)
        if labelled:
            return True, labelled
        body = _content(node, document, flags)
        if body:
            return True, body
        return False, ""
    if local == "fieldset":
        return _subtree_or_title(node, document, flags, "legend")
    if local == "table":
        return _subtree_or_title(node, document, flags, "caption")
    if local == "output":
        labelled = _labels_text(node, document, flags)
        if labelled:
            return True, labelled
        return False, ""
    if local == "area":
        alt = _attrib(node).get("alt")
        if alt is not None and _flat(alt):
            return True, _flat(alt)
        return False, ""
    return False, ""


def _img_name(node: object, document: _Doc, flags: _Flags) -> str:
    attrs = _attrib(node)
    if "alt" in attrs:
        return _flat(attrs["alt"])
    title = _flat(attrs.get("title", ""))
    if title:
        return title
    caption = _figure_caption(node, document, flags)
    return caption or ""


def _input_name(node: object, document: _Doc, flags: _Flags) -> str:
    labelled = _labels_text(node, document, flags)
    if labelled:
        return labelled
    kind = _input_type(node)
    attrs = _attrib(node)
    if kind == "image":
        alt = _flat(attrs.get("alt", "")) if "alt" in attrs else ""
        if alt:
            return alt
        title = _flat(attrs.get("title", ""))
        return title or "Submit"
    if kind in {"submit", "reset", "button"}:
        value = _flat(attrs["value"]) if "value" in attrs else ""
        if value:
            return value
        if kind == "submit" and "value" not in attrs:
            return "Submit"
        if kind == "reset" and "value" not in attrs:
            return "Reset"
        return _flat(attrs.get("title", ""))
    if kind in _TEXT_INPUTS:
        return _text_control_name(node, document, flags, labelled_already=True)
    return _flat(attrs.get("title", ""))


def _text_control_name(
    node: object,
    document: _Doc,
    flags: _Flags,
    *,
    labelled_already: bool = False,
) -> str:
    if not labelled_already:
        labelled = _labels_text(node, document, flags)
        if labelled:
            return labelled
    attrs = _attrib(node)
    title = _flat(attrs.get("title", ""))
    if title:
        return title
    placeholder = _flat(attrs.get("placeholder", ""))
    if placeholder:
        return placeholder
    return _flat(attrs.get("aria-placeholder", ""))


def _label_or_title(node: object, document: _Doc, flags: _Flags) -> str:
    labelled = _labels_text(node, document, flags)
    if labelled:
        return labelled
    return _flat(_attrib(node).get("title", ""))


def _subtree_or_title(
    node: object,
    document: _Doc,
    flags: _Flags,
    child_name: str,
) -> tuple[bool, str]:
    for child in _element_children(node):
        if _local(child) != child_name:
            continue
        text = _content(child, document, flags)
        if text:
            return True, text
        break
    return False, ""


def _figure_caption(img: object, document: _Doc, flags: _Flags) -> str:
    figure = _ancestor(img, document, "figure")
    if figure is None or not _sole_figure_image(figure, img):
        return ""
    for child in _element_children(figure):
        if _local(child) == "figcaption":
            return _content(child, document, flags)
    return ""


def _sole_figure_image(figure: object, img: object) -> bool:
    if _significant(_text_of(figure)):
        return False
    captions = 0
    for child in list(figure):
        tail = getattr(child, "tail", None) or ""
        if _significant(tail):
            return False
        if not _is_element(child):
            continue
        if child is img:
            continue
        if _local(child) == "figcaption":
            captions += 1
            continue
        return False
    return captions > 0


def _labels_text(control: object, document: _Doc, flags: _Flags) -> str:
    control_id = _attrib(control).get("id", "")
    parts: list[str] = []
    for node in document.elements:
        if _local(node) != "label":
            continue
        attrs = _attrib(node)
        if "for" in attrs:
            matched = bool(control_id) and attrs["for"] == control_id
        else:
            matched = _first_labelable(node) is control
        if not matched:
            continue
        parts.append(
            _content(
                node,
                document,
                _Flags(
                    in_content=True,
                    allow_hidden=flags.allow_hidden or _hidden(node, document),
                    skip=control,
                ),
            )
        )
    return _flat(" ".join(part for part in parts if part))


def _content(node: object, document: _Doc, flags: _Flags) -> str:
    parts: list[str] = []
    opening = _text_of(node)
    if opening:
        parts.append(opening)
    child_flags = _Flags(
        in_content=True,
        allow_hidden=flags.allow_hidden,
        skip=flags.skip,
    )
    for child in list(node):
        tail = getattr(child, "tail", None) or ""
        if _is_element(child):
            parts.append(_alternative(child, document, child_flags))
        if tail:
            parts.append(tail)
    return _flat("".join(parts))


def _embedded_kind(node: object) -> str:
    role = _explicit_role(node)
    if role in {"combobox", "listbox", "slider", "spinbutton", "textbox"}:
        return role
    local = _local(node)
    if local == "textarea":
        return "textbox"
    if local == "select":
        return "listbox" if "multiple" in _attrib(node) else "combobox"
    if local == "input":
        kind = _input_type(node)
        if kind == "range":
            return "slider"
        if kind in _TEXT_INPUTS:
            return "textbox"
    return ""


def _embedded_value(node: object) -> str:
    kind = _embedded_kind(node)
    attrs = _attrib(node)
    if kind == "textbox":
        if _local(node) == "input":
            return attrs.get("value", "")
        return _raw_text(node)
    if kind in {"combobox", "listbox"}:
        chosen = _chosen_options(node)
        return " ".join(_raw_text(option) for option in chosen)
    if attrs.get("aria-valuetext", "").strip():
        return attrs["aria-valuetext"]
    if "aria-valuenow" in attrs:
        return attrs["aria-valuenow"]
    if _local(node) == "input":
        return attrs.get("value", "")
    return _raw_text(node)


def _chosen_options(select: object) -> list[object]:
    options = [node for node in _descendants(select) if _local(node) == "option"]
    selected = [node for node in options if "selected" in _attrib(node)]
    if selected:
        return selected
    if options and "multiple" not in _attrib(select):
        return [options[0]]
    return []


def _first_labelable(node: object) -> object | None:
    for child in _element_children(node):
        if _labelable(child):
            return child
        found = _first_labelable(child)
        if found is not None:
            return found
    return None


def _labelable(node: object) -> bool:
    local = _local(node)
    if local == "input":
        return _input_type(node) != "hidden"
    return local in _LABELABLE


def _hidden(node: object, document: _Doc) -> bool:
    current: object | None = node
    while current is not None:
        if _self_hidden(current):
            return True
        current = document.parents.get(id(current))
    return False


def _self_hidden(node: object) -> bool:
    if not _is_element(node):
        return False
    if _local(node) in _SKIPPED:
        return True
    attrs = _attrib(node)
    if "hidden" in attrs:
        return True
    if attrs.get("aria-hidden", "").strip().lower() == "true":
        return True
    return _style_hides(attrs.get("style", ""))


def _style_hides(style: str) -> bool:
    for chunk in style.split(";"):
        if ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        property_name = name.strip().lower()
        property_value = value.split("!", 1)[0].strip().lower()
        if property_name == "display" and property_value == "none":
            return True
        if property_name == "visibility" and property_value in {"hidden", "collapse"}:
            return True
        if property_name == "content-visibility" and property_value == "hidden":
            return True
    return False


def _idrefs(node: object, document: _Doc, attribute: str) -> list[object]:
    raw = _attrib(node).get(attribute, "")
    found: list[object] = []
    for token in raw.split():
        target = document.ids.get(token)
        if target is not None and target not in found:
            found.append(target)
    return found


def _ancestor(node: object, document: _Doc, local: str) -> object | None:
    current = document.parents.get(id(node))
    while current is not None:
        if _local(current) == local:
            return current
        current = document.parents.get(id(current))
    return None


def _descendants(node: object) -> list[object]:
    found: list[object] = []
    for child in _element_children(node):
        found.append(child)
        found.extend(_descendants(child))
    return found


def _raw_text(node: object) -> str:
    parts: list[str] = []
    opening = _text_of(node)
    if opening:
        parts.append(opening)
    for child in list(node):
        tail = getattr(child, "tail", None) or ""
        if _is_element(child) and _local(child) not in _SKIPPED:
            parts.append(_raw_text(child))
        if tail:
            parts.append(tail)
    return "".join(parts)


def _element_children(node: object) -> list[object]:
    return [child for child in list(node) if _is_element(child)]


def _explicit_role(node: object) -> str:
    tokens = _attrib(node).get("role", "").split()
    return tokens[0].lower() if tokens else ""


def _input_type(node: object) -> str:
    raw = _attrib(node).get("type", "text").strip().lower()
    return raw or "text"


def _local(node: object) -> str:
    tag = getattr(node, "tag", "")
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        tag = tag.rsplit("}", 1)[1]
    return tag.lower()


def _attrib(node: object) -> dict[str, str]:
    raw = getattr(node, "attrib", None)
    if not raw:
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key)
        if "}" in name:
            name = name.rsplit("}", 1)[1]
        result[name.lower()] = str(value)
    return result


def _text_of(node: object) -> str:
    text = getattr(node, "text", None)
    return text if isinstance(text, str) else ""


def _is_element(node: object) -> bool:
    return isinstance(getattr(node, "tag", None), str)


def _significant(value: str) -> bool:
    return bool(value.strip(_WHITESPACE))


def _flat(value: str) -> str:
    collapsed = []
    pending = False
    for character in value:
        if character in _WHITESPACE:
            pending = True
            continue
        if pending and collapsed:
            collapsed.append(" ")
        pending = False
        collapsed.append(character)
    return "".join(collapsed)
