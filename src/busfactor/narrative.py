"""Turn the test result into sentences, so the site's wording can't drift from the numbers.

A pass and a fail are both ordinary outcomes here. Each sentence is built from the result file,
which means a failed test can't be left with leftover optimistic copy.
"""

from datetime import date


def percent(x: float) -> str:
    return f"{100 * x:.0f}%"


def context(backtest: dict, track: dict, today: date, model_name: str) -> dict:
    """Everything the templates need beyond the package table."""
    primary = backtest["overall"]["logistic"]
    base_name = backtest["best_baseline"]
    baseline = backtest["overall"][base_name]
    gain = backtest["logistic_vs_best_baseline"]
    plain = {"last_commit": "the date of the last commit", "commits_past_year": "past-year commits"}
    if backtest["passed"]:
        summary = (
            f"Yes, modestly. In a test on past years, a model using git history beat the best "
            f"simple rule ({plain[base_name]}): log loss {primary['log_loss']:.3f} against "
            f"{baseline['log_loss']:.3f}. The rule for passing was published before the test ran."
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
        "track": track,
    }
