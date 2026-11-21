# CS5805 Information Visualization – Class Project

**Looking Inside Three Online Quizzes: A Visual Study of Time, Difficulty and Re-attempts**

Group [XX] – [member names]

This repository has the code, data and report for our class project. We clean
the attempt logs of three Moodle quizzes (32,596 attempts by 6,656 students,
March 2022 – March 2025) and use visualizations to test ten hypotheses:
five given in the brief (Task 1) and five of our own (Task 2).

---

## 1. Folder structure

```
quiz-data-visualization/
├── README.md               this file
├── requirements.txt        Python packages needed
├── run_all.py              runs the whole project (data -> figures -> numbers)
├── dataset/                original data (not modified)
│   ├── quiz1/quiz1_marks.csv
│   ├── quiz2/quiz2_marks.csv
│   └── quiz3/quiz3_marks.csv
├── src/
│   ├── config.py           paths, cleaning thresholds, colour palette
│   ├── data_prep.py        load + clean data, attempt numbers, student tiers
│   ├── stats_utils.py      confidence intervals and statistical tests
│   ├── style.py            shared matplotlib style (fonts, grid, log-time axis)
│   ├── eda.py              dataset overview figure and tables
│   ├── task1.py            hypotheses H1–H5 (given)
│   └── task2.py            hypotheses H6–H10 (our own)
├── tests/
│   └── test_data_prep.py   unit tests for the cleaning code
├── outputs/                created by run_all.py
│   ├── figures/            fig01 ... fig11 (PDF for the report, PNG for preview)
│   ├── tables/             cleaning log, dataset summary
│   ├── cleaned_attempts.csv
│   ├── students.csv
│   └── results.json        every number quoted in the report
└── report/
    ├── report.tex          LaTeX source (main file)
    ├── sec_*.tex           results and discussion sections
    ├── references.bib      references
    └── report.pdf          final report
```

## 2. How to run

Requires Python 3.9 or newer.

```bash
pip install -r requirements.txt
python run_all.py          # about 10 seconds
python -m pytest -q        # optional: run the tests
```

Each analysis file can also be run on its own, for example
`python -m src.task1` or `python -m src.data_prep`.

To rebuild the report PDF (needs a LaTeX installation):

```bash
cd report
latexmk -pdf report.tex
```

## 3. What the code does

### Data preparation (`src/data_prep.py`)
1. Loads the three CSV files and adds a `quiz` column.
2. Removes the 189 `In progress` attempts (no marks recorded).
3. Parses dates and converts "Time taken" text (e.g. `7 mins 25 secs`,
   `1 day 1 hour`, `1 year 362 days`) into seconds.
4. Converts `-` in question columns (question left blank) to 0 and keeps a
   `Qn_skipped` flag. Checks that the grade equals the sum of question marks.
5. Orders each student's attempts by start time and adds attempt number,
   number of attempts, previous grade, change in grade and waiting time since
   the previous attempt.
6. Flags attempts longer than 60 minutes as `long_session` (tab left open).
   These are kept for score analyses and removed from time analyses.
7. Builds a student table. Performance tier = average first-attempt grade over
   the three quizzes: Low < 4, Medium 4 to < 6, High ≥ 6.

### Figures and hypotheses

| Figure | Script | Hypothesis | Decision |
|---|---|---|---|
| fig01_dataset_overview | eda.py | Dataset overview | – |
| fig02_h1_time_vs_score | task1.py | H1 Longer time → higher score | Partly accepted |
| fig03_h2_question_difficulty | task1.py | H2 Some questions consistently harder | Accepted |
| fig04_h3_progress_by_tier | task1.py | H3 High performers improve steadily, low performers erratic | Rejected |
| fig05_h4_difficulty_speed | task1.py | H4 Hard questions take longer; strong students faster | Rejected (indirect test) |
| fig06_h5_optimal_time | task1.py | H5 Optimal time range | Partly accepted |
| fig07_h6_pass_mark | task2.py | H6 Students re-attempt to pass, not to master | Accepted |
| fig08_h7_retake_delay | task2.py | H7 Instant re-attempts reuse the feedback | Accepted |
| fig09_h8_carry_over | task2.py | H8 Good in Quiz 1 → good in later quizzes | Partly accepted |
| fig10_h9_cohort_trend | task2.py | H9 Later cohorts score higher | Partly accepted |
| fig11_h10_blank_answers | task2.py | H10 A blank answer is a sign of low effort | Accepted |

### Design choices used in every figure (`src/style.py`, `src/config.py`)
- Same colour for the same thing everywhere: Quiz 1 blue, Quiz 2 orange,
  Quiz 3 green (checked for colour-blind safety); tiers use one blue from
  light (Low) to dark (High).
- Main comparison always on a common position scale; colour only for groups.
- Log scale for all time axes; 95% confidence intervals shown for means and
  medians; no pie charts, no dual axes, no 3D.

## 4. Notes
- All randomness (bootstrap) uses a fixed seed (`RANDOM_SEED` in `config.py`),
  so results are the same on every run.
- The original CSV files are never changed; all outputs go to `outputs/`.
