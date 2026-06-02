"""Downloader for gotquestions.online packs.

Two phases, both resumable and throttled:

  1. ``listing`` — walk the paginated ``/api/packs/`` index and store every page
     as ``data/listing/page_XXXX.json``. Each entry already carries the pack's
     editors with a ``gender`` field, so we can filter without the detail call.

  2. ``packs`` — read the saved listing, select packs that have at least one
     woman editor, and store each full pack as ``data/packs/<id>.json`` via the
     ``/api/pack/<id>`` endpoint.

Resuming is purely file-based: a target whose JSON file already exists on disk
is skipped, so re-running the command only fetches what is missing.

Usage:
    uv run download.py listing
    uv run download.py packs
    uv run download.py all
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import niquests
from tqdm import tqdm

BASE = "https://gotquestions.online"
LISTING_URL = BASE + "/api/packs/"
PACK_URL = BASE + "/api/pack/{id}"

DATA = Path(__file__).parent / "data"
LISTING_DIR = DATA / "listing"
PACKS_DIR = DATA / "packs"

# Gender codes considered "a woman". "HE" is man; the woman's code on this site
# is "SE" (verified against the listing: the only two values present are "HE"
# and "SE", and every "SE" editor has an unambiguously woman's name). Any other /
# missing value would *not* be treated as a woman for the download filter, but
# is preserved in the data so the analysis phase can audit gender coverage.
WOMAN_CODES = {"SE"}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def make_session() -> niquests.Session:
    s = niquests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def throttle(delay: float) -> None:
    """Sleep ``delay`` seconds plus a little jitter to be polite."""
    if delay > 0:
        time.sleep(delay + random.uniform(0, delay * 0.5))


def get_json(session: niquests.Session, url: str, *, retries: int = 6) -> dict:
    """GET with exponential backoff on transient failures."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - retry anything transient
            if attempt == retries - 1:
                raise
            wait = min(2 ** attempt, 30)
            tqdm.write(f"  ! {url} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------- #
# Phase 1: listing
# --------------------------------------------------------------------------- #
def download_listing(session: niquests.Session, delay: float) -> None:
    LISTING_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch page 1 to learn the total page count (always re-fetched cheaply if
    # missing; if present we still need the count, so read it from disk).
    first_path = LISTING_DIR / "page_0001.json"
    if first_path.exists():
        first = json.loads(first_path.read_text(encoding="utf-8"))
    else:
        first = get_json(session, f"{LISTING_URL}?page=1")
        first_path.write_text(
            json.dumps(first, ensure_ascii=False), encoding="utf-8"
        )
        throttle(delay)

    per_page = len(first["results"]) or 1
    total_pages = -(-first["count"] // per_page)  # ceil div
    print(f"Listing: {first['count']} packs across {total_pages} pages")

    for page in tqdm(range(1, total_pages + 1), desc="listing", unit="page"):
        path = LISTING_DIR / f"page_{page:04d}.json"
        if path.exists():
            continue
        data = get_json(session, f"{LISTING_URL}?page={page}")
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        throttle(delay)


def iter_listed_packs() -> "list[dict]":
    """Yield every pack summary from the saved listing pages."""
    packs: list[dict] = []
    for path in sorted(LISTING_DIR.glob("page_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        packs.extend(data.get("results", []))
    return packs


def is_woman_edited(pack: dict) -> bool:
    return any(e.get("gender") in WOMAN_CODES for e in pack.get("editors", []))


# --------------------------------------------------------------------------- #
# Phase 2: pack details
# --------------------------------------------------------------------------- #
def download_packs(session: niquests.Session, delay: float, scope: str) -> None:
    if not LISTING_DIR.exists() or not any(LISTING_DIR.glob("page_*.json")):
        sys.exit("No listing found. Run `download.py listing` first.")

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    listed = iter_listed_packs()
    if scope == "all":
        targets = listed
        print(f"Scope=all: targeting every listed pack ({len(targets)})")
    else:
        targets = [p for p in listed if is_woman_edited(p)]
        print(
            f"Found {len(targets)} woman-edited packs "
            f"out of {len(listed)} listed (filter: gender in {sorted(WOMAN_CODES)})"
        )

    todo = [p for p in targets if not (PACKS_DIR / f"{p['id']}.json").exists()]
    print(f"{len(targets) - len(todo)} already downloaded; {len(todo)} to fetch")

    failures = []
    for pack in tqdm(todo, desc="packs", unit="pack"):
        pid = pack["id"]
        try:
            data = get_json(session, PACK_URL.format(id=pid))
        except Exception as exc:  # noqa: BLE001 - record and keep going
            failures.append(pid)
            tqdm.write(f"  ✗ giving up on pack {pid} ({exc}); will retry on re-run")
            continue
        (PACKS_DIR / f"{pid}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        throttle(delay)

    if failures:
        print(
            f"\n{len(failures)} pack(s) failed after retries and were skipped "
            f"(re-run to retry): {failures[:20]}"
            + (" …" if len(failures) > 20 else "")
        )


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=["listing", "packs", "all"], help="which phase to run"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.7,
        help="base throttle delay in seconds between requests (default 0.7)",
    )
    parser.add_argument(
        "--scope",
        choices=["women", "all"],
        default="women",
        help="which packs to fetch details for: 'women' (>=1 woman editor, "
        "default) or 'all' (every listed pack)",
    )
    args = parser.parse_args()

    session = make_session()
    if args.phase in ("listing", "all"):
        download_listing(session, args.delay)
    if args.phase in ("packs", "all"):
        download_packs(session, args.delay, args.scope)


if __name__ == "__main__":
    main()
