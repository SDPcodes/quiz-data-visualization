"""Small statistics helpers used next to the charts.

The charts are the main evidence. These numbers back them up so that the
accept / reject decision does not depend only on how a chart looks.
With ~30,000 attempts almost every test gives a tiny p-value, so we always
report an effect size (correlation, difference in means, share) as well.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import RANDOM_SEED

_rng = np.random.default_rng(RANDOM_SEED)


def bootstrap_ci(values, func=np.mean, n_boot: int = 2000, level: float = 0.95):
    """Percentile bootstrap confidence interval for any statistic."""
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return (np.nan, np.nan)
    idx = _rng.integers(0, len(values), size=(n_boot, len(values)))
    boots = func(values[idx], axis=1)
    lo, hi = np.percentile(boots, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def mean_ci(values, level: float = 0.95):
    """Mean with a normal-approximation confidence interval (fast)."""
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    n = len(values)
    if n < 2:
        return float(np.mean(values)) if n else np.nan, np.nan, np.nan, n
    m = values.mean()
    se = values.std(ddof=1) / np.sqrt(n)
    z = stats.norm.ppf((1 + level) / 2)
    return float(m), float(m - z * se), float(m + z * se), n


def summarise_mean(df: pd.DataFrame, by, col: str) -> pd.DataFrame:
    """Group means with 95% CI and counts, as a tidy table."""
    rows = []
    for key, g in df.groupby(by, observed=True):
        m, lo, hi, n = mean_ci(g[col])
        key = key if isinstance(key, tuple) else (key,)
        rows.append((*key, m, lo, hi, n))
    by = [by] if isinstance(by, str) else list(by)
    return pd.DataFrame(rows, columns=by + ["mean", "lo", "hi", "n"])


def spearman(x, y) -> dict:
    """Spearman rank correlation as a plain dict (rho, p, n)."""
    r = stats.spearmanr(x, y, nan_policy="omit")
    return {"rho": float(r.statistic), "p": float(r.pvalue), "n": int(len(x))}


def kruskal(groups) -> dict:
    """Kruskal-Wallis test across several groups (non-parametric ANOVA)."""
    groups = [np.asarray(g) for g in groups if len(g) > 0]
    r = stats.kruskal(*groups)
    return {"H": float(r.statistic), "p": float(r.pvalue)}


def chi2_equal_props(successes, totals) -> dict:
    """Chi-square test that several proportions are equal."""
    table = np.array([successes, np.asarray(totals) - np.asarray(successes)])
    chi2, p, dof, _ = stats.chi2_contingency(table)
    n = table.sum()
    cramers_v = np.sqrt(chi2 / (n * (min(table.shape) - 1)))
    return {"chi2": float(chi2), "dof": int(dof), "p": float(p),
            "cramers_v": float(cramers_v)}


def mann_whitney(a, b) -> dict:
    """Mann-Whitney U test with the common-language effect size."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    r = stats.mannwhitneyu(a, b, alternative="two-sided")
    cles = r.statistic / (len(a) * len(b))   # P(random a > random b)
    return {"U": float(r.statistic), "p": float(r.pvalue), "cles": float(cles),
            "n_a": int(len(a)), "n_b": int(len(b))}


def fmt_p(p: float) -> str:
    """Readable p-value for the report."""
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"
