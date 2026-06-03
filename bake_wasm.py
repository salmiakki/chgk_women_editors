"""Bake the data the notebook needs into a WASM export's ``public/`` folder.

A kernel-less WASM notebook (``marimo export html-wasm``) runs in the browser
via Pyodide and has no access to the local 777 MB ``data/packs/``. This script
writes a *reduced* dataset (only the fields ``analysis.py`` reads — editors,
authors, genders, tournament ids/types) plus the mislabel list into
``output/wasm/public/`` so the served notebook can fetch them.

Reduced JSON is ~60 MB but gzips to ~3 MB. Run after the WASM export:

    uv run marimo export html-wasm analysis.py -o output/wasm
    uv run bake_wasm.py
"""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
DATA_PACKS = HERE / "data" / "packs"
MISLABELS = HERE / "output" / "mislabels_corrected.csv"
PUBLIC = HERE / "output" / "wasm" / "public"


def person(p: dict) -> dict:
    return {"id": p.get("id"), "name": p.get("name"), "gender": p.get("gender")}


def reduce_pack(pk: dict) -> dict:
    return {
        "id": pk["id"],
        "title": pk.get("title", ""),
        "editors": [person(e) for e in pk.get("editors", [])],
        "tours": [
            {
                "id": t["id"],
                "number": t.get("number"),
                "editors": [person(e) for e in t.get("editors", [])],
                "questions": [
                    {
                        "id": q["id"],
                        "authors": [person(a) for a in q.get("authors", []) or []],
                        "tournaments": [
                            {
                                "id": tr["id"],
                                "typeoft": {
                                    "title": (tr.get("typeoft") or {}).get("title")
                                },
                            }
                            for tr in q.get("tournaments", []) or []
                        ],
                    }
                    for q in t.get("questions", [])
                ],
            }
            for t in pk.get("tours", [])
        ],
    }


def main() -> None:
    files = sorted(DATA_PACKS.glob("*.json"))
    if not files:
        raise SystemExit("No packs found in data/packs/. Run `just packs-all` first.")
    PUBLIC.mkdir(parents=True, exist_ok=True)

    reduced = [reduce_pack(json.loads(f.read_text(encoding="utf-8"))) for f in files]
    raw = json.dumps(reduced, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, 9)
    (PUBLIC / "packs_reduced.json.gz").write_bytes(gz)

    if MISLABELS.exists():
        shutil.copyfile(MISLABELS, PUBLIC / "mislabels_corrected.csv")
    else:
        print("! output/mislabels_corrected.csv missing — run `just mislabels` first")

    # Build timestamp the served notebook displays (cells run in-browser, so
    # they can't see build time otherwise).
    (PUBLIC / "generated_at.txt").write_text(
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), encoding="utf-8"
    )

    print(
        f"Baked {len(reduced)} packs → {PUBLIC}/packs_reduced.json.gz "
        f"({len(raw) / 1e6:.0f} MB → {len(gz) / 1e6:.1f} MB gzipped) "
        f"+ mislabels_corrected.csv"
    )


if __name__ == "__main__":
    main()
