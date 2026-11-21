"""Basic tests for the cleaning code.  Run with:  python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from src import config as C
from src.data_prep import (assign_tier, clean_attempts, load_clean,
                           parse_duration)


# ------------------------------------------------------------ parse_duration
@pytest.mark.parametrize("text, seconds", [
    ("41 secs", 41),
    ("1 min 4 secs", 64),
    ("7 mins 25 secs", 445),
    ("2 days 21 hours", 2 * 86400 + 21 * 3600),
    ("1 year 362 days", 365 * 86400 + 362 * 86400),
    ("12 days", 12 * 86400),
])
def test_parse_duration(text, seconds):
    assert parse_duration(text) == seconds


def test_parse_duration_missing():
    assert np.isnan(parse_duration("-"))
    assert np.isnan(parse_duration(None))


# ------------------------------------------------------------ clean_attempts
def _toy_raw():
    """Three attempts by student 7 on quiz 1 (out of order) + one unfinished."""
    rows = [
        # id, state, start, end, time, grade, q1..q5
        ("7", "Finished", "1 April 2023  10:30 AM", "1 April 2023  10:40 AM",
         "10 mins", "6.00", "2.00", "2.00", "2.00", "0.00", "0.00"),
        ("7", "Finished", "1 April 2023  8:00 AM", "1 April 2023  8:05 AM",
         "5 mins", "2.00", "2.00", "0.00", "0.00", "-", "0.00"),
        ("7", "Finished", "3 April 2023  9:00 AM", "4 April 2023  9:00 AM",
         "1 day", "8.00", "2.00", "2.00", "2.00", "2.00", "0.00"),
        ("8", "In progress", "2 April 2023  9:00 AM", "-", "-", "-",
         "-", "-", "-", "-", "-"),
    ]
    cols = ["student_id", "state", "started_raw", "completed_raw",
            "time_taken_raw", "grade_raw"] + [f"Q{i}_raw" for i in range(1, 6)]
    df = pd.DataFrame(rows, columns=cols)
    df["quiz"] = 1
    df["row_in_file"] = range(len(df))
    return df


def test_clean_attempts_toy():
    out = clean_attempts(_toy_raw())
    # unfinished attempt removed
    assert len(out) == 3 and set(out["student_id"]) == {7}
    # attempts are numbered by start time, not by file order
    assert out["grade"].tolist() == [2, 6, 8]
    assert out["attempt_no"].tolist() == [1, 2, 3]
    assert out["n_attempts"].eq(3).all()
    # blank answer -> 0 marks + skipped flag
    first = out.iloc[0]
    assert first["Q4"] == 0 and bool(first["Q4_skipped"])
    # change in grade and waiting time since the previous attempt
    assert out["grade_change"].tolist()[1:] == [4, 2]
    assert out["gap_since_prev_min"].iloc[1] == pytest.approx(145)
    # the 1-day attempt is flagged as a long session
    assert out["long_session"].tolist() == [False, False, True]


# ------------------------------------------------------------ tiers
def test_assign_tier_cutoffs():
    tiers = assign_tier(pd.Series([0, 3.9, 4.0, 5.99, 6.0, 10]))
    assert list(tiers) == ["Low", "Low", "Medium", "Medium", "High", "High"]


# ------------------------------------------------------------ real data
@pytest.fixture(scope="module")
def real():
    if not C.QUIZ_FILES[1].exists():
        pytest.skip("dataset not found")
    return load_clean()


def test_real_grade_equals_question_sum(real):
    att, _ = real
    assert (att[C.QUESTIONS].sum(axis=1) == att["grade"]).all()


def test_real_attempt_numbers_are_complete(real):
    att, _ = real
    g = att.groupby(["student_id", "quiz"])["attempt_no"]
    assert (g.max() == g.size()).all()


def test_real_counts(real):
    att, stu = real
    assert len(att) == 32_407
    assert len(stu) == 6_656
