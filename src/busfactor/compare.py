"""PyPI and npm side by side, exactly as fixed in advance in docs/decisions.md (D23).

Every measure is computed twice: per package, and per repo with each repo counted once, because
npm often publishes many small packages from one repo. Intervals come from resampling repos, the
unit people actually maintain. A difference is reported as one only when its interval excludes
zero, and the wording never says one ecosystem is "more fragile".
"""

import numpy as np
import pandas as pd

MEASURES = ("bus_factor_1", "looks_quiet", "few_contributors", "median_active", "unknown")
LABELS = {
    "bus_factor_1": "One person made half the commits",
    "looks_quiet": "Looks quiet",
    "few_contributors": "Few active contributors",
    "median_active": "Median active people (active projects)",
    "unknown": "Unknown",
}


def _measures(t: pd.DataFrame) -> dict[str, float]:
    known = t[t["has_history"]]
    live = known[known["state"].isin(["active", "slowing"])]
    n = len(known)
    return {
        "bus_factor_1": float((known["bus_factor"] == 1).mean()) if n else np.nan,
        "looks_quiet": float((known["state"] == "quiet").mean()) if n else np.nan,
        "few_contributors": float(known["few_people"].mean()) if n else np.nan,
        "median_active": float(live["active_humans"].median()) if len(live) else np.nan,
        "unknown": float((t["state"] == "unknown").mean()) if len(t) else np.nan,
    }


def prepare(table: pd.DataFrame, level: str) -> pd.DataFrame:
    """Columns the measures need, plus a cluster id. Repo level keeps one row per repo."""
    t = table[
        [
            "name",
            "rank",
            "repo_key",
            "state",
            "has_history",
            "bus_factor",
            "few_people",
            "active_humans",
        ]
    ].copy()
    t["cluster"] = t["repo_key"].where(t["repo_key"].notna(), "pkg:" + t["name"])
    t["has_history"] = t["has_history"].astype(bool)
    t["few_people"] = t["few_people"].astype(bool)
    if level == "repo":
        t = t.sort_values("rank").drop_duplicates("cluster")
    return t.reset_index(drop=True)


def _draws(t: pd.DataFrame, reps: int, rng) -> list[dict[str, float]]:
    groups = list(t.groupby("cluster").indices.values())
    out = []
    for _ in range(reps):
        pick = rng.integers(0, len(groups), len(groups))
        out.append(_measures(t.iloc[np.concatenate([groups[i] for i in pick])]))
    return out


def compare(pypi: pd.DataFrame, npm: pd.DataFrame, reps: int = 2000, seed: int = 0) -> dict:
    """D23 measures for both ecosystems, at package and repo level, top 5,000 and top 100."""
    rng = np.random.default_rng(seed)
    result = {}
    for scope, limit in (("top_all", None), ("top_100", 100)):
        for level in ("package", "repo"):
            a = prepare(pypi if limit is None else pypi[pypi["rank"] <= limit], level)
            b = prepare(npm if limit is None else npm[npm["rank"] <= limit], level)
            da, db = _draws(a, reps, rng), _draws(b, reps, rng)
            rows = {}
            for m in MEASURES:
                xa = np.array([d[m] for d in da])
                xb = np.array([d[m] for d in db])
                diff = xb - xa
                lo, hi = np.nanquantile(diff, [0.025, 0.975])
                rows[m] = {
                    "pypi": _measures(a)[m],
                    "npm": _measures(b)[m],
                    "pypi_ci": [float(np.nanquantile(xa, 0.025)), float(np.nanquantile(xa, 0.975))],
                    "npm_ci": [float(np.nanquantile(xb, 0.025)), float(np.nanquantile(xb, 0.975))],
                    "diff_ci": [float(lo), float(hi)],
                    "different": bool(lo > 0 or hi < 0),
                }
            result[f"{scope}_{level}"] = {
                "n_pypi": int(len(a)),
                "n_npm": int(len(b)),
                "measures": rows,
            }
    return result
