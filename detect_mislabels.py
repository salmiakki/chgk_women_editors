"""Flag people whose recorded gender contradicts Russian name morphology.

The site's gender field (`HE` / `SE`) is hand-entered and skews male: many
women are tagged `HE`. This script scans the downloaded packs and writes, into
``output/``, the people whose *given name* and/or *surname ending* disagree
with their tag — as ``mislabels_corrected.csv`` (the flips the analysis applies,
read by the notebook) and ``mislabels_remaining.csv`` (still-`HE`, unflagged),
each also dumped as a plain ``.txt`` name list.

Confidence tiers (for the dominant "tagged HE but looks like a woman" case):

  very high — woman's given name AND feminine surname ending (-ова/-ева/-ина/…)
  high      — woman's given name (surname inconclusive)
  medium    — feminine surname ending AND given name ends in а/я

The notebook reads the CSV, so re-running this after downloading more packs
keeps the analysis's correction in sync.

Usage:
    uv run detect_mislabels.py
"""

from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
DATA_PACKS = HERE / "data" / "packs"
OUTPUT_DIR = HERE / "output"
OUT_CORRECTED = OUTPUT_DIR / "mislabels_corrected.csv"
OUT_REMAINING = OUTPUT_DIR / "mislabels_remaining.csv"
OUT_CORRECTED_TXT = OUTPUT_DIR / "mislabels_corrected.txt"
OUT_REMAINING_TXT = OUTPUT_DIR / "mislabels_remaining.txt"

WOMAN_FIRST = {
    "Юлия", "Юля", "Мария", "Маша", "Анна", "Аня", "Елена", "Лена", "Ольга",
    "Оля", "Наталья", "Наталия", "Наташа", "Ирина", "Ира", "Екатерина", "Катя",
    "Татьяна", "Таня", "Светлана", "Света", "Дарья", "Даша", "Ксения", "Ксюша",
    "Вера", "Виктория", "Вика", "Маргарита", "Рита", "Лидия", "Анастасия",
    "Настя", "Елизавета", "Лиза", "Иделия", "Надежда", "Надя", "Полина",
    "Алёна", "Алена", "Галина", "Галя", "Любовь", "Оксана", "Яна", "Валентина",
    "София", "Софья", "Соня", "Евгения", "Жанна", "Альбина", "Инна", "Зоя",
    "Нина", "Алина", "Кристина", "Людмила", "Диана", "Дина", "Регина", "Карина",
    "Вероника", "Снежана", "Майя", "Лилия", "Лиля", "Эльвира", "Динара",
    "Гузель", "Лариса", "Тамара", "Раиса", "Римма", "Зинаида", "Антонина",
    "Клавдия", "Валерия", "Лера", "Милана", "Ангелина", "Арина", "Варвара",
    "Варя", "Влада", "Владислава", "Дарина", "Камила", "Камилла", "Сабина",
    "Таисия", "Ульяна", "Эмилия", "Ярослава", "Марина", "Олеся", "Элина",
    "Амина", "Виолетта", "Ника", "Агата", "Стелла", "Эльза",
}
MAN_FIRST = {
    "Александр", "Алексей", "Андрей", "Антон", "Артём", "Артем", "Борис",
    "Вадим", "Валерий", "Василий", "Виктор", "Виталий", "Владимир", "Владислав",
    "Вячеслав", "Геннадий", "Георгий", "Григорий", "Денис", "Дмитрий",
    "Евгений", "Егор", "Иван", "Игорь", "Илья", "Кирилл", "Константин", "Лев",
    "Леонид", "Максим", "Михаил", "Никита", "Николай", "Олег", "Павел", "Пётр",
    "Петр", "Роман", "Руслан", "Сергей", "Станислав", "Степан", "Тимофей",
    "Тимур", "Фёдор", "Федор", "Юрий", "Ярослав", "Анатолий", "Аркадий",
    "Арсений", "Богдан", "Вениамин", "Всеволод", "Гавриил", "Даниил", "Захар",
    "Игнат", "Макар", "Марк", "Матвей", "Назар", "Платон", "Родион", "Савелий",
    "Семён", "Семен", "Эдуард", "Эмиль", "Юлиан",
}
WOMAN_SURNAME_ENDINGS = ("ова", "ёва", "ева", "ина", "ына", "ская", "цкая", "ная", "няя")
MAN_SURNAME_ENDINGS = ("ов", "ёв", "ев", "ин", "ын", "ский", "цкий", "ной", "ный")

# Non-person entries (teams/groups) — these have no gender and must never be
# flagged. They otherwise trip the morphology rules ("Команда ...ова" looks
# feminine). Detected by a leading team word or a quoted team name.
TEAM_WORDS = {"Команда", "Команды", "Сборная", "Дуэт", "Группа", "Клуб", "Гильдия", "Лига", "Дети"}


def is_non_person(name: str) -> bool:
    toks = name.split()
    return bool(toks) and (toks[0] in TEAM_WORDS or "«" in name)


