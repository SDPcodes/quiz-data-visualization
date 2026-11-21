"""Load, clean and enrich the three quiz files.

Running this file on its own builds the cleaned tables and prints a short
data-quality summary:

    python -m src.data_prep

Main outputs
------------
attempts : one row per *finished* attempt (all three quizzes together)
students : one row per student with first-attempt marks, attempt counts
           and a performance tier (Low / Medium / High)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C

_RAW_COLUMNS = {
    "Student Code": "student_id",
    "State": "state",
    "Started on": "started_raw",
    "Completed": "completed_raw",
    "Time taken": "time_taken_raw",
    "Grade/10.00": "grade_raw",
    "Q. 1 /2.00": "Q1_raw",
    "Q. 2 /2.00": "Q2_raw",
    "Q. 3 /2.00": "Q3_raw",
    "Q. 4 /2.00": "Q4_raw",
    "Q. 5 /2.00": "Q5_raw",
}

_UNIT_SECONDS = {"year": 365 * 86400, "day": 86400, "hour": 3600,
                 "min": 60, "sec": 1}
_TIME_PATTERN = re.compile(r"(\d+)\s*(year|day|hour|min|sec)s?")
_DATE_FORMAT = "%d %B %Y %I:%M %p"          # e.g. "14 March 2022  6:55 AM"


@dataclass
class CleaningLog:
    """Keeps a record of every cleaning step so it can go into the report."""
    steps: list = field(default_factory=list)

    def add(self, step: str, rows_before: int, rows_after: int, note: str = ""):
        self.steps.append({"step": step, "rows_before": rows_before,
                           "rows_after": rows_after,
                           "rows_removed": rows_before - rows_after,
                           "note": note})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.steps)


# ---------------------------------------------------------------- helpers
def parse_duration(text: str) -> float:
    """Turn Moodle's 'Time taken' text into seconds.

    >>> parse_duration("7 mins 25 secs")
    445.0
    >>> parse_duration("1 day 1 hour")
    90000.0
    >>> bool(np.isnan(parse_duration("-")))
    True
    """
    if not isinstance(text, str) or text.strip() == "-":
        return np.nan
    parts = _TIME_PATTERN.findall(text)
    if not parts:
        return np.nan
    return float(sum(int(n) * _UNIT_SECONDS[u] for n, u in parts))


def load_raw() -> pd.DataFrame:
    """Read the three CSV files and stack them with a `quiz` column."""
    frames = []
    for quiz, path in C.QUIZ_FILES.items():
        df = pd.read_csv(path, dtype=str).rename(columns=_RAW_COLUMNS)
        df["quiz"] = quiz
        df["row_in_file"] = np.arange(len(df))   # keeps original order for ties
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- cleaning
def clean_attempts(raw: pd.DataFrame, log: CleaningLog | None = None
                   ) -> pd.DataFrame:
    """Apply the cleaning rules and add attempt-level features."""
    log = log or CleaningLog()
    df = raw.copy()

    # 1. Keep finished attempts only. "In progress" rows have no marks.
    n0 = len(df)
    df = df[df["state"] == "Finished"].copy()
    log.add("Drop 'In progress' attempts", n0, len(df),
            "No grade, end time or question marks are recorded for these.")

    # 2. Types: ids, dates, numbers.
    df["student_id"] = df["student_id"].astype(int)
    df["started"] = pd.to_datetime(df["started_raw"], format=_DATE_FORMAT)
    df["completed"] = pd.to_datetime(df["completed_raw"], format=_DATE_FORMAT)
    df["duration_sec"] = df["time_taken_raw"].map(parse_duration)
    df["duration_min"] = df["duration_sec"] / 60.0
    df["grade"] = pd.to_numeric(df["grade_raw"])

    # 3. Question marks. A '-' in a finished attempt means the question was
    #    left blank. Moodle counts it as 0 (the grade always equals the sum
    #    of the question marks with '-' as 0), so we do the same and keep a
    #    separate 'skipped' flag.
    for q in C.QUESTIONS:
        raw_col = df[f"{q}_raw"].str.strip()
        df[f"{q}_skipped"] = raw_col.eq("-")
        df[q] = pd.to_numeric(raw_col.replace("-", np.nan)).fillna(0.0)
        df[f"{q}_correct"] = df[q].eq(C.MARK_PER_QUESTION)
    df["n_correct"] = df[[f"{q}_correct" for q in C.QUESTIONS]].sum(axis=1)
    df["n_skipped"] = df[[f"{q}_skipped" for q in C.QUESTIONS]].sum(axis=1)

    mismatch = (df[C.QUESTIONS].sum(axis=1) != df["grade"]).sum()
    log.add("Check grade = sum of question marks", len(df), len(df),
            f"{mismatch} mismatches found.")

    # 4. Attempt order inside each student-quiz pair.
    df = df.sort_values(["student_id", "quiz", "started", "row_in_file"])
    grp = df.groupby(["student_id", "quiz"], sort=False)
    df["attempt_no"] = grp.cumcount() + 1
    df["n_attempts"] = grp["attempt_no"].transform("max")
    df["is_first"] = df["attempt_no"].eq(1)
    df["is_last"] = df["attempt_no"].eq(df["n_attempts"])
    df["prev_grade"] = grp["grade"].shift(1)
    df["grade_change"] = df["grade"] - df["prev_grade"]
    prev_end = grp["completed"].shift(1)
    df["gap_since_prev_min"] = (df["started"] - prev_end).dt.total_seconds() / 60

    # 5. Time flags. No time limit -> some attempts were left open.
    df["long_session"] = df["duration_min"] > C.MAX_ACTIVE_MINUTES
    log.add(f"Flag attempts longer than {C.MAX_ACTIVE_MINUTES} min",
            len(df), len(df),
            f"{int(df['long_session'].sum())} attempts flagged; kept for "
            "score analyses, excluded from time analyses.")

    # 6. Calendar features.
    df["hour"] = df["started"].dt.hour
    df["weekday"] = df["started"].dt.day_name()
    df["year"] = df["started"].dt.year
    df["half_year"] = (df["year"].astype(str) + "-H"
                       + np.where(df["started"].dt.month <= 6, "1", "2"))

    keep = (["student_id", "quiz", "attempt_no", "n_attempts", "is_first",
             "is_last", "started", "completed", "duration_sec", "duration_min",
             "long_session", "grade", "prev_grade", "grade_change",
             "gap_since_prev_min", "n_correct", "n_skipped"]
            + C.QUESTIONS
            + [f"{q}_correct" for q in C.QUESTIONS]
            + [f"{q}_skipped" for q in C.QUESTIONS]
            + ["hour", "weekday", "year", "half_year"])
    return df[keep].reset_index(drop=True)


# ---------------------------------------------------------------- students
def build_students(attempts: pd.DataFrame) -> pd.DataFrame:
    """One row per student, with first-attempt marks and a performance tier.

    Tier rule: the average of the student's FIRST-attempt grades in the
    three quizzes. Low < 4, Medium 4 to <6, High >= 6 (out of 10).
    First attempts are used because later attempts are affected by the
    feedback a student saw, so they say less about what the student knew.
    """
    first = attempts[attempts["is_first"]]
    wide = first.pivot(index="student_id", columns="quiz", values="grade")
    wide.columns = [f"first_q{c}" for c in wide.columns]

    n_att = attempts.pivot_table(index="student_id", columns="quiz",
                                 values="attempt_no", aggfunc="max")
    n_att.columns = [f"attempts_q{c}" for c in n_att.columns]

    best = attempts.pivot_table(index="student_id", columns="quiz",
                                values="grade", aggfunc="max")
    best.columns = [f"best_q{c}" for c in best.columns]

    start = first.pivot(index="student_id", columns="quiz", values="started")
    start.columns = [f"start_q{c}" for c in start.columns]

    st = pd.concat([wide, n_att, best, start], axis=1)
    st["quizzes_done"] = wide.notna().sum(axis=1)
    st["first_mean"] = wide.mean(axis=1)
    st["total_attempts"] = n_att.sum(axis=1)
    st["span_days"] = ((st["start_q3"] - st["start_q1"]).dt.total_seconds()
                       / 86400)

    st["tier"] = assign_tier(st["first_mean"])
    return st.reset_index()


def assign_tier(mean_grade: pd.Series) -> pd.Categorical:
    """Map an average mark (0-10) to Low / Medium / High using fixed cut-offs."""
    lo, hi = C.TIER_CUTS
    tier = pd.cut(mean_grade, bins=[-np.inf, lo, hi, np.inf], right=False,
                  labels=C.TIER_LABELS)
    return pd.Categorical(tier, categories=C.TIER_LABELS, ordered=True)


def leave_one_quiz_out_tier(attempts: pd.DataFrame) -> pd.DataFrame:
    """Tier for each (student, quiz) based only on the OTHER two quizzes.

    Used as a robustness check, so that a student's level is not decided by
    the same marks we are analysing (avoids regression-to-the-mean bias).
    """
    first = attempts[attempts["is_first"]].pivot(
        index="student_id", columns="quiz", values="grade")
    rows = []
    for q in first.columns:
        others = first.drop(columns=q).mean(axis=1)
        tier = assign_tier(others)
        rows.append(pd.DataFrame({"student_id": first.index, "quiz": q,
                                  "tier_loo": np.asarray(tier)}))
    out = pd.concat(rows, ignore_index=True)
    out["tier_loo"] = pd.Categorical(out["tier_loo"], categories=C.TIER_LABELS,
                                     ordered=True)
    return out


def load_clean(return_log: bool = False):
    """Convenience wrapper used by every analysis script."""
    log = CleaningLog()
    raw = load_raw()
    log.add("Load three CSV files", len(raw), len(raw),
            ", ".join(f"Quiz {q}: {n}" for q, n in
                      raw["quiz"].value_counts().sort_index().items()))
    attempts = clean_attempts(raw, log)
    students = build_students(attempts)
    attempts = attempts.merge(students[["student_id", "tier", "first_mean"]],
                              on="student_id", how="left")
    if return_log:
        return attempts, students, raw, log
    return attempts, students


def timed(attempts: pd.DataFrame) -> pd.DataFrame:
    """Attempts that are usable for time analyses (not left open)."""
    return attempts[~attempts["long_session"]].copy()


if __name__ == "__main__":
    att, stu, raw, log = load_clean(return_log=True)
    C.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    att.to_csv(C.OUT_DIR / "cleaned_attempts.csv", index=False)
    stu.to_csv(C.OUT_DIR / "students.csv", index=False)
    log.to_frame().to_csv(C.TABLE_DIR / "cleaning_log.csv", index=False)
    print(log.to_frame().to_string(index=False))
    print(f"\nFinished attempts: {len(att):,} | students: {len(stu):,}")
    print(stu["tier"].value_counts().sort_index())
    print(stu.groupby("tier", observed=True)["first_mean"].agg(["min", "max", "mean"]))
