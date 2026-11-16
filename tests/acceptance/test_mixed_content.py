"""Subresource loads are upgraded or blocked as mixed content.

An https document rewrites an http image to https and blocks an http script.
An http image whose host is an IP address is not rewritten and is blocked.
Loopback script stays on http and is allowed. An http document framed by
https blocks an http script, while a top-level data document allows it.
An https request whose response URL is http is blocked after the request
was allowed. A worker does not inherit an https ancestor.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the checker is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.mixed_content import load_mixed_content
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    page = "https://secure.example/index.html"
    try:
        image = load_mixed_content(page, r"http://cdn.example\a.png", destination="image")
        audio = load_mixed_content(page, "http://cdn.example:8080/a.mp3", destination="audio")
        script = load_mixed_content(page, "http://cdn.example/app.js", destination="script")
        ip_image = load_mixed_content(page, "http://8.8.8.8/a.png", destination="image")
        imageset = load_mixed_content(
            page,
            "http://cdn.example/a.png",
            destination="image",
            initiator="imageset",
        )
        loopback = load_mixed_content(page, "http://127.1/app.js", destination="script")
        mapped = load_mixed_content(page, "http://[::ffff:127.0.0.1]/app.js", destination="script")
        local_name = load_mixed_content(page, "http://foo.localhost/app.js", destination="script")
        local_page = load_mixed_content(
            "http://localhost/home",
            "http://evil.example/app.js",
            destination="script",
        )
        framed = load_mixed_content(
            "http://a.example/",
            "http://evil.example/app.js",
            destination="script",
            ancestors=("https://b.example/",),
        )
        data_top = load_mixed_content(
            "data:text/html,hi",
            "http://evil.example/app.js",
            destination="script",
        )
        data_framed = load_mixed_content(
            "data:text/html,hi",
            "http://evil.example/app.js",
            destination="script",
            ancestors=("https://a.example/",),
        )
        navigation = load_mixed_content(
            page,
            "http://evil.example/",
            destination="document",
            parent=False,
        )
        frame_nav = load_mixed_content(
            page,
            "http://evil.example/",
            destination="document",
            parent=True,
        )
        redirect = load_mixed_content(
            page,
            "https://cdn.example/a.png",
            destination="image",
            response_url="http://cdn.example/a.png",
        )
        worker = load_mixed_content(
            "http://a.example/",
            "http://evil.example/app.js",
            destination="script",
            ancestors=("https://b.example/",),
            kind="worker",
        )
        plain = load_mixed_content(
            "http://a.example/",
            "http://evil.example/app.js",
            destination="script",
        )
    except Exception as exc:  # noqa: BLE001 - a broken checker is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed = {
        "image": image,
        "audio": audio,
        "script": script,
        "ip_image": ip_image,
        "imageset": imageset,
        "loopback": loopback,
        "mapped": mapped,
        "local_name": local_name,
        "local_page": local_page,
        "framed": framed,
        "data_top": data_top,
        "data_framed": data_framed,
        "navigation": navigation,
        "frame_nav": frame_nav,
        "redirect": redirect,
        "worker": worker,
        "plain": plain,
    }
    passed = (
        image["request"] == "allowed"
        and image["upgraded"] is True
        and image["url"] == "https://cdn.example/a.png"
        and image["prohibits"] is True
        and audio["upgraded"] is True
        and audio["url"] == "https://cdn.example:8080/a.mp3"
        and audio["request"] == "allowed"
        and script["request"] == "blocked"
        and script["upgraded"] is False
        and script["url"] == "http://cdn.example/app.js"
        and ip_image["request"] == "blocked"
        and ip_image["upgraded"] is False
        and ip_image["url"] == "http://8.8.8.8/a.png"
        and imageset["request"] == "blocked"
        and imageset["upgraded"] is False
        and loopback["request"] == "allowed"
        and loopback["upgraded"] is False
        and loopback["url"] == "http://127.0.0.1/app.js"
        and mapped["request"] == "blocked"
        and mapped["upgraded"] is False
        and local_name["request"] == "allowed"
        and local_page["request"] == "blocked"
        and local_page["prohibits"] is True
        and framed["request"] == "blocked"
        and framed["prohibits"] is True
        and data_top["request"] == "allowed"
        and data_top["prohibits"] is False
        and data_framed["request"] == "blocked"
        and data_framed["prohibits"] is True
        and navigation["request"] == "allowed"
        and frame_nav["request"] == "blocked"
        and redirect["request"] == "allowed"
        and redirect["upgraded"] is False
        and redirect["response"] == "blocked"
        and worker["request"] == "allowed"
        and worker["prohibits"] is False
        and plain["request"] == "allowed"
        and plain["prohibits"] is False
    )
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
