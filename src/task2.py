"""Task 2: our own five hypotheses (H6 - H10).

    python -m src.task2

H6  Students re-attempt to reach a pass mark, not to get full marks.
H7  Instant re-attempts (no waiting time) give much bigger gains, because
    students can reuse what they just saw in the feedback.
H8  Students who do well in Quiz 1 also do well in Quiz 2 and Quiz 3.
H9  Later groups of students score higher on their first attempt than
    earlier groups (the quizzes became "easier" over time).
H10 Leaving a question blank is a sign of low effort: those attempts are
    faster and also score lower on the questions that were answered.
"""
from __future__ import annotations

import json

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.transforms as mtrans
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path
from scipy import stats as st

from . import config as C
from .data_prep import load_clean, timed
from .stats_utils import (chi2_equal_props, mann_whitney, mean_ci, spearman,
                          summarise_mean)
from .style import apply_style, save, set_time_axis

GRADE_RAMP = {0: "#e8f0fb", 2: "#cde2fb", 4: "#86b6ef", 6: "#3987e5",
              8: "#1c5cab", 10: "#0d366b"}
DELAY_START = pd.Timestamp("2022-05-13")    # first day with no re-attempt < 2 h


# ======================================================================
# H6  Re-attempt to pass, not to master
# ======================================================================
def h6_pass_mark(att: pd.DataFrame) -> dict:
    x = att.assign(another=~att["is_last"])
    p = x.groupby(["quiz", "grade"])["another"].agg(["mean", "size"]).reset_index()
    res = {"p_another": {f"q{r.quiz}-{int(r.grade)}": round(r.mean, 3)
                         for r in p.itertuples()}}
    below = x[x["grade"] < 4]["another"]
    above = x[(x["grade"] >= 4) & (x["grade"] < 10)]["another"]
    res["p_another_below4"] = float(below.mean())
    res["p_another_4to8"] = float(above.mean())
    res["p_another_10"] = float(x[x["grade"] == 10]["another"].mean())
    res["chi2_below_vs_above"] = chi2_equal_props(
        [int(below.sum()), int(above.sum())], [len(below), len(above)])

    retakers_final = att[att["is_last"] & (att["n_attempts"] > 1)]
    one_shot = att[att["is_first"] & (att["n_attempts"] == 1)]
    dist_ret = retakers_final["grade"].value_counts(normalize=True).sort_index() * 100
    dist_one = one_shot["grade"].value_counts(normalize=True).sort_index() * 100
    res["final_grade_retakers_pct"] = dist_ret.round(1).to_dict()
    res["grade_one_shot_pct"] = dist_one.round(1).to_dict()
    res["n_retakers"] = int(len(retakers_final))
    res["n_one_shot"] = int(len(one_shot))
    res["one_shot_below4"] = int((one_shot["grade"] < 4).sum())

    # ---------------------------------------------------------------- figure
    apply_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.8),
                               gridspec_kw={"width_ratios": [1.25, 1]})
    grades = np.arange(0, 11, 2)
    w = 0.52
    for i, q in enumerate((1, 2, 3)):
        d = p[p["quiz"] == q].set_index("grade").reindex(grades)
        a.bar(grades + (i - 1) * w, d["mean"] * 100, width=w - 0.08,
              color=C.QUIZ_COLORS[q], label=f"Quiz {q}")
    a.axvspan(-1, 3, color="#f4f3ef", zorder=0)
    a.text(1, 104, "below 4/10", ha="center", fontsize=6.5, color=C.INK_2)
    a.text(7, 104, "4/10 or more", ha="center", fontsize=6.5, color=C.INK_2)
    a.set_xlim(-1, 11)
    a.set_ylim(0, 112)
    a.set_xticks(grades)
    a.set_xlabel("Grade of this attempt (out of 10)")
    a.set_ylabel("% followed by another attempt")
    a.set_title("(a) Who tries again?")
    a.legend(loc="center right", handlelength=1)
    a.grid(axis="x", visible=False)

    # (b) final grade of students who re-attempted vs one-shot students
    ypos = [1, 0]
    for yy, (lab, dist, n) in zip(ypos, (
            ("Re-attempted:\nlast attempt", dist_ret, len(retakers_final)),
            ("One attempt\nonly", dist_one, len(one_shot)))):
        left = 0
        for g in grades:
            v = float(dist.get(g, 0))
            b.barh(yy, v, left=left, color=GRADE_RAMP[g], height=0.55,
                   edgecolor="white", linewidth=1.2)
            if v >= 9:
                b.text(left + v / 2, yy, f"{v:.0f}%", ha="center", va="center",
                       fontsize=6.5, color="white" if g >= 6 else C.INK)
            left += v
    b.set_yticks(ypos, [f"Re-attempted:\nlast attempt\n(n = {len(retakers_final):,})",
                        f"One attempt\nonly\n(n = {len(one_shot):,})"], fontsize=6.5)
    b.tick_params(axis="y", length=0)
    b.set_xlim(0, 100)
    b.set_xlabel("% of student-quiz pairs")
    b.set_title("(b) Where do they stop?")
    b.grid(axis="y", visible=False)
    b.legend(handles=[Rectangle((0, 0), 1, 1, color=GRADE_RAMP[g], label=f"{g}")
                      for g in grades],
             title="Final grade", ncol=6, loc="upper center",
             bbox_to_anchor=(0.45, -0.3), handlelength=1, columnspacing=0.6,
             fontsize=6.3, title_fontsize=6.3)
    fig.tight_layout(w_pad=2)
    save(fig, "fig07_h6_pass_mark")
    return res


