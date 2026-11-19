"""A live HTML document with DOM event dispatch and mutation-live CSS queries."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable

from blackhole_agent.css_selectors import cascaded_element_value, matching_elements
from blackhole_agent.html5_document import parse_tree

_HTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
_TAG_NAME = re.compile(r"[A-Za-z][^\t\n\f\r />\x00]*\Z")


class Event:
    NONE = 0
    CAPTURING_PHASE = 1
    AT_TARGET = 2
    BUBBLING_PHASE = 3

    def __init__(self, event_type: str, *, bubbles: bool = False, cancelable: bool = False) -> None:
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event type must be a non-empty string")
        self.type = event_type
        self.bubbles = bool(bubbles)
        self.cancelable = bool(cancelable)
        self.target: Element | Document | None = None
        self.current_target: Element | Document | None = None
        self.event_phase = self.NONE
        self.default_prevented = False
        self._path: list[Element | Document] = []
        self._stop_propagation = False
        self._stop_immediate = False
        self._in_passive = False
        self._dispatching = False

    @property
    def cancel_bubble(self) -> bool:
        return self._stop_propagation

    @cancel_bubble.setter
    def cancel_bubble(self, value: bool) -> None:
        if value:
            self.stop_propagation()

    def composed_path(self) -> list[Element | Document]:
        return list(self._path)

    def prevent_default(self) -> None:
        if self.cancelable and not self._in_passive:
            self.default_prevented = True

    def stop_propagation(self) -> None:
        self._stop_propagation = True

    def stop_immediate_propagation(self) -> None:
        self._stop_propagation = True
        self._stop_immediate = True


@dataclass
class _Listener:
    callback: Callable[[Event], None]
    capture: bool
    once: bool
    passive: bool


class _EventTarget:
    @property
    def _event_key(self) -> object:
        raise NotImplementedError

    @property
    def _owner(self) -> Document:
        raise NotImplementedError

    def add_event_listener(
        self,
        event_type: str,
        callback: Callable[[Event], None],
        *,
        capture: bool = False,
        once: bool = False,
        passive: bool = False,
    ) -> None:
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event type must be a non-empty string")
        if not callable(callback):
            raise TypeError("event listener must be callable")
        listeners = self._owner._listeners.setdefault((self._event_key, event_type), [])
        if any(item.callback is callback and item.capture is bool(capture) for item in listeners):
            return
        listeners.append(_Listener(callback, bool(capture), bool(once), bool(passive)))

    def remove_event_listener(
        self,
        event_type: str,
        callback: Callable[[Event], None],
        *,
        capture: bool = False,
    ) -> None:
        key = (self._event_key, event_type)
        listeners = self._owner._listeners.get(key, [])
        self._owner._listeners[key] = [
            item for item in listeners if not (item.callback is callback and item.capture is bool(capture))
        ]

    def dispatch_event(self, event: Event) -> bool:
        return self._owner._dispatch(self, event)


class Document(_EventTarget):
    def __init__(self, markup: str) -> None:
        self._root = parse_tree(markup)
        self._handles: dict[object, Element] = {}
        self._listeners: dict[tuple[object, str], list[_Listener]] = {}

    @property
    def _event_key(self) -> object:
        return self

    @property
    def _owner(self) -> Document:
        return self

    @property
    def document_element(self) -> Element:
        return self._handle(self._root)

    def create_element(self, tag_name: str) -> Element:
        if not isinstance(tag_name, str) or not _TAG_NAME.fullmatch(tag_name):
            raise ValueError("invalid HTML tag name")
        return self._handle(ET.Element(f"{{{_HTML_NAMESPACE}}}{tag_name.lower()}"))

    def get_element_by_id(self, identity: str) -> Element | None:
        for raw in self._parent_map():
            if raw.get("id") == identity:
                return self._handle(raw)
        return None

    def query_selector(self, selector: str) -> Element | None:
        matches = self.query_selector_all(selector)
        return matches[0] if matches else None

    def query_selector_all(self, selector: str) -> list[Element]:
        return [self._handle(raw) for raw in matching_elements(self._root, selector)]

    def _handle(self, raw) -> Element:
        handle = self._handles.get(raw)
        if handle is None:
            handle = Element(self, raw)
            self._handles[raw] = handle
        return handle

    def _parent_map(self) -> dict[object, object | None]:
        parents: dict[object, object | None] = {self._root: None}

        def walk(raw) -> None:
            for child in list(raw):
                if not isinstance(child.tag, str):
                    continue
                parents[child] = raw
                walk(child)

        walk(self._root)
        return parents

    def _dispatch(self, target: _EventTarget, event: Event) -> bool:
        if not isinstance(event, Event):
            raise TypeError("dispatch_event requires an Event")
        if event._dispatching:
            raise RuntimeError("event is already being dispatched")
        if isinstance(target, Element):
            if target._owner is not self or target._raw not in self._parent_map():
                raise ValueError("event target is detached or belongs to another document")
            parents = self._parent_map()
            raw_path = [target._raw]
            while parents[raw_path[-1]] is not None:
                raw_path.append(parents[raw_path[-1]])
            path: list[_EventTarget] = [*(self._handle(raw) for raw in raw_path), self]
        elif target is self:
            path = [self]
        else:
            raise ValueError("event target belongs to another document")

        event.target = target  # type: ignore[assignment]
        event._path = [item if item is self else item for item in path]  # type: ignore[misc]
        event._stop_propagation = False
        event._stop_immediate = False
        event._dispatching = True
        try:
            for current in reversed(path[1:]):
                if event._stop_propagation:
                    break
                self._invoke(current, event, Event.CAPTURING_PHASE, capture=True)
            if not event._stop_propagation:
                self._invoke(target, event, Event.AT_TARGET, capture=None)
            if event.bubbles and not event._stop_propagation:
                for current in path[1:]:
                    if event._stop_propagation:
                        break
                    self._invoke(current, event, Event.BUBBLING_PHASE, capture=False)
        finally:
            event.current_target = None
            event.event_phase = Event.NONE
            event._in_passive = False
            event._dispatching = False
        return not event.default_prevented

    def _invoke(self, target: _EventTarget, event: Event, phase: int, *, capture: bool | None) -> None:
        listeners = list(self._listeners.get((target._event_key, event.type), []))
        event.current_target = target  # type: ignore[assignment]
        event.event_phase = phase
        event._stop_immediate = False
        for listener in listeners:
            if capture is not None and listener.capture is not capture:
                continue
            active = self._listeners.get((target._event_key, event.type), [])
            if not any(item is listener for item in active):
                continue
            if listener.once:
                active.remove(listener)
            event._in_passive = listener.passive
            listener.callback(event)
            event._in_passive = False
            if event._stop_immediate:
                break


class Element(_EventTarget):
    def __init__(self, owner: Document, raw) -> None:
        self._owner_document = owner
        self._raw = raw

    @property
    def _event_key(self) -> object:
        return self._raw

    @property
    def _owner(self) -> Document:
        return self._owner_document

    @property
    def tag_name(self) -> str:
        return self._raw.tag.split("}", 1)[-1].upper()

    @property
    def id(self) -> str:
        return self._raw.get("id", "")

    @id.setter
    def id(self, value: str) -> None:
        self.set_attribute("id", value)

    @property
    def parent_element(self) -> Element | None:
        parent = self._owner._parent_map().get(self._raw)
        return self._owner._handle(parent) if parent is not None else None

    @property
    def children(self) -> list[Element]:
        return [self._owner._handle(raw) for raw in list(self._raw) if isinstance(raw.tag, str)]

    @property
    def text_content(self) -> str:
        return "".join(self._raw.itertext())

    def get_attribute(self, name: str) -> str | None:
        return self._raw.get(name)

    def set_attribute(self, name: str, value: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("attribute name must be non-empty")
        self._raw.set(name, str(value))

    def remove_attribute(self, name: str) -> None:
        self._raw.attrib.pop(name, None)

    def append(self, child: Element) -> Element:
        if not isinstance(child, Element) or child._owner is not self._owner:
            raise ValueError("child belongs to another document")
        ancestor = self
        while ancestor is not None:
            if ancestor is child:
                raise ValueError("append would create a cycle")
            ancestor = ancestor.parent_element
        parent = child._owner._parent_map().get(child._raw)
        if parent is not None:
            parent.remove(child._raw)
        self._raw.append(child._raw)
        return child

    def remove(self) -> None:
        parent = self._owner._parent_map().get(self._raw)
        if parent is not None:
            parent.remove(self._raw)

    def query_selector(self, selector: str) -> Element | None:
        matches = self.query_selector_all(selector)
        return matches[0] if matches else None

    def query_selector_all(self, selector: str) -> list[Element]:
        return [
            element
            for element in self._owner.query_selector_all(selector)
            if element is not self and self._contains(element)
        ]

    def computed_style(self, property_name: str, stylesheet: str, *, media: dict | None = None) -> str:
        return cascaded_element_value(self._owner._root, self._raw, stylesheet, property_name, media=media)

    def _contains(self, other: Element) -> bool:
        current: Element | None = other
        while current is not None:
            if current is self:
                return True
            current = current.parent_element
        return False
