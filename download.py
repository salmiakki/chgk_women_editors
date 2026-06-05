"""Downloader for gotquestions.online packs (server-side-rendered pages).

The JSON API is JWT-protected, but the site is a Next.js app that renders pages
server-side: the server makes the authenticated API call and embeds the result
in the page HTML (both as markup and as the React-Flight `__next_f` payload).
So anonymous HTTP fetches of the *pages* yield the full data — no token, no
browser. We parse the flight payload out of the HTML.

  * listing — ``/?page=N`` embeds the same paginated index the API returned
    ({results, count}); saved as ``data/listing/page_XXXX.json``.
  * pack    — ``/pack/<id>`` embeds the full pack; saved as
    ``data/packs/<id>.json`` (identical schema to the old API payload).

Both phases are resumable (skip files already on disk) and throttled.

Usage:
    uv run download.py listing
    uv run download.py packs --scope all
    uv run download.py all --scope all
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

import niquests
from tqdm import tqdm

BASE = "https://gotquestions.online"
LIST_PAGE = BASE + "/?page={n}"
PACK_PAGE = BASE + "/pack/{id}"

DATA = Path(__file__).parent / "data"
LISTING_DIR = DATA / "listing"
PACKS_DIR = DATA / "packs"

WOMAN_CODES = {"SE"}  # gender code for women; "HE" is man

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?)\]\)</script>', re.S)


def make_session() -> niquests.Session:
    s = niquests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})
    return s


def throttle(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)


# --------------------------------------------------------------------------- #
# Flight-payload parsing
# --------------------------------------------------------------------------- #
def flight_blob(html: str) -> str:
    """Concatenate the decoded __next_f flight string chunks."""
    parts = []
    for m in _PUSH_RE.finditer(html):
        try:
            parts.append(json.loads(m.group(1)))
        except Exception:  # noqa: BLE001
            pass
    return "".join(parts)


def _match(blob: str, start: int) -> "str | None":
    """Return the balanced {...}/[...] slice beginning at index `start`,
    respecting string literals so braces inside text don't break matching."""
    open_c = blob[start]
    close_c = "}" if open_c == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(blob)):
        c = blob[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0:
                    return blob[start : j + 1]
    return None


def _obj_after(blob: str, key: str, frm: int = 0):
    """Parse the JSON object/array that is the value of `key` (searched from
    `frm`). Returns (value, next_index). If the value isn't an object/array
    (e.g. a string), returns (None, just-past-key) so callers can keep scanning
    later occurrences of the same key."""
    i = blob.find(key, frm)
    if i < 0:
        return None, -1
    j = i + len(key)
    while j < len(blob) and blob[j] in " \t\r\n":
        j += 1
    if j >= len(blob) or blob[j] not in "{[":
        return None, i + len(key)
    s = _match(blob, j)
    if not s:
        return None, i + len(key)
    try:
        return json.loads(s), j + len(s)
    except Exception:  # noqa: BLE001
        return None, j + len(s)


def parse_pack(html: str) -> "dict | None":
    obj, _ = _obj_after(flight_blob(html), '"pack":')
    return obj


def parse_listing(html: str) -> dict:
    """Extract {results, count} from a listing page. The pack array is the
    value of the `packs` key (other `packs` keys exist — nav label etc. — so
    scan until we find the array whose items are pack summaries)."""
    blob = flight_blob(html)
    results = []
    frm = 0
    while True:
        arr, nxt = _obj_after(blob, '"packs":', frm)
        if nxt < 0:
            break
        frm = nxt
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "id" in arr[0]:
            results = arr
            break
    m = re.search(r'"count":(\d+)', blob)
    count = int(m.group(1)) if m else len(results)
    return {"results": results, "count": count}


# --------------------------------------------------------------------------- #
def get_html(session: niquests.Session, url: str, *, retries: int = 6) -> "str | None":
    """GET a page; None on 404 (a deleted/absent id). Retries transient errors."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=60)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # noqa: BLE001
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

    first_path = LISTING_DIR / "page_0001.json"
    if first_path.exists():
        first = json.loads(first_path.read_text(encoding="utf-8"))
    else:
        first = parse_listing(get_html(session, LIST_PAGE.format(n=1)))
        first_path.write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8")
        throttle(delay)

    per_page = len(first["results"]) or 1
    total_pages = math.ceil(first["count"] / per_page)
    print(f"Listing: {first['count']} packs across {total_pages} pages")

    for page in tqdm(range(1, total_pages + 1), desc="listing", unit="page"):
        path = LISTING_DIR / f"page_{page:04d}.json"
        if path.exists():
            continue
        data = parse_listing(get_html(session, LIST_PAGE.format(n=page)))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        throttle(delay)


def iter_listed_packs() -> "list[dict]":
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
        html = get_html(session, PACK_PAGE.format(id=pid))
        data = parse_pack(html) if html is not None else None
        if data is None:
            failures.append(pid)
            tqdm.write(f"  ✗ pack {pid}: no data (404 or unparseable); skipping")
            continue
        (PACKS_DIR / f"{pid}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        throttle(delay)

    if failures:
        print(
            f"\n{len(failures)} pack(s) had no data and were skipped "
            f"(re-run to retry): {failures[:20]}" + (" …" if len(failures) > 20 else "")
        )


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["listing", "packs", "all"])
    parser.add_argument(
        "--delay",
        type=float,
        default=0.7,
        help="throttle delay in seconds between requests (default 0.7)",
    )
    parser.add_argument(
        "--scope",
        choices=["women", "all"],
        default="women",
        help="which packs to fetch details for (default women)",
    )
    args = parser.parse_args()

    session = make_session()
    if args.phase in ("listing", "all"):
        download_listing(session, args.delay)
    if args.phase in ("packs", "all"):
        download_packs(session, args.delay, args.scope)


if __name__ == "__main__":
    main()
