from __future__ import annotations

from blackhole_agent.dom_runtime import Document, Event


def document() -> Document:
    return Document(
        "<!doctype html><main id=root><section id=panel class=card>"
        "<button id=go class=action>Go</button></section></main>"
    )


def test_event_path_captures_targets_and_bubbles_in_order() -> None:
    doc = document()
    root = doc.get_element_by_id("root")
    panel = doc.get_element_by_id("panel")
    go = doc.get_element_by_id("go")
    assert root and panel and go
    calls: list[tuple[str, int, object]] = []
    for name, target in [("document", doc), ("root", root), ("panel", panel), ("go", go)]:
        target.add_event_listener("click", lambda event, name=name: calls.append((name, event.event_phase, event.current_target)), capture=True)
        target.add_event_listener("click", lambda event, name=name: calls.append((name, event.event_phase, event.current_target)))

    event = Event("click", bubbles=True, cancelable=True)
    panel.add_event_listener("click", lambda event: event.prevent_default())

    assert go.dispatch_event(event) is False
    assert event.default_prevented is True
    assert [name for name, _phase, _target in calls] == [
        "document",
        "root",
        "panel",
        "go",
        "go",
        "panel",
        "root",
        "document",
    ]
    assert [phase for _name, phase, _target in calls[:4]] == [1, 1, 1, 2]
    assert event.composed_path() == [go, panel, root, root.parent_element, doc.document_element, doc]
    assert event.current_target is None
    assert event.event_phase == Event.NONE


def test_non_bubbling_event_still_captures() -> None:
    doc = document()
    panel = doc.get_element_by_id("panel")
    go = doc.get_element_by_id("go")
    assert panel and go
    calls: list[str] = []
    doc.add_event_listener("ping", lambda _event: calls.append("capture"), capture=True)
    panel.add_event_listener("ping", lambda _event: calls.append("bubble"))

    assert go.dispatch_event(Event("ping")) is True
    assert calls == ["capture"]


def test_stop_propagation_preserves_current_target_listeners() -> None:
    doc = document()
    root = doc.get_element_by_id("root")
    go = doc.get_element_by_id("go")
    assert root and go
    calls: list[str] = []
    root.add_event_listener("click", lambda event: (calls.append("first"), event.stop_propagation()), capture=True)
    root.add_event_listener("click", lambda _event: calls.append("second"), capture=True)
    go.add_event_listener("click", lambda _event: calls.append("target"))

    go.dispatch_event(Event("click", bubbles=True))
    assert calls == ["first", "second"]


def test_stop_immediate_propagation_skips_remaining_listeners() -> None:
    doc = document()
    go = doc.get_element_by_id("go")
    assert go
    calls: list[str] = []
    go.add_event_listener("click", lambda event: (calls.append("first"), event.stop_immediate_propagation()))
    go.add_event_listener("click", lambda _event: calls.append("second"))

    go.dispatch_event(Event("click"))
    assert calls == ["first"]


def test_once_deduplication_removal_and_passive_cancellation() -> None:
    doc = document()
    go = doc.get_element_by_id("go")
    assert go
    calls: list[str] = []

    def once(_event: Event) -> None:
        calls.append("once")

    def passive(event: Event) -> None:
        event.prevent_default()

    go.add_event_listener("click", once, once=True)
    go.add_event_listener("click", once, once=True, passive=True)
    go.add_event_listener("click", passive, passive=True)
    event = Event("click", cancelable=True)
    assert go.dispatch_event(event) is True
    assert go.dispatch_event(Event("click", cancelable=True)) is True
    assert calls == ["once"]
    assert event.default_prevented is False

    go.remove_event_listener("click", passive)
    go.add_event_listener("click", passive)
    assert go.dispatch_event(Event("click", cancelable=True)) is False


def test_mutations_are_live_for_selectors_and_the_cascade() -> None:
    doc = document()
    root = doc.get_element_by_id("root")
    panel = doc.get_element_by_id("panel")
    go = doc.get_element_by_id("go")
    assert root and panel and go
    stylesheet = ".card .action { color: red } .card.selected .action { color: green }"
    assert go.computed_style("color", stylesheet) == "red"

    panel.set_attribute("class", "card selected")
    note = doc.create_element("aside")
    note.id = "note"
    note.set_attribute("class", "action")
    panel.append(note)

    assert go.computed_style("color", stylesheet) == "green"
    assert note.computed_style("color", stylesheet) == "green"
    assert doc.query_selector_all(".card > .action") == [go, note]
    assert panel.query_selector_all(".card") == []
    assert panel.query_selector_all(".card .action") == [go, note]

    root.append(note)
    assert doc.query_selector_all(".card > .action") == [go]
    assert doc.query_selector_all("#root > .action") == [note]
    go.remove()
    assert doc.get_element_by_id("go") is None
    assert doc.query_selector("button") is None
