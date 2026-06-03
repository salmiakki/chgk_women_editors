"""Marimo analyser for women-edited packs from gotquestions.online.

Reads the JSON payloads written by ``download.py`` (``data/packs/*.json``) and
explores the research question: *for tours edited by women, what are the
genders of the question authors?*

Run with:
    uv run marimo edit analysis.py      # interactive
    uv run marimo run analysis.py       # app view
"""

import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="ЧГК — women editors & question-author genders")


@app.cell
def _():
    import gzip
    import io
    import json
    import urllib.request
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import pandas as pd

    # `__file__` is undefined when running in the browser (WASM/Pyodide).
    try:
        HERE = Path(__file__).parent
    except NameError:
        HERE = Path(".")
    PACKS_DIR = HERE / "data" / "packs"
    WOMAN = "SE"  # woman's gender code on the site; "HE" is man

    # Human-readable column headers for displayed tables. The underlying frames
    # keep their snake_case names (used in code/charts); `pretty()` renames only
    # the copy passed to mo.ui.table, falling back to Title Case for anything
    # not listed here.
    LABELS = {
        "author_name": "Author",
        "author_gender": "Gender",
        "gender_adj": "Gender (corrected)",
        "credits": "Credits",
        "pct": "% of credits",
        "suspicion": "Suspicion",
        "confidence": "Confidence",
        "appearances": "Appearances",
        "author_questions": "Author questions",
        "editor_roles": "Editor roles",
        "name": "Name",
        "genders_tagged": "Tagged gender(s)",
        "tournaments_per_pack": "Tournaments per pack",
        "all_packs": "All packs",
        "woman_edited_packs": "Woman-edited packs",
        "tournament_type": "Tournament type",
        "tour_editor_kind": "Tour editorship",
        "tour_editor_kind_raw": "Tour editorship (raw)",
        "tours": "Tours",
        "questions": "Questions",
        "author_credits": "Author credits",
        "women_credits": "Women credits",
        "men_credits": "Men credits",
        "pct_women": "% women (raw)",
        "pct_women_corr": "% women (corrected)",
        "editor": "Editor",
        "collaborators": "Collaborators",
        "women_collaborators": "Women collaborators",
        "women_authors": "Women collaborators",
        "pct_women_collaborators": "% women collaborators",
        "women_credits": "Women-author credits",
        "men_credits": "Men-author credits",
        "self": "Self",
        "other_women": "Other women",
        "men": "Men",
        "pct_self": "% self",
        "pct_other_women": "% other women",
        "pct_men": "% men",
        "own_questions_only": "Own questions only",
        "pack_title": "Pack",
        "SE": "Women (SE)",
        "HE": "Men (HE)",
        "person_a": "Person A",
        "person_b": "Person B",
        "a_edits_b": "A edits B",
        "b_edits_a": "B edits A",
        "total": "Total",
    }

    def pretty(df):
        # Rename to human headers and promote the first column to the index, so
        # tables show a meaningful key on the left instead of a 0..N row number
        # (marimo 0.23.8 has no hide-index option).
        out = df.rename(
            columns=lambda c: LABELS.get(c, str(c).replace("_", " ").capitalize())
        )
        if len(out.columns):
            out = out.set_index(out.columns[0])
        return out

    return HERE, PACKS_DIR, WOMAN, alt, gzip, io, json, mo, pd, pretty, urllib


@app.cell
def _(mo):
    mo.md("""
    # ЧГК packs — editors, question-author genders & tournaments

    Source: `gotquestions.online`. `data/packs/` holds **every downloaded
    pack** (run `download.py packs --scope all`); the *woman-edited* subset
    (a pack with ≥1 editor of gender `SE`) is computed here and used by the
    gender-focused sections. Whole-corpus stats are shown alongside for
    comparison.

    Central question: *in tours edited by a woman, who writes the questions —
    and what is their gender?* Plus a structural look at how packs map to
    tournaments.

    *Prepared for Lesha Pak, using GotQuestions ([gotquestions.online](https://gotquestions.online)) data.
    Source & docs: [github.com/salmiakki/chgk_women_editors](https://github.com/salmiakki/chgk_women_editors).*

    *Note: this analysis uses only two genders (`HE` / `SE`) because that is the
    only gender information the source data records. No exclusion is intended —
    apologies to everyone this fails to represent.*
    """)
    return


@app.cell
def _(mo, urllib):
    # When was this built? For the static report, cells run at export time, so
    # now() is the regeneration time. For the WASM build (cells run in the
    # viewer's browser) we read a timestamp baked into public/ at build time.
    from datetime import datetime, timezone

    try:
        _u = str(mo.notebook_location() / "public" / "generated_at.txt")
        _generated = urllib.request.urlopen(_u).read().decode().strip()
    except Exception:
        _generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mo.md(f"*Regenerated: {_generated}*")
    return


@app.cell
def _(PACKS_DIR, gzip, json, mo, urllib):
    # Load pack payloads. Locally: the full JSON in data/packs/. When served as
    # a kernel-less WASM notebook (no local files), fall back to the baked,
    # reduced dataset shipped in public/ — fetched relative to the notebook via
    # mo.notebook_location() (works for both file:// dev and http hosting).
    _files = sorted(PACKS_DIR.glob("*.json"))
    if _files:
        packs = [json.loads(p.read_text(encoding="utf-8")) for p in _files]
    else:
        _url = str(mo.notebook_location() / "public" / "packs_reduced.json.gz")
        _raw = urllib.request.urlopen(_url).read()
        packs = json.loads(gzip.decompress(_raw).decode("utf-8"))
        # The reduced dataset drops question ids (they don't compress); the
        # question-id-based aggregations just need them unique, so synthesize.
        _qid = 0
        for _pk in packs:
            for _t in _pk.get("tours", []):
                for _q in _t.get("questions", []):
                    _q["id"] = _qid
                    _qid += 1
    return (packs,)


