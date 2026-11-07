"""The public record: freeze a week's predictions before the outcomes exist, grade them later.

A frozen file is written once and never touched, so the git history of the `predictions` branch
proves when each forecast was made. Rows are sorted by repo key, not by probability, so the file
isn't a ranked list of the likeliest projects. The model is stored as plain numbers: the weekly
job scores with it but never refits, because a model that changed every week couldn't be graded.

Scoring rules are in docs/decisions.md (D15) and were published before the first freeze.
"""

import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import HORIZON_DAYS
from .forecast import EPS, Gbm, design, log_loss_each
from .health import BOT, day_number

# Each pair reads (when the value is low, when the value is high).
PHRASES = {
    "days_since_human": ("A human committed recently", "The last human commit was a while ago"),
    "commits_90d": ("Few commits in the past 3 months", "Many commits in the past 3 months"),
    "commits_365d": ("Few commits in the past year", "Many commits in the past year"),
    "commits_prev_365d": ("Few commits the year before", "Many commits the year before"),
    "trend": ("Commits fell from the year before", "Commits rose from the year before"),
    "active_humans": ("Few people committed this year", "Many people committed this year"),
    "regular_humans": ("Few people commit regularly", "Several people commit regularly"),
    "bus_factor": ("Commits are concentrated in few people", "Commits are spread across people"),
    "top_share": ("No single person dominates commits", "One person made most commits"),
    "hhi": ("Commits are spread out", "Commits are concentrated"),
    "active_months": ("Commits landed in few months", "Commits landed in most months"),
    "longest_gap_days": ("Gaps between commits were short", "There was a long gap in commits"),
    "bot_share": ("Few commits came from automation", "Most commits came from automation"),
    "age_days": ("The project is young", "The project has a long history"),
    "handovers_3y": ("The top contributor hasn't changed", "The top contributor has changed"),
    "top_share_of_lifetime": (
        "Its history has many authors",
        "Few people wrote most of its history",
    ),
}


def model_to_json(model, name: str, train: pd.DataFrame | None = None) -> dict:
    """Store a fitted model as plain data, so the weekly job applies it without refitting."""
    platt = {"platt_a": float(model.platt.coef_[0][0]), "platt_b": float(model.platt.intercept_[0])}
    if isinstance(model, Gbm):
        x = design(train, model.columns)
        return {
            "name": name,
            "columns": model.columns,
            "booster": model.model.booster_.model_to_string(),
            # Typical values, used only to word the reasons ("fewer commits than usual").
            "mean": x.mean(axis=0).tolist(),
            **platt,
        }
    return {
        "name": name,
        "columns": model.columns,
        "mean": model.scaler.mean_.tolist(),
        "scale": model.scaler.scale_.tolist(),
        "coef": model.model.coef_[0].tolist(),
        "intercept": float(model.model.intercept_[0]),
        **platt,
    }


