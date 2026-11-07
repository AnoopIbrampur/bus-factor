"""Command line entry points, one per pipeline step, so each Actions job stays a single line."""

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import deps, harvest, universe
from .config import DATA_DIR, PRIVATE_DIR
from .repos import host_of, repo_key


def cmd_plan(args) -> None:
    """Fetch the top list and requirements, and write the repo list to harvest."""
    DATA_DIR.mkdir(exist_ok=True)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    top = universe.fetch_top()
    req = deps.fetch_requires(top["name"].tolist())
    req.to_parquet(DATA_DIR / "requires.parquet", index=False)
    # Fill gaps in repo links from PyPI's own metadata.
    hints = dict(zip(top["name"].map(deps.canon), req["repo_hint"], strict=True))
    gaps = top["_url"].isna()
    filled = top.loc[gaps, "name"].map(lambda n: hints.get(deps.canon(n)))
    top.loc[gaps, "_url"] = filled
    top.loc[gaps, "repo_key"] = filled.map(lambda u: repo_key(u) if u else None)
    top.loc[gaps, "host"] = filled.map(host_of)
    top["repo_from_pypi"] = gaps & top["_url"].notna()
    req = req.drop(columns=["repo_hint"])
    req.to_parquet(DATA_DIR / "requires.parquet", index=False)
    universe.save(top, DATA_DIR / "universe.parquet")
    current = pd.read_parquet(PRIVATE_DIR / "repo_map.parquet")
    cohort_path = PRIVATE_DIR / "cohort_map.parquet"
    frames = [current]
    if cohort_path.exists():
        frames.append(pd.read_parquet(cohort_path))
    targets = pd.concat(frames, ignore_index=True).drop_duplicates("repo_key")
    targets.to_parquet(PRIVATE_DIR / "targets.parquet", index=False)
    print(f"{len(top)} packages, {len(current)} current repos, {len(targets)} targets")


def cmd_harvest(args) -> None:
    targets = pd.read_parquet(PRIVATE_DIR / "targets.parquet")
    fresh_after = (
        args.fresh_after or (datetime.now(UTC).date() - timedelta(days=args.fresh_days)).isoformat()
    )
    harvest.run_shard(
        targets,
        args.shard,
        args.of,
        Path(args.rows),
        Path(args.status),
        fresh_after,
        args.budget,
        args.workers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="busfactor")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    h = sub.add_parser("harvest")
    h.add_argument("--shard", type=int, required=True)
    h.add_argument("--of", type=int, required=True)
    h.add_argument("--rows", required=True)
    h.add_argument("--status", required=True)
    h.add_argument("--fresh-after", default=None)
    h.add_argument("--fresh-days", type=int, default=5)
    h.add_argument("--budget", type=int, default=18000)
    h.add_argument("--workers", type=int, default=6)
    h.set_defaults(func=cmd_harvest)
    args = parser.parse_args()
    args.func(args)
