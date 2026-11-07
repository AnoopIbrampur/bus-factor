"""Join every data source into the one table the site renders.

This is where a project gets its activity label, so the language rules live here. Labels
describe commits and nothing else: a project "looks quiet", never "abandoned". Anything we can't
measure is "unknown", with the reason. No code path may turn missing data into a good label,
and tests/test_build.py checks that.
"""

import glob
import math
from datetime import date

import pandas as pd

from .deps import canon, edges
from .health import measures_at
from .simulator import simulate

STATE_LABEL = {
    "active": "Active",
    "slowing": "Slowing down",
    "quiet": "Looks quiet",
    "archived": "Archived by its owners",
    "unknown": "Unknown",
}
STATE_CLASS = {"active": 1, "slowing": 2, "quiet": 3, "archived": 0, "unknown": 0}
SLOWDOWN = math.log(0.5)  # commits at least halved, year on year
MIN_PRIOR_COMMITS = 10  # small projects swing too much for a trend to mean anything


def load_rows(data_dir) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in sorted(glob.glob(str(data_dir / "rows-*.parquet")))]
    return pd.concat(frames, ignore_index=True)


def load_status(data_dir) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in sorted(glob.glob(str(data_dir / "status-*.parquet")))]
    return pd.concat(frames, ignore_index=True)


def classify(row: dict) -> tuple[str, str | None]:
    """Return (state, reason if unknown) for one package row."""
    if row.get("repo_key") is None or pd.isna(row.get("repo_key")):
        return "unknown", "We couldn't find a source repository we can read."
    days = row.get("days_since_human")
    if days is None or pd.isna(days):
        return "unknown", "We couldn't read its git history."
    if row.get("archived") is True:
        return "archived", None
    if days >= 365:
        return "quiet", None
    prior = row.get("commits_prev_365d") or 0
    if prior >= MIN_PRIOR_COMMITS and row.get("trend", 0) <= SLOWDOWN:
        return "slowing", None
    return "active", None


def is_few(row: dict) -> bool:
    """Few active contributors: one person made half the commits, or two or fewer are active."""
    if row["state"] not in ("active", "slowing"):
        return False
    return row["bus_factor"] == 1 or row["active_humans"] <= 2


def band(prob) -> tuple[str | None, int | None]:
    """Fixed display bands, set in D14 before any result. Text always goes with the colour."""
    if prob is None or pd.isna(prob):
        return None, None
    if prob < 0.10:
        return "Lower chance", 1
    if prob < 0.30:
        return "Middle chance", 2
    return "Higher chance", 3


def assemble(
    universe: pd.DataFrame,
    requires: pd.DataFrame,
    rows: pd.DataFrame,
    today: date,
    forecast: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (package table, simulator table)."""
    u = universe.copy()
    u["name"] = u["name"].map(canon)
    u = u.drop_duplicates("name")
    downloads = dict(zip(u["name"], u["downloads"].fillna(0).astype(int), strict=True))
    graph = edges(requires, set(u["name"]))
    sim = simulate(graph, downloads)
    tracked = rows[rows["repo_key"].isin(set(u["repo_key"].dropna()))]
    m = measures_at(tracked, today)
    table = u.merge(m, on="repo_key", how="left")
    table = table.merge(sim.drop(columns=["direct", "indirect"]), on="name", how="left")
    table["total_dependents"] = table["n_direct"].fillna(0) + table["n_indirect"].fillna(0)
    table["total_dependents"] = table["total_dependents"].astype(int)
    shared = table.groupby("repo_key")["name"].transform("size")
    table["shared_repo"] = shared.fillna(1).astype(int)
    if forecast is not None and len(forecast):
        table = table.merge(forecast, on="repo_key", how="left")
    else:
        table["prob"] = None
        table["reasons"] = None

    out = []
    for row in table.to_dict("records"):
        state, reason = classify(row)
        row["state"] = state
        row["unknown_reason"] = reason
        row["has_history"] = state != "unknown"
        row["few_people"] = is_few(row) if row["has_history"] else False
        if not row["has_history"]:
            row["bus_factor"] = None  # never let a missing value read as a number
        row["state_label"] = STATE_LABEL[state]
        row["state_class"] = STATE_CLASS[state]
        prob = row.get("prob")
        row["band_label"], row["band_class"] = band(prob)
        row["prob_pct"] = None if prob is None or pd.isna(prob) else round(100 * float(prob))
        share = row.get("top_share")
        row["top_share_pct"] = None if share is None or pd.isna(share) else round(100 * share)
        bots = row.get("bot_share")
        row["bot_share_pct"] = None if bots is None or pd.isna(bots) else round(100 * bots)
        if not isinstance(row.get("reasons"), list):
            row["reasons"] = []
        out.append(row)
    return pd.DataFrame(out), sim
