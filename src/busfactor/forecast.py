"""Walk-forward test of whether git history predicts a project going quiet.

The rules are pre-registered in docs/decisions.md, and this module does exactly what they say.
Three things keep the test fair:

- Features come from `health.measures_at`, which can't see past the cutoff.
- A training row is used only if its 12-month outcome had finished by the test date
  (`train_cutoffs_for`), so the model never learns from a result that wasn't known yet.
- Baselines are fitted through the same pipeline as the model. A one-feature logistic fit turns
  each simple rule into a probability, so all are compared on the same proper score.

Repos are the unit, and the bootstrap resamples repos, because a repo appears once per test year
and those rows are not independent.
"""

import json
from datetime import date, timedelta

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from .config import HORIZON_DAYS, TEST_CUTOFFS, TRAIN_CUTOFFS
from .health import BOT, FEATURES, day_number, measures_at

LOG_FEATURES = {
    "days_since_human",
    "commits_90d",
    "commits_365d",
    "commits_prev_365d",
    "active_humans",
    "regular_humans",
    "bus_factor",
    "longest_gap_days",
    "age_days",
    # D22 revival features. Not in D13's feature list, so D13 is unaffected.
    "releases_365d",
    "bot_commits_365d",
}
BASELINES = {"last_commit": ["days_since_human"], "commits_past_year": ["commits_365d"]}
EPS = 1e-6


def train_cutoffs_for(test: date, candidates=TRAIN_CUTOFFS) -> list[date]:
    """Training cutoffs whose outcome window had closed by the test date."""
    return [c for c in candidates if c + timedelta(days=HORIZON_DAYS) <= test]


def outcome(rows: pd.DataFrame, cutoff: date) -> pd.Series:
    """True per repo with a human commit in the 365 days after the cutoff."""
    t = day_number(cutoff)
    humans = rows[(rows["person"] != BOT) & (rows["day"] > t) & (rows["day"] <= t + HORIZON_DAYS)]
    return pd.Series(True, index=humans["repo_key"].unique(), name="commit_after", dtype=bool)


def panel_row(rows: pd.DataFrame, cutoff: date, release_days=None) -> pd.DataFrame:
    """Eligible repos at one cutoff, with features and the outcome.

    Eligible means at least one human commit in the prior 365 days. `quiet` is the primary
    outcome. `quiet_strict` also needs no PyPI release in the window, when release dates exist.
    """
    m = measures_at(rows, cutoff)
    m = m[m["commits_365d"] > 0].copy()
    after = outcome(rows, cutoff)
    m["quiet"] = (~m["repo_key"].isin(after.index)).astype(int)
    if release_days is not None:
        t = day_number(cutoff)
        rel = release_days[(release_days["day"] > t) & (release_days["day"] <= t + HORIZON_DAYS)]
        released = set(rel["repo_key"])
        m["quiet_strict"] = (m["quiet"].eq(1) & ~m["repo_key"].isin(released)).astype(int)
    return m


