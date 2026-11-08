"""How long a project may go without a human commit: the D18 survival test.

D13 asks one yes-or-no question: no human commit in the next 12 months? This module asks for the
whole curve. S(h) is the chance of no human commit in (t, t+h], for h of 3 months, 6 months,
1 year and 2 years. S(365) is exactly D13's `quiet`.

The model is a discrete-time hazard. Each repo at a cutoff gets one row per interval it enters
while still silent, labelled by whether its next human commit lands inside that interval. Any
classifier then estimates the hazard, and S(h) is the product of (1 - hazard) up to h. That keeps
every curve in order (S can only fall) and lets a 2021 row teach the 3-month interval even though
its 2-year outcome wasn't known yet.

Two rules keep the test honest, and tests/test_survival.py checks both:

- A training row from cutoff c, used for test cutoff T, sees only commits on or before T. Its
  interval is used only if it had fully ended by T.
- A test item (cutoff T, horizon h) is scored only if T + h is on or before the pinned as-of date,
  so every scored outcome is fully known. No censoring weights are needed.

Rules are in docs/decisions.md (D18), committed before this ran on real data.
"""

from datetime import date, timedelta

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .config import TEST_CUTOFFS, TRAIN_CUTOFFS
from .forecast import (
    BASELINES,
    EPS,
    FEATURES,
    Gbm,
    calibration_table,
    design,
    fit_on,
    log_loss_each,
    metrics,
    paired_cluster_ci,
    train_cutoffs_for,
)
from .health import BOT, day_number

INTERVALS = ((0, 90), (90, 180), (180, 365), (365, 730))
HORIZONS = tuple(hi for _, hi in INTERVALS)
CANDIDATES = ("logistic", "lightgbm", "km", *BASELINES)
SURVIVAL_BASELINES = ("km", *BASELINES)


def next_gap(rows: pd.DataFrame, cutoff: date, seen_until: date) -> pd.Series:
    """Days from the cutoff to the next human commit, using only commits up to seen_until.

    A repo with no such commit is missing from the result: as far as anyone could tell on
    seen_until, it was still silent.
    """
    t, s = day_number(cutoff), day_number(seen_until)
    humans = rows[(rows["person"] != BOT) & (rows["day"] > t) & (rows["day"] <= s)]
    return humans.groupby("repo_key")["day"].min() - t


def expand(base: pd.DataFrame, gap: pd.Series, cutoff: date, seen_until: date) -> pd.DataFrame:
    """One row per (repo, interval) entered while silent, for intervals over by seen_until."""
    room = (seen_until - cutoff).days
    g = base["repo_key"].map(gap)
    parts = []
    for k, (lo, hi) in enumerate(INTERVALS):
        if hi > room:
            break  # this interval hadn't ended by seen_until, so its outcome wasn't known
        alive = g.isna() | (g > lo)
        frame = base[alive.to_numpy()].copy()
        gk = g[alive]
        frame["interval"] = k
        frame["event"] = (gk.notna() & (gk > lo) & (gk <= hi)).astype(int).to_numpy()
        parts.append(frame)
    if not parts:
        return base.iloc[0:0].assign(interval=pd.Series(dtype=int), event=pd.Series(dtype=int))
    return pd.concat(parts, ignore_index=True)


def silent_through(gap: pd.Series, keys: pd.Series, h: int) -> np.ndarray:
    """1 if no human commit within h days of the cutoff, from gaps seen far enough ahead."""
    g = keys.map(gap)
    return (g.isna() | (g > h)).astype(int).to_numpy()


def _dummies(intervals: np.ndarray) -> np.ndarray:
    return np.column_stack([(intervals == k).astype(float) for k in range(1, len(INTERVALS))])


class HazardModel:
    """Shared curve logic: hazards for every interval, multiplied into survival chances."""

    def hazard(self, frame: pd.DataFrame, interval: int) -> np.ndarray:
        raise NotImplementedError

    def survival(self, frame: pd.DataFrame) -> np.ndarray:
        """S at each horizon, shape (rows, 4). Falls (or stays level) from left to right."""
        h = np.column_stack([self.hazard(frame, k) for k in range(len(INTERVALS))])
        return np.cumprod(1 - np.clip(h, EPS, 1 - EPS), axis=1)


