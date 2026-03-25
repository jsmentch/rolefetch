"""Unit tests for Apple search pagination without calling the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from career_scraper.sources.apple import fetch_jobs_for_locations

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _make_transport() -> httpx.MockTransport:
    page1 = json.loads((FIXTURES / "apple_search_page.json").read_text(encoding="utf-8"))
    page2: dict[str, Any] = {
        "totalRecords": 2,
        "searchResults": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/role/search":
            body = json.loads(request.content.decode())
            if body.get("page") == 1:
                return httpx.Response(200, json=page1)
            return httpx.Response(200, json=page2)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_fetch_stops_when_no_new_results() -> None:
    transport = _make_transport()
    with httpx.Client(transport=transport, base_url="https://jobs.apple.com") as client:
        jobs = fetch_jobs_for_locations(
            client,
            location_ids=["postLocation-USA"],
            query="",
            locale="en-us",
            page_delay_sec=0,
            include_raw=False,
        )
    assert len(jobs) == 1
    assert jobs[0].external_id == "PIPE-114438206"
