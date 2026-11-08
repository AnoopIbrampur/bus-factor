"""Turn the test result into sentences, so the site's wording can't drift from the numbers.

A pass and a fail are both ordinary outcomes here. Each sentence is built from the result file,
which means a failed test can't be left with leftover optimistic copy.
"""

from datetime import date


def percent(x: float) -> str:
    return f"{100 * x:.0f}%"


def calibration_svg(table: list[dict]) -> str:
    """A small dependency-free chart: stated chance against what happened, per tenth of rows."""
    size, pad = 320, 40
    top = max(max(b["mean_predicted"], b["observed"]) for b in table) * 1.1
    span = size - pad - 8

    def x(v: float) -> float:
        return pad + v / top * span

    def y(v: float) -> float:
        return size - pad - v / top * span

    dots = "".join(
        f'<circle class="dot" cx="{x(b["mean_predicted"]):.1f}" cy="{y(b["observed"]):.1f}" r="4"/>'
        for b in table
    )
    ticks = "".join(
        f'<text x="{x(t):.1f}" y="{size - pad + 16}" text-anchor="middle">{t:.0%}</text>'
        f'<text x="{pad - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:.0%}</text>'
        for t in (0.0, 0.25, 0.5)
        if t <= top
    )
    return (
        f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="Calibration chart: '
        f'predicted chance against observed share, by tenth of projects">'
        f'<path class="axis" d="M{pad} {size - pad}H{x(top):.1f}M{pad} {size - pad}V{y(top):.1f}"/>'
        f'<path class="ink" d="M{x(0):.1f} {y(0):.1f}L{x(top):.1f} {y(top):.1f}"/>'
        f"{dots}{ticks}"
        f'<text x="{(pad + size) / 2}" y="{size - 6}" text-anchor="middle">Stated chance</text>'
        f'<text x="12" y="{size / 2}" text-anchor="middle" '
        f'transform="rotate(-90 12 {size / 2})">What happened</text></svg>'
    )


AUDIT_LINE = (
    "about 4 in 10 projects that went a year without a human commit later had one again, and "
    "about half of those that stayed quiet looked finished rather than unattended."
)


def context(
    backtest: dict, track: dict, today: date, model_name: str, audit_line: str = AUDIT_LINE
) -> dict:
    """Everything the templates need beyond the package table."""
    published = model_name if model_name in ("logistic", "lightgbm") else backtest["best_baseline"]
    primary = backtest["overall"][published]
    base_name = backtest["best_baseline"]
    baseline = backtest["overall"][base_name]
    gain = backtest[
        "lightgbm_vs_best_baseline" if published == "lightgbm" else "logistic_vs_best_baseline"
    ]
    plain = {"last_commit": "the date of the last commit", "commits_past_year": "past-year commits"}
    if backtest["passed"]:
        summary = (
            f"Yes, modestly. In a test on four past years, a model using git history beat the "
            f"best simple rule ({plain[base_name]}): log loss {primary['log_loss']:.3f} against "
            f"{baseline['log_loss']:.3f}, and ROC-AUC {primary['roc_auc']:.2f} against "
            f"{baseline['roc_auc']:.2f}. The rule for passing was published before the test ran."
        )
    else:
        summary = (
            f"Not better than a simple rule. In a test on past years, a model using git history "
            f"did not clearly beat {plain[base_name]}: log loss {primary['log_loss']:.3f} against "
            f"{baseline['log_loss']:.3f}. So this site uses the simple rule. The rule for "
            f"passing was published before the test ran."
        )
    return {
        "updated": today.isoformat(),
        "result_summary": summary,
        "backtest": backtest,
        "base_label": plain[base_name],
        "gain": gain,
        "model_name": model_name,
        "published": published,
        "published_label": {"logistic": "Logistic model", "lightgbm": "LightGBM model"}.get(
            published, "Simple rule"
        ),
        "track": track,
        "audit_line": audit_line,
        "calibration_svg": calibration_svg(backtest["calibration"][published]),
    }


SURVIVAL_LABELS = {
    "logistic": "Logistic curve model",
    "lightgbm": "LightGBM curve model",
    "km": "Same curve for every project",
    "last_commit": "Last commit date",
    "commits_past_year": "Commits in past year",
}
HORIZON_LABELS = {"90": "3 months", "180": "6 months", "365": "12 months", "730": "2 years"}