class HazardLogit(HazardModel):
    """Standardised logistic hazard with interval dummies. With no columns, dummies only."""

    def __init__(self, columns: list[str]):
        self.columns = columns
        self.scaler = StandardScaler()
        self.model = LogisticRegression(C=1.0, max_iter=2000)

    def _x(self, frame: pd.DataFrame, intervals: np.ndarray, fit: bool = False) -> np.ndarray:
        d = _dummies(intervals)
        if not self.columns:
            return d
        x = design(frame, self.columns)
        z = self.scaler.fit_transform(x) if fit else self.scaler.transform(x)
        return np.column_stack([z, d])

    def fit(self, train: pd.DataFrame) -> "HazardLogit":
        self.model.fit(self._x(train, train["interval"].to_numpy(), fit=True), train["event"])
        return self

    def hazard(self, frame: pd.DataFrame, interval: int) -> np.ndarray:
        x = self._x(frame, np.full(len(frame), interval))
        return self.model.predict_proba(x)[:, 1]


class HazardGbm(HazardModel):
    """LightGBM hazard with D13's fixed settings and the interval index as one more input."""

    def __init__(self, columns: list[str]):
        self.columns = columns
        self.model = Gbm(columns).model  # same hyperparameters as the D13 challenger

    def _x(self, frame: pd.DataFrame, intervals: np.ndarray) -> np.ndarray:
        return np.column_stack([design(frame, self.columns), intervals.astype(float)])

    def fit(self, train: pd.DataFrame) -> "HazardGbm":
        self.model.fit(self._x(train, train["interval"].to_numpy()), train["event"])
        return self

    def hazard(self, frame: pd.DataFrame, interval: int) -> np.ndarray:
        return self.model.predict_proba(self._x(frame, np.full(len(frame), interval)))[:, 1]


class KaplanMeier(HazardModel):
    """No features: each interval's hazard is the share of training rows with a commit in it."""

    def fit(self, train: pd.DataFrame) -> "KaplanMeier":
        rates = train.groupby("interval")["event"].mean()
        self.rates = [float(rates.get(k, 0.5)) for k in range(len(INTERVALS))]
        return self

    def hazard(self, frame: pd.DataFrame, interval: int) -> np.ndarray:
        return np.full(len(frame), self.rates[interval])


MAKERS = {
    "logistic": lambda: HazardLogit(FEATURES),
    "lightgbm": lambda: HazardGbm(FEATURES),
    "km": KaplanMeier,
    **{k: (lambda c=v: HazardLogit(c)) for k, v in BASELINES.items()},
}


def training_rows(
    panel: pd.DataFrame, rows: pd.DataFrame, seen_until: date, cutoffs
) -> pd.DataFrame:
    """Person-period rows from every usable cutoff, seeing commits only up to seen_until."""
    parts = []
    for c in sorted(cutoffs):
        if c >= seen_until:
            continue
        base = panel[panel["cutoff"] == c.isoformat()]
        if len(base):
            parts.append(expand(base, next_gap(rows, c, seen_until), c, seen_until))
    return pd.concat(parts, ignore_index=True)


def walk_forward(panel: pd.DataFrame, rows: pd.DataFrame, as_of: date, makers=None) -> pd.DataFrame:
    """Scored items for every test cutoff and horizon whose outcome is known by as_of.

    One row per (repo, cutoff, horizon): y = 1 if silent through the horizon, and each
    candidate's S(h). At 365 days the D13 LightGBM, refitted here, sits alongside for comparison.
    """
    makers = makers or MAKERS
    out = []
    for test in TEST_CUTOFFS:
        if test + timedelta(days=HORIZONS[0]) > as_of:
            continue
        train = training_rows(panel, rows, test, TRAIN_CUTOFFS)
        frame = panel[panel["cutoff"] == test.isoformat()].reset_index(drop=True)
        gap = next_gap(rows, test, as_of)
        curves = {name: maker().fit(train).survival(frame) for name, maker in makers.items()}
        d13 = None
        past = train_cutoffs_for(test)
        if test + timedelta(days=365) <= as_of and len(past) >= 2 and "quiet" in panel:
            d13 = fit_on(panel, past, lambda: Gbm(FEATURES), "quiet").predict(frame)
        for j, h in enumerate(HORIZONS):
            if test + timedelta(days=h) > as_of:
                continue
            items = pd.DataFrame(
                {
                    "repo_key": frame["repo_key"].to_numpy(),
                    "cutoff": test.isoformat(),
                    "horizon": h,
                    "y": silent_through(gap, frame["repo_key"], h),
                }
            )
            for name, s in curves.items():
                items[name] = s[:, j]
            items["d13_lightgbm"] = d13 if (h == 365 and d13 is not None) else np.nan
            out.append(items)
    return pd.concat(out, ignore_index=True)


