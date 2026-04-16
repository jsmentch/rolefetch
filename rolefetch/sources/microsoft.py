from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from rolefetch.models import Job

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

MICROSOFT_APPLY_BASE = "https://apply.careers.microsoft.com"
SEARCH_URL = urljoin(MICROSOFT_APPLY_BASE, "/api/pcsx/search")
DEFAULT_DOMAIN = "microsoft.com"

_MAX_SAFETY_PAGES = 5000


class MicrosoftCareersError(RuntimeError):
    """Raised when Microsoft Eightfold pcsx/search returns an error or unexpected payload."""


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _posted_at_str(posted_ts: Any) -> Optional[str]:
    if posted_ts is None:
        return None
    try:
        ts = int(posted_ts)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _job_url(position_url: str) -> str:
    path = (position_url or "").strip()
    if not path:
        return ""
    return urljoin(MICROSOFT_APPLY_BASE, path)


def _locations(record: Dict[str, Any]) -> List[str]:
    std = record.get("standardizedLocations")
    if isinstance(std, list) and std:
        out = [str(x).strip() for x in std if str(x).strip()]
        if out:
            return out
    locs = record.get("locations")
    if isinstance(locs, list):
        return [str(x).strip() for x in locs if str(x).strip()]
    return []


def normalize_microsoft_position(record: Dict[str, Any], *, include_raw: bool) -> Job:
    eid = str(record.get("id") or record.get("displayJobId") or "").strip()
    title = str(record.get("name") or "").strip() or "(no title)"
    path = str(record.get("positionUrl") or "").strip()
    url = _job_url(path)
    dept = record.get("department")
    team = str(dept).strip() if dept else None
    raw = dict(record) if include_raw else None
    return Job(
        source="microsoft",
        external_id=eid or path,
        title=title,
        company="Microsoft",
        url=url,
        posted_at=_posted_at_str(record.get("postedTs")),
        summary=None,
        team=team,
        locations=_locations(record),
        raw=raw,
    )


def fetch_jobs(
    client: httpx.Client,
    *,
    domain: str = DEFAULT_DOMAIN,
    query: str = "",
    location: str = "",
    sort_by: str = "",
    page_delay_sec: float = 0.35,
    max_pages: Optional[int] = None,
    include_raw: bool = True,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Job]:
    """
    Paginate ``/api/pcsx/search`` (Eightfold PCSX) using ``start`` offsets until a page
    returns no positions, or ``max_pages`` is reached.

    This endpoint is used by ``apply.careers.microsoft.com`` and is not documented as a
    public API; it may change without notice.
    """
    dom = domain.strip() or DEFAULT_DOMAIN
    collected: Dict[str, Job] = {}
    start = 0
    page_idx = 0
    total_reported: Optional[int] = None

    while True:
        if max_pages is not None and page_idx >= max_pages:
            break
        if page_idx >= _MAX_SAFETY_PAGES:
            raise MicrosoftCareersError(
                f"Stopped after {_MAX_SAFETY_PAGES} pages to avoid an infinite loop."
            )

        params: Dict[str, Any] = {
            "domain": dom,
            "query": query.strip(),
            "location": location.strip(),
            "start": start,
        }
        if sort_by.strip():
            params["sort_by"] = sort_by.strip()

        r = client.get(SEARCH_URL, params=params, headers=_headers())
        _raise_microsoft_http(r)

        try:
            payload = r.json()
        except ValueError as e:
            raise MicrosoftCareersError(f"Non-JSON response: {r.text[:400]!r}") from e

        if not isinstance(payload, dict):
            raise MicrosoftCareersError(f"Expected JSON object, got {type(payload).__name__}.")

        status = payload.get("status")
        if status is not None and int(status) >= 400:
            err = payload.get("error")
            raise MicrosoftCareersError(f"API status {status}: {err!r}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise MicrosoftCareersError("Missing or invalid `data` object.")

        if total_reported is None:
            c = data.get("count")
            if c is not None:
                try:
                    total_reported = int(c)
                except (TypeError, ValueError):
                    total_reported = None

        batch = data.get("positions") or []
        if not isinstance(batch, list):
            raise MicrosoftCareersError("`positions` is not a list.")

        if not batch:
            break

        before = len(collected)
        for item in batch:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or item.get("displayJobId") or "").strip()
            if not key:
                continue
            if key not in collected:
                collected[key] = normalize_microsoft_position(item, include_raw=include_raw)

        added = len(collected) - before
        if progress is not None:
            parts = [
                f"page {page_idx + 1}",
                f"start={start}",
                f"+{added} new",
                f"{len(collected)} unique",
            ]
            if total_reported is not None:
                parts.append(f"reported_total={total_reported}")
            progress("Microsoft careers — " + ", ".join(parts))

        start += len(batch)
        page_idx += 1

        if total_reported is not None and start >= total_reported:
            break

        time.sleep(page_delay_sec)

    return list(collected.values())


def microsoft_client(*, timeout: float = 30.0) -> httpx.Client:
    t = httpx.Timeout(
        timeout,
        connect=min(15.0, float(timeout)),
        read=float(timeout),
        write=min(30.0, float(timeout)),
        pool=min(15.0, float(timeout)),
    )
    return httpx.Client(timeout=t, follow_redirects=True, headers=_headers())


def _raise_microsoft_http(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise MicrosoftCareersError(
            "HTTP 429: rate limited. Increase --page-delay and retry later."
        )
    if response.status_code == 403:
        raise MicrosoftCareersError(
            "HTTP 403: forbidden. Try again later or from another network."
        )
    if response.status_code >= 400:
        raise MicrosoftCareersError(
            f"HTTP {response.status_code}: {response.text[:400]!r}"
        )
