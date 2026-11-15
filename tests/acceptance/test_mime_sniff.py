"""Computed media type from resource bytes, not from the label alone.

PNG bytes labeled image/gif become image/png. The same bytes labeled
text/html or image/svg+xml keep that label. An exact text/plain label on
those bytes becomes application/octet-stream, and nosniff keeps text/plain.
A lowercase utf-8 parameter is not that Apache label, so the label stays.
A script tag with no label is text/html, and nosniff makes it text/plain.
An octet-stream label is not sniffed into an image.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A missing sniffer is an unmet outcome, not a crash.
"""

from __future__ import annotations

import json

PNG = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))
GIF = b"GIF89a"
SCRIPT = b" \t<ScRiPt "
XML = b"<?xml"
ZIP = b"PK\x03\x04xxxx"
GZIP = bytes((0x1F, 0x8B, 0x08, 0x00))
MP4 = bytes((0x00, 0x00, 0x00, 0x0C, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6F, 0x6D))
WEBM = bytes((0x1A, 0x45, 0xDF, 0xA3, 0x42, 0x82, 0x80, 0x77, 0x65, 0x62, 0x6D, 0x00))
ID3 = b"ID3rest"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.mime_sniff import computed_mime_type
    except Exception as exc:  # noqa: BLE001 - baseline without the sniffer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases: tuple[tuple[str, bytes, str | None, bool, str], ...] = (
        ("png_unlabeled", PNG, None, False, "image/png"),
        ("png_as_gif", PNG, "image/gif", False, "image/png"),
        ("png_as_html", PNG, "text/html", False, "text/html"),
        ("png_as_html_nosniff", PNG, "Text/HTML", True, "text/html"),
        ("png_as_svg", PNG, "image/svg+xml", False, "image/svg+xml"),
        ("png_as_plain", PNG, "text/plain", False, "application/octet-stream"),
        ("png_as_plain_charset", PNG, "text/plain; charset=UTF-8", False, "application/octet-stream"),
        ("png_as_plain_lower", PNG, "text/plain; charset=utf-8", False, "text/plain"),
        ("png_as_plain_nosniff", PNG, "text/plain", True, "text/plain"),
        ("png_as_octet_stream", PNG, "application/octet-stream", False, "application/octet-stream"),
        ("script", SCRIPT, None, False, "text/html"),
        ("script_nosniff", SCRIPT, None, True, "text/plain"),
        ("xml", XML, None, False, "text/xml"),
        ("zip", ZIP, None, False, "application/zip"),
        ("gzip", GZIP, None, False, "application/x-gzip"),
        ("mp4", MP4, None, False, "video/mp4"),
        ("webm", WEBM, None, False, "video/webm"),
        ("id3", ID3, None, False, "audio/mpeg"),
        ("gif_unknown", GIF, "application/unknown", False, "image/gif"),
        ("gif_star", GIF, "*/*", False, "image/gif"),
        ("hello_plain", b"hello", "text/plain", False, "text/plain"),
        ("gif_kept", GIF, "image/gif", False, "image/gif"),
    )
    sniffed: dict[str, object] = {}
    mismatch = ""
    for name, resource, label, no_sniff, expected in cases:
        try:
            got = computed_mime_type(resource, label, no_sniff=no_sniff)
        except Exception as exc:  # noqa: BLE001 - record the miss and keep going
            got = f"{type(exc).__name__}: {exc}"
        sniffed[name] = got
        if got != expected and not mismatch:
            mismatch = name
    observed: dict[str, object] = {"sniffed": sniffed}
    if mismatch:
        observed["mismatch"] = mismatch
        return False, observed
    return True, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