def survival_context(
    result: dict, n_curves: int = 0, n_adjusted: int = 0, n_visible: int = 0
) -> dict:
    """Sentences and table rows for the D18 test, built from its result file alone."""
    best = result["best_baseline"]
    pub = result["published_model"]
    shown = pub or "logistic"
    gain = result[
        "lightgbm_vs_best_baseline" if shown == "lightgbm" else "logistic_vs_best_baseline"
    ]
    model_ll = result["overall"][shown]["log_loss"]
    base_ll = result["overall"][best]["log_loss"]
    if result["passed"]:
        summary = (
            f"Yes. Across all four horizons, the {SURVIVAL_LABELS[pub]} beat the best simple "
            f"method "
            f"({SURVIVAL_LABELS[best].lower()}): log loss {model_ll:.3f} against {base_ll:.3f}. "
            f"The rule for passing was published before the test ran."
        )
    else:
        summary = (
            f"No. The curve model didn't clearly beat the best simple method "
            f"({SURVIVAL_LABELS[best].lower()}): log loss {model_ll:.3f} against {base_ll:.3f}. "
            f"So package pages don't show a curve. The rule for passing was published before "
            f"the test ran."
        )
    rows = []
    for h, by in sorted(result["by_horizon"].items(), key=lambda kv: int(kv[0])):
        rows.append(
            {
                "label": HORIZON_LABELS[h],
                "n": by[shown]["n"],
                "silent": by[shown]["positives"],
                "model": by[shown]["log_loss"],
                "base": by[best]["log_loss"],
                "model_auc": by[shown]["roc_auc"],
            }
        )
    return {
        "summary": summary,
        "passed": result["passed"],
        "shown": shown,
        "shown_label": SURVIVAL_LABELS[shown],
        "best": best,
        "best_label": SURVIVAL_LABELS[best],
        "gain": gain,
        "model_ll": model_ll,
        "base_ll": base_ll,
        "overall": [
            {"label": SURVIVAL_LABELS[k], **v}
            for k, v in result["overall"].items()
            if k in SURVIVAL_LABELS
        ],
        "rows": rows,
        "n_items": result["n_items"],
        "n_repos": result["n_repos"],
        "at_year": result.get("at_365_vs_d13_refit"),
        "n_curves": n_curves,
        "n_adjusted": n_adjusted,
        "n_visible": n_visible,
        "top_tenth": [
            {
                "label": HORIZON_LABELS[h],
                "said": result["calibration"][h][shown][-1]["mean_predicted"],
                "saw": result["calibration"][h][shown][-1]["observed"],
            }
            for h in sorted(result.get("calibration", {}), key=int)
            if h != "365"  # the site's 12-month chance comes from the calibrated D13 model
        ],
    }


def compare_context(result: dict) -> dict:
    """Table rows for the PyPI and npm comparison, with D23's wording rule built in."""
    from .compare import LABELS

    def fmt(m: str, v) -> str:
        if v is None or v != v:
            return "n/a"
        return f"{v:.0f}" if m == "median_active" else f"{100 * v:.0f}%"

    out = {}
    for key, block in result.items():
        if not isinstance(block, dict) or "measures" not in block:
            continue
        rows = []
        for m, r in block["measures"].items():
            if r["different"]:
                verdict = "npm higher" if r["diff_ci"][0] > 0 else "npm lower"
            else:
                verdict = "No clear difference"
            rows.append(
                {
                    "label": LABELS[m],
                    "pypi": fmt(m, r["pypi"]),
                    "npm": fmt(m, r["npm"]),
                    "verdict": verdict,
                }
            )
        out[key] = {"n_pypi": block["n_pypi"], "n_npm": block["n_npm"], "rows": rows}
    return out


def recal_context(result: dict) -> dict:
    """The D21 attempt to recalibrate the curve, in sentences built from its result file."""
    gain = result["recal_vs_d18"]
    top = result["top_tenth"]["730"]
    verdict = (
        "It passed, so the site now uses it."
        if result["passed"]
        else "That gain wasn't clearly above zero, so under the rule written in advance the "
        "original curve stays."
    )
    return {
        "text": (
            f"A second attempt (D21) added a recalibration step. It brought the 2-year top tenth "
            f"to {100 * top['lightgbm_recal']['mean_predicted']:.0f}% said against "
            f"{100 * top['lightgbm_recal']['observed']:.0f}% observed, and improved log loss by "
            f"{gain['gain']:.4f} (95% interval {gain['ci'][0]:.4f} to {gain['ci'][1]:.4f}). "
            f"{verdict}"
        ),
        "passed": result["passed"],
    }


REVIVAL_LABELS = {
    "logistic": "Logistic model",
    "lightgbm": "LightGBM model",
    "days_since_human": "Days since last human commit",
    "releases_365d": "Releases in the past year",
}


def revival_context(result: dict) -> dict:
    """Sentences and rows for the D22 revival test, from its result file alone."""
    best = result["best_baseline"]
    pub = result["published_model"]
    shown = pub or "logistic"
    gain = result[
        "lightgbm_vs_best_baseline" if shown == "lightgbm" else "logistic_vs_best_baseline"
    ]
    o = result["overall"]
    rates = result["revival_rate_by_year"]
    if result["passed"]:
        summary = (
            f"Yes, but only just. The {REVIVAL_LABELS[shown].lower()} beat the best simple rule "
            f"({REVIVAL_LABELS[best].lower()}): log loss {o[shown]['log_loss']:.3f} against "
            f"{o[best]['log_loss']:.3f}. Almost all of what can be predicted is how long a "
            f"project has already been quiet."
        )
    else:
        summary = (
            f"No. Nothing clearly beat the simple rule ({REVIVAL_LABELS[best].lower()}): log loss "
            f"{o[shown]['log_loss']:.3f} against {o[best]['log_loss']:.3f}. So package pages "
            f"don't show a chance of coming back."
        )
    return {
        "summary": summary,
        "passed": result["passed"],
        "gain": gain,
        "n": result["n_rows"],
        "positives": o[shown]["positives"],
        "rates": [{"year": y[:4], "rate": r} for y, r in sorted(rates.items())],
        "rows": [
            {"label": REVIVAL_LABELS[k], "log_loss": v["log_loss"], "roc_auc": v["roc_auc"]}
            for k, v in o.items()
        ],
    }
