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
        for t in (top * 0.0, round(top / 2, 2), round(top * 0.95, 2))
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


def context(
    backtest: dict, track: dict, today: date, model_name: str, audit_line: str = ""
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
