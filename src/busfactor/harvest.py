"""Fetch git history for one shard of repos, resumably, within a runner's time limit.

A job can stop at any point: whatever was finished is written out, and the next run skips repos
already fresh. Repos are assigned to shards by hash, so a repo always lands in the same shard
and its earlier output can be replaced cleanly. Logs print counts only, because this repo's
Actions logs are public and a URL can contain a username.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .gitlog import harvest_repo

ROW_COLS = ["repo_key", "day", "person", "n", "m"]


def shard_of(key: str, of: int) -> int:
    return int(key, 16) % of


def _load(path: Path, columns: list[str]) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=columns)


def run_shard(
    targets: pd.DataFrame,
    shard: int,
    of: int,
    rows_path: Path,
    status_path: Path,
    fresh_after: str,
    budget_s: int,
    workers: int = 6,
) -> dict:
    """Harvest stale repos in this shard until done or out of time. Returns a count summary."""
    mine = targets[targets["repo_key"].map(lambda k: shard_of(k, of)) == shard]
    status = _load(status_path, ["repo_key", "status", "fetched_at", "n_commits"])
    fresh = set(status.loc[status["fetched_at"] >= fresh_after, "repo_key"])
    todo = mine[~mine["repo_key"].isin(fresh)]
    print(f"shard {shard}/{of}: {len(mine)} repos, {len(todo)} to do", flush=True)

    start = time.monotonic()
    now_ts = int(time.time())
    today = datetime.now(UTC).date().isoformat()
    new_rows: dict[str, list] = {}
    new_status: list[dict] = []
    items = iter(todo[["repo_key", "url"]].itertuples(index=False))
    done = 0
    with ThreadPoolExecutor(workers) as pool:
        running = {}
        while True:
            while len(running) < workers and time.monotonic() - start < budget_s:
                item = next(items, None)
                if item is None:
                    break
                running[pool.submit(harvest_repo, item.url, now_ts)] = item.repo_key
            if not running:
                break
            finished = next(as_completed(running))
            key = running.pop(finished)
            try:
                st, rows = finished.result()
            except Exception as err:  # noqa: BLE001 - one odd repo must not lose the shard
                st, rows = f"error:{type(err).__name__}", []
            new_status.append(
                {
                    "repo_key": key,
                    "status": st,
                    "fetched_at": today,
                    "n_commits": sum(r[2] for r in rows),
                }
            )
            if rows:
                new_rows[key] = rows
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(todo)} in {time.monotonic() - start:.0f}s", flush=True)

    frames = [
        pd.DataFrame([(k, *r) for r in rows], columns=ROW_COLS) for k, rows in new_rows.items()
    ]
    old = _load(rows_path, ROW_COLS)
    replaced = {s["repo_key"] for s in new_status if s["status"] == "ok"}
    # A failed refetch keeps the earlier rows: a blip is no reason to forget a project's history.
    keep = old[~old["repo_key"].isin(replaced)]
    merged = pd.concat([f for f in [keep, *frames] if len(f)], ignore_index=True)
    if len(merged):
        merged = merged.astype({"day": "int32", "person": "int32", "n": "int32", "m": "int32"})
    merged.to_parquet(rows_path, index=False, compression="zstd")
    st_new = pd.DataFrame(new_status, columns=status.columns)
    st_all = pd.concat([f for f in [status, st_new] if len(f)], ignore_index=True)
    st_all = st_all.drop_duplicates("repo_key", keep="last")
    st_all.to_parquet(status_path, index=False)
    counts = st_new["status"].value_counts().to_dict() if len(st_new) else {}
    summary = {"attempted": done, "remaining": len(todo) - done, **counts}
    print(summary, flush=True)
    return summary