@app.cell
def _(HERE, io, mo, pd, urllib):
    # Load the mislabel list produced by `detect_mislabels.py` (regenerate with
    # `just mislabels`). Locally from output/; when served WASM-style, from the
    # baked copy in public/. Re-running picks up the latest corrections.
    #
    # gender_fix maps a name -> corrected gender, applied to the confidence
    # tiers in CORRECT_TIERS.
    CORRECT_TIERS = {"very high", "high", "medium"}
    _local = HERE / "output" / "mislabels_corrected.csv"
    try:
        if _local.exists():
            mislabels_df = pd.read_csv(_local)
        else:
            _url = str(mo.notebook_location() / "public" / "mislabels_corrected.csv")
            _text = urllib.request.urlopen(_url).read().decode("utf-8")
            mislabels_df = pd.read_csv(io.StringIO(_text))
    except Exception:
        mislabels_df = pd.DataFrame(
            columns=[
                "name",
                "suspicion",
                "confidence",
                "author_questions",
                "editor_roles",
                "genders_tagged",
            ]
        )
    _fix_to = {"woman_tagged_HE": "SE", "man_tagged_SE": "HE"}
    gender_fix = {
        row["name"]: _fix_to[row["suspicion"]]
        for _, row in mislabels_df.iterrows()
        if row["confidence"] in CORRECT_TIERS
    }
    return CORRECT_TIERS, gender_fix, mislabels_df


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    # Flatten to two tidy frames.
    #
    #  * questions_df — one row per question, with its tour/pack context and
    #    counts of authors by gender.
    #  * authors_df   — one row per (question, author): the exploded view used
    #    for gender tallies. Carries both the raw `author_gender` and the
    #    corrected `gender_adj` (HE->SE for high-confidence mislabels).
    #
    # A tour is "woman-edited" when any of its own editors is a woman. The
    # gender correction (HE->SE for high-confidence mislabels) is applied to
    # EVERYONE — editors and authors alike — so the corrected values are the
    # primary basis here; the raw `*_raw` columns are kept alongside so the
    # effect of the correction is visible. Tour editor lists are sometimes
    # empty (editing recorded only at pack level); a pack-level flag is kept too.

    def genders(people, corrected=False):
        if corrected:
            return [gender_fix.get(p.get("name"), p.get("gender")) for p in people or []]
        return [p.get("gender") for p in people or []]

    def has_woman(people, corrected=False):
        return any(g == WOMAN for g in genders(people, corrected))

    def editor_kind(people, corrected=False):
        # How is this tour's editorship composed? This makes mixed-gender tours
        # (>=1 woman AND >=1 man) a category of their own, instead of folding
        # them into "woman-edited" via the any()-style flag.
        gs = genders(people, corrected)
        if not gs:
            return "no editors"
        any_w = any(g == WOMAN for g in gs)
        any_m = any(g == "HE" for g in gs)
        if any_w and any_m:
            return "mixed"
        if any_w:
            return "women-only"
        if any_m:
            return "men-only"
        return "other/unknown"

    q_rows = []
    a_rows = []
    for pack in packs:
        pack_eds = pack.get("editors")
        pack_woman = has_woman(pack_eds, corrected=True)
        pack_woman_raw = has_woman(pack_eds, corrected=False)
        for tour in pack.get("tours", []):
            tour_eds = tour.get("editors", [])
            tour_woman = has_woman(tour_eds, corrected=True)
            tour_woman_raw = has_woman(tour_eds, corrected=False)
            tour_has_editors = bool(tour_eds)
            tour_kind = editor_kind(tour_eds, corrected=True)
            tour_kind_raw = editor_kind(tour_eds, corrected=False)
            for q in tour.get("questions", []):
                authors = q.get("authors", []) or []
                a_genders = genders(authors)
                a_genders_adj = [
                    gender_fix.get(a.get("name"), a.get("gender")) for a in authors
                ]
                q_rows.append(
                    {
                        "pack_id": pack["id"],
                        "pack_title": pack["title"],
                        "tour_id": tour["id"],
                        "tour_number": tour.get("number"),
                        "tour_has_editors": tour_has_editors,
                        "tour_woman_edited": tour_woman,
                        "tour_woman_edited_raw": tour_woman_raw,
                        "tour_editor_kind": tour_kind,
                        "tour_editor_kind_raw": tour_kind_raw,
                        "pack_woman_edited": pack_woman,
                        "pack_woman_edited_raw": pack_woman_raw,
                        "question_id": q["id"],
                        "question_number": q.get("number"),
                        "n_authors": len(authors),
                        "n_women_authors": sum(g == WOMAN for g in a_genders),
                        "n_men_authors": sum(g == "HE" for g in a_genders),
                        "n_women_authors_adj": sum(g == WOMAN for g in a_genders_adj),
                    }
                )
                for a in authors:
                    raw_g = a.get("gender")
                    a_rows.append(
                        {
                            "pack_id": pack["id"],
                            "pack_title": pack["title"],
                            "tour_id": tour["id"],
                            "tour_number": tour.get("number"),
                            "tour_woman_edited": tour_woman,
                            "tour_editor_kind": tour_kind,
                            "tour_editor_kind_raw": tour_kind_raw,
                            "pack_woman_edited": pack_woman,
                            "question_id": q["id"],
                            "author_id": a.get("id"),
                            "author_name": a.get("name"),
                            "author_gender": raw_g,
                            "gender_adj": gender_fix.get(a.get("name"), raw_g),
                        }
                    )

    questions_df = pd.DataFrame(q_rows)
    authors_df = pd.DataFrame(a_rows)
    return authors_df, questions_df


@app.cell
def _(mo):
    mo.md("""
    ## 1. Data coverage & gender-field audit
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    > **How credits are counted**
    >
    > - **Shared question credits** — stats are by *author credit*, one tally
    >   per (question, author). A question with two authors yields two credits
    >   (one per author's gender); it is never collapsed to a single author.
    >   ~97% of questions have one author, so this rarely shifts aggregates.
    > - **Shared tour editorship** — a tour is classified by its *whole* editor
    >   set (women-only / mixed / men-only). In the per-editor breakdowns a tour
    >   co-edited by several women counts **once for each** of them: the same
    >   questions are attributed to every co-editor, not split between them.
    > - **Self vs. collaborators** — "self" matches the author id to the editor
    >   id; distinct *collaborators* count unique author ids excluding the editor
    >   themselves, and "% women collaborators" is distinct women ÷ distinct
    >   collaborators.
    """)
    return


@app.cell
def _(authors_df, mo, packs, questions_df):
    n_tours = questions_df["tour_id"].nunique()

    def _npacks(col):
        return questions_df.loc[questions_df[col], "pack_id"].nunique()

    def _ntours(col):
        return questions_df.loc[questions_df[col], "tour_id"].nunique()

    n_woman_packs, n_woman_packs_raw = _npacks("pack_woman_edited"), _npacks(
        "pack_woman_edited_raw"
    )
    n_woman_tours, n_woman_tours_raw = _ntours("tour_woman_edited"), _ntours(
        "tour_woman_edited_raw"
    )
    empty_tour_eds = (~questions_df["tour_has_editors"]).sum()

    gender_counts = authors_df["author_gender"].value_counts(dropna=False)
    missing_author_gender = authors_df["author_gender"].isna().sum()
    no_author_qs = (questions_df["n_authors"] == 0).sum()

    mo.md(
        f"""
        **Whole corpus (all downloaded packs):**

        - **Packs:** {len(packs)} &nbsp;|&nbsp; **Tours:** {n_tours} &nbsp;|&nbsp;
          **Questions:** {len(questions_df)} &nbsp;|&nbsp;
          **Author credits:** {len(authors_df)}
        - Questions with **no author credited:** {no_author_qs}
        - Author credits **missing a gender value:** {missing_author_gender}

        **Woman-edited subset** (raw tag → after `HE→SE` correction of editors):

        - **Woman-edited packs:** {n_woman_packs_raw} → **{n_woman_packs}**
          ({n_woman_packs / len(packs):.1%} of packs)
        - **Woman-edited tours:** {n_woman_tours_raw} → **{n_woman_tours}**
          ({n_woman_tours / n_tours:.1%} of tours)
        - Question rows in tours with **no tour-level editor list:**
          {empty_tour_eds} (editing recorded only at pack level)

        **Author gender codes present:** `{dict(gender_counts)}`

        > ⚠️ The gender field is hand-entered and skews male — many women are
        > tagged `HE`. The corrected counts apply the high-confidence `HE→SE`
        > fixes from the audit below; raw values are shown alongside throughout.
        """
    )
    return