def model_id(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


def _booster(spec: dict) -> lgb.Booster:
    return lgb.Booster(model_str=spec["booster"])


def _raw_score(spec: dict, frame: pd.DataFrame) -> np.ndarray:
    x = design(frame, spec["columns"])
    if "booster" in spec:
        p = _booster(spec).predict(x).clip(EPS, 1 - EPS)
        return np.log(p / (1 - p))
    z = (x - np.array(spec["mean"])) / np.array(spec["scale"])
    return z @ np.array(spec["coef"]) + spec["intercept"]


def predict(spec: dict, frame: pd.DataFrame) -> np.ndarray:
    """Chance of going quiet, from the stored model alone."""
    raw = _raw_score(spec, frame)
    return 1 / (1 + np.exp(-(spec["platt_a"] * raw + spec["platt_b"])))


def reasons(spec: dict, frame: pd.DataFrame, top: int = 3) -> list[list[str]]:
    """Plain-language drivers per repo: the features pushing the estimate furthest up.

    For the logistic model a contribution is coefficient times standardised value. For LightGBM it
    is the tree model's own per-feature contribution (TreeSHAP). Either way it says how this
    project differs from typical ones in the model's eyes. These are associations, not causes.
    """
    x = design(frame, spec["columns"])
    if "booster" in spec:
        contrib = _booster(spec).predict(x, pred_contrib=True)[:, :-1]
        above = x > np.array(spec["mean"])
    else:
        z = (x - np.array(spec["mean"])) / np.array(spec["scale"])
        contrib = z * np.array(spec["coef"])
        above = z > 0
    out = []
    for i in range(len(frame)):
        row = []
        for j in np.argsort(-contrib[i])[:top]:
            if contrib[i, j] <= 0.05:
                continue
            low_text, high_text = PHRASES[spec["columns"][j]]
            row.append(high_text if above[i, j] else low_text)
        out.append(row)
    return out


def week_of(day: date) -> date:
    """The Monday that names a week."""
    return day - timedelta(days=day.weekday())


def freeze_payload(
    scored: pd.DataFrame, today: date, primary_id: str, baseline_id: str, rules: str
) -> dict:
    """Build the frozen record. Sorted by repo key on purpose."""
    rows = scored.sort_values("repo_key")
    return {
        "week": week_of(today).isoformat(),
        "frozen_on": today.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "due_on": (today + timedelta(days=HORIZON_DAYS)).isoformat(),
        "primary_model": primary_id,
        "baseline_model": baseline_id,
        "rules": rules,
        "note": "Not a ranking. Sorted by hashed repo key. Chance of no human commit in 365 days.",
        "predictions": [
            {
                "repo_key": r.repo_key,
                "packages": list(r.packages),
                "prob": round(float(r.prob), 4),
                "baseline_prob": round(float(r.baseline_prob), 4),
            }
            for r in rows.itertuples()
        ],
    }


def write_frozen(payload: dict, folder: Path) -> Path | None:
    """Write this week's file, once. Returns None when the week is already frozen."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{payload['week']}.json.gz"
    if path.exists():
        return None
    raw = json.dumps(payload, indent=0, sort_keys=True).encode()
    with open(path, "wb") as f, gzip.GzipFile(filename="", fileobj=f, mtime=0, mode="wb") as z:
        z.write(raw)
    return path


def read_frozen(folder: Path) -> list[dict]:
    out = []
    for path in sorted(folder.glob("*.json.gz")):
        with gzip.open(path) as f:
            out.append(json.load(f))
    return out


def grade(frozen: list[dict], rows: pd.DataFrame, today: date) -> dict:
    """Grade every prediction whose 12 months are over, per the published rules."""
    weeks, due = [], []
    for rec in frozen:
        start = date.fromisoformat(rec["frozen_on"])
        end = date.fromisoformat(rec["due_on"])
        if end >= today:
            due.append(rec["due_on"])
            weeks.append({"week": rec["week"], "n": len(rec["predictions"]), "graded": False})
            continue
        humans = rows[
            (rows["person"] != BOT)
            & (rows["day"] > day_number(start))
            & (rows["day"] <= day_number(end))
        ]
        seen = set(humans["repo_key"])
        known = set(rows["repo_key"])
        preds = [p for p in rec["predictions"] if p["repo_key"] in known]
        y = np.array([0.0 if p["repo_key"] in seen else 1.0 for p in preds])
        p = np.array([q["prob"] for q in preds])
        b = np.array([q["baseline_prob"] for q in preds])
        weeks.append(
            {
                "week": rec["week"],
                "n": len(rec["predictions"]),
                "graded": True,
                "n_graded": len(preds),
                "quiet": int(y.sum()),
                "log_loss": float(log_loss_each(y, p).mean()) if len(y) else None,
                "baseline_log_loss": float(log_loss_each(y, b).mean()) if len(y) else None,
            }
        )
    return {"weeks": weeks, "next_due": min(due) if due else None}