# ======================================================================
# H7  Instant re-attempts reuse the feedback
# ======================================================================
def h7_retake_delay(att: pd.DataFrame) -> dict:
    r = att[att["attempt_no"] > 1].copy()
    r["period"] = np.where(r["started"] < DELAY_START, "before", "after")
    r["quick"] = r["gap_since_prev_min"] < 120
    r["group"] = np.select(
        [(r["period"] == "before") & r["quick"],
         (r["period"] == "before") & ~r["quick"]],
        ["Before: within 2 h", "Before: after 2 h+"], "After: always 2 h+")
    order = ["Before: within 2 h", "Before: after 2 h+", "After: always 2 h+"]

    res = {"last_quick_retake": str(r.loc[r["quick"], "started"].max()),
           "min_gap_after": float(r.loc[r["period"] == "after", "gap_since_prev_min"].min()),
           "groups": {}}
    for g in order:
        d = r[r["group"] == g]
        m, lo, hi, n = mean_ci(d["grade_change"])
        res["groups"][g] = {"n": n, "mean_gain": m, "gain_lo": lo, "gain_hi": hi,
                            "mean_grade": float(d["grade"].mean()),
                            "full_marks": float((d["grade"] == 10).mean()),
                            "median_min": float(d["duration_min"].median()),
                            "prev_grade": float(d["prev_grade"].mean())}
    res["mw_gain_quick_vs_after"] = mann_whitney(
        r.loc[r["group"] == order[0], "grade_change"],
        r.loc[r["group"] == order[2], "grade_change"])
    f = att[att["is_first"]]
    res["first_grade_before_after"] = {
        "before": float(f.loc[f["started"] < DELAY_START, "grade"].mean()),
        "after": float(f.loc[f["started"] >= DELAY_START, "grade"].mean())}

    # ---------------------------------------------------------------- figure
    apply_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.9),
                               gridspec_kw={"width_ratios": [1.35, 1]})
    gap = r["gap_since_prev_min"].clip(lower=0.5)
    col = np.where(r["grade"] == 10, C.ACCENT, C.MUTED)
    order_idx = np.argsort(r["grade"].values == 10)          # full marks on top
    a.scatter(r["started"].values[order_idx], gap.values[order_idx], s=2.5,
              c=col[order_idx], alpha=0.4, linewidths=0, rasterized=True)
    a.axhline(120, color=C.INK_2, lw=0.8)
    a.axvline(DELAY_START, color=C.INK_2, lw=0.8)
    a.text(DELAY_START + pd.Timedelta(days=25), 1.0,
           "13 May 2022: no re-attempt\nstarts within 2 h after this",
           fontsize=6.3, color=C.INK_2, va="bottom")
    a.text(pd.Timestamp("2025-04-20"), 120, "2 h", fontsize=6.3, color=C.INK_2,
           va="center", ha="left")
    set_time_axis(a, "y", ticks=(1, 10, 60, 1440, 10080, 43200 * 3),
                  label="Wait since previous attempt (log)")
    a.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: {1: "1 min", 10: "10 min", 60: "1 h", 1440: "1 day",
                      10080: "1 week", 129600: "3 months"}.get(int(v), "")))
    a.set_ylim(0.4, 2.5e6)
    a.xaxis.set_major_locator(mdates.YearLocator())
    a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    a.set_xlabel("Date of re-attempt")
    a.set_title("(a) Waiting time before each re-attempt")
    a.legend(handles=[Line2D([], [], marker="o", ls="", color=C.ACCENT, ms=4,
                             label="Re-attempt scored 10/10"),
                      Line2D([], [], marker="o", ls="", color=C.MUTED,
                             ms=4, label="Scored less than 10")],
             loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2,
             fontsize=6.3, handletextpad=0.2)

    # (b) grade distribution of re-attempts per group (100% stacked)
    grades = np.arange(0, 11, 2)
    ypos = np.arange(3)[::-1]
    for yy, g in zip(ypos, order):
        d = r[r["group"] == g]["grade"].value_counts(normalize=True) * 100
        left = 0
        for gr in grades:
            v = float(d.get(gr, 0))
            b.barh(yy, v, left=left, color=GRADE_RAMP[gr], height=0.55,
                   edgecolor="white", linewidth=1.2)
            if v >= 9:
                b.text(left + v / 2, yy, f"{v:.0f}%", ha="center", va="center",
                       fontsize=6.3, color="white" if gr >= 6 else C.INK)
            left += v
        gg = res["groups"][g]
        b.text(2.5, yy + 0.37, f"n = {gg['n']:,} · mean gain {gg['mean_gain']:+.1f} · "
               f"median {gg['median_min']:.1f} min", fontsize=5.8, color=C.INK_2)
    b.set_yticks(ypos, ["Before May 2022,\nwithin 2 h", "Before May 2022,\nafter 2 h+",
                        "After May 2022\n(2 h+ wait)"], fontsize=6.5)
    b.set_xlim(0, 100)
    b.set_ylim(-0.5, 2.75)
    b.set_xlabel("% of re-attempts")
    b.set_title("(b) Grade of the re-attempt")
    b.grid(axis="y", visible=False)
    b.legend(handles=[Rectangle((0, 0), 1, 1, color=GRADE_RAMP[g], label=f"{g}")
                      for g in grades],
             title="Grade", ncol=6, loc="upper center", bbox_to_anchor=(0.4, -0.22),
             handlelength=1, columnspacing=0.6, fontsize=6.3, title_fontsize=6.3)
    fig.tight_layout(w_pad=1.4)
    save(fig, "fig08_h7_retake_delay")
    return res


