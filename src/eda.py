"""Dataset overview figure and summary tables (report Section 3).

    python -m src.eda
"""
from __future__ import annotations

import json

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C
from .data_prep import load_clean
from .style import apply_style, save, set_time_axis


def dataset_overview(att: pd.DataFrame, stu: pd.DataFrame) -> dict:
    apply_style()
    fig, axes = plt.subplots(2, 2, figsize=(6.5, 4.9))
    (a, b), (c, d) = axes

    # (a) Finished attempts per month, one line per quiz -----------------
    monthly = (att.groupby([att["started"].dt.to_period("M"), "quiz"])
                  .size().unstack("quiz"))
    x = monthly.index.to_timestamp()
    for q in (1, 2, 3):
        a.plot(x, monthly[q], color=C.QUIZ_COLORS[q], lw=1.3, label=f"Quiz {q}")
    a.legend(loc="upper right", handlelength=1.2)
    a.set_title("(a) Attempts per month")
    a.set_ylabel("Finished attempts")
    a.set_ylim(0, None)
    a.set_xlim(x[0], x[-1])
    a.xaxis.set_major_locator(mdates.YearLocator())
    a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # (b) Time taken, log histogram with the 60-minute cut-off -----------
    mins = att["duration_min"].clip(lower=0.1)
    bins = np.logspace(np.log10(0.1), np.log10(mins.max()), 70)
    keep = mins <= C.MAX_ACTIVE_MINUTES
    b.hist(mins[keep], bins=bins, color=C.QUIZ_COLORS[1], rwidth=0.85)
    b.hist(mins[~keep], bins=bins, color=C.NEUTRAL_COLOR, rwidth=0.85)
    b.axvline(C.MAX_ACTIVE_MINUTES, color=C.INK_2, lw=0.8)
    share_long = (~keep).mean()
    b.text(C.MAX_ACTIVE_MINUTES * 1.15, b.get_ylim()[1] * 0.92,
           f"> 60 min: {share_long:.1%}\nof attempts\n(tab left open,\nnot used for time)",
           fontsize=6.5, color=C.INK_2, va="top")
    set_time_axis(b, "x", ticks=(0.1, 1, 10, 60, 1440, 43200),
                  label="Time taken (log scale)")
    b.set_title("(b) Time taken is very right-skewed")
    b.set_ylabel("Attempts")

    # (c) Grade distribution, first attempts ------------------------------
    first = att[att["is_first"]]
    grades = np.arange(0, 11, 2)
    w = 0.26
    for i, q in enumerate((1, 2, 3)):
        share = (first[first["quiz"] == q]["grade"].value_counts(normalize=True)
                 .reindex(grades, fill_value=0) * 100)
        c.bar(grades + (i - 1) * w * 2, share, width=w * 2 - 0.08,
              color=C.QUIZ_COLORS[q], label=f"Quiz {q}")
    c.set_xticks(grades)
    c.set_xlabel("Grade on first attempt (out of 10)")
    c.set_ylabel("% of students")
    c.set_title("(c) First-attempt grades")
    c.legend(loc="upper right", ncol=1, handlelength=1)
    c.grid(axis="x", visible=False)

    # (d) Number of attempts per student, 100% stacked bars ---------------
    cats = ["1", "2", "3", "4", "5+"]
    ramp = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
    per = first.assign(k=first["n_attempts"].clip(upper=5).astype(int)
                       .astype(str).replace("5", "5+"))
    tab = (pd.crosstab(per["quiz"], per["k"], normalize="index")
             .reindex(columns=cats, fill_value=0) * 100)
    left = np.zeros(3)
    ypos = np.arange(3)[::-1]
    for j, k in enumerate(cats):
        d.barh(ypos, tab[k].values, left=left, color=ramp[j], height=0.55,
               edgecolor="white", linewidth=1.2, label=k)
        for yy, val, l0 in zip(ypos, tab[k].values, left):
            if val >= 7:
                d.text(l0 + val / 2, yy, f"{val:.0f}%", ha="center",
                       va="center", fontsize=6.5,
                       color="white" if j >= 2 else C.INK)
        left += tab[k].values
    d.set_yticks(ypos, [f"Quiz {q}" for q in (1, 2, 3)])
    d.set_xlim(0, 100)
    d.set_xlabel("% of students")
    d.set_title("(d) Attempts per student")
    d.legend(title="Number of attempts", ncol=5, loc="upper center",
             bbox_to_anchor=(0.5, -0.2), fontsize=6.5, title_fontsize=6.5,
             handlelength=1, columnspacing=0.8)
    d.grid(axis="y", visible=False)

    fig.tight_layout(h_pad=1.6, w_pad=1.6)
    save(fig, "fig01_dataset_overview")

    return {
        "share_long_sessions": float(share_long),
        "attempts_per_quiz": att["quiz"].value_counts().sort_index().to_dict(),
        "mean_first_grade": first.groupby("quiz")["grade"].mean().round(2).to_dict(),
        "median_time_first": first.loc[~first["long_session"]]
            .groupby("quiz")["duration_min"].median().round(2).to_dict(),
        "share_retake": first.groupby("quiz")["n_attempts"]
            .apply(lambda s: (s > 1).mean()).round(3).to_dict(),
        "date_min": str(att["started"].min()), "date_max": str(att["started"].max()),
    }


def summary_tables(att, stu, raw) -> dict:
    """Tables for the Dataset section."""
    C.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    per_quiz = []
    for q in (1, 2, 3):
        r = raw[raw["quiz"] == q]
        a = att[att["quiz"] == q]
        f = a[a["is_first"]]
        per_quiz.append({
            "quiz": q, "raw_rows": len(r),
            "in_progress": int((r["state"] != "Finished").sum()),
            "finished": len(a), "students": a["student_id"].nunique(),
            "mean_attempts": round(a.groupby("student_id").size().mean(), 2),
            "max_attempts": int(a["n_attempts"].max()),
            "first_mean_grade": round(f["grade"].mean(), 2),
            "best_mean_grade": round(a.groupby("student_id")["grade"].max().mean(), 2),
            "median_minutes": round(a.loc[~a["long_session"], "duration_min"].median(), 1),
            "long_sessions": int(a["long_session"].sum()),
            "blank_answers": int(a["n_skipped"].gt(0).sum()),
        })
    t = pd.DataFrame(per_quiz)
    t.to_csv(C.TABLE_DIR / "dataset_summary.csv", index=False)
    return {"per_quiz": per_quiz,
            "students_total": int(stu["student_id"].nunique()),
            "tier_counts": stu["tier"].value_counts().sort_index().to_dict(),
            "tier_mean_first": stu.groupby("tier", observed=True)["first_mean"]
                                  .mean().round(2).to_dict()}


if __name__ == "__main__":
    att, stu, raw, log = load_clean(return_log=True)
    out = dataset_overview(att, stu)
    out.update(summary_tables(att, stu, raw))
    print(json.dumps(out, indent=2, default=str))
