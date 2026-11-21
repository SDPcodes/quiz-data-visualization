"""Run the whole project from raw CSV files to figures and result numbers.

Usage (from the project folder):

    python run_all.py

Outputs
    outputs/cleaned_attempts.csv   cleaned attempt-level data
    outputs/students.csv           one row per student (tiers etc.)
    outputs/tables/*.csv           cleaning log and dataset summary
    outputs/figures/*.pdf|png      all figures used in the report
    outputs/results.json           every number quoted in the report
"""
import json
import time

from src import config as C
from src import eda, task1, task2
from src.data_prep import load_clean


def main() -> None:
    t0 = time.time()
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    C.TABLE_DIR.mkdir(parents=True, exist_ok=True)

    print("1/4  Loading and cleaning data ...")
    att, stu, raw, log = load_clean(return_log=True)
    att.to_csv(C.OUT_DIR / "cleaned_attempts.csv", index=False)
    stu.to_csv(C.OUT_DIR / "students.csv", index=False)
    log.to_frame().to_csv(C.TABLE_DIR / "cleaning_log.csv", index=False)

    print("2/4  Dataset overview ...")
    results = {"dataset": eda.dataset_overview(att, stu)}
    results["dataset"].update(eda.summary_tables(att, stu, raw))
    results["cleaning_log"] = log.to_frame().to_dict(orient="records")

    print("3/4  Task 1 hypotheses (H1-H5) ...")
    results.update(task1.run(att, stu))

    print("4/4  Task 2 hypotheses (H6-H10) ...")
    results.update(task2.run(att, stu))

    with open(C.OUT_DIR / "results.json", "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    n_fig = len(list(C.FIG_DIR.glob("*.pdf")))
    print(f"Done in {time.time() - t0:.1f}s - {n_fig} figures in {C.FIG_DIR}")


if __name__ == "__main__":
    main()