@app.cell
def _(authors_df, mo, pretty):
    # Per-author roster (name ↔ gender), handy for spotting mislabelled people.
    # Over the full corpus this is tens of thousands of authors, so the static
    # report shows only the top slice by credit count; the full frame stays in
    # `roster` for interactive querying.
    roster = (
        authors_df.groupby(["author_name", "author_gender"], dropna=False)
        .agg(credits=("question_id", "count"))
        .reset_index()
        .sort_values("credits", ascending=False)
        .reset_index(drop=True)
    )
    mo.vstack(
        [
            mo.md(
                f"Author roster — **{len(roster)}** distinct (name, gender) "
                "pairs; showing the top 500 by credits."
            ),
            mo.ui.table(pretty(roster.head(500)), label="Author roster (top 500)"),
        ]
    )
    return


@app.cell
def _(CORRECT_TIERS, gender_fix, mislabels_df, mo, pretty):
    # Suspected gender mislabels, loaded from output/mislabels_corrected.csv.
    _n_women = int((mislabels_df["suspicion"] == "woman_tagged_HE").sum())
    _n_men = int((mislabels_df["suspicion"] == "man_tagged_SE").sum())
    mo.vstack(
        [
            mo.md(
                f"""
                ### Suspected gender mislabels

                Loaded from `output/mislabels_corrected.csv` (regenerate with
                `just mislabels`). People whose name morphology contradicts
                their tag: **{_n_women}** look like women but are tagged `HE`,
                **{_n_men}** look like men but are tagged `SE` — the error is
                essentially one-directional (women under-tagged).

                The corrected views below override `HE → SE` for the
                **{sorted(CORRECT_TIERS)}** tiers ({len(gender_fix)} people) —
                i.e. every flagged suspect, since manual review confirmed they
                are all women. The correction is applied to **everyone —
                editors and authors** — so it reshapes both the woman-edited
                classification and the author tallies. Raw values are always
                shown alongside.
                """
            ),
            mo.ui.table(
                pretty(
                    mislabels_df[["name", "confidence", "author_questions", "editor_roles"]]
                ),
                label="Suspected mislabels (all tiers)",
            ),
        ]
    )
    return


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    # Pack- and tournament-level frames.
    #
    #  * packs_df       — one row per pack: editorship flag, tour/question
    #    counts, and how many distinct tournaments reference its questions.
    #  * tournaments_df — one row per (tournament, pack): id + type, for type
    #    tallies. (A tournament normally maps to a single pack.)
    #
    # `woman_edited` uses the corrected editor gender (HE->SE fixes applied).
    def build_pack_tournament_frames():
        prows = []
        trows = []
        for pk in packs:
            woman = any(
                gender_fix.get(e.get("name"), e.get("gender")) == WOMAN
                for e in pk.get("editors", [])
            )
            trn = {}
            n_q = 0
            n_t = 0
            for tour in pk.get("tours", []):
                n_t += 1
                for q in tour.get("questions", []):
                    n_q += 1
                    for tr in q.get("tournaments", []) or []:
                        trn[tr["id"]] = (tr.get("typeoft") or {}).get("title")
            prows.append(
                {
                    "pack_id": pk["id"],
                    "pack_title": pk["title"],
                    "woman_edited": woman,
                    "n_tours": n_t,
                    "n_questions": n_q,
                    "n_tournaments": len(trn),
                }
            )
            for tid, ty in trn.items():
                trows.append(
                    {
                        "tournament_id": tid,
                        "tournament_type": ty,
                        "pack_id": pk["id"],
                        "woman_edited": woman,
                    }
                )
        return pd.DataFrame(prows), pd.DataFrame(trows)

    packs_df, tournaments_df = build_pack_tournament_frames()
    return packs_df, tournaments_df


@app.cell
def _(mo):
    mo.md("""
    ## 2. Packs ↔ tournaments

    A **pack** is one question set; a **tournament** is a scheduled *run* of
    it. A pack commonly maps to more than one tournament — typically a
    synchronous (`Синхрон`) live run **plus** an asynchronous/online run of the
    same questions — and some packs carry no tournament reference at all. Stats
    for the whole corpus, with the woman-edited subset alongside.
    """)
    return


@app.cell
def _(mo, packs_df, pd, pretty, tournaments_df):
    _all_d = packs_df["n_tournaments"].value_counts().sort_index()
    _w_d = (
        packs_df[packs_df.woman_edited]["n_tournaments"].value_counts().sort_index()
    )
    per_pack = (
        pd.DataFrame({"all_packs": _all_d, "woman_edited_packs": _w_d})
        .fillna(0)
        .astype(int)
        .rename_axis("tournaments_per_pack")
        .reset_index()
    )
    n_distinct = tournaments_df["tournament_id"].nunique()
    n_distinct_w = tournaments_df.loc[
        tournaments_df.woman_edited, "tournament_id"
    ].nunique()
    mo.vstack(
        [
            mo.md(
                f"**Packs:** {len(packs_df)} "
                f"({int(packs_df.woman_edited.sum())} woman-edited) &nbsp;|&nbsp; "
                f"**tours:** {int(packs_df.n_tours.sum())} "
                f"({int(packs_df[packs_df.woman_edited].n_tours.sum())} in woman-edited packs) "
                f"&nbsp;|&nbsp; **distinct tournaments:** {n_distinct} "
                f"({n_distinct_w} in woman-edited packs) &nbsp;|&nbsp; "
                f"packs with ≥2 tournaments: {int((packs_df.n_tournaments >= 2).sum())} "
                f"&nbsp;|&nbsp; with 0: {int((packs_df.n_tournaments == 0).sum())}"
            ),
            mo.ui.table(pretty(per_pack), label="Tournaments per pack"),
        ]
    )
    return


