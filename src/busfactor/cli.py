"""Command line entry points, one per pipeline step, so each Actions job stays a single line."""

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import build, deps, forecast, harvest, live, narrative, site, survival, universe
from .config import DATA_DIR, PRIVATE_DIR, SURVIVAL_AS_OF, TEST_CUTOFFS, TRAIN_CUTOFFS
from .health import FEATURES, day_number, measures_at
from .repos import host_of, normalize_repo_url, repo_key


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
    filled = filled.where(filled.notna(), None).astype(object)
    top["_url"] = top["_url"].astype(object)
    top.loc[gaps, "_url"] = filled
    top.loc[gaps, "repo_key"] = [repo_key(u) if isinstance(u, str) else None for u in filled]
    top.loc[gaps, "host"] = [host_of(u) if isinstance(u, str) else None for u in filled]
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


def cmd_releases(args) -> None:
    """Record each cohort repo's PyPI release days, for the stricter outcome."""
    cohort = pd.read_parquet(DATA_DIR / "cohort.parquet").dropna(subset=["repo_key"])
    days = deps.fetch_release_days(cohort["name"].tolist())
    keys = dict(zip(cohort["name"], cohort["repo_key"], strict=True))
    days["repo_key"] = days["name"].map(keys)
    days = days[["repo_key", "day"]].drop_duplicates()
    days.to_parquet(DATA_DIR / "release_days.parquet", index=False)
    print(f"{len(days)} repo release days")


def cmd_backtest(args) -> None:
    """Run the pre-registered test. See docs/decisions.md before changing anything here."""
    cohort = pd.read_parquet(DATA_DIR / "cohort.parquet")
    keys = set(cohort["repo_key"].dropna())
    rows = build.load_rows(DATA_DIR)
    rows = rows[rows["repo_key"].isin(keys)]
    status = build.load_status(DATA_DIR)
    status = status[status["repo_key"].isin(keys)]
    release_days = pd.read_parquet(DATA_DIR / "release_days.parquet")
    panel = forecast.build_panel(rows, release_days)
    panel.to_parquet(DATA_DIR / "panel.parquet", index=False)
    preds = forecast.walk_forward(panel, "quiet")
    preds.to_parquet(DATA_DIR / "backtest_preds.parquet", index=False)
    result = forecast.evaluate(preds, args.reps)
    strict = forecast.walk_forward(panel, "quiet_strict")
    result["strict"] = forecast.evaluate(strict, args.reps)

    crit_map = pd.read_parquet(DATA_DIR / "criticality.parquet")
    scores = crit_map.set_index("repo_key")["score"]
    result["criticality"] = forecast.criticality_comparison(preds, scores, args.reps)

    # Coverage and the sensitivity check for repos that can no longer be read.
    test_n = panel[panel["cutoff"].isin([c.isoformat() for c in TEST_CUTOFFS])]
    n_quiet, n_all = int(test_n["quiet"].sum()), len(test_n)
    unreadable = int((status["status"] != "ok").sum()) + len(keys - set(status["repo_key"]))
    result["coverage"] = {
        "cohort_packages": len(cohort),
        "cohort_no_repo": int(cohort["repo_key"].isna().sum()),
        "cohort_repos": len(keys),
        "repos_read": int((status["status"] == "ok").sum()),
        "repos_unreadable": unreadable,
        "test_rows": n_all,
        "test_base_rate": n_quiet / n_all,
        "base_rate_if_all_unreadable_were_quiet": (n_quiet + unreadable * len(TEST_CUTOFFS))
        / (n_all + unreadable * len(TEST_CUTOFFS)),
    }
    result["eligible_by_cutoff"] = panel.groupby("cutoff")["quiet"].agg(["size", "mean"]).to_dict()
    forecast.save_json(result, DATA_DIR / "backtest.json")

    # The models the weekly job will use: fitted once here, then only ever applied.
    names = sorted({c for c in TRAIN_CUTOFFS} | {c for c in TEST_CUTOFFS})
    usable = [c for c in names if c <= TEST_CUTOFFS[-1]]
    primary_name = result["published_model"]
    makers = {
        "logistic": lambda: forecast.Logit(FEATURES),
        "lightgbm": lambda: forecast.Gbm(FEATURES),
        **{k: (lambda c=v: forecast.Logit(c)) for k, v in forecast.BASELINES.items()},
    }
    primary = forecast.fit_on(panel, usable, makers[primary_name], "quiet")
    train_rows = panel[panel["cutoff"].isin([c.isoformat() for c in usable])]
    base_cols = forecast.BASELINES[result["best_baseline"]]
    baseline = forecast.fit_on(panel, usable, lambda: forecast.Logit(base_cols), "quiet")
    forecast.save_json(
        {
            "primary": live.model_to_json(primary, primary_name, train_rows),
            "baseline": live.model_to_json(baseline, result["best_baseline"]),
            "passed": result["passed"],
        },
        DATA_DIR / "models.json",
    )
    print(json.dumps({k: result[k] for k in ("passed", "published_model", "best_baseline")}))