def evaluate(items: pd.DataFrame, reps: int = 2000) -> dict:
    """Apply the D18 pass rule, and gather everything the report shows."""
    cands = [c for c in CANDIDATES if c in items]
    bases = [c for c in SURVIVAL_BASELINES if c in items]
    y = items["y"].to_numpy(float)
    overall = {c: metrics(y, items[c].to_numpy()) for c in cands}
    by_horizon, by_fold, calibration = {}, {}, {}
    for h, g in items.groupby("horizon"):
        gy = g["y"].to_numpy(float)
        by_horizon[str(h)] = {c: metrics(gy, g[c].to_numpy()) for c in cands}
        calibration[str(h)] = {c: calibration_table(gy, g[c].to_numpy()) for c in cands}
        for cutoff, f in g.groupby("cutoff"):
            fy = f["y"].to_numpy(float)
            by_fold[f"{cutoff} {h}"] = {c: metrics(fy, f[c].to_numpy()) for c in cands}
    best = min(bases, key=lambda c: overall[c]["log_loss"])
    gain, lo, hi = paired_cluster_ci(items, "logistic", best, reps)
    g_gain, g_lo, g_hi = paired_cluster_ci(items, "lightgbm", "logistic", reps)
    gb_gain, gb_lo, gb_hi = paired_cluster_ci(items, "lightgbm", best, reps)
    passed = lo > 0
    lgb_clear = g_lo > 0 and gb_lo > 0
    result = {
        "overall": overall,
        "by_horizon": by_horizon,
        "by_fold": by_fold,
        "calibration": calibration,
        "best_baseline": best,
        "logistic_vs_best_baseline": {"gain": gain, "ci": [lo, hi]},
        "lightgbm_vs_logistic": {"gain": g_gain, "ci": [g_lo, g_hi]},
        "lightgbm_vs_best_baseline": {"gain": gb_gain, "ci": [gb_lo, gb_hi]},
        "passed": bool(passed or lgb_clear),
        "published_model": "lightgbm" if lgb_clear else ("logistic" if passed else None),
        "n_items": int(len(items)),
        "n_repos": int(items["repo_key"].nunique()),
    }
    at_year = items[(items["horizon"] == 365) & items["d13_lightgbm"].notna()]
    if len(at_year):
        yy = at_year["y"].to_numpy(float)
        result["at_365_vs_d13_refit"] = {
            c: float(log_loss_each(yy, at_year[c].to_numpy()).mean())
            for c in [*cands, "d13_lightgbm"]
        }
    return result


def model_to_json(model: HazardModel, name: str) -> dict:
    """Store the adopted hazard model as plain data for the weekly job, which never refits."""
    if isinstance(model, HazardGbm):
        return {
            "name": name,
            "kind": "lightgbm",
            "columns": model.columns,
            "booster": model.model.booster_.model_to_string(),
        }
    return {
        "name": name,
        "kind": "logistic",
        "columns": model.columns,
        "mean": model.scaler.mean_.tolist(),
        "scale": model.scaler.scale_.tolist(),
        "coef": model.model.coef_[0].tolist(),
        "intercept": float(model.model.intercept_[0]),
    }


def curve_from_json(spec: dict, frame: pd.DataFrame) -> np.ndarray:
    """S at 90, 180, 365 and 730 days from a stored model. Shape (rows, 4)."""
    x = design(frame, spec["columns"])
    hazards = []
    if spec["kind"] == "lightgbm":
        booster = lgb.Booster(model_str=spec["booster"])
        for k in range(len(INTERVALS)):
            hazards.append(booster.predict(np.column_stack([x, np.full(len(frame), float(k))])))
    else:
        z = (x - np.array(spec["mean"])) / np.array(spec["scale"])
        coef = np.array(spec["coef"])
        for k in range(len(INTERVALS)):
            d = _dummies(np.full(len(frame), k))
            score = np.column_stack([z, d]) @ coef + spec["intercept"]
            hazards.append(1 / (1 + np.exp(-score)))
    h = np.clip(np.column_stack(hazards), EPS, 1 - EPS)
    return np.cumprod(1 - h, axis=1)


def displayed(s90: float, s180: float, s730: float, year: float) -> dict:
    """D18 display rule: keep the shown points in order around the frozen 12-month chance."""
    shown = {"s90": max(s90, year), "s180": max(s180, year), "s730": min(s730, year)}
    return {
        **{k: round(100 * v) for k, v in shown.items()},
        "adjusted": [k for k, raw in zip(shown, (s90, s180, s730), strict=True) if shown[k] != raw],
    }
