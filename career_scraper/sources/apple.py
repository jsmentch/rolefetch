from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from career_scraper.models import Job

SEARCH_URL = "https://jobs.apple.com/api/role/search"
POSTLOCATION_URL = "https://jobs.apple.com/api/v1/refData/postlocation"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class AppleAPIError(RuntimeError):
    """Raised when Apple's jobs API returns an unexpected or error response."""


def _client_headers(locale: str) -> Dict[str, str]:
    lc = locale.lower().replace("_", "-")
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://jobs.apple.com",
        "Referer": f"https://jobs.apple.com/{lc}/search",
    }


def fetch_postlocation_matches(
    client: httpx.Client,
    *,
    input_query: str,
    locale: str = "en-us",
) -> List[Dict[str, Any]]:
    """Return candidate location objects from Apple's refdata endpoint (shape varies)."""
    params = {"input": input_query}
    r = client.get(POSTLOCATION_URL, params=params)
    _raise_for_apple_status(r)
    data = r.json()
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("results", "data", "locations", "postLocations"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def resolve_location_id(
    client: httpx.Client,
    *,
    location_query: str,
    locale: str = "en-us",
    pick_index: int = 0,
) -> str:
    matches = fetch_postlocation_matches(client, input_query=location_query, locale=locale)
    if not matches:
        raise AppleAPIError(f"No location matches for query: {location_query!r}")
    if pick_index < 0 or pick_index >= len(matches):
        raise AppleAPIError(
            f"Location pick index {pick_index} out of range (0..{len(matches) - 1})"
        )
    chosen = matches[pick_index]
    lid = chosen.get("id") or chosen.get("postLocationId") or chosen.get("locationId")
    if not lid or not isinstance(lid, str):
        raise AppleAPIError(f"Could not read location id from match: {chosen!r}")
    return lid


def normalize_apple_job(record: Dict[str, Any], *, locale: str, include_raw: bool) -> Job:
    external_id = str(record.get("id") or record.get("reqId") or record.get("positionId", ""))
    position_id = str(record.get("positionId") or "").strip()
    if not position_id and external_id:
        if external_id.startswith("PIPE-"):
            position_id = external_id.removeprefix("PIPE-")
        else:
            position_id = external_id
    lc = locale.lower().replace("_", "-")
    url = f"https://jobs.apple.com/{lc}/details/{position_id}" if position_id else ""

    title = str(record.get("postingTitle") or record.get("transformedPostingTitle") or "").strip()
    summary = record.get("jobSummary")
    summary_str = str(summary).strip() if summary is not None else None

    team_name = None
    team = record.get("team")
    if isinstance(team, dict):
        tn = team.get("teamName")
        if tn is not None:
            team_name = str(tn).strip() or None

    locs: List[str] = []
    raw_locs = record.get("locations")
    if isinstance(raw_locs, list):
        for loc in raw_locs:
            if not isinstance(loc, dict):
                continue
            name = loc.get("name") or loc.get("city") or loc.get("countryName")
            if name:
                locs.append(str(name).strip())
            elif loc.get("countryName"):
                locs.append(str(loc["countryName"]).strip())

    posted = record.get("postDateInGMT")
    posted_str = str(posted).strip() if posted else None

    raw = dict(record) if include_raw else None
    return Job(
        source="apple",
        external_id=external_id or position_id,
        title=title or "(no title)",
        company="Apple",
        url=url,
        posted_at=posted_str,
        summary=summary_str,
        team=team_name,
        locations=locs,
        raw=raw,
    )


def fetch_jobs_for_locations(
    client: httpx.Client,
    *,
    location_ids: list[str],
    query: str = "",
    locale: str = "en-us",
    page_delay_sec: float = 0.35,
    max_pages: Optional[int] = None,
    include_raw: bool = True,
) -> List[Job]:
    """Paginate search until all records are retrieved or a page adds nothing / max_pages hit."""
    if not location_ids:
        raise AppleAPIError("At least one location id is required (e.g. postLocation-USA).")

    lc = locale.lower().replace("_", "-")
    request_body: Dict[str, Any] = {
        "query": query,
        "locale": lc,
        "filters": {"postingpostLocation": location_ids},
        "page": 1,
    }

    collected: List[Dict[str, Any]] = []
    expected_count: Optional[int] = None
    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break

        request_body["page"] = page
        r = client.post(SEARCH_URL, json=request_body)
        _raise_for_apple_status(r)

        try:
            payload = r.json()
        except ValueError as e:
            raise AppleAPIError(f"Search response was not JSON: {r.text[:500]!r}") from e

        if not isinstance(payload, dict):
            raise AppleAPIError(f"Unexpected search payload type: {type(payload).__name__}")

        batch = payload.get("searchResults") or payload.get("results") or []
        if not isinstance(batch, list):
            raise AppleAPIError("searchResults is not a list")

        tr = payload.get("totalRecords")
        if tr is not None:
            try:
                expected_count = int(tr)
            except (TypeError, ValueError):
                pass

        before = len(collected)
        for item in batch:
            if isinstance(item, dict):
                collected.append(item)

        if len(collected) == before:
            break
        if expected_count is not None and len(collected) >= expected_count:
            break

        page += 1
        time.sleep(page_delay_sec)

    by_id: Dict[str, Dict[str, Any]] = {}
    for item in collected:
        key = str(item.get("id") or item.get("reqId") or item.get("positionId", ""))
        if key and key not in by_id:
            by_id[key] = item

    return [
        normalize_apple_job(rec, locale=locale, include_raw=include_raw) for rec in by_id.values()
    ]


def apple_client(*, locale: str = "en-us", timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers=_client_headers(locale),
        timeout=timeout,
        follow_redirects=True,
    )


def _raise_for_apple_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise AppleAPIError("HTTP 429: rate limited. Increase --page-delay or retry later.")
    if response.status_code == 403:
        raise AppleAPIError(
            "HTTP 403: forbidden. Apple's edge may block automated clients; try another network."
        )
    if response.status_code >= 400:
        raise AppleAPIError(
            f"HTTP {response.status_code}: {response.text[:400]!r}"
        )
