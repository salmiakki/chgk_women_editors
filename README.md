# women_editors

Scrape ЧГК question packs from [gotquestions.online](https://gotquestions.online)
and analyse the gender of **question authors in tours edited by women**, plus
how packs map to tournaments.

*Prepared for Lesha Pak, using GotQuestions ([gotquestions.online](https://gotquestions.online)) data.*

The site exposes a clean Django REST API, so no HTML parsing is needed:

- `GET /api/packs/?page=N` — paginated pack index (~6,701 packs). Each entry
  already carries its editors with a `gender` field.
- `GET /api/pack/<id>` — a full pack: tours → questions, with each question's
  `authors`, `editors`, and `tournaments` (editors/authors are gendered).

Gender codes: **`HE`** = man, **`SE`** = woman. (Hand-entered and imperfect —
a few clearly women's names are tagged `HE` — so treat the split as approximate.
The analyser surfaces an author roster to eyeball this.)

## Setup

```bash
just sync        # or: uv sync
```

Requires [`uv`](https://docs.astral.sh/uv/) and (optionally)
[`just`](https://github.com/casey/just). Every recipe just wraps a `uv run`
command, so you can run those directly if you prefer.

## 1. Download (`download.py`)

Two resumable, throttled phases. Resume is file-based: a pack whose
`data/packs/<id>.json` already exists is skipped, so re-running only fetches
what is missing. Failed requests retry with exponential backoff.

```bash
just rebuild            # download EVERYTHING + rebuild mislabels CSV + report
just listing            # phase 1: all index pages → data/listing/
just packs              # phase 2: woman-edited packs → data/packs/
just packs-all          # phase 2 (full): EVERY pack → data/packs/
just download-all       # listing + all pack details, in order
just status             # how much is downloaded so far
```

`just rebuild` is the one-shot: it runs `download-all` → `mislabels` → `report`
in order (all resumable, so re-running only fetches what's missing).

Throttle is the `delay` variable (default `1`s + jitter):
`just delay=0.6 packs-all`.

Both scopes write to the same `data/packs/` dir, so escalating from
woman-edited to all only downloads the missing packs. The pack-level editor
list is a superset of the tour editors, so the woman-edited scope still
captures every woman-edited *tour*. Payloads are stored verbatim as JSON; the
analyser is the only thing that interprets them, and it derives the
woman-edited subset from the data — so it works with either scope.

Direct equivalents:

```bash
uv run download.py listing --delay 0.4
uv run download.py packs   --delay 0.4 --scope all   # or --scope women
```

## 2. Gender-mislabel audit (`detect_mislabels.py`)

The site's `HE`/`SE` field is hand-entered and skews male — many women are
tagged `HE` (never the reverse). `detect_mislabels.py` scans the packs and uses
Russian name morphology (women's given names + feminine surname endings) to flag
likely mislabels. It writes three CSVs into `output/`:

- `mislabels_corrected.csv` — every flagged person (the `HE→SE` flips,
  read by the notebook), with role counts (questions authored, editor roles).
- `mislabels_remaining.csv` — people still tagged `HE` that were *not* flagged
  (the review queue for misses the heuristic can't catch, e.g. non-Slavic
  surnames like `-дзе`, `-ко`, indeclinable).

```bash
just mislabels          # → output/*.csv   (uv run detect_mislabels.py)
```

The notebook **reads `output/mislabels_corrected.csv`**, so regenerate it after
downloading more packs and re-run the notebook to refresh the corrections. The
corrected views override `HE → SE` for the tiers in `CORRECT_TIERS` (in
`analysis.py`; currently **all tiers** — manual review confirmed the flagged
people are all women). Raw values are always shown alongside.

## 3. Analyse (`analysis.py`, marimo)

```bash
just edit               # interactive notebook  (uv run marimo edit analysis.py)
just app                # read-only app view
just report             # static HTML → output/women_editors_report.html
just report-with-code   # same, with Python source shown
```

The notebook (sections):

1. **Coverage & gender audit** — corpus totals, woman-edited subset, gender
   codes present, an author roster, and the mislabel table loaded
   from `output/mislabels_corrected.csv`.
2. **Packs ↔ tournaments** — a *pack* is one question set; a *tournament* is a
   scheduled run of it. Distribution of tournaments-per-pack, whole corpus vs
   woman-edited.
3. **Author genders by tour-editor composition** — author-credit gender mix in
   tours that are *women-only*, *mixed*, *men-only*, or *no editors*.
4. **Each woman editor: own vs. other women vs. men** — for tours she
   personally edited, how author credits split between herself, other women,
   and men (sorted most-self-reliant first), plus distinct women collaborators
   and their share.
5. **Authors who contribute most to woman-edited tours** — top women and men
   authors across all woman-edited tours, absolute credits and as a share.
6. **Explore by individual woman editor** — interactive drill-down.
7. **Men editors & their women-author collaborations** — top men editors by
   total credits, women-author credits, and distinct women authors.

### How credits are counted

- **Shared question credits.** Stats are by **author credit** — one tally per
  (question, author). A question with two authors yields two credits, one for
  each author's gender; a 3-author question yields three. So a co-authored
  question is *not* collapsed to a single author or gender. (~97% of questions
  have exactly one author, so this rarely shifts aggregates.)
- **Shared tour editorship.** A tour is classified by its *whole* editor set
  (women-only / mixed / men-only). In the per-editor breakdowns, a tour
  co-edited by several women counts **once for each** of those women — its
  questions contribute to every co-editor's tally (the same questions are
  attributed to each, not split between them).
- **Self vs. collaborators.** "Self" matches the author's id to the editor's.
  Distinct **collaborators** count unique author *ids* excluding the editor
  herself/himself; "% women collaborators" is distinct women ÷ distinct
  collaborators.

### Exporting a report

`just report` produces a static, self-contained HTML snapshot (code hidden) —
no kernel or server needed. For PDF, open it in a browser and Print → Save as
PDF. For a Jupyter notebook: `uv run marimo export ipynb analysis.py -o analysis.ipynb`.

## Layout

```
download.py                       # phase 1 + 2 downloader
detect_mislabels.py               # writes the output/*.csv mislabel lists
analysis.py                       # marimo analyser
justfile                          # task runner (just --list)
data/listing/                     # index pages (page_0001.json …)   [gitignored]
data/packs/                       # full pack payloads (<id>.json)    [gitignored]
output/mislabels_corrected.csv    # the HE→SE flips, with role counts (read by notebook)
output/mislabels_corrected.txt    # same, names only
output/mislabels_remaining.csv    # still-HE, unflagged (review queue)
output/mislabels_remaining.txt    # same, names only
output/women_editors_report.html  # generated static report
```

Both `data/` and `output/` are gitignored (regenerable): `data/` via
`download.py`, and everything in `output/` via `just mislabels` + `just report`
(or the one-shot `just rebuild`).
