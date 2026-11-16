"""Content-Disposition filenames stay advisory and path-free."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from blackhole_agent.content_disposition import content_disposition

PROBE = Path(__file__).resolve().parent / "acceptance" / "test_content_disposition.py"


def test_content_disposition_acceptance_fixture() -> None:
    namespace = runpy.run_path(str(PROBE), run_name="not_main")
    passed, observed = namespace["observe"]()
    assert passed, observed


def test_field_value_without_header_name() -> None:
    assert content_disposition("Attachment; filename=example.html") == {
        "type": "attachment",
        "filename": "example.html",
    }


def test_empty_star_overrides_plain_filename() -> None:
    header = "attachment; filename=\"kept.txt\"; filename*=UTF-8''"
    assert content_disposition(header) == {"type": "attachment", "filename": ""}


def test_parent_segment_and_nul_are_not_filenames() -> None:
    assert content_disposition('attachment; filename="foo/.."') == {"type": "attachment", "filename": ""}
    assert content_disposition('attachment; filename=".."') == {"type": "attachment", "filename": ""}
    assert content_disposition("attachment; filename*=UTF-8''a%00b.txt") == {
        "type": "attachment",
        "filename": "",
    }


def test_raw_nul_makes_the_quoted_field_invalid() -> None:
    assert content_disposition('attachment; filename="a\x00b.txt"') == {"type": "", "filename": ""}


def test_quoted_pair_keeps_an_escaped_quote() -> None:
    assert content_disposition('attachment; filename="say \\"hi\\".txt"')["filename"] == 'say "hi".txt'


def test_duplicate_extension_parameter_invalidates_the_field() -> None:
    assert content_disposition("attachment; name=a; name=b; filename=kept.txt") == {"type": "", "filename": ""}


def test_folded_pair_still_prefers_filename_star() -> None:
    header = 'attachment;\r\n filename="EURO rates";\r\n filename*=utf-8\'\'%e2%82%ac%20rates'
    assert content_disposition(header)["filename"] == "\u20ac rates"


def test_language_tag_is_ignored() -> None:
    assert content_disposition("attachment; filename*=UTF-8'en-US'%41%42")["filename"] == "AB"


def test_non_string_is_rejected() -> None:
    with pytest.raises(TypeError):
        content_disposition(b"attachment; filename=a.txt")  # type: ignore[arg-type]