# ======================================================================
# H8  Doing well in Quiz 1 carries over to Quiz 2 and 3
# ======================================================================
BANDS = ["0–2", "4", "6–10"]
BAND_COLORS = {"0–2": "#86b6ef", "4": "#2a78d6", "6–10": "#104281"}


def _band(g):
    return np.select([g <= 2, g == 4], ["0–2", "4"], "6–10")


def _ribbon(ax, x0, x1, y0a, y0b, y1a, y1b, color, alpha=0.5):
    """Filled S-shaped band from (x0, y0a..y0b) to (x1, y1a..y1b)."""
    xm = (x0 + x1) / 2
    verts = [(x0, y0a), (xm, y0a), (xm, y1a), (x1, y1a),
             (x1, y1b), (xm, y1b), (xm, y0b), (x0, y0b), (x0, y0a)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, alpha=alpha,
                           edgecolor="none"))


def h8_carry_over(stu: pd.DataFrame) -> dict:
    s = stu.dropna(subset=["first_q1", "first_q2", "first_q3"]).copy()
    for q in (1, 2, 3):
        s[f"b{q}"] = _band(s[f"first_q{q}"])
    res = {"n": int(len(s)),
           "spearman_12": spearman(s["first_q1"], s["first_q2"]),
           "spearman_13": spearman(s["first_q1"], s["first_q3"]),
           "spearman_23": spearman(s["first_q2"], s["first_q3"])}
    ct = pd.crosstab(s["b1"], s["b3"], normalize="index") * 100
    res["q3_band_given_q1_band_pct"] = ct.round(1).to_dict(orient="index")
    ct2 = pd.crosstab(s["b1"], s["b2"], normalize="index") * 100
    res["q2_band_given_q1_band_pct"] = ct2.round(1).to_dict(orient="index")
    tab = pd.crosstab(s["b1"], s["b3"])
    chi2, p, dof, _ = st.chi2_contingency(tab)
    res["chi2_q1_q3"] = {"chi2": float(chi2), "p": float(p), "dof": int(dof),
                         "cramers_v": float(np.sqrt(chi2 / (tab.values.sum() * 2)))}
    stay_top = s[s["b1"] == "6–10"]
    res["top_q1_top_all"] = float(((stay_top["b2"] == "6–10") &
                                   (stay_top["b3"] == "6–10")).mean())
    res["band_share"] = {q: (s[f"b{q}"].value_counts(normalize=True) * 100)
                         .round(1).to_dict() for q in (1, 2, 3)}

    # ---------------------------------------------------------------- figure
    apply_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 3.1),
                               gridspec_kw={"width_ratios": [1.6, 1]})
    N = len(s)
    gap = 0.03
    xs = {1: 0.0, 2: 1.0, 3: 2.0}
    wnode = 0.06
    # node positions (top = high band)
    pos = {}
    for q in (1, 2, 3):
        y = 1 + gap * 2
        for band in reversed(BANDS):            # 6-10 at top
            h = (s[f"b{q}"] == band).mean()
            pos[(q, band)] = [y - h, y]          # [bottom, top]
            y = y - h - gap
    # flows: colour = band in Quiz 1 (so you can follow a group)
    for (qa, qb) in ((1, 2), (2, 3)):
        out_cursor = {band: pos[(qa, band)][1] for band in BANDS}
        in_cursor = {band: pos[(qb, band)][1] for band in BANDS}
        combos = (s.groupby([f"b{qa}", f"b{qb}", "b1"]).size() / N)
        for src in reversed(BANDS):
            for dst in reversed(BANDS):
                for origin in reversed(BANDS):
                    h = combos.get((src, dst, origin), 0)
                    if h <= 0:
                        continue
                    y0t = out_cursor[src]; y0b = y0t - h
                    out_cursor[src] = y0b
                    y1t = in_cursor[dst]; y1b = y1t - h
                    in_cursor[dst] = y1b
                    _ribbon(a, xs[qa] + wnode / 2, xs[qb] - wnode / 2,
                            y0t, y0b, y1t, y1b, BAND_COLORS[origin], alpha=0.45)
    for (q, band), (y0, y1) in pos.items():
        a.add_patch(Rectangle((xs[q] - wnode / 2, y0), wnode, y1 - y0,
                              color=BAND_COLORS[band], zorder=3))
        share = (y1 - y0) * 100
        ha, dx = ("right", -wnode) if q == 1 else ("left", wnode)
        if q == 2:
            ha, dx = "center", 0
        lab = f"{band}  ({share:.0f}%)" if q != 2 else f"{share:.0f}%"
        if q == 2:
            a.text(xs[q], (y0 + y1) / 2, lab, ha="center", va="center",
                   fontsize=5.8, color="white", zorder=4, rotation=90)
        else:
            a.text(xs[q] + dx, (y0 + y1) / 2, lab, ha=ha, va="center",
                   fontsize=6.5, color=C.INK_2)
    for q in (1, 2, 3):
        a.text(xs[q], 1.1, f"Quiz {q}", ha="center", fontsize=7.5,
               fontweight="bold", color=C.INK)
    a.set_xlim(-0.55, 2.55)
    a.set_ylim(-0.08, 1.2)
    a.axis("off")
    a.set_title("(a) Grade band on first attempt, followed across quizzes", pad=4)
    a.text(-0.55, -0.08, "Flow colour = grade band in Quiz 1", fontsize=6.3,
           color=C.MUTED)

    # (b) % reaching 6-10 in Quiz 3 by Quiz 1 band
    for i, band in enumerate(BANDS):
        d = s[s["b1"] == band]
        m, lo, hi, n = mean_ci((d["b3"] == "6–10").astype(float))
        b.bar(i, m * 100, width=0.5, color=BAND_COLORS[band])
        b.errorbar(i, m * 100, yerr=[[100 * (m - lo)], [100 * (hi - m)]],
                   color=C.INK_2, lw=1, capsize=0)
        b.text(i, m * 100 + 4, f"{m * 100:.0f}%", ha="center", fontsize=7,
               color=C.INK, fontweight="bold")
    b.set_xticks(range(3), BANDS)
    b.set_xlabel("Grade band in Quiz 1 (first attempt)")
    b.set_ylabel("% scoring 6–10 in Quiz 3\n(first attempt, 95% CI)")
    b.set_ylim(0, 100)
    b.set_title("(b) Quiz 1 band vs Quiz 3 result")
    b.grid(axis="x", visible=False)
    rho = res["spearman_13"]["rho"]
    b.text(0.02, 0.97, f"Spearman ρ (Quiz 1 vs 3) = {rho:.2f}",
           transform=b.transAxes, fontsize=6.5, color=C.INK_2, va="top")
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig09_h8_carry_over")
    return res