@app.cell
def _(alt, mo, packs_df, pd):
    # Woman-edited packs (250) vs everything else (~6.5k) can't be compared by
    # raw counts — the bars for the small group vanish. Normalise to the % of
    # packs *within each scope*, bucketed 0/1/2/3+, so the two distributions are
    # directly comparable.
    _bucket = packs_df["n_tournaments"].clip(upper=3).map({0: "0", 1: "1", 2: "2", 3: "3+"})
    _df = packs_df.assign(
        scope=packs_df.woman_edited.map({True: "woman-edited", False: "other packs"}),
        bucket=_bucket,
    )
    _g = _df.groupby(["scope", "bucket"]).size().rename("packs").reset_index()
    _g["pct"] = (100 * _g["packs"] / _g.groupby("scope")["packs"].transform("sum")).round(1)
    tour_chart = (
        alt.Chart(_g)
        .mark_bar()
        .encode(
            x=alt.X("bucket:N", sort=["0", "1", "2", "3+"], title="tournaments per pack"),
            y=alt.Y("pct:Q", title="% of packs in scope"),
            color=alt.Color("scope:N", title=None),
            xOffset="scope:N",
            tooltip=["scope", "bucket", "packs", "pct"],
        )
        .properties(
            width=420,
            height=260,
            title="Tournaments per pack (normalised within scope)",
        )
    )
    mo.ui.altair_chart(tour_chart)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Author genders by tour-editor composition

    Each tour is classified by who edited it: **women-only**, **mixed** (at
    least one woman *and* one man), **men-only**, or **no editors** (editing
    recorded only at pack level). Below, the author-credit gender mix in each.

    > Note: a tour counts as a given category by its *own* editor list, using
    > the **corrected** editor gender (so some tours that look men-only by the
    > raw tag move into *mixed* / *women-only* here). `tour_editor_kind_raw`
    > keeps the uncorrected classification.
    >
    > `pct_women` is the raw author tag; `pct_women_corr` applies the same
    > high-confidence `HE → SE` correction to authors.
    """)
    return


@app.cell
def _(authors_df, pd):
    def mix(df):
        vc = df["author_gender"].value_counts(dropna=False)
        vc_adj = df["gender_adj"].value_counts(dropna=False)
        total = vc.sum()
        return pd.Series(
            {
                "tours": df["tour_id"].nunique(),
                "author_credits": int(total),
                "women_credits": int(vc.get("SE", 0)),
                "men_credits": int(vc.get("HE", 0)),
                "pct_women": round(100 * vc.get("SE", 0) / total, 1) if total else 0,
                "pct_women_corr": (
                    round(100 * vc_adj.get("SE", 0) / total, 1) if total else 0
                ),
            }
        )

    _order = ["women-only", "mixed", "men-only", "no editors", "other/unknown"]
    comparison = (
        authors_df.groupby("tour_editor_kind")
        .apply(mix, include_groups=False)
        .reset_index()
    )
    comparison["_o"] = comparison["tour_editor_kind"].map(
        {k: i for i, k in enumerate(_order)}
    )
    comparison = comparison.sort_values("_o").drop(columns="_o").reset_index(drop=True)
    return (comparison,)


@app.cell
def _(comparison, mo, pretty):
    mo.ui.table(pretty(comparison), label="Author-gender mix by tour-editor composition")
    return


@app.cell
def _(alt, comparison, mo):
    # Raw vs corrected (HE->SE) share of women authors, grouped per category.
    _long = comparison.melt(
        id_vars=["tour_editor_kind"],
        value_vars=["pct_women", "pct_women_corr"],
        var_name="measure",
        value_name="pct",
    )
    _long["measure"] = _long["measure"].map(
        {"pct_women": "raw", "pct_women_corr": "corrected"}
    )
    chart = (
        alt.Chart(_long)
        .mark_bar()
        .encode(
            x=alt.X(
                "tour_editor_kind:N",
                title=None,
                sort=["women-only", "mixed", "men-only", "no editors"],
            ),
            y=alt.Y("pct:Q", title="% of author credits that are women"),
            color=alt.Color("measure:N", title=None),
            xOffset="measure:N",
            tooltip=["tour_editor_kind", "measure", "pct"],
        )
        .properties(width=420, height=260, title="Share of women authors (raw vs corrected)")
    )
    mo.ui.altair_chart(chart)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. Each woman editor: own vs. other women vs. men

    For every woman editor, looking only at tours **she personally edited**
    (matched by editor id), how are the question-author credits split between:

    - **self** — questions she (co-)authored herself,
    - **other women** — questions by *other* `SE` authors,
    - **men** — questions by `HE` authors.

    This separates editors who mostly run their own questions from those who
    source heavily from other women, or mostly from men. Credits, not
    questions: a question with two authors contributes two credits.
    """)
    return


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    def build_editor_breakdown():
        # Walk editor -> tour -> question -> author, attributing each author
        # credit relative to the woman editor whose tour it is. A tour
        # co-edited by several women contributes to each of them.
        #
        # "self" is matched by author id (gender-independent). The other-women
        # vs men split uses the corrected gender (HE->SE for the mislabels),
        # which is the analysis basis throughout.
        stats = {}
        names = {}
        for pk in packs:
            for tour in pk.get("tours", []):
                women_eds = [
                    (e["id"], e.get("name"))
                    for e in tour.get("editors", [])
                    if gender_fix.get(e.get("name"), e.get("gender")) == WOMAN
                ]
                if not women_eds:
                    continue
                for eid, ename in women_eds:
                    names[eid] = ename
                    s = stats.setdefault(
                        eid,
                        {
                            "tours": set(),
                            "questions": set(),
                            "self": 0,
                            "other_women": 0,
                            "men": 0,
                            "other": 0,
                            "women_ids": set(),
                            "collab_ids": set(),
                        },
                    )
                    s["tours"].add(tour["id"])
                    for q in tour.get("questions", []):
                        s["questions"].add(q["id"])
                        for a in q.get("authors", []) or []:
                            if a.get("id") == eid:
                                s["self"] += 1
                                continue
                            s["collab_ids"].add(a.get("id"))
                            g_adj = gender_fix.get(a.get("name"), a.get("gender"))
                            if g_adj == WOMAN:
                                s["other_women"] += 1
                                s["women_ids"].add(a.get("id"))
                            elif g_adj == "HE":
                                s["men"] += 1
                            else:
                                s["other"] += 1
        rows = []
        for eid, s in stats.items():
            credits = s["self"] + s["other_women"] + s["men"] + s["other"]
            denom = credits or 1
            rows.append(
                {
                    "editor": names[eid],
                    "tours": len(s["tours"]),
                    "questions": len(s["questions"]),
                    "credits": credits,
                    "collaborators": len(s["collab_ids"]),
                    "women_collaborators": len(s["women_ids"]),
                    "pct_women_collaborators": round(
                        100 * len(s["women_ids"]) / (len(s["collab_ids"]) or 1), 1
                    ),
                    "self": s["self"],
                    "other_women": s["other_women"],
                    "men": s["men"],
                    "pct_self": round(100 * s["self"] / denom, 1),
                    "pct_other_women": round(100 * s["other_women"] / denom, 1),
                    "pct_men": round(100 * s["men"] / denom, 1),
                    # only women's questions: no men authors, no unknown-gender
                    # authors, and at least one credit.
                    "women_only": credits > 0 and s["men"] == 0 and s["other"] == 0,
                }
            )
        return pd.DataFrame(rows).sort_values("credits", ascending=False).reset_index(
            drop=True
        )

    editor_breakdown = build_editor_breakdown()
    return (editor_breakdown,)


