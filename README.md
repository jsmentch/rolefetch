# career-scraper

Python CLI to download job postings from employer career sites in **JSONL** or **CSV** for local filtering and parsing. The first supported source is **Apple** (`jobs.apple.com`).

## Install

```bash
cd /Users/jeff/Documents/career_scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# All active roles in the United States (default location filter)
python -m career_scraper apple --out apple_us.jsonl

# Keyword search + explicit location IDs (repeatable)
python -m career_scraper apple --query "machine learning" \
  --location-id postLocation-USA \
  --out apple_ml.jsonl

# Resolve location IDs from a free-text query (uses Apple's refdata API; picks first match)
python -m career_scraper apple --location-query "United States" --out apple_us.jsonl

# List candidate location IDs for a string
python -m career_scraper apple --list-locations "Germany"

# CSV instead of JSONL
python -m career_scraper apple --format csv --out apple_us.csv
```

### Apple API note

Apple does not document a public JSON API for job search. This tool calls the same endpoints the web UI uses (`POST /api/role/search`, `GET /api/v1/refData/postlocation`). Those endpoints **may change or restrict access** at any time. Use modest request pacing (`--page-delay`); comply with [Apple’s site terms](https://www.apple.com/legal/internet-services/terms/site.html) and applicable law.

## Development

```bash
pytest
ruff check career_scraper tests
```

### Manual smoke test

With network access, run:

```bash
python -m career_scraper apple --query "" --location-id postLocation-USA --max-pages 2 --out /tmp/apple_sample.jsonl
```

Confirm the file is non-empty JSONL (`wc -l`, or `python -c "import json; print(json.loads(open('/tmp/apple_sample.jsonl').readline())['title'])"`).
