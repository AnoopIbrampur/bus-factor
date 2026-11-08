"""Which quiet projects come back? The D22 revival test.

About 4 in 10 projects that go a year without a human commit later have one again. This module
asks whether git history and release activity can tell which ones, under the same walk-forward
rules as the main forecast (D13): features see only data dated on or before the cutoff, a training
row is used only if its 12-month outcome had ended by the test date, and baselines go through the
same pipeline.

One bias is built in and disclosed: training cutoffs before 2022 come from a cohort chosen for
being popular in 2022, and a project quiet in 2019 that was popular in 2022 had partly come back
already. That can only hurt the model on the test years, which use the cohort's own date or later,
so it can't make the test look better than it is.
"""

from datetime import date

import pandas as pd

from .config import TEST_CUTOFFS, TRAIN_CUTOFFS
from .forecast import (
    Gbm,
    Logit,
    calibration_table,
    fit_on,
    metrics,
    outcome,
    paired_cluster_ci,
    train_cutoffs_for,
)
from .health import BOT, FEATURES, YEAR, day_number, measures_at

EXTRA = ["releases_365d", "bot_commits_365d"]
REVIVAL_FEATURES = [*FEATURES, *EXTRA]
BASELINES = {"days_since_human": ["days_since_human"], "releases_365d": ["releases_365d"]}
CANDIDATES = ("logistic", "lightgbm", *BASELINES)


def extra_features(m: pd.DataFrame, rows: pd.DataFrame, release_days, t: int) -> pd.DataFrame:
    """Add release days and bot commits from the 365 days up to day t. Nothing after t."""
    rel = release_days[(release_days["day"] > t - YEAR) & (release_days["day"] <= t)]
    m["releases_365d"] = m["repo_key"].map(rel.groupby("repo_key")["day"].nunique()).fillna(0)
    bots = rows[(rows["person"] == BOT) & (rows["day"] > t - YEAR) & (rows["day"] <= t)]
    m["bot_commits_365d"] = m["repo_key"].map(bots.groupby("repo_key")["n"].sum()).fillna(0)
    return m


def panel_row(rows: pd.DataFrame, cutoff: date, release_days: pd.DataFrame) -> pd.DataFrame:
    """Quiet repos at one cutoff, with features and whether a human commit came within a year."""
    m = measures_at(rows, cutoff)
    m = m[m["commits_365d"] == 0].copy()
    m = extra_features(m, rows, release_days, day_number(cutoff))
    m["revived"] = m["repo_key"].isin(outcome(rows, cutoff).index).astype(int)
    return m


def build_panel(rows: pd.DataFrame, release_days: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for c in sorted(set(TRAIN_CUTOFFS) | set(TEST_CUTOFFS)):
        frames.append(panel_row(rows, c, release_days))
        print(f"revival panel {c}: {len(frames[-1])} quiet repos", flush=True)
    return pd.concat(frames, ignore_index=True)


MAKERS = {
    "logistic": lambda: Logit(REVIVAL_FEATURES),
    "lightgbm": lambda: Gbm(REVIVAL_FEATURES),
    **{k: (lambda c=v: Logit(c)) for k, v in BASELINES.items()},
}


def walk_forward(panel: pd.DataFrame, makers=None) -> pd.DataFrame:
    """Predictions for every test cutoff from every candidate. One row per repo and year."""
    makers = makers or MAKERS
    out = []
    for test in TEST_CUTOFFS:
        past = train_cutoffs_for(test)
        frame = panel[panel["cutoff"] == test.isoformat()]
        preds = frame[["repo_key", "cutoff", "revived"]].rename(columns={"revived": "y"}).copy()
        for name, maker in makers.items():
            preds[name] = fit_on(panel, past, maker, "revived").predict(frame)
        out.append(preds)
    return pd.concat(out, ignore_index=True)


def evaluate(preds: pd.DataFrame, reps: int = 2000) -> dict:
    """The D22 pass rule, which is D13's rule with this test's baselines."""
    y = preds["y"].to_numpy(float)
    overall = {c: metrics(y, preds[c].to_numpy()) for c in CANDIDATES}
    by_year = {
        cutoff: {c: metrics(g["y"].to_numpy(float), g[c].to_numpy()) for c in CANDIDATES}
        for cutoff, g in preds.groupby("cutoff")
    }
    best = min(BASELINES, key=lambda c: overall[c]["log_loss"])
    gain, lo, hi = paired_cluster_ci(preds, "logistic", best, reps)
    g_gain, g_lo, g_hi = paired_cluster_ci(preds, "lightgbm", "logistic", reps)
    gb_gain, gb_lo, gb_hi = paired_cluster_ci(preds, "lightgbm", best, reps)
    passed = lo > 0
    lgb_clear = g_lo > 0 and gb_lo > 0
    return {
        "overall": overall,
        "by_year": by_year,
        "revival_rate_by_year": preds.groupby("cutoff")["y"].mean().to_dict(),
        "best_baseline": best,
        "logistic_vs_best_baseline": {"gain": gain, "ci": [lo, hi]},
        "lightgbm_vs_logistic": {"gain": g_gain, "ci": [g_lo, g_hi]},
        "lightgbm_vs_best_baseline": {"gain": gb_gain, "ci": [gb_lo, gb_hi]},
        "passed": bool(passed or lgb_clear),
        "published_model": "lightgbm" if lgb_clear else ("logistic" if passed else None),
        "calibration": {c: calibration_table(y, preds[c].to_numpy()) for c in CANDIDATES},
        "n_rows": int(len(preds)),
        "n_repos": int(preds["repo_key"].nunique()),
    }


def live_frame(now: pd.DataFrame, rows: pd.DataFrame, release_days, today: date) -> pd.DataFrame:
    """Today's quiet repos with the two extra features, ready for the stored model."""
    quiet = now[now["commits_365d"] == 0].copy()
    return extra_features(quiet, rows, release_days, day_number(today))