@app.cell
def _(editor_breakdown, mo, pretty):
    mo.ui.table(
        pretty(editor_breakdown),
        label="Per woman editor: self / other-women / men author credits",
    )
    return


@app.cell
def _(alt, editor_breakdown, mo):
    # Chart the most prolific woman editors (by credits) — after correcting
    # editor gender there can be many, so cap to keep the bars readable.
    TOP_N = 30
    _top = editor_breakdown.nlargest(TOP_N, "credits")
    _long = _top.melt(
        id_vars=["editor", "credits"],
        value_vars=["pct_self", "pct_other_women", "pct_men"],
        var_name="source",
        value_name="pct",
    )
    _long["source"] = _long["source"].map(
        {"pct_self": "self", "pct_other_women": "other women", "pct_men": "men"}
    )
    # Sort by total share of women authors (self + other women) descending,
    # then by % self as a tiebreaker — so the most women-sourced editors are at
    # the top, and among ties the more self-reliant ones rank higher.
    _editor_order = (
        _top.assign(pct_women=_top["pct_self"] + _top["pct_other_women"])
        .sort_values(["pct_women", "pct_self"], ascending=[False, False])["editor"]
        .tolist()
    )
    ed_chart = (
        alt.Chart(_long)
        .mark_bar()
        .encode(
            y=alt.Y("editor:N", sort=_editor_order, title=None),
            x=alt.X("pct:Q", title="% of author credits", stack="zero"),
            color=alt.Color(
                "source:N",
                title="author",
                scale=alt.Scale(
                    domain=["self", "other women", "men"],
                    range=["#1b7837", "#7fbf7b", "#9e9ac8"],
                ),
            ),
            tooltip=["editor", "source", "pct", "credits"],
        )
        .properties(
            width=460,
            height=24 * len(_top),
            title=f"Author source mix — top {TOP_N} woman editors by credits",
        )
    )
    mo.ui.altair_chart(ed_chart)
    return


@app.cell
def _(alt, editor_breakdown, mo):
    # Same author-source mix and formatting as the top-30 chart above, but for
    # ALL woman editors (no cap). One labelled 24px bar each, sorted by total
    # women share; tall, so scroll. Hover for exact percentages.
    _all_long = editor_breakdown.melt(
        id_vars=["editor", "credits"],
        value_vars=["pct_self", "pct_other_women", "pct_men"],
        var_name="source",
        value_name="pct",
    )
    _all_long["source"] = _all_long["source"].map(
        {"pct_self": "self", "pct_other_women": "other women", "pct_men": "men"}
    )
    _all_order = (
        editor_breakdown.assign(
            pct_women=editor_breakdown["pct_self"] + editor_breakdown["pct_other_women"]
        )
        .sort_values(["pct_women", "pct_self"], ascending=[False, False])["editor"]
        .tolist()
    )
    ed_chart_all = (
        alt.Chart(_all_long)
        .mark_bar()
        .encode(
            y=alt.Y("editor:N", sort=_all_order, title=None),
            x=alt.X("pct:Q", title="% of author credits", stack="zero"),
            color=alt.Color(
                "source:N",
                title="author",
                scale=alt.Scale(
                    domain=["self", "other women", "men"],
                    range=["#1b7837", "#7fbf7b", "#9e9ac8"],
                ),
            ),
            tooltip=["editor", "source", "pct", "credits"],
        )
        .properties(
            width=460,
            height=24 * len(_all_order),
            title=f"Author source mix — all {len(_all_order)} woman editors",
        )
    )
    mo.ui.altair_chart(ed_chart_all)
    return


@app.cell
def _(mo):
    mo.md("""
    ### Woman editors who use *only* women's questions

    Editors whose tours have **zero** men authors and no unknown-gender authors
    (corrected) — every question is by a woman (the editor herself and/or other
    women). Listed in full below, sorted by author credits.
    """)
    return


