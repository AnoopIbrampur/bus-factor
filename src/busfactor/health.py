"""Health measures for a repo as of any date, built only from commits dated on or before it.

`measures_at` drops every later row before it computes anything. That single filter is what
keeps the backtest honest, and tests/test_point_in_time.py fails if a future commit can change
any value. All measures use human commits; bots are counted separately so a project kept busy
by automation doesn't look staffed.

Input rows are (repo_key, day, person, n, m), where person -1 pools all bots.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

BOT = -1
EPOCH = date(1970, 1, 1)
YEAR = 365
FEATURES = [
    "days_since_human",
    "commits_90d",
    "commits_365d",
    "commits_prev_365d",
    "trend",
    "active_humans",
    "regular_humans",
    "bus_factor",
    "top_share",
    "hhi",
    "active_months",
    "longest_gap_days",
    "bot_share",
    "age_days",
    "handovers_3y",
    "top_share_of_lifetime",
]


def day_number(d: date) -> int:
    return (d - EPOCH).days


def from_day(n: int) -> date:
    return EPOCH + timedelta(days=int(n))


def bus_factor(counts: np.ndarray) -> int:
    """Fewest people who together made at least half of these commits. 0 if there are none."""
    total = counts.sum()
    if total == 0:
        return 0
    ordered = np.sort(counts)[::-1]
    return int(np.searchsorted(np.cumsum(ordered), total / 2, side="left")) + 1


def _top_person(frame: pd.DataFrame) -> int | None:
    if frame.empty:
        return None
    return int(
        frame.groupby("person")["n"].sum().sort_values(ascending=False, kind="stable").index[0]
    )


def repo_measures(repo: pd.DataFrame, t: int) -> dict | None:
    """All measures for one repo at day t. None when no human commit exists by then."""
    repo = repo[repo["day"] <= t]  # the point-in-time filter: nothing after t is ever seen
    humans = repo[repo["person"] != BOT]
    if humans.empty:
        return None
    last = int(humans["day"].max())
    window = humans[humans["day"] > t - YEAR]
    prev = humans[(humans["day"] > t - 2 * YEAR) & (humans["day"] <= t - YEAR)]
    per_person = window.groupby("person")["n"].sum().to_numpy(dtype=float)
    total = per_person.sum()
    commits_365 = int(total)
    commits_prev = int(prev["n"].sum())

    # Months with any human commit, and the longest silence, within the last 365 days.
    if len(window):
        active_months = ((window["day"] - (t - YEAR + 1)) // 30).clip(upper=11).nunique()
        days = np.sort(window["day"].unique())
        edges = np.concatenate([[t - YEAR], days, [t]])
        longest_gap = int(np.diff(edges).max())
    else:
        active_months = 0
        longest_gap = YEAR

    # Handovers: how often the top contributor changed across the last three yearly windows.
    tops = []
    for k in range(4):
        hi = t - k * YEAR
        tops.append(_top_person(humans[(humans["day"] > hi - YEAR) & (humans["day"] <= hi)]))
    seq = [p for p in reversed(tops) if p is not None]
    handovers = sum(1 for a, b in zip(seq, seq[1:], strict=False) if a != b)

    all_bots = repo.loc[repo["person"] == BOT, "n"]
    bots_365 = int(repo.loc[(repo["person"] == BOT) & (repo["day"] > t - YEAR), "n"].sum())
    lifetime = humans.groupby("person")["n"].sum()
    top_id = _top_person(window)
    return {
        "days_since_human": t - last,
        "commits_90d": int(window.loc[window["day"] > t - 90, "n"].sum()),
        "commits_365d": commits_365,
        "commits_prev_365d": commits_prev,
        "trend": float(np.log1p(commits_365) - np.log1p(commits_prev)),
        "active_humans": int(len(per_person)),
        "regular_humans": int((per_person >= 4).sum()),
        "bus_factor": bus_factor(per_person),
        "top_share": float(per_person.max() / total) if total else 0.0,
        "hhi": float(((per_person / total) ** 2).sum()) if total else 0.0,
        "active_months": int(active_months),
        "longest_gap_days": longest_gap,
        "bot_share": float(bots_365 / (bots_365 + commits_365)) if bots_365 + commits_365 else 0.0,
        "age_days": t - int(repo["day"].min()),
        "handovers_3y": handovers,
        "top_share_of_lifetime": float(lifetime.get(top_id, 0) / lifetime.sum())
        if top_id is not None
        else 0.0,
        "n_bot_lifetime": int(all_bots.sum()),
    }


def measures_at(rows: pd.DataFrame, cutoff: date) -> pd.DataFrame:
    """Measures for every repo with any human commit on or before the cutoff."""
    t = day_number(cutoff)
    rows = rows[rows["day"] <= t]
    out = []
    for key, repo in rows.groupby("repo_key", sort=True):
        m = repo_measures(repo, t)
        if m is not None:
            out.append({"repo_key": key, "cutoff": cutoff.isoformat(), **m})
    return pd.DataFrame(out)
