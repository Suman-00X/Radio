"""The features page's pieces without a database: Reason dialogs, named items, tabs, includes and the media route."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from radreport.api.app import create_app
from radreport.api.markdown import render
from radreport.api.routes.showcase import _split_tabs

FEATURE = """**Speak, don't type**
Dictate naturally.

> **Why:** Radiologists already dictate.
"""


def test_a_why_quote_becomes_a_reason_dialog_titled_with_its_feature() -> None:
    html = render(FEATURE, reasons=True).html
    assert 'data-dialog-open="reason-speak-dont-type"' in html
    assert '<dialog class="reason-dialog" id="reason-speak-dont-type"' in html
    assert ">Speak, don&#x27;t type</div>" in html and "Radiologists already dictate." in html
    assert "<blockquote>" not in html


def test_without_reasons_a_why_quote_stays_a_quote() -> None:
    html = render(FEATURE).html
    assert "<blockquote>" in html and "<dialog" not in html


def test_two_features_with_the_same_name_get_distinct_dialogs() -> None:
    html = render(FEATURE + "\n" + FEATURE, reasons=True).html
    assert 'id="reason-speak-dont-type"' in html and 'id="reason-speak-dont-type-1"' in html


def test_a_bold_line_over_text_is_a_named_item_on_its_own_line() -> None:
    html = render("**Two-person sign-off**\nAn assistant edits; a radiologist signs.").html
    assert html == '<p class="named"><strong class="named-title">Two-person sign-off</strong>An assistant edits; a radiologist signs.</p>'


def test_reason_text_is_escaped() -> None:
    html = render("**<b>x</b>**\ny\n\n> **Why:** <script>alert(1)</script>", reasons=True).html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_tab_markers_split_the_document() -> None:
    intro, tabs = _split_tabs("# Title\n\n<!-- tab: features | Features -->\nA\n<!-- tab: hld | System design -->\nB\n")
    assert intro.strip() == "# Title"
    assert [(k, label, body.strip()) for k, label, body in tabs] == [("features", "Features", "A"), ("hld", "System design", "B")]


def test_the_features_page_is_one_page_without_tabs() -> None:
    page = TestClient(create_app()).get("/features").text
    assert 'role="tab"' not in page and "data-dialog-open=" in page
    assert "By the numbers" not in page, "the numbers live on the recruiter tour only"
    assert 'href="/recruiter#crash-test"' in TestClient(create_app()).get("/recruiter").text, "links into a tour tab point at the tour"
    assert "<!--" not in page.split("<main", 1)[1], "no marker leaks into the page"


def test_the_recruiter_tour_has_its_tabs_in_order_and_the_crash_results() -> None:
    page = TestClient(create_app()).get("/recruiter").text
    keys = ("in-action", "hld", "crash-test")
    assert page.count('role="tab"') == 3 and all(f'data-key="{key}"' in page for key in keys)
    assert [page.index(f'data-key="{key}"') for key in keys] == sorted(page.index(f'data-key="{key}"') for key in keys)
    overview = page.split('id="tab-in-action"', 1)[1].split('id="tab-hld"', 1)[0]
    assert ">For Recruiters</button>" in page and "HTTP routes" in overview and "<video" in overview, "the numbers and recordings sit in the For Recruiters tab"
    assert "HTTP routes" not in page.split('id="tab-in-action"', 1)[0], "no numbers above the tabs"
    assert 'class="tab-sparkle"' in page.split('data-key="crash-test"', 1)[1].split(">", 1)[0], "the crash-test tab sparkles"
    assert 'data-test-run="/recruiter/tests/stream"' in page and "showtime.js" in page, "the test environment offers the live run"
    assert "failures handled as designed" in page, "the crash-test report is included"
    assert "<!--" not in page.split("<main", 1)[1], "no marker leaks into the page"


def test_media_names_are_allow_listed() -> None:
    client = TestClient(create_app())
    assert client.get("/media/..%2F..%2F.env").status_code in (400, 404)
    assert client.get("/media/not-there.mp4").status_code == 404
    assert client.get("/media/admin-panel.webm").status_code in (400, 404)


def test_media_honours_byte_ranges() -> None:
    response = TestClient(create_app()).get("/media/admin-panel.mp4", headers={"Range": "bytes=0-9"})
    assert response.status_code == 206 and len(response.content) == 10
    assert response.headers["content-type"] == "video/mp4"


def _fresh_client() -> TestClient:
    """A client at its own address, so the run's per-address limit, kept in the shared store, never carries over."""
    return TestClient(create_app(), client=(f"test-{uuid.uuid4().hex[:12]}", 50000))


def test_the_live_run_streams_each_event_as_a_server_sent_event(monkeypatch) -> None:
    from radreport.devtools import test_stream

    async def fake_run():
        yield {"type": "start", "total": 1, "files": ["tests/unit/test_x.py"]}
        yield {"type": "test", "id": "tests/unit/test_x.py::test_y", "outcome": "passed", "seconds": 0.01}
        yield {"type": "done", "passed": 1, "failed": 0, "skipped": 0, "error": 0, "seconds": 0.1, "exit": 0}

    monkeypatch.setattr(test_stream, "run_suite", fake_run)
    response = _fresh_client().get("/recruiter/tests/stream")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    events = [line for line in response.text.split("\n\n") if line]
    assert [e.split('"type": "', 1)[1].split('"', 1)[0] for e in events] == ["start", "test", "done"]


def test_a_second_live_run_is_told_the_first_is_still_going(monkeypatch) -> None:
    from radreport.devtools import test_stream

    async def busy():
        raise test_stream.SuiteBusy("a test run is already in progress")
        yield {}

    monkeypatch.setattr(test_stream, "run_suite", busy)
    assert '"type": "busy"' in _fresh_client().get("/recruiter/tests/stream").text


def test_the_live_run_is_refused_outside_development(monkeypatch) -> None:
    from radreport.core.config import get_settings

    client = _fresh_client()
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.get("/recruiter/tests/stream").status_code == 404
    page = client.get("/recruiter").text
    assert "data-test-run=" not in page and "available on local and development deployments" in page