def design(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Model inputs: counts and durations on a log scale, the rest as they are."""
    parts = [
        np.log1p(frame[c].to_numpy(float)) if c in LOG_FEATURES else frame[c].to_numpy(float)
        for c in columns
    ]
    return np.column_stack(parts)


class Logit:
    """Standardised logistic regression, followed by Platt calibration on the latest year."""

    def __init__(self, columns: list[str]):
        self.columns = columns
        self.scaler = StandardScaler()
        self.model = LogisticRegression(C=1.0, max_iter=2000)
        self.platt = LogisticRegression(C=1e6, max_iter=1000)

    def _score(self, frame: pd.DataFrame) -> np.ndarray:
        return self.model.decision_function(self.scaler.transform(design(frame, self.columns)))

    def fit(self, train: pd.DataFrame, calib: pd.DataFrame, target: str) -> "Logit":
        self.scaler.fit(design(train, self.columns))
        self.model.fit(self.scaler.transform(design(train, self.columns)), train[target])
        self.platt.fit(self._score(calib).reshape(-1, 1), calib[target])
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.platt.predict_proba(self._score(frame).reshape(-1, 1))[:, 1]


class Gbm:
    """LightGBM challenger, deliberately small, with the same Platt step on its log-odds."""

    def __init__(self, columns: list[str]):
        self.columns = columns
        self.model = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.03,
            num_leaves=8,
            min_child_samples=30,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            random_state=0,
            n_jobs=2,
            verbosity=-1,
        )
        self.platt = LogisticRegression(C=1e6, max_iter=1000)

    def _score(self, frame: pd.DataFrame) -> np.ndarray:
        p = self.model.predict_proba(design(frame, self.columns))[:, 1].clip(EPS, 1 - EPS)
        return np.log(p / (1 - p))

    def fit(self, train: pd.DataFrame, calib: pd.DataFrame, target: str) -> "Gbm":
        self.model.fit(design(train, self.columns), train[target])
        self.platt.fit(self._score(calib).reshape(-1, 1), calib[target])
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.platt.predict_proba(self._score(frame).reshape(-1, 1))[:, 1]


def fit_on(panel: pd.DataFrame, cutoffs: list[date], maker, target: str):
    """Fit on all but the latest cutoff and calibrate on the latest."""
    names = sorted(c.isoformat() for c in cutoffs)
    train = panel[panel["cutoff"].isin(names[:-1])]
    calib = panel[panel["cutoff"] == names[-1]]
    return maker().fit(train, calib, target)


def walk_forward(panel: pd.DataFrame, target: str = "quiet") -> pd.DataFrame:
    """Predictions for every test cutoff from every candidate. One row per repo and year."""
    makers = {
        "logistic": lambda: Logit(FEATURES),
        "lightgbm": lambda: Gbm(FEATURES),
        **{k: (lambda c=v: Logit(c)) for k, v in BASELINES.items()},
    }
    out = []
    for test in TEST_CUTOFFS:
        past = train_cutoffs_for(test)
        frame = panel[panel["cutoff"] == test.isoformat()]
        preds = frame[["repo_key", "cutoff", target]].rename(columns={target: "y"}).copy()
        for name, maker in makers.items():
            preds[name] = fit_on(panel, past, maker, target).predict(frame)
        out.append(preds)
    return pd.concat(out, ignore_index=True)


def log_loss_each(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    k = max(1, int(round(0.1 * len(y))))
    top = np.argsort(-p, kind="stable")[:k]
    both = len(set(y.tolist())) == 2
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "log_loss": float(log_loss_each(y, p).mean()),
        "brier": float(((p - y) ** 2).mean()),
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
        "pr_auc": float(average_precision_score(y, p)) if both else None,
        "precision_top_decile": float(y[top].mean()),
    }


def paired_cluster_ci(
    frame: pd.DataFrame, a: str, b: str, reps: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    """Mean log-loss of b minus a, with a 95% CI from resampling repos. Above 0 favours a."""
    work = pd.DataFrame(
        {
            "repo_key": frame["repo_key"].to_numpy(),
            "diff": log_loss_each(frame["y"].to_numpy(float), frame[b].to_numpy())
            - log_loss_each(frame["y"].to_numpy(float), frame[a].to_numpy()),
        }
    )
    per = work.groupby("repo_key")["diff"].agg(["sum", "size"])
    s, c = per["sum"].to_numpy(), per["size"].to_numpy()
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(len(s), np.full(len(s), 1 / len(s)), size=reps)
    stats = (draws @ s) / (draws @ c)
    return (
        float(s.sum() / c.sum()),
        float(np.quantile(stats, 0.025)),
        float(np.quantile(stats, 0.975)),
    )


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    order = np.argsort(p, kind="stable")
    return [
        {
            "n": int(len(ix)),
            "mean_predicted": float(p[ix].mean()),
            "observed": float(y[ix].mean()),
        }
        for ix in np.array_split(order, bins)
        if len(ix)
    ]


def evaluate(preds: pd.DataFrame, reps: int = 2000) -> dict:
    """Apply the pre-registered pass rule (D13) and return everything the report shows."""
    y = preds["y"].to_numpy(float)
    candidates = ["logistic", "lightgbm", *BASELINES]
    overall = {c: metrics(y, preds[c].to_numpy()) for c in candidates}
    by_year = {
        cutoff: {c: metrics(g["y"].to_numpy(float), g[c].to_numpy()) for c in candidates}
        for cutoff, g in preds.groupby("cutoff")
    }
    best_base = min(BASELINES, key=lambda c: overall[c]["log_loss"])
    gain, lo, hi = paired_cluster_ci(preds, "logistic", best_base, reps)
    g_gain, g_lo, g_hi = paired_cluster_ci(preds, "lightgbm", "logistic", reps)
    gb_gain, gb_lo, gb_hi = paired_cluster_ci(preds, "lightgbm", best_base, reps)
    passed = lo > 0
    lgb_clear = g_lo > 0 and gb_lo > 0
    return {
        "overall": overall,
        "by_year": by_year,
        "best_baseline": best_base,
        "logistic_vs_best_baseline": {"gain": gain, "ci": [lo, hi]},
        "lightgbm_vs_logistic": {"gain": g_gain, "ci": [g_lo, g_hi]},
        "lightgbm_vs_best_baseline": {"gain": gb_gain, "ci": [gb_lo, gb_hi]},
        "passed": bool(passed or lgb_clear),
        "published_model": "lightgbm" if lgb_clear else ("logistic" if passed else best_base),
        "calibration": {c: calibration_table(y, preds[c].to_numpy()) for c in candidates},
    }


def criticality_comparison(preds: pd.DataFrame, scores: pd.Series, reps: int = 2000) -> dict | None:
    """Compare ranking quality with OpenSSF criticality on the only year it can be used.

    Scores can't be turned into probabilities without earlier data, so this compares ROC-AUC, on
    the repos the score covers. Direction was fixed in advance: a lower score means more likely
    quiet. CI comes from resampling repos.
    """
    last = preds[preds["cutoff"] == TEST_CUTOFFS[-1].isoformat()].copy()
    last["criticality"] = last["repo_key"].map(scores)
    last = last.dropna(subset=["criticality"])
    if last.empty or last["y"].nunique() < 2:
        return None
    y = last["y"].to_numpy()
    model, crit = last["logistic"].to_numpy(), -last["criticality"].to_numpy()
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(reps):
        ix = rng.integers(0, len(y), len(y))
        if len(set(y[ix].tolist())) == 2:
            diffs.append(roc_auc_score(y[ix], model[ix]) - roc_auc_score(y[ix], crit[ix]))
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "logistic_auc": float(roc_auc_score(y, model)),
        "criticality_auc": float(roc_auc_score(y, crit)),
        "diff_ci": [float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))],
    }


def build_panel(rows: pd.DataFrame, release_days=None) -> pd.DataFrame:
    """Features and outcomes for every cutoff. Slow, so it is run once and saved."""
    frames = []
    for c in sorted(set(TRAIN_CUTOFFS) | set(TEST_CUTOFFS)):
        frames.append(panel_row(rows, c, release_days))
        print(f"panel {c}: {len(frames[-1])} eligible repos", flush=True)
    return pd.concat(frames, ignore_index=True)


def save_json(obj, path) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