def cmd_survival(args) -> None:
    """Run the pre-registered D18 test. It writes only its own files, never models.json."""
    as_of = SURVIVAL_AS_OF
    cohort = pd.read_parquet(DATA_DIR / "cohort.parquet")
    keys = set(cohort["repo_key"].dropna())
    status = build.load_status(DATA_DIR)
    ok = status[(status["status"] == "ok") & (status["fetched_at"] >= as_of.isoformat())]
    usable = keys & set(ok["repo_key"])
    rows = build.load_rows(DATA_DIR)
    rows = rows[rows["repo_key"].isin(usable) & (rows["day"] <= day_number(as_of))]
    panel = forecast.build_panel(rows)
    items = survival.walk_forward(panel, rows, as_of)
    items.to_parquet(DATA_DIR / "survival_items.parquet", index=False)
    result = survival.evaluate(items, args.reps)
    result["as_of"] = as_of.isoformat()
    result["coverage"] = {
        "cohort_repos": len(keys),
        "repos_used": len(usable),
        "eligible_by_cutoff": panel.groupby("cutoff").size().to_dict(),
    }
    forecast.save_json(result, DATA_DIR / "survival.json")
    name = result["published_model"]
    if name:
        # The live model learns from every cutoff, with outcomes seen up to the as-of date.
        cutoffs = sorted(set(TRAIN_CUTOFFS) | set(TEST_CUTOFFS))
        train = survival.training_rows(panel, rows, as_of, cutoffs)
        model = survival.MAKERS[name]().fit(train)
        spec = {**survival.model_to_json(model, name), "as_of": as_of.isoformat()}
        forecast.save_json(spec, DATA_DIR / "survival_model.json")
    print(json.dumps({k: result[k] for k in ("passed", "published_model", "best_baseline")}))


def cmd_criticality(args) -> None:
    """Reduce the OpenSSF score file to hashed repo keys and scores."""
    table = pd.read_csv(args.csv, usecols=["repo.url", "default_score"])
    urls = table["repo.url"].map(normalize_repo_url)
    keep = urls.notna() & table["default_score"].notna()
    out = pd.DataFrame(
        {"repo_key": urls[keep].map(repo_key), "score": table.loc[keep, "default_score"]}
    )
    out.drop_duplicates("repo_key").to_parquet(DATA_DIR / "criticality.parquet", index=False)
    print(f"{len(out)} scored repos")


def cmd_weekly(args) -> None:
    """Score this week, freeze it once, grade anything due, and write what the site reads."""
    today = date.fromisoformat(args.today) if args.today else datetime.now(UTC).date()
    universe_df = pd.read_parquet(DATA_DIR / "universe.parquet")
    requires = pd.read_parquet(DATA_DIR / "requires.parquet")
    rows = build.load_rows(DATA_DIR)
    specs = json.loads((DATA_DIR / "models.json").read_text())
    backtest = json.loads((DATA_DIR / "backtest.json").read_text())
    tracked = rows[rows["repo_key"].isin(set(universe_df["repo_key"].dropna()))]
    now = measures_at(tracked, today)
    archived = set(universe_df.loc[universe_df["archived"].eq(True), "repo_key"])
    eligible = now[(now["days_since_human"] < 365) & ~now["repo_key"].isin(archived)].copy()
    eligible["prob"] = live.predict(specs["primary"], eligible)
    eligible["baseline_prob"] = live.predict(specs["baseline"], eligible)
    # Reasons only where there is something to explain: a lower chance needs none.
    reasons = live.reasons(specs["primary"], eligible)
    eligible["reasons"] = [
        r if p >= 0.10 else [] for r, p in zip(reasons, eligible["prob"], strict=True)
    ]
    names = universe_df.assign(name=universe_df["name"].map(deps.canon)).dropna(subset=["repo_key"])
    packages = names.sort_values("rank").groupby("repo_key")["name"].apply(list)
    eligible["packages"] = eligible["repo_key"].map(packages)

    folder = Path(args.predictions)
    payload = live.freeze_payload(
        eligible,
        today,
        live.model_id(specs["primary"]),
        live.model_id(specs["baseline"]),
        "docs/decisions.md D15",
    )
    written = live.write_frozen(payload, folder)
    print("froze" if written else "already frozen", payload["week"], len(eligible))
    status = build.load_status(DATA_DIR)
    track = live.grade(live.read_frozen(folder), rows, today, status)

    extra = []
    surv_path = DATA_DIR / "survival_model.json"
    if surv_path.exists():  # written only if the D18 test passed
        curves = survival.curve_from_json(json.loads(surv_path.read_text()), eligible)
        shown = [
            survival.displayed(a, b, d, y)
            for a, b, d, y in zip(
                curves[:, 0], curves[:, 1], curves[:, 3], eligible["prob"], strict=True
            )
        ]
        extra = list(shown[0]) if shown else []
        for key in extra:
            eligible[key] = [row[key] for row in shown]
    forecast_cols = eligible[["repo_key", "prob", "reasons", *extra]]
    table, sim = build.assemble(universe_df, requires, rows, today, forecast_cols)
    table.to_parquet(DATA_DIR / "site_packages.parquet", index=False)
    sim.to_parquet(DATA_DIR / "simulator.parquet", index=False)
    context = narrative.context(backtest, track, today, specs["primary"]["name"])
    forecast.save_json(context, DATA_DIR / "site_context.json")


def cmd_site(args) -> None:
    site.build(DATA_DIR, Path(args.out))


def main() -> None:
    parser = argparse.ArgumentParser(prog="busfactor")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    sub.add_parser("releases").set_defaults(func=cmd_releases)
    c = sub.add_parser("criticality")
    c.add_argument("csv")
    c.set_defaults(func=cmd_criticality)
    w = sub.add_parser("weekly")
    w.add_argument("--predictions", required=True)
    w.add_argument("--today", default=None)
    w.set_defaults(func=cmd_weekly)
    st = sub.add_parser("site")
    st.add_argument("--out", default="_site")
    st.set_defaults(func=cmd_site)
    b = sub.add_parser("backtest")
    b.add_argument("--reps", type=int, default=2000)
    b.set_defaults(func=cmd_backtest)
    sv = sub.add_parser("survival")
    sv.add_argument("--reps", type=int, default=2000)
    sv.set_defaults(func=cmd_survival)
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
