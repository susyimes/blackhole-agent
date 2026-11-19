"""Dispatch DOM events and restyle mutated elements in one live HTML tree."""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.dom_runtime import Document, Event
    except Exception as exc:  # noqa: BLE001 - a tree without the live DOM still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []
    doc = Document(
        "<!doctype html><main id=root><section id=panel class=card>"
        "<button id=go class=action>Go</button></section></main>"
    )
    root = doc.get_element_by_id("root")
    panel = doc.get_element_by_id("panel")
    go = doc.get_element_by_id("go")
    checks.extend([root is not None, panel is not None, go is not None])
    if root is None or panel is None or go is None:
        return False, {"error": "fixture elements were not parsed", "checks": checks}

    calls: list[str] = []
    doc.add_event_listener("click", lambda _event: calls.append("document:capture"), capture=True)
    doc.add_event_listener("click", lambda _event: calls.append("document:bubble"))
    root.add_event_listener("click", lambda _event: calls.append("root:capture"), capture=True)
    root.add_event_listener("click", lambda _event: calls.append("root:bubble"))
    panel.add_event_listener("click", lambda _event: calls.append("panel:capture"), capture=True)
    panel.add_event_listener("click", lambda _event: calls.append("panel:bubble"))
    go.add_event_listener("click", lambda _event: calls.append("target:capture"), capture=True)
    go.add_event_listener("click", lambda _event: calls.append("target:bubble"))
    panel.add_event_listener("click", lambda event: event.prevent_default())
    click = Event("click", bubbles=True, cancelable=True)
    not_canceled = go.dispatch_event(click)
    expected_order = [
        "document:capture",
        "root:capture",
        "panel:capture",
        "target:capture",
        "target:bubble",
        "panel:bubble",
        "root:bubble",
        "document:bubble",
    ]
    observed["event_order"] = calls
    observed["dispatch_return"] = not_canceled
    observed["default_prevented"] = click.default_prevented
    observed["composed_path"] = [
        "document" if item is doc else item.id or item.tag_name.lower() for item in click.composed_path()
    ]
    checks.extend(
        [
            calls == expected_order,
            not_canceled is False,
            click.default_prevented is True,
            click.composed_path() == [go, panel, root, root.parent_element, doc.document_element, doc],
            click.current_target is None,
            click.event_phase == Event.NONE,
        ]
    )

    stopped: list[str] = []
    root.add_event_listener("halt", lambda event: (stopped.append("first"), event.stop_immediate_propagation()), capture=True)
    root.add_event_listener("halt", lambda _event: stopped.append("second"), capture=True)
    go.add_event_listener("halt", lambda _event: stopped.append("target"))
    go.dispatch_event(Event("halt", bubbles=True))
    observed["stop_immediate"] = stopped
    checks.append(stopped == ["first"])

    once_calls: list[str] = []
    go.add_event_listener("once", lambda _event: once_calls.append("called"), once=True)
    go.dispatch_event(Event("once"))
    go.dispatch_event(Event("once"))
    passive = Event("passive", cancelable=True)
    go.add_event_listener("passive", lambda event: event.prevent_default(), passive=True)
    passive_return = go.dispatch_event(passive)
    observed["once_calls"] = once_calls
    observed["passive_default_prevented"] = passive.default_prevented
    checks.extend([once_calls == ["called"], passive_return is True, passive.default_prevented is False])

    stylesheet = ".card .action { color: red } .card.selected .action { color: green }"
    initial_color = go.computed_style("color", stylesheet)
    panel.set_attribute("class", "card selected")
    mutated_color = go.computed_style("color", stylesheet)
    note = doc.create_element("aside")
    note.id = "note"
    note.set_attribute("class", "action")
    panel.append(note)
    inserted_matches = [element.id for element in doc.query_selector_all(".card > .action")]
    inserted_color = note.computed_style("color", stylesheet)
    root.append(note)
    moved_panel_matches = [element.id for element in doc.query_selector_all(".card > .action")]
    moved_root_matches = [element.id for element in doc.query_selector_all("#root > .action")]
    go.remove()
    observed["styles"] = {"initial": initial_color, "mutated": mutated_color, "inserted": inserted_color}
    observed["mutation_matches"] = {
        "inserted": inserted_matches,
        "moved_panel": moved_panel_matches,
        "moved_root": moved_root_matches,
        "removed_go_absent": doc.get_element_by_id("go") is None,
    }
    checks.extend(
        [
            initial_color == "red",
            mutated_color == "green",
            inserted_color == "green",
            inserted_matches == ["go", "note"],
            moved_panel_matches == ["go"],
            moved_root_matches == ["note"],
            doc.get_element_by_id("go") is None,
            doc.query_selector("button") is None,
        ]
    )
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