# ======================================================================
# H9  Later cohorts score higher on the first attempt
# ======================================================================
def h9_cohort_trend(att: pd.DataFrame) -> dict:
    f = att[att["is_first"]].copy()
    halves = sorted(f["half_year"].unique())
    idx = {h: i for i, h in enumerate(halves)}
    f["hidx"] = f["half_year"].map(idx)
    res = {"half_years": halves, "per_quiz": {}}

    apply_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.8))
    for q in (1, 2, 3):
        d = summarise_mean(f[f["quiz"] == q], "hidx", "grade")
        a.fill_between(d["hidx"], d["lo"], d["hi"], color=C.QUIZ_COLORS[q],
                       alpha=0.16, lw=0)
        a.plot(d["hidx"], d["mean"], "-o", color=C.QUIZ_COLORS[q], ms=3.4,
               markeredgecolor="white", markeredgewidth=0.6)
        a.annotate(f"Quiz {q}", (d["hidx"].iloc[-1], d["mean"].iloc[-1]),
                   xytext=(5, {1: 0, 2: 5, 3: -5}[q]), textcoords="offset points",
                   fontsize=6.5, va="center", color=C.INK_2, fontweight="bold")
        rr = f[f["quiz"] == q].assign(retook=lambda x: (x["n_attempts"] > 1).astype(float))
        e = summarise_mean(rr, "hidx", "retook")
        b.fill_between(e["hidx"], e["lo"] * 100, e["hi"] * 100,
                       color=C.QUIZ_COLORS[q], alpha=0.16, lw=0)
        b.plot(e["hidx"], e["mean"] * 100, "-o", color=C.QUIZ_COLORS[q], ms=3.4,
               markeredgecolor="white", markeredgewidth=0.6)
        b.annotate(f"Quiz {q}", (e["hidx"].iloc[-1], e["mean"].iloc[-1] * 100),
                   xytext=(5, 0), textcoords="offset points", fontsize=6.5,
                   va="center", color=C.INK_2, fontweight="bold")
        sp = spearman(f.loc[f["quiz"] == q, "hidx"], f.loc[f["quiz"] == q, "grade"])
        res["per_quiz"][q] = {
            "mean_by_half": dict(zip(halves, d["mean"].round(2))),
            "n_by_half": dict(zip(halves, d["n"].astype(int))),
            "retake_pct_by_half": dict(zip(halves, (e["mean"] * 100).round(1))),
            "spearman_time_grade": sp,
            "first_half": round(float(d["mean"].iloc[0]), 2),
            "last_half": round(float(d["mean"].iloc[-1]), 2)}
    labels = [f"{h[-2:]}\n'{h[2:4]}" for h in halves]
    for ax in (a, b):
        ax.set_xticks(range(len(halves)), labels, fontsize=6.3)
        ax.set_xlim(-0.3, len(halves) - 0.2)
        ax.grid(axis="x", visible=False)
    a.set_ylim(0, 10)
    a.set_ylabel("Mean first-attempt grade (95% CI)")
    a.set_title("(a) First-attempt grade by cohort")
    b.set_ylim(0, 100)
    b.set_ylabel("% who needed a re-attempt")
    b.set_title("(b) Students who had to try again")
    fig.tight_layout(w_pad=2)
    fig.text(0.01, 0.0, "Cohort = half-year in which the student made the first "
             "attempt (H1 = Jan–Jun, H2 = Jul–Dec). Shaded band = 95% CI.",
             fontsize=6.3, color=C.MUTED, va="top")
    save(fig, "fig10_h9_cohort_trend")
    return res


