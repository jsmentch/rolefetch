"""Tests for Microsoft careers pcsx/search client (no live network)."""

from __future__ import annotations

import httpx

from rolefetch.sources.microsoft import (
    MicrosoftCareersError,
    fetch_jobs,
    normalize_microsoft_position,
)


def test_normalize_microsoft_position() -> None:
    rec = {
        "id": 1970393556642414,
        "displayJobId": "200016292",
        "name": "Principal Applied Scientist",
        "locations": ["United States, Washington, Redmond"],
        "standardizedLocations": ["Redmond, WA, US"],
        "postedTs": 1700000000,
        "department": "Applied Sciences",
        "positionUrl": "/careers/job/1970393556642414",
    }
    job = normalize_microsoft_position(rec, include_raw=True)
    assert job.source == "microsoft"
    assert job.external_id == "1970393556642414"
    assert job.title == "Principal Applied Scientist"
    assert job.company == "Microsoft"
    assert job.url == "https://apply.careers.microsoft.com/careers/job/1970393556642414"
    assert job.team == "Applied Sciences"
    assert job.locations == ["Redmond, WA, US"]
    assert job.posted_at is not None and job.posted_at.startswith("2023-11-14")
    assert job.summary is None
    assert job.raw is not None
    assert job.raw["displayJobId"] == "200016292"


def test_normalize_falls_back_to_locations_without_standardized() -> None:
    rec = {
        "id": 1,
        "name": "Engineer",
        "locations": ["Canada, ON, Toronto"],
        "positionUrl": "/careers/job/1",
    }
    job = normalize_microsoft_position(rec, include_raw=False)
    assert job.locations == ["Canada, ON, Toronto"]


def test_fetch_paginates_until_empty_batch() -> None:
    """First page: 2 positions. Second: 1. Third: empty -> stop."""

    def page(positions: list, count: int) -> dict:
        return {
            "status": 200,
            "error": {"message": "", "body": ""},
            "data": {
                "positions": positions,
                "count": count,
                "filterDef": {},
                "sortBy": None,
                "appliedFilters": {},
            },
        }

    p1 = page(
        [
            {"id": 10, "name": "A", "positionUrl": "/careers/job/10", "postedTs": 1},
            {"id": 20, "name": "B", "positionUrl": "/careers/job/20", "postedTs": 2},
        ],
        3,
    )
    p2 = page(
        [
            {"id": 30, "name": "C", "positionUrl": "/careers/job/30", "postedTs": 3},
        ],
        3,
    )
    starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("start", "0")
        starts.append(int(q))
        if q == "0":
            return httpx.Response(200, json=p1)
        if q == "2":
            return httpx.Response(200, json=p2)
        return httpx.Response(200, json=page([], 0))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        jobs = fetch_jobs(
            client,
            query="",
            location="",
            page_delay_sec=0,
            include_raw=False,
        )

    assert len(jobs) == 3
    assert {j.external_id for j in jobs} == {"10", "20", "30"}
    # Stops when start reaches reported count (3) without an extra empty request.
    assert starts == [0, 2]


def test_api_status_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": 500, "error": {"message": "x"}, "data": {}},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        try:
            fetch_jobs(client, page_delay_sec=0, include_raw=False)
        except MicrosoftCareersError as e:
            assert "500" in str(e)
        else:
            raise AssertionError("expected MicrosoftCareersError")


def test_http_429_raises() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(429, text="slow down"))
    with httpx.Client(transport=transport) as client:
        try:
            fetch_jobs(client, page_delay_sec=0, include_raw=False)
        except MicrosoftCareersError as e:
            assert "429" in str(e)
        else:
            raise AssertionError("expected MicrosoftCareersError")