@app.cell
def _(editor_breakdown, mo, pretty):
    women_only_editors = editor_breakdown[editor_breakdown["women_only"]].copy()
    # Within the women-only group, who uses ONLY their own questions (no other
    # authors at all) vs. those who also source from other women.
    women_only_editors["own_questions_only"] = women_only_editors["other_women"] == 0
    women_only_editors = women_only_editors.sort_values(
        ["own_questions_only", "credits"], ascending=[False, False]
    ).reset_index(drop=True)
    _cols = [
        "editor",
        "tours",
        "questions",
        "credits",
        "women_collaborators",
        "pct_self",
        "pct_other_women",
        "own_questions_only",
    ]
    _own = women_only_editors[women_only_editors["own_questions_only"]]["editor"].tolist()
    _other = women_only_editors[~women_only_editors["own_questions_only"]]["editor"].tolist()
    mo.vstack(
        [
            mo.md(
                f"**{len(women_only_editors)}** woman editors use only women's "
                f"questions. Of those, **{len(_own)}** use **only their own** "
                "questions (no other authors at all):\n\n"
                f"**Own questions only ({len(_own)}):** {'; '.join(_own)}\n\n"
                f"**Own + other women ({len(_other)}):** {'; '.join(_other)}"
            ),
            mo.ui.table(
                pretty(women_only_editors[_cols]),
                label="Woman editors using only women's questions "
                "(own_questions_only flags the self-only ones)",
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Authors who contribute most to woman-edited tours

    Across all tours edited by a woman (corrected), which authors supply the
    most questions — by absolute author credits and as a share of all credits
    in woman-edited tours — split by gender (corrected).

    **Two views:**

    - **(a) All authors** — every credit in woman-edited tours. Note this is
      dominated by editor/authors writing in *their own* tours (e.g. Мария
      Подрядчикова's credits are ~all self-edited), so it reflects authorship
      volume, not collaboration.
    - **(b) Collaborators only** — excludes credits where the author also
      *edited* that tour, leaving genuine outside contributors to women's
      tours.
    """)
    return


@app.cell
def _(authors_df, pd):
    # Author credits within woman-edited tours only.
    _sub = authors_df[authors_df["tour_woman_edited"]]
    _total = len(_sub)
    contrib = (
        _sub.groupby(["author_name", "gender_adj"])
        .size()
        .rename("credits")
        .reset_index()
    )
    contrib["pct"] = (100 * contrib["credits"] / (_total or 1)).round(2)
    contrib = contrib.sort_values("credits", ascending=False).reset_index(drop=True)
    women_contrib = contrib[contrib["gender_adj"] == "SE"].reset_index(drop=True)
    men_contrib = contrib[contrib["gender_adj"] == "HE"].reset_index(drop=True)
    return contrib, men_contrib, women_contrib


@app.cell
def _(men_contrib, mo, pretty, women_contrib):
    mo.vstack(
        [
            mo.md(
                f"**(a) All authors** — **{len(women_contrib)}** distinct women, "
                f"**{len(men_contrib)}** distinct men in woman-edited tours. "
                "`pct` = share of all author credits in woman-edited tours."
            ),
            mo.ui.table(
                pretty(women_contrib.head(100)[["author_name", "credits", "pct"]]),
                label="(a) Top women authors in woman-edited tours",
            ),
            mo.ui.table(
                pretty(men_contrib.head(100)[["author_name", "credits", "pct"]]),
                label="(a) Top men authors in woman-edited tours",
            ),
        ]
    )
    return


@app.cell
def _(alt, men_contrib, mo, women_contrib):
    def _bar(df, title, color):
        _top = df.head(20)
        return (
            alt.Chart(_top)
            .mark_bar(color=color)
            .encode(
                y=alt.Y("author_name:N", sort=_top["author_name"].tolist(), title=None),
                x=alt.X("credits:Q", title="author credits in woman-edited tours"),
                tooltip=["author_name", "credits", "pct"],
            )
            .properties(width=420, height=24 * len(_top), title=title)
        )

    mo.hstack(
        [
            mo.ui.altair_chart(_bar(women_contrib, "(a) Top 20 women authors", "#7fbf7b")),
            mo.ui.altair_chart(_bar(men_contrib, "(a) Top 20 men authors", "#9e9ac8")),
        ],
        widths="equal",
    )
    return


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    # (b) Collaborators only: credits in woman-edited tours where the author did
    # NOT also edit that tour — i.e. genuine outside contributors, dropping the
    # editor-authors-in-their-own-tour self-contribution.
    _rows = []
    for _pk in packs:
        for _t in _pk.get("tours", []):
            _eds = _t.get("editors", [])
            if not any(
                gender_fix.get(e.get("name"), e.get("gender")) == WOMAN for e in _eds
            ):
                continue
            _ed_ids = {e.get("id") for e in _eds}
            for _q in _t.get("questions", []):
                for _a in _q.get("authors", []) or []:
                    if _a.get("id") in _ed_ids:
                        continue  # author edited this tour → not a collaborator
                    _rows.append(
                        (_a.get("name"), gender_fix.get(_a.get("name"), _a.get("gender")))
                    )
    _df = pd.DataFrame(_rows, columns=["author_name", "gender_adj"])
    _total = len(_df)
    contrib_collab = (
        _df.groupby(["author_name", "gender_adj"]).size().rename("credits").reset_index()
    )
    contrib_collab["pct"] = (100 * contrib_collab["credits"] / (_total or 1)).round(2)
    contrib_collab = contrib_collab.sort_values("credits", ascending=False).reset_index(
        drop=True
    )
    women_collab = contrib_collab[contrib_collab["gender_adj"] == "SE"].reset_index(drop=True)
    men_collab = contrib_collab[contrib_collab["gender_adj"] == "HE"].reset_index(drop=True)
    return men_collab, women_collab


@app.cell
def _(men_collab, mo, pretty, women_collab):
    mo.vstack(
        [
            mo.md(
                "**(b) Collaborators only** — excludes credits where the author "
                "also edited the tour. `pct` = share of all collaborator credits "
                "in woman-edited tours."
            ),
            mo.ui.table(
                pretty(women_collab.head(100)[["author_name", "credits", "pct"]]),
                label="(b) Top women collaborators (excl. own-edited tours)",
            ),
            mo.ui.table(
                pretty(men_collab.head(100)[["author_name", "credits", "pct"]]),
                label="(b) Top men collaborators (excl. own-edited tours)",
            ),
        ]
    )
    return


@app.cell
def _(alt, men_collab, mo, women_collab):
    def _bar(df, title, color):
        _top = df.head(20)
        return (
            alt.Chart(_top)
            .mark_bar(color=color)
            .encode(
                y=alt.Y("author_name:N", sort=_top["author_name"].tolist(), title=None),
                x=alt.X("credits:Q", title="collaborator credits in woman-edited tours"),
                tooltip=["author_name", "credits", "pct"],
            )
            .properties(width=420, height=24 * len(_top), title=title)
        )

    mo.hstack(
        [
            mo.ui.altair_chart(_bar(women_collab, "(b) Top 20 women collaborators", "#7fbf7b")),
            mo.ui.altair_chart(_bar(men_collab, "(b) Top 20 men collaborators", "#9e9ac8")),
        ],
        widths="equal",
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6. Explore by individual woman editor

    Pick a woman editor to see the tours she edited and the gender mix of
    the questions' authors in those tours.
    """)
    return


@app.cell
def _(WOMAN, gender_fix, mo, packs):
    # Women editors by corrected gender (HE->SE fixes applied), sorted by last
    # name (last token), then full name.
    women_editors = sorted(
        {
            e["name"]
            for pk in packs
            for e in pk.get("editors", [])
            if gender_fix.get(e.get("name"), e.get("gender")) == WOMAN
        },
        key=lambda n: (n.split()[-1] if n.split() else n, n),
    )
    editor_select = mo.ui.dropdown(
        options=women_editors,
        value=women_editors[0] if women_editors else None,
        label="Woman editor",
    )
    editor_select
    return (editor_select,)


@app.cell
def _(WOMAN, authors_df, editor_select, gender_fix, mo, packs, pretty):
    # Tour ids this editor personally edited (corrected gender).
    sel = editor_select.value
    tour_ids = {
        tour["id"]
        for pk in packs
        for tour in pk.get("tours", [])
        if any(
            e.get("name") == sel
            and gender_fix.get(e.get("name"), e.get("gender")) == WOMAN
            for e in tour.get("editors", [])
        )
    }

    sub = authors_df[authors_df["tour_id"].isin(tour_ids)]
    if sub.empty:
        out = mo.md(
            f"**{sel}** has no *tour-level* editor credits in the data "
            "(she may be credited only at pack level)."
        )
    else:
        vc = sub["author_gender"].value_counts(dropna=False)
        by_pack = (
            sub.groupby("pack_title")["author_gender"]
            .value_counts()
            .unstack(fill_value=0)
            .reset_index()
        )
        out = mo.vstack(
            [
                mo.md(
                    f"**{sel}** — {len(tour_ids)} tour(s), "
                    f"{sub['question_id'].nunique()} questions, "
                    f"{len(sub)} author credits "
                    f"({vc.get('SE', 0)} women / {vc.get('HE', 0)} men)."
                ),
                mo.ui.table(pretty(by_pack), label="Author gender by pack"),
            ]
        )
    out
    return


@app.cell
def _(mo):
    mo.md("""
    ## 7. Men editors & their women-author collaborations

    For each **man editor** (corrected gender), across tours he personally
    edited: total author credits, how many of those credits are women authors,
    and how many *distinct* women authors he worked with. Three charts below —
    top 30 by **total credits** (high-volume editors), by **women-author
    credits** (volume of collaboration with women), and by **distinct women
    authors** (breadth of collaboration).
    """)
    return


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    def build_man_editor_breakdown():
        # Mirror of the woman-editor breakdown, for man editors (corrected
        # gender == HE). Tallies the genders of the authors in their tours.
        stats = {}
        names = {}
        for pk in packs:
            for tour in pk.get("tours", []):
                men_eds = [
                    (e["id"], e.get("name"))
                    for e in tour.get("editors", [])
                    if gender_fix.get(e.get("name"), e.get("gender")) == "HE"
                ]
                if not men_eds:
                    continue
                for eid, ename in men_eds:
                    names[eid] = ename
                    s = stats.setdefault(
                        eid,
                        {
                            "tours": set(),
                            "women": 0,
                            "men": 0,
                            "other": 0,
                            "women_ids": set(),
                            "collab_ids": set(),
                        },
                    )
                    s["tours"].add(tour["id"])
                    for q in tour.get("questions", []):
                        for a in q.get("authors", []) or []:
                            aid = a.get("id")
                            g = gender_fix.get(a.get("name"), a.get("gender"))
                            if g == WOMAN:
                                s["women"] += 1
                            elif g == "HE":
                                s["men"] += 1
                            else:
                                s["other"] += 1
                            # distinct collaborators exclude the editor himself
                            if aid != eid:
                                s["collab_ids"].add(aid)
                                if g == WOMAN:
                                    s["women_ids"].add(aid)
        rows = []
        for eid, s in stats.items():
            credits = s["women"] + s["men"] + s["other"]
            denom = credits or 1
            rows.append(
                {
                    "editor": names[eid],
                    "tours": len(s["tours"]),
                    "credits": credits,
                    "women_credits": s["women"],
                    "men_credits": s["men"],
                    "women_authors": len(s["women_ids"]),
                    "collaborators": len(s["collab_ids"]),
                    "pct_women_collaborators": round(
                        100 * len(s["women_ids"]) / (len(s["collab_ids"]) or 1), 1
                    ),
                    "pct_women": round(100 * s["women"] / denom, 1),
                }
            )
        return pd.DataFrame(rows).sort_values("credits", ascending=False).reset_index(
            drop=True
        )

    man_editor_breakdown = build_man_editor_breakdown()
    return (man_editor_breakdown,)


@app.cell
def _(man_editor_breakdown, mo, pretty):
    mo.ui.table(
        pretty(man_editor_breakdown.nlargest(100, "women_credits").reset_index(drop=True)),
        label="Man editors by women-author credits (top 100)",
    )
    return


@app.cell
def _(alt, man_editor_breakdown, mo):
    # Top 30 man editors by TOTAL author credits — bar split women vs men authors.
    _top = man_editor_breakdown.nlargest(30, "credits")
    _long = _top.melt(
        id_vars=["editor", "credits", "tours", "women_authors"],
        value_vars=["women_credits", "men_credits"],
        var_name="author",
        value_name="n",
    )
    _long["author"] = _long["author"].map(
        {"women_credits": "women authors", "men_credits": "men authors"}
    )
    _order = _top.sort_values("credits", ascending=False)["editor"].tolist()
    chart_credits = (
        alt.Chart(_long)
        .mark_bar()
        .encode(
            y=alt.Y("editor:N", sort=_order, title=None),
            x=alt.X("n:Q", title="author credits", stack="zero"),
            color=alt.Color(
                "author:N",
                title=None,
                scale=alt.Scale(
                    domain=["women authors", "men authors"],
                    range=["#7fbf7b", "#9e9ac8"],
                ),
            ),
            tooltip=["editor", "author", "n", "credits", "women_authors", "tours"],
        )
        .properties(
            width=460,
            height=24 * len(_top),
            title="Men editors — top 30 by total credits (women vs men authors)",
        )
    )
    mo.ui.altair_chart(chart_credits)
    return


@app.cell
def _(alt, man_editor_breakdown, mo):
    # Top 30 man editors by WOMEN-AUTHOR credits — who collaborates most with women.
    _top = man_editor_breakdown.nlargest(30, "women_credits")
    _order = _top.sort_values("women_credits", ascending=False)["editor"].tolist()
    chart_women = (
        alt.Chart(_top)
        .mark_bar(color="#7fbf7b")
        .encode(
            y=alt.Y("editor:N", sort=_order, title=None),
            x=alt.X("women_credits:Q", title="women-author credits"),
            tooltip=[
                "editor",
                "women_credits",
                "women_authors",
                "credits",
                "pct_women",
                "tours",
            ],
        )
        .properties(
            width=460,
            height=24 * len(_top),
            title="Men editors — top 30 by women-author credits",
        )
    )
    mo.ui.altair_chart(chart_women)
    return


@app.cell
def _(alt, man_editor_breakdown, mo):
    # Top 30 man editors by DISTINCT women authors collaborated with.
    _top = man_editor_breakdown.nlargest(30, "women_authors")
    _order = _top.sort_values("women_authors", ascending=False)["editor"].tolist()
    chart_distinct = (
        alt.Chart(_top)
        .mark_bar(color="#1b7837")
        .encode(
            y=alt.Y("editor:N", sort=_order, title=None),
            x=alt.X("women_authors:Q", title="distinct women authors"),
            tooltip=[
                "editor",
                "women_authors",
                "women_credits",
                "credits",
                "pct_women",
                "tours",
            ],
        )
        .properties(
            width=460,
            height=24 * len(_top),
            title="Men editors — top 30 by distinct women authors",
        )
    )
    mo.ui.altair_chart(chart_distinct)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 8. Frequent collaborator pairs

    Recurring **(woman editor → author)** partnerships: within tours a woman
    edited, which authors supply questions again and again (counting questions
    per pair, excluding her own). Split by author gender (corrected) — the most
    frequent woman-editor ↔ **woman-author** pairs and woman-editor ↔
    **man-author** pairs.
    """)
    return


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    _TEAM = {"Команда", "Команды", "Сборная", "Дуэт", "Группа", "Клуб", "Гильдия", "Лига", "Дети"}

    def _is_person(n):
        t = (n or "").split()
        return bool(t) and t[0] not in _TEAM and "«" not in n

    # Pairs are keyed by (editor_id, author_id) so same-named people are not
    # conflated; names/genders are resolved per id afterwards.
    _rows = []
    _id_name = {}
    _id_gender = {}
    for _pk in packs:
        for _t in _pk.get("tours", []):
            _weds = [
                e["id"]
                for e in _t.get("editors", [])
                if gender_fix.get(e.get("name"), e.get("gender")) == WOMAN
                and (_id_name.setdefault(e["id"], e.get("name")) or True)
            ]
            if not _weds:
                continue
            for _q in _t.get("questions", []):
                for _a in _q.get("authors", []) or []:
                    _aid, _an = _a.get("id"), _a.get("name")
                    if _aid is None or not _is_person(_an):
                        continue
                    _id_name.setdefault(_aid, _an)
                    _id_gender.setdefault(_aid, gender_fix.get(_an, _a.get("gender")))
                    for _eid in _weds:
                        if _aid != _eid:
                            _rows.append((_eid, _aid))
    collab_pairs = (
        pd.DataFrame(_rows, columns=["editor_id", "author_id"])
        .groupby(["editor_id", "author_id"])
        .size()
        .rename("questions")
        .reset_index()
    )
    collab_pairs["editor"] = collab_pairs["editor_id"].map(_id_name)
    collab_pairs["author"] = collab_pairs["author_id"].map(_id_name)
    collab_pairs["author_gender"] = collab_pairs["author_id"].map(_id_gender)
    collab_pairs = collab_pairs.sort_values("questions", ascending=False).reset_index(
        drop=True
    )
    women_pairs = collab_pairs[collab_pairs.author_gender == WOMAN].reset_index(drop=True)
    men_pairs = collab_pairs[collab_pairs.author_gender == "HE"].reset_index(drop=True)

    # Reciprocal woman↔woman pairs: both edit each other's questions. Surfaces
    # who edits whom (the two directions side by side). Only women-women pairs
    # can be reciprocal (men aren't woman editors here).
    _directed = {
        (r.editor_id, r.author_id): r.questions
        for r in women_pairs.itertuples(index=False)
    }
    _recip = {}
    for (_e, _a), _n in _directed.items():
        _key = (_e, _a) if _e < _a else (_a, _e)
        _recip.setdefault(_key, {})[(_e, _a)] = _n
    _recip_rows = []
    for (_i, _j), _d in _recip.items():
        _ij, _ji = _d.get((_i, _j), 0), _d.get((_j, _i), 0)
        if _ij > 0 and _ji > 0:
            _recip_rows.append([_id_name.get(_i), _id_name.get(_j), _ij, _ji, _ij + _ji])
    reciprocal_women = (
        pd.DataFrame(
            _recip_rows,
            columns=["person_a", "person_b", "a_edits_b", "b_edits_a", "total"],
        )
        .sort_values("total", ascending=False)
        .reset_index(drop=True)
    )
    return men_pairs, reciprocal_women, women_pairs


@app.cell
def _(men_pairs, mo, pretty, reciprocal_women, women_pairs):
    _cols = ["editor", "author", "questions"]
    mo.vstack(
        [
            mo.md(
                f"**{len(women_pairs)}** distinct woman-editor ↔ woman-author pairs, "
                f"**{len(men_pairs)}** woman-editor ↔ man-author pairs "
                "(in woman-edited tours). Top 40 each by shared questions."
            ),
            mo.ui.table(
                pretty(women_pairs.head(40)[_cols]),
                label="Top woman-editor ↔ woman-author pairs",
            ),
            mo.ui.table(
                pretty(men_pairs.head(40)[_cols]),
                label="Top woman-editor ↔ man-author pairs",
            ),
            mo.md(
                "**Reciprocal women** — pairs who edit *each other*. "
                "`a_edits_b` = questions A edited that B wrote, and vice versa, "
                "showing who edits whom more."
            ),
            mo.ui.table(
                pretty(reciprocal_women.head(40)),
                label="Reciprocal woman ↔ woman pairs (both directions)",
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 9. Co-editor pairs (≥ 1 woman)

    People who **edit the same tour together**, counted by number of tours
    co-edited — restricted to pairs with at least one woman (corrected). Matched
    by id; split into woman ↔ woman and woman ↔ man co-editor pairs.
    """)
    return


@app.cell
def _(WOMAN, gender_fix, packs, pd):
    _TEAM = {"Команда", "Команды", "Сборная", "Дуэт", "Группа", "Клуб", "Гильдия", "Лига", "Дети"}

    def _is_person(n):
        t = (n or "").split()
        return bool(t) and t[0] not in _TEAM and "«" not in n

    _pair_tours = {}
    _id_name, _id_gender = {}, {}
    for _pk in packs:
        for _t in _pk.get("tours", []):
            _eds = {}
            for e in _t.get("editors", []):
                _eid, _en = e.get("id"), e.get("name")
                if _eid is None or not _is_person(_en):
                    continue
                _g = gender_fix.get(_en, e.get("gender"))
                _id_name.setdefault(_eid, _en)
                _id_gender.setdefault(_eid, _g)
                _eds[_eid] = _g
            _ids = list(_eds)
            for _i in range(len(_ids)):
                for _j in range(_i + 1, len(_ids)):
                    _a, _b = _ids[_i], _ids[_j]
                    if _eds[_a] != WOMAN and _eds[_b] != WOMAN:
                        continue  # need at least one woman
                    _key = (_a, _b) if _a < _b else (_b, _a)
                    _pair_tours[_key] = _pair_tours.get(_key, 0) + 1
    _rows = []
    for (_a, _b), _n in _pair_tours.items():
        _both_women = _id_gender[_a] == WOMAN and _id_gender[_b] == WOMAN
        _rows.append(
            [_id_name[_a], _id_name[_b], "woman ↔ woman" if _both_women else "woman ↔ man", _n]
        )
    coeditor_pairs = (
        pd.DataFrame(_rows, columns=["person_a", "person_b", "kind", "tours"])
        .sort_values("tours", ascending=False)
        .reset_index(drop=True)
    )
    coed_ww = coeditor_pairs[coeditor_pairs.kind == "woman ↔ woman"].reset_index(drop=True)
    coed_wm = coeditor_pairs[coeditor_pairs.kind == "woman ↔ man"].reset_index(drop=True)
    return coed_wm, coed_ww


@app.cell
def _(coed_wm, coed_ww, mo, pretty):
    _cols = ["person_a", "person_b", "tours"]
    mo.vstack(
        [
            mo.md(
                f"**{len(coed_ww)}** woman ↔ woman co-editor pairs, "
                f"**{len(coed_wm)}** woman ↔ man co-editor pairs. "
                "Top 40 each by tours co-edited."
            ),
            mo.ui.table(
                pretty(coed_ww.head(40)[_cols]),
                label="Top woman ↔ woman co-editor pairs",
            ),
            mo.ui.table(
                pretty(coed_wm.head(40)[_cols]),
                label="Top woman ↔ man co-editor pairs",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""

    """)
    return


if __name__ == "__main__":
    app.run()
