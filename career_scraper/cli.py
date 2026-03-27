from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from career_scraper.export import write_csv, write_jsonl
from career_scraper.sources.apple import (
    AppleAPIError,
    apple_client,
    fetch_jobs_for_locations,
    fetch_postlocation_matches,
    resolve_location_slug,
)


def _cmd_apple(args: argparse.Namespace) -> int:
    if args.list_locations is not None:
        with apple_client(locale=args.locale, timeout=args.timeout) as client:
            matches = fetch_postlocation_matches(
                client, input_query=args.list_locations, locale=args.locale
            )
        if not matches:
            print("No matches.", file=sys.stderr)
            return 1
        for i, m in enumerate(matches):
            lid = m.get("id") or m.get("postLocationId") or m.get("locationId", "")
            name = (
                m.get("displayName")
                or m.get("name")
                or m.get("label")
                or m.get("title")
                or m
            )
            print(f"{i}\t{lid}\t{name}")
        return 0

    location_ids: list[str] = list(args.location_id or [])
    with apple_client(locale=args.locale, timeout=args.timeout) as client:
        if args.location_query:
            slug = resolve_location_slug(
                client,
                location_query=args.location_query,
                locale=args.locale,
                pick_index=args.location_index,
            )
            location_ids.append(slug)
        if not location_ids:
            location_ids = ["united-states-USA"]

        try:
            jobs = fetch_jobs_for_locations(
                client,
                location_ids=location_ids,
                query=args.query,
                locale=args.locale,
                page_delay_sec=args.page_delay,
                max_pages=args.max_pages,
                include_raw=not args.no_raw,
            )
        except AppleAPIError as e:
            print(f"Apple API error: {e}", file=sys.stderr)
            return 1

    out = Path(args.out)
    if args.format == "csv":
        write_csv(jobs, out)
    else:
        write_jsonl(jobs, out, include_raw=not args.no_raw)

    print(f"Wrote {len(jobs)} jobs to {out}", file=sys.stderr)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="career-scraper",
        description="Download job listings from employer career sites.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    apple = sub.add_parser("apple", help="Fetch listings from jobs.apple.com")
    apple.add_argument("--query", default="", help="Search query string (default: empty).")
    apple.add_argument(
        "--locale",
        default="en-us",
        help="Locale path segment (default: en-us).",
    )
    apple.add_argument(
        "--location-id",
        action="append",
        dest="location_id",
        metavar="ID",
        help="postLocation id, e.g. postLocation-USA (repeatable).",
    )
    apple.add_argument(
        "--location-query",
        help="Resolve a location id via Apple's refdata API (see also --location-index).",
    )
    apple.add_argument(
        "--location-index",
        type=int,
        default=0,
        help="When using --location-query, pick this match index (default: 0).",
    )
    apple.add_argument(
        "--list-locations",
        metavar="TEXT",
        help="Print candidate location ids for TEXT and exit (tab-separated: index, id, label).",
    )
    apple.add_argument(
        "--out",
        "-o",
        help="Output file path (required unless --list-locations).",
    )
    apple.add_argument(
        "--format",
        choices=("jsonl", "csv"),
        default="jsonl",
        help="Output format (default: jsonl).",
    )
    apple.add_argument(
        "--page-delay",
        type=float,
        default=0.35,
        metavar="SEC",
        help="Delay between paginated requests (default: 0.35).",
    )
    apple.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N pages (for testing).",
    )
    apple.add_argument(
        "--no-raw",
        action="store_true",
        help="Omit raw API payload from JSONL output.",
    )
    apple.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30).",
    )
    apple.set_defaults(func=_cmd_apple)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "apple":
        if args.list_locations is None and not args.out:
            parser.error("--out is required unless using --list-locations")

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