# ======================================================================
# H10  Blank answers signal low effort
# ======================================================================
def h10_blank_answers(att: pd.DataFrame) -> dict:
    f = att[att["is_first"]].copy()
    # Only two questions are left blank often: Quiz 1 Q4 and Quiz 2 Q5.
    skip_rate = (f.groupby("quiz")[[f"{q}_skipped" for q in C.QUESTIONS]].mean() * 100)
    res = {"skip_rate_first_pct": skip_rate.round(2).to_dict(orient="index")}
    targets = {1: "Q4", 2: "Q5"}
    rows = []
    for q, qq in targets.items():
        d = f[f["quiz"] == q].copy()
        others = [x for x in C.QUESTIONS if x != qq]
        d["others_score"] = d[others].sum(axis=1)          # out of 8
        d["blank"] = d[f"{qq}_skipped"]
        dt = d[~d["long_session"]]
        for blank in (False, True):
            g = d[d["blank"] == blank]
            gt = dt[dt["blank"] == blank]
            m, lo, hi, n = mean_ci(g["others_score"])
            rows.append({"quiz": q, "question": qq, "blank": blank, "n": n,
                         "others_mean": m, "others_lo": lo, "others_hi": hi,
                         "median_min": float(gt["duration_min"].median()),
                         "q1_min": float(gt["duration_min"].quantile(0.25)),
                         "q3_min": float(gt["duration_min"].quantile(0.75)),
                         "low_tier_pct": float((g["tier"] == "Low").mean() * 100),
                         "under_2min_pct": float((gt["duration_min"] < 2).mean() * 100)})
        res[f"mw_time_q{q}"] = mann_whitney(dt.loc[dt["blank"], "duration_min"],
                                            dt.loc[~dt["blank"], "duration_min"])
        res[f"mw_others_q{q}"] = mann_whitney(d.loc[d["blank"], "others_score"],
                                              d.loc[~d["blank"], "others_score"])
        res[f"blank_by_tier_q{q}"] = (d.groupby("tier", observed=True)["blank"]
                                      .mean().mul(100).round(1).to_dict())
        res[f"blank_by_year_q{q}"] = (d.groupby("year")["blank"].mean()
                                      .mul(100).round(1).to_dict())
    tb = pd.DataFrame(rows)
    res["groups"] = tb.round(3).to_dict(orient="records")

    # ---------------------------------------------------------------- figure
    apply_style()
    fig, axes = plt.subplots(1, 3, figsize=(6.5, 2.7),
                             gridspec_kw={"width_ratios": [1.2, 1, 1]})
    a, b, c = axes
    t = timed(f)
    pos = []
    for i, (q, qq) in enumerate(targets.items()):
        d = t[t["quiz"] == q]
        for j, blank in enumerate((False, True)):
            vals = d.loc[d[f"{qq}_skipped"] == blank, "duration_min"]
            x = i * 2.6 + j
            pos.append(x)
            bp = a.boxplot(vals, positions=[x], widths=0.6,
                           patch_artist=True, showfliers=False,
                           medianprops=dict(color="white", lw=1.4),
                           whiskerprops=dict(color=C.QUIZ_COLORS[q], lw=0.9),
                           capprops=dict(color=C.QUIZ_COLORS[q], lw=0.9))
            for box in bp["boxes"]:
                box.set(facecolor=C.QUIZ_COLORS[q] if blank else "white",
                        edgecolor=C.QUIZ_COLORS[q], linewidth=1)
            if blank:
                for med in bp["medians"]:
                    med.set(color="white")
            else:
                for med in bp["medians"]:
                    med.set(color=C.QUIZ_COLORS[q])
    def group_labels(ax):
        ax.set_xticks(pos, ["no", "yes", "no", "yes"], fontsize=6.5)
        tr = mtrans.blended_transform_factory(ax.transData, ax.transAxes)
        for i, (q, qq) in enumerate(targets.items()):
            ax.text(i * 2.6 + 0.5, -0.13, f"Quiz {q} · {qq}", ha="center",
                    va="top", fontsize=6.5, color=C.INK_2, fontweight="bold",
                    transform=tr)
        ax.set_xlabel("Left blank?", labelpad=14)
    group_labels(a)
    set_time_axis(a, "y", ticks=(0.5, 1, 2, 5, 10, 20, 60),
                  label="Time taken (min, log)")
    a.set_ylim(0.25, 70)
    a.set_title("(a) Time taken")
    a.grid(axis="x", visible=False)

    for k, (ax, col, lab, lim) in enumerate((
            (b, "others_mean", "Marks on the other 4\nquestions (of 8, 95% CI)", 4.5),
            (c, "low_tier_pct", "% of attempts by\nLow-tier students", 80))):
        for i, (q, qq) in enumerate(targets.items()):
            for j, blank in enumerate((False, True)):
                r = tb[(tb["quiz"] == q) & (tb["blank"] == blank)].iloc[0]
                x = i * 2.6 + j
                if k == 0:
                    ax.errorbar(x, r[col], yerr=[[r[col] - r["others_lo"]],
                                                 [r["others_hi"] - r[col]]],
                                fmt="o", ms=5, color=C.QUIZ_COLORS[q],
                                mfc=C.QUIZ_COLORS[q] if blank else "white",
                                mew=1.2, elinewidth=1, capsize=0)
                else:
                    ax.bar(x, r[col], width=0.6, color=C.QUIZ_COLORS[q] if blank else "white",
                           edgecolor=C.QUIZ_COLORS[q], linewidth=1)
                ax.text(x, (r[col] + (0.25 if k == 0 else 3)), f"{r[col]:.1f}" if k == 0 else f"{r[col]:.0f}%",
                        ha="center", va="bottom", fontsize=6.2, color=C.INK_2)
        group_labels(ax)
        ax.set_ylim(0, lim)
        ax.set_ylabel(lab)
        ax.grid(axis="x", visible=False)
    b.set_title("(b) Score on the rest")
    c.set_title("(c) Who leaves it blank?")
    fig.tight_layout(w_pad=1.3)
    fig.text(0.01, -0.03, "First attempts only. Hollow = question answered, "
             "filled = question left blank. Quiz 1 Q4 and Quiz 2 Q5 are the only "
             "questions left blank in more than 1% of attempts.",
             fontsize=6.3, color=C.MUTED, va="top")
    save(fig, "fig11_h10_blank_answers")
    return res


def run(att=None, stu=None) -> dict:
    if att is None:
        att, stu = load_clean()
    apply_style()
    return {"H6": h6_pass_mark(att), "H7": h7_retake_delay(att),
            "H8": h8_carry_over(stu), "H9": h9_cohort_trend(att),
            "H10": h10_blank_answers(att)}


if __name__ == "__main__":
    out = run()
    C.OUT_DIR.mkdir(exist_ok=True, parents=True)
    with open(C.OUT_DIR / "results_task2.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("Task 2 figures and results saved.")
