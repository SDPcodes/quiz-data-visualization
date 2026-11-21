"""Task 1: check the five hypotheses given in the project brief.

    python -m src.task1

Each function draws one figure and returns the numbers we quote in the
report, so the text and the charts always come from the same code.
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

from . import config as C
from .data_prep import load_clean, leave_one_quiz_out_tier, timed
from .stats_utils import (bootstrap_ci, chi2_equal_props, kruskal, mean_ci,
                          spearman, summarise_mean)
from .style import SEQ_CMAP, apply_style, note, save, set_time_axis

QLABEL = {1: "Quiz 1", 2: "Quiz 2", 3: "Quiz 3"}


# ======================================================================
# H1  Students who take longer to complete the quiz tend to score higher
# ======================================================================
def h1_time_vs_score(att: pd.DataFrame) -> dict:
    t = timed(att)
    groups = {"First attempts": t[t["is_first"]],
              "Re-attempts (2nd, 3rd ...)": t[~t["is_first"]]}
    res = {"spearman": {}}

    fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.9), sharey=True)
    grades = np.arange(0, 11, 2)
    for ax, (name, d) in zip(axes, groups.items()):
        res["spearman"][name] = {"pooled": spearman(d["duration_min"], d["grade"])}
        for i, q in enumerate((1, 2, 3)):
            dq = d[d["quiz"] == q]
            sp = spearman(dq["duration_min"], dq["grade"])
            res["spearman"][name][f"quiz{q}"] = sp
            g = dq.groupby("grade")["duration_min"]
            med = g.median().reindex(grades)
            q1, q3 = g.quantile(0.25).reindex(grades), g.quantile(0.75).reindex(grades)
            n = g.size().reindex(grades).fillna(0)
            ok = n >= 30                      # hide unstable points
            x = grades + (i - 1) * 0.35
            ax.vlines(x[ok], q1[ok], q3[ok], color=C.QUIZ_COLORS[q], lw=0.9,
                      alpha=0.55)
            ax.plot(x[ok], med[ok], "-o", color=C.QUIZ_COLORS[q], ms=3.6,
                    lw=1.3, label=f"Quiz {q}: ρ = {sp['rho']:+.2f}",
                    markeredgecolor="white", markeredgewidth=0.6)
        ax.set_title(name)
        ax.set_xticks(grades)
        ax.set_xlabel("Grade (out of 10)")
        ax.legend(loc="lower right" if "First" in name else "upper right",
                  handlelength=1.2, handletextpad=0.3, fontsize=6.5,
                  title="Spearman ρ (time vs grade)", title_fontsize=6.3)
        ax.grid(axis="x", visible=False)
    set_time_axis(axes[0], "y", ticks=(0.5, 1, 2, 5, 10, 20),
                  label="Median time taken (min, log)")
    axes[0].set_ylim(0.45, 30)
    fig.tight_layout(w_pad=1.5)
    fig.text(0.01, 0.0, "Dots = median time, bars = middle 50% (IQR). Attempts over "
             "60 min removed. Points with fewer than 30 attempts hidden.",
             fontsize=6.5, color=C.MUTED, ha="left", va="top")
    save(fig, "fig02_h1_time_vs_score")

    # Extra numbers for the text
    f = groups["First attempts"]
    res["first_median_by_grade"] = (f.groupby("grade")["duration_min"]
                                    .median().round(2).to_dict())
    r = groups["Re-attempts (2nd, 3rd ...)"]
    res["re_median_by_grade"] = (r.groupby("grade")["duration_min"]
                                 .median().round(2).to_dict())
    res["all_pooled"] = spearman(t["duration_min"], t["grade"])

    # Sensitivity check: does the 60-minute cut-off change the answer?
    res["cutoff_sensitivity"] = {}
    for cut in (30, 45, 60, 90, 120):
        d = att[att["duration_min"] <= cut]
        res["cutoff_sensitivity"][cut] = {
            "excluded_pct": float((att["duration_min"] > cut).mean() * 100),
            **{f"first_q{q}": spearman(d[d["is_first"] & (d["quiz"] == q)]["duration_min"],
                                       d[d["is_first"] & (d["quiz"] == q)]["grade"])["rho"]
               for q in (1, 2, 3)},
            **{f"re_q{q}": spearman(d[~d["is_first"] & (d["quiz"] == q)]["duration_min"],
                                    d[~d["is_first"] & (d["quiz"] == q)]["grade"])["rho"]
               for q in (1, 2, 3)}}
    return res


# ======================================================================
# H2  Some questions are consistently harder than others
# ======================================================================
def h2_question_difficulty(att: pd.DataFrame) -> dict:
    f = att[att["is_first"]]
    cols = [f"{q}_correct" for q in C.QUESTIONS]
    fac = f.groupby("quiz")[cols].mean() * 100
    fac.columns = C.QUESTIONS
    res = {"facility_first": fac.round(1).to_dict(orient="index")}

    # chi-square: are the 5 questions equally hard inside each quiz?
    res["chi2"] = {}
    for q in (1, 2, 3):
        d = f[f["quiz"] == q]
        succ = [int(d[c].sum()) for c in cols]
        res["chi2"][q] = chi2_equal_props(succ, [len(d)] * 5)

    # by tier
    by_tier = (f.groupby(["quiz", "tier"], observed=True)[cols].mean() * 100)
    by_tier.columns = C.QUESTIONS

    # over time (half-years)
    by_time = (f.groupby(["quiz", "half_year"])[cols].mean() * 100)
    by_time.columns = C.QUESTIONS
    halves = sorted(f["half_year"].unique())

    # rank stability: is the hardest question the hardest in each half-year?
    res["hardest"] = {}
    for q in (1, 2, 3):
        hardest = fac.loc[q].idxmin()
        per_half = by_time.loc[q].idxmin(axis=1)
        tiers_hard = by_tier.loc[q].idxmin(axis=1)
        # Kendall's W (agreement of question ranks across half-years)
        ranks = by_time.loc[q].rank(axis=1).values         # m x n
        m, n = ranks.shape
        R = ranks.sum(axis=0)
        W = 12 * ((R - R.mean()) ** 2).sum() / (m ** 2 * (n ** 3 - n))
        res["hardest"][q] = {
            "question": hardest,
            "facility": round(float(fac.loc[q, hardest]), 1),
            "half_years_hardest": int((per_half == hardest).sum()),
            "half_years_total": int(len(per_half)),
            "hardest_in_each_tier": tiers_hard.to_dict(),
            "kendall_W_time": round(float(W), 3),
        }

    # ---------------------------------------------------------------- figure
    apply_style()
    fig = plt.figure(figsize=(6.5, 4.9))
    gs = GridSpec(3, 2, figure=fig, width_ratios=[1.1, 1],
                  height_ratios=[0.8, 1.45, 0.06], wspace=0.42, hspace=0.5)
    a = fig.add_subplot(gs[0, 0])
    c = fig.add_subplot(gs[1, 0])
    cax = fig.add_subplot(gs[2, 0])
    b = fig.add_subplot(gs[:, 1])

    # (a) heatmap quiz x question
    im = a.imshow(fac.values, cmap=SEQ_CMAP, vmin=0, vmax=100, aspect="auto")
    for i in range(3):
        for j in range(5):
            v = fac.values[i, j]
            a.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=7,
                   color="white" if v > 55 else C.INK, fontweight="bold")
    a.set_xticks(range(5), C.QUESTIONS)
    a.set_yticks(range(3), [QLABEL[q] for q in (1, 2, 3)])
    a.grid(False)
    for s in a.spines.values():
        s.set_visible(False)
    a.tick_params(length=0)
    a.set_title("(a) % correct on first attempt")

    # (c) heatmap over time: 15 rows x half-years
    rows, labels = [], []
    for q in (1, 2, 3):
        for qq in C.QUESTIONS:
            rows.append(by_time.loc[q][qq].reindex(halves).values)
            labels.append(f"Q{q}.{qq[1]}")
    mat = np.array(rows)
    c.imshow(mat, cmap=SEQ_CMAP, vmin=0, vmax=100, aspect="auto")
    c.set_yticks(range(15), labels, fontsize=6)
    c.set_xticks(range(len(halves)), [h.replace("-", "\n") for h in halves],
                 fontsize=6)
    for k in (4.5, 9.5):
        c.axhline(k, color="white", lw=2)
    c.grid(False)
    for s in c.spines.values():
        s.set_visible(False)
    c.tick_params(length=0)
    c.set_title("(c) % correct by half-year")
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label("% correct on first attempt (same scale in a and c)", fontsize=6.5)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=6)

    # (b) dot plot by tier, 15 questions ordered by facility within quiz
    ypos, ylabels, y = [], [], 0
    order = []
    for q in (1, 2, 3):
        qs = fac.loc[q].sort_values(ascending=False).index
        for qq in qs:
            order.append((q, qq, y))
            ylabels.append(f"Q{q}.{qq[1]}")
            ypos.append(y)
            y += 1
        y += 0.8
    for q, qq, yy in order:
        vals = by_tier.loc[q][qq].reindex(C.TIER_LABELS)
        b.plot([vals.min(), vals.max()], [yy, yy], color=C.GRID, lw=2.2,
               solid_capstyle="round", zorder=1)
        for tier in C.TIER_LABELS:
            b.scatter(vals[tier], yy, s=26, color=C.TIER_COLORS[tier],
                      edgecolor="white", linewidth=0.7, zorder=3)
    b.set_yticks(ypos, ylabels, fontsize=6.5)
    b.invert_yaxis()
    for q, yy in zip((1, 2, 3), (2, 7.8, 13.6)):
        b.text(101, yy, f"Quiz {q}", rotation=270, va="center", ha="left",
               fontsize=6.5, color=C.MUTED)
    b.set_xlim(0, 100)
    b.set_xlabel("% correct on first attempt")
    b.set_title("(b) By student tier (Q2.3 = Quiz 2, Q3)")
    b.grid(axis="y", visible=False)
    handles = [Line2D([], [], marker="o", ls="", color=C.TIER_COLORS[t],
                      markeredgecolor="white", ms=6, label=f"{t} tier")
               for t in C.TIER_LABELS]
    b.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.45, -0.2),
             ncol=3, handletextpad=0.2, columnspacing=0.9)
    save(fig, "fig03_h2_question_difficulty")

    res["facility_by_tier"] = {f"{q}-{t}": by_tier.loc[(q, t)].round(1).to_dict()
                               for q, t in by_tier.index}
    res["facility_by_time"] = {f"{q}|{h}": by_time.loc[(q, h)].round(1).to_dict()
                               for q, h in by_time.index}
    all_fac = att.groupby("quiz")[cols].mean() * 100
    all_fac.columns = C.QUESTIONS
    res["facility_all_attempts"] = all_fac.round(1).to_dict(orient="index")
    return res


# ======================================================================
# H3  High performers consistently improve, low performers are erratic
# ======================================================================
def _path_stats(g: pd.DataFrame) -> pd.Series:
    gr = g.sort_values("attempt_no")["grade"].to_numpy()
    d = np.diff(gr)
    return pd.Series({"n": len(gr), "net_gain": gr[-1] - gr[0],
                      "any_drop": bool((d < 0).any()),
                      "zigzag": bool(len(d) > 1 and
                                     (np.sign(d[1:]) * np.sign(d[:-1]) < 0).any()),
                      "never_down_and_up": bool((d >= 0).all() and gr[-1] > gr[0])})


def h3_progress_by_tier(att: pd.DataFrame) -> dict:
    multi = att[att["n_attempts"] >= 2].copy()
    loo = leave_one_quiz_out_tier(att)
    multi = multi.merge(loo, on=["student_id", "quiz"], how="left")

    paths = (multi.groupby(["student_id", "quiz"])
                  .apply(_path_stats, include_groups=False).reset_index())
    tiers = multi.groupby(["student_id", "quiz"]).agg(
        tier=("tier", "first"), tier_loo=("tier_loo", "first")).reset_index()
    paths = paths.merge(tiers, on=["student_id", "quiz"])
    for col in ("any_drop", "zigzag", "never_down_and_up"):
        paths[col] = paths[col].astype(bool)

    changes = multi[multi["attempt_no"] > 1]

    res = {"retake_share_by_tier":
           att[att["is_first"]].groupby("tier", observed=True)["n_attempts"]
              .apply(lambda s: (s > 1).mean()).round(3).to_dict()}

    def direction_table(tcol):
        out = {}
        for t, g in changes.groupby(tcol, observed=True):
            s = g["grade_change"]
            out[t] = {"up": float((s > 0).mean()), "same": float((s == 0).mean()),
                      "down": float((s < 0).mean()), "n": int(len(s)),
                      "sd_change": float(s.std())}
        return out
    res["direction"] = direction_table("tier")
    res["direction_loo"] = direction_table("tier_loo")

    def path_table(tcol, p):
        out = {}
        for t, g in p.groupby(tcol, observed=True):
            out[t] = {"n": int(len(g)), "net_gain": float(g["net_gain"].mean()),
                      "any_drop": float(g["any_drop"].mean()),
                      "zigzag": float(g["zigzag"].mean()),
                      "steady_up": float(g["never_down_and_up"].mean())}
        return out
    res["paths_2plus"] = path_table("tier", paths)
    res["paths_3plus"] = path_table("tier", paths[paths["n"] >= 3])
    res["paths_3plus_loo"] = path_table("tier_loo", paths[paths["n"] >= 3])

    # mean grade by attempt number per tier (attempts 1..5)
    mt = summarise_mean(multi[multi["attempt_no"] <= 5], ["tier", "attempt_no"], "grade")
    res["mean_by_attempt"] = {f"{r.tier}-{r.attempt_no}": round(r.mean, 2)
                              for r in mt.itertuples()}

    # ---------------------------------------------------------------- figure
    apply_style()
    fig, axes = plt.subplots(1, 3, figsize=(6.5, 2.75),
                             gridspec_kw={"width_ratios": [1.25, 1.1, 1]})
    a, b, c = axes

    for t in C.TIER_LABELS:
        d = mt[(mt["tier"] == t) & (mt["n"] >= 20)]
        a.fill_between(d["attempt_no"], d["lo"], d["hi"],
                       color=C.TIER_COLORS[t], alpha=0.18, lw=0)
        a.plot(d["attempt_no"], d["mean"], "-o", color=C.TIER_COLORS[t],
               ms=3.5, markeredgecolor="white", markeredgewidth=0.6)
        a.annotate(t, (d["attempt_no"].iloc[0], d["mean"].iloc[0]),
                   xytext=(-5, 0), textcoords="offset points", fontsize=6.5,
                   va="center", ha="right", color=C.INK_2, fontweight="bold")
    a.set_xticks(range(1, 6))
    a.set_xlim(0.0, 5.3)
    a.set_ylim(0, 10)
    a.set_xlabel("Attempt number")
    a.set_ylabel("Mean grade (95% CI)")
    a.set_title("(a) Grade by attempt")

    # (b) direction of change, 100% stacked bars (diverging colours)
    ypos = np.arange(3)[::-1]
    for yy, t in zip(ypos, C.TIER_LABELS):
        r = res["direction"][t]
        left = 0
        for key, col in (("down", C.DOWN_COLOR), ("same", C.NEUTRAL_COLOR),
                         ("up", C.UP_COLOR)):
            v = r[key] * 100
            b.barh(yy, v, left=left, color=col, height=0.55, edgecolor="white",
                   linewidth=1.2)
            if v >= 9:
                b.text(left + v / 2, yy, f"{v:.0f}%", ha="center", va="center",
                       fontsize=6.5, color="white" if key != "same" else C.INK)
            left += v
    b.set_yticks(ypos, C.TIER_LABELS)
    b.set_xlim(0, 100)
    b.set_xlabel("% of re-attempts")
    b.set_title("(b) Change vs previous try")
    b.grid(axis="y", visible=False)
    b.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=C.DOWN_COLOR, label="Down"),
                      plt.Rectangle((0, 0), 1, 1, color=C.NEUTRAL_COLOR, label="Same"),
                      plt.Rectangle((0, 0), 1, 1, color=C.UP_COLOR, label="Up")],
             loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=3,
             handlelength=1, columnspacing=0.8)

    # (c) erratic paths: % with at least one drop (3+ attempts)
    p3 = paths[paths["n"] >= 3]
    for k, (tcol, mk, off, lab) in enumerate((("tier", "o", -0.12, "Tier from all quizzes"),
                                              ("tier_loo", "D", 0.12, "Tier from other 2 quizzes"))):
        for i, t in enumerate(C.TIER_LABELS):
            s = p3.loc[p3[tcol] == t, "any_drop"].astype(float)
            m, lo, hi, n = mean_ci(s)
            c.errorbar(i + off, m * 100, yerr=[[100 * (m - lo)], [100 * (hi - m)]],
                       fmt=mk, color=C.TIER_COLORS[t], ms=4.5,
                       mfc=C.TIER_COLORS[t] if k == 0 else "white",
                       mew=1.1, elinewidth=1, capsize=0)
    c.set_xticks(range(3), C.TIER_LABELS)
    c.set_xlim(-0.6, 2.6)
    c.set_ylim(0, 40)
    c.set_ylabel("% with at least one drop")
    c.set_title("(c) Erratic paths (3+ tries)")
    c.grid(axis="x", visible=False)
    c.legend(handles=[Line2D([], [], marker="o", ls="", color=C.INK_2, label="Tier: all 3 quizzes"),
                      Line2D([], [], marker="D", ls="", color=C.INK_2, mfc="white",
                             label="Tier: other 2 quizzes")],
             loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=1,
             handletextpad=0.2, fontsize=6.3)
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig04_h3_progress_by_tier")
    return res


# ======================================================================
# H4  Difficult questions take longer; high performers answer them faster
# ======================================================================
def h4_difficulty_and_speed(att: pd.DataFrame) -> dict:
    t = timed(att)
    f = t[t["is_first"]]
    rows = []
    for q in (1, 2, 3):
        d = f[f["quiz"] == q]
        for qq in C.QUESTIONS:
            ok = d[f"{qq}_correct"]
            rows.append({"quiz": q, "question": qq, "facility": ok.mean() * 100,
                         "t_correct": d.loc[ok, "duration_min"].median(),
                         "t_wrong": d.loc[~ok, "duration_min"].median(),
                         "n_correct": int(ok.sum())})
    qt = pd.DataFrame(rows)
    qt["ratio"] = qt["t_correct"] / qt["t_wrong"]
    res = {"question_time": qt.round(3).to_dict(orient="records"),
           "spearman_facility_ratio": spearman(qt["facility"], qt["ratio"])}

    # Hardest question of each quiz (lowest % correct on first attempt)
    hardest = qt.loc[qt.groupby("quiz")["facility"].idxmin(), ["quiz", "question"]]
    hardest = dict(zip(hardest["quiz"], hardest["question"]))
    res["hardest"] = hardest
    tier_rows = []
    for q, qq in hardest.items():
        d = f[(f["quiz"] == q) & f[f"{qq}_correct"]]
        for tier in C.TIER_LABELS:
            s = d.loc[d["tier"] == tier, "duration_min"]
            lo, hi = bootstrap_ci(s.values, np.median)
            tier_rows.append({"quiz": q, "question": qq, "tier": tier,
                              "median": s.median(), "lo": lo, "hi": hi,
                              "n": int(len(s))})
        res[f"kruskal_q{q}"] = kruskal([d.loc[d["tier"] == tr, "duration_min"]
                                        for tr in C.TIER_LABELS])
    tt = pd.DataFrame(tier_rows)
    res["hard_q_time_by_tier"] = tt.round(2).to_dict(orient="records")
    res["all_first_time_by_tier"] = (f.groupby(["quiz", "tier"], observed=True)
                                     ["duration_min"].median().round(2)
                                     .unstack().to_dict(orient="index"))
    res["quiz_level"] = {q: {"median_min": float(f.loc[f["quiz"] == q, "duration_min"].median()),
                             "mean_grade": float(f.loc[f["quiz"] == q, "grade"].mean())}
                         for q in (1, 2, 3)}

    # ---------------------------------------------------------------- figure
    apply_style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.9),
                               gridspec_kw={"width_ratios": [1.1, 1]})
    a.axhline(1, color=C.AXIS, lw=0.9)
    a.text(98, 1.015, "no time difference", ha="right", va="bottom",
           fontsize=6.3, color=C.MUTED)
    for q in (1, 2, 3):
        d = qt[qt["quiz"] == q]
        a.scatter(d["facility"], d["ratio"], s=34, color=C.QUIZ_COLORS[q],
                  edgecolor="white", linewidth=0.7, zorder=3, label=QLABEL[q])
        for r in d.itertuples():
            lab = f"Q{q}.{r.question[1]}"
            off = {"Q2.3": (-4, -7), "Q2.3h": "right"}.get(lab, (3.5, 2.5))
            ha = "right" if lab == "Q2.3" else "left"
            a.annotate(lab, (r.facility, r.ratio), xytext=off, ha=ha,
                       textcoords="offset points", fontsize=5.8, color=C.INK_2)
    # simple least-squares trend line to guide the eye
    k, m0 = np.polyfit(qt["facility"], qt["ratio"], 1)
    xs = np.array([0, 100])
    a.plot(xs, m0 + k * xs, color=C.MUTED, lw=0.9, ls=(0, (1, 0)), alpha=0.7, zorder=2)
    a.set_xlim(0, 100)
    a.set_xlabel("% correct on first attempt   (← harder | easier →)")
    a.set_ylabel("Time ratio: correct ÷ wrong\n(median attempt time)")
    a.set_title("(a) Do hard questions need more time?")
    a.legend(loc="upper left", handletextpad=0.2)
    rho = res["spearman_facility_ratio"]["rho"]
    a.text(0.98, 0.04, f"Spearman ρ = {rho:+.2f} (15 questions)",
           transform=a.transAxes, ha="right", fontsize=6.5, color=C.INK_2)

    # (b) median time by tier, attempts that got the hardest question right
    for i, q in enumerate((1, 2, 3)):
        for j, tier in enumerate(C.TIER_LABELS):
            r = tt[(tt["quiz"] == q) & (tt["tier"] == tier)].iloc[0]
            x = i + (j - 1) * 0.22
            b.errorbar(x, r["median"], yerr=[[r["median"] - r["lo"]], [r["hi"] - r["median"]]],
                       fmt="o", color=C.TIER_COLORS[tier], ms=4.5, elinewidth=1,
                       capsize=0, mec="white", mew=0.6,
                       label=f"{tier} tier" if i == 0 else None)
            b.text(x, 0.35, f"{int(r['n'])}", ha="center", va="bottom",
                   fontsize=5.5, color=C.MUTED)
    b.set_xticks(range(3), [f"Quiz {q}\n(hardest: {hardest[q]})" for q in (1, 2, 3)])
    b.set_ylabel("Median minutes (95% CI)")
    b.set_ylim(0, 15)
    b.set_title("(b) Time of those who got it right")
    b.grid(axis="x", visible=False)
    b.legend(loc="upper right", ncol=3, handletextpad=0.1, columnspacing=0.6,
             fontsize=6.3)
    note(b, "Small grey numbers = attempts in each group.", loc=(0, -0.27))
    fig.tight_layout(w_pad=1.6)
    save(fig, "fig05_h4_difficulty_speed")
    return res


# ======================================================================
# H5  There is an optimal time range for higher scores
# ======================================================================
TIME_BINS = [0, 1, 2, 3, 5, 8, 12, 20, 30, 45, 60, 180, 1440, np.inf]
BIN_CENTRES = [0.6, 1.4, 2.45, 3.9, 6.3, 9.8, 15.5, 24.5, 36.7, 52, 104, 510, 4000]


def h5_optimal_time(att: pd.DataFrame) -> dict:
    f = att[att["is_first"]].copy()        # include long sessions on purpose
    f["tbin"] = pd.cut(f["duration_min"], TIME_BINS, right=True, labels=False)
    res = {"bins": TIME_BINS[:-1] + ["inf"], "per_quiz": {}}

    apply_style()
    fig, (a, b) = plt.subplots(2, 1, figsize=(6.5, 3.9), sharex=True,
                               gridspec_kw={"height_ratios": [2.4, 1]})
    a.axvspan(C.MAX_ACTIVE_MINUTES, 20000, color="#f4f3ef", zorder=0)
    a.text(C.MAX_ACTIVE_MINUTES * 1.12, 9.3, "Over 1 hour: tab most likely left open",
           fontsize=6.5, color=C.MUTED, va="top")
    for q in (1, 2, 3):
        d = summarise_mean(f[f["quiz"] == q], "tbin", "grade")
        d["x"] = [BIN_CENTRES[int(i)] for i in d["tbin"]]
        a.fill_between(d["x"], d["lo"], d["hi"], color=C.QUIZ_COLORS[q],
                       alpha=0.16, lw=0)
        a.plot(d["x"], d["mean"], "-o", color=C.QUIZ_COLORS[q], ms=3.4,
               markeredgecolor="white", markeredgewidth=0.6)
        a.annotate(f"Quiz {q}", (d["x"].iloc[-1], d["mean"].iloc[-1]),
                   xytext=(5, 0), textcoords="offset points", fontsize=6.5,
                   va="center", color=C.INK_2, fontweight="bold")
        active = d[d["x"] <= C.MAX_ACTIVE_MINUTES]
        best = active.loc[active["mean"].idxmax()]
        a.scatter(best["x"], best["mean"], s=70, facecolor="none",
                  edgecolor=C.INK, linewidth=0.9, zorder=4)
        res["per_quiz"][q] = {
            "mean_by_bin": d.set_index("tbin")["mean"].round(2).to_dict(),
            "n_by_bin": d.set_index("tbin")["n"].to_dict(),
            "best_bin": int(best["tbin"]), "best_mean": round(float(best["mean"]), 2),
            "under_1min": round(float(d.loc[d["tbin"] == 0, "mean"].iloc[0]), 2),
        }
    a.set_ylim(0, 10)
    a.set_ylabel("Mean grade, first attempt\n(95% CI)")
    a.set_title("Mean first-attempt grade by time taken")
    a.scatter([], [], s=50, facecolor="none", edgecolor=C.INK, linewidth=0.9,
              label="Best time band (under 1 hour)")
    a.legend(loc="upper left", fontsize=6.5)

    # sample size panel (shared x, separate axis -> no dual axis)
    cnt = f.groupby("tbin").size()
    lefts = [max(TIME_BINS[int(i)], 0.3) for i in cnt.index]
    rights = [min(TIME_BINS[int(i) + 1], 20000) for i in cnt.index]
    for l, r_, v, i in zip(lefts, rights, cnt.values, cnt.index):
        b.bar(l, v, width=(r_ - l) * 0.9, align="edge",
              color=C.NEUTRAL_COLOR if TIME_BINS[int(i)] >= 60 else C.MUTED)
    b.set_ylabel("First\nattempts")
    set_time_axis(b, "x", ticks=(0.5, 1, 2, 5, 10, 20, 60, 1440),
                  label="Time taken (minutes, log scale)")
    b.set_xlim(0.3, 20000)
    b.grid(axis="x", visible=False)
    fig.tight_layout(h_pad=0.6)
    save(fig, "fig06_h5_optimal_time")

    # Pooled numbers: grade relative to quiz mean, so quizzes can be combined
    f["rel"] = f["grade"] - f.groupby("quiz")["grade"].transform("mean")
    pooled = summarise_mean(f, "tbin", "rel")
    res["pooled_relative"] = pooled.round(3).to_dict(orient="records")
    tt = f[f["duration_min"] <= C.MAX_ACTIVE_MINUTES]
    x = np.log10(tt["duration_min"])
    co = np.polyfit(x, tt["grade"] - tt.groupby("quiz")["grade"].transform("mean"), 2)
    res["quadratic_peak_min"] = float(10 ** (-co[1] / (2 * co[0])))
    res["quadratic_coef"] = co.tolist()
    return res


def run(att=None, stu=None) -> dict:
    if att is None:
        att, stu = load_clean()
    apply_style()
    return {"H1": h1_time_vs_score(att), "H2": h2_question_difficulty(att),
            "H3": h3_progress_by_tier(att), "H4": h4_difficulty_and_speed(att),
            "H5": h5_optimal_time(att)}


if __name__ == "__main__":
    out = run()
    C.OUT_DIR.mkdir(exist_ok=True, parents=True)
    with open(C.OUT_DIR / "results_task1.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("Task 1 figures and results saved.")
