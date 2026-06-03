"""Build a canonical people table from the downloaded packs.

The site's ``/api/persons/`` endpoint is auth-locked (401), but every person who
authors or edits appears in the packs with ``id / name / gender``. This unions
all author/editor entries across ``data/packs/`` into one row per person id —
the canonical id → name → gender list the other tools can build on.

Writes ``output/people.csv``. Gender here is the *raw* site tag; the corrected
(HE→SE) view lives in ``mislabels_corrected.csv`` / ``women_authors.csv``.

Usage:
    uv run build_people.py
"""

from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

from detect_mislabels import split_name

HERE = Path(__file__).parent
DATA_PACKS = HERE / "data" / "packs"
OUT = HERE / "output" / "people.csv"


def main() -> None:
    files = sorted(DATA_PACKS.glob("*.json"))
    if not files:
        raise SystemExit("No packs found in data/packs/. Run `just packs-all` first.")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    people: dict = {}

    def add(person, *, role):
        pid = person.get("id")
        name = person.get("name")
        if pid is None or not name:
            return
        rec = people.setdefault(
            pid,
            {"names": collections.Counter(), "genders": collections.Counter(),
             "author_questions": 0, "editor_roles": 0},
        )
        rec["names"][name] += 1
        rec["genders"][person.get("gender")] += 1
        if role == "author":
            rec["author_questions"] += 1
        else:
            rec["editor_roles"] += 1

    for f in files:
        pk = json.loads(f.read_text(encoding="utf-8"))
        for e in pk.get("editors", []) or []:
            add(e, role="editor")
        for t in pk.get("tours", []):
            for e in t.get("editors", []) or []:
                add(e, role="editor")
            for q in t.get("questions", []):
                for a in q.get("authors", []) or []:
                    add(a, role="author")
                for e in q.get("editors", []) or []:
                    add(e, role="editor")

    rows = []
    for pid, rec in people.items():
        name = rec["names"].most_common(1)[0][0]
        gender = rec["genders"].most_common(1)[0][0]
        first, patronymic, last = split_name(name)
        rows.append(
            [pid, first, patronymic, last, name, gender,
             rec["author_questions"], rec["editor_roles"]]
        )
    rows.sort(key=lambda r: (r[3], r[1]))  # last name, then first name

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["id", "first_name", "patronymic", "last_name", "full_name",
             "gender", "author_questions", "editor_roles"]
        )
        w.writerows(rows)

    by_g = collections.Counter(r[5] for r in rows)
    print(f"Wrote {len(rows)} people → {OUT.relative_to(HERE)}  (raw genders: {dict(by_g)})")


if __name__ == "__main__":
    main()