def woman_surname(s: str) -> bool:
    return s.endswith(WOMAN_SURNAME_ENDINGS)


def man_surname(s: str) -> bool:
    return s.endswith(MAN_SURNAME_ENDINGS)


def collect_people():
    """Tally each person: total appearances, gender tag(s), and per-role counts
    (questions authored vs. editor roles held)."""
    appearances: collections.Counter = collections.Counter()
    author_q: collections.Counter = collections.Counter()
    editor_roles: collections.Counter = collections.Counter()
    tags: dict = collections.defaultdict(set)

    def add(people, *, role):
        for p in people or []:
            name = p.get("name")
            if name:
                appearances[name] += 1
                tags[name].add(p.get("gender"))
                if role == "author":
                    author_q[name] += 1
                else:
                    editor_roles[name] += 1

    for path in sorted(DATA_PACKS.glob("*.json")):
        pk = json.loads(path.read_text(encoding="utf-8"))
        add(pk.get("editors"), role="editor")
        for tour in pk.get("tours", []):
            add(tour.get("editors"), role="editor")
            for q in tour.get("questions", []):
                add(q.get("authors"), role="author")
                add(q.get("editors"), role="editor")
    return appearances, tags, author_q, editor_roles


def classify(appearances, tags):
    rows = []
    for name, cnt in appearances.items():
        if is_non_person(name):
            continue
        gs = tags[name]
        parts = name.split()
        first = parts[0]
        last = parts[-1] if len(parts) > 1 else ""
        first_woman, first_man = first in WOMAN_FIRST, first in MAN_FIRST
        surname_woman, surname_man = woman_surname(last), man_surname(last)

        # Dominant case: tagged HE but looks like a woman.
        if "HE" in gs and not first_man:
            if first_woman and surname_woman:
                tier = "very high"
            elif first_woman:
                tier = "high"
            elif surname_woman and first.endswith(("а", "я")):
                tier = "medium"
            else:
                tier = None
            if tier:
                rows.append(
                    ("woman_tagged_HE", tier, cnt, name, "|".join(map(str, sorted(gs))))
                )

        # Rare reverse case: tagged SE but looks like a man.
        if "SE" in gs and not first_woman and first_man:
            tier = "very high" if surname_man else "high"
            rows.append(
                ("man_tagged_SE", tier, cnt, name, "|".join(map(str, sorted(gs))))
            )

    tier_rank = {"very high": 0, "high": 1, "medium": 2}
    rows.sort(key=lambda r: (r[0], tier_rank[r[1]], -r[2]))
    return rows


def main() -> None:
    if not DATA_PACKS.exists() or not any(DATA_PACKS.glob("*.json")):
        raise SystemExit("No packs found. Run `download.py packs` first.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    appearances, tags, author_q, editor_roles = collect_people()
    rows = classify(appearances, tags)

    # Corrected list — every flagged person (the gender flips the analysis
    # applies), sorted by impact and enriched with role counts. This is the
    # canonical file the notebook reads.
    flagged = {r[3] for r in rows}
    corrected = sorted(
        rows, key=lambda r: -(author_q[r[3]] + editor_roles[r[3]])
    )
    with OUT_CORRECTED.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["name", "suspicion", "confidence", "author_questions", "editor_roles", "genders_tagged"]
        )
        for suspicion, conf, _cnt, name, gs in corrected:
            w.writerow([name, suspicion, conf, author_q[name], editor_roles[name], gs])

    # Remaining list — people still tagged HE that the heuristic did NOT flag
    # (the review queue for misses it can't catch, e.g. non-Slavic surnames).
    remaining = sorted(
        (
            (name, appearances[name], author_q[name], editor_roles[name])
            for name in appearances
            if "HE" in tags[name] and name not in flagged and not is_non_person(name)
        ),
        key=lambda r: -r[1],
    )
    with OUT_REMAINING.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "appearances", "author_questions", "editor_roles"])
        w.writerows(remaining)

    # Plain-text name lists (one per line), same order as the CSVs.
    OUT_CORRECTED_TXT.write_text(
        "\n".join(r[3] for r in corrected) + "\n", encoding="utf-8"
    )
    OUT_REMAINING_TXT.write_text(
        "\n".join(r[0] for r in remaining) + "\n", encoding="utf-8"
    )

    n_woman = sum(r[0] == "woman_tagged_HE" for r in rows)
    n_man = sum(r[0] == "man_tagged_SE" for r in rows)
    n_packs = len(list(DATA_PACKS.glob("*.json")))
    print(
        f"Scanned {n_packs} packs. "
        f"Corrected (woman-tagged-HE: {n_woman}, man-tagged-SE: {n_man}). "
        f"Remaining HE (unflagged): {len(remaining)}.\n"
        f"Wrote mislabels_corrected.csv/.txt and mislabels_remaining.csv/.txt "
        f"to {OUTPUT_DIR.name}/"
    )


if __name__ == "__main__":
    main()
