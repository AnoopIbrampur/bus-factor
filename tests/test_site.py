"""Design and safety rules, checked by machine so they survive later edits."""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from busfactor import narrative, site

CSS = Path("site/static/style.css").read_text()
TEMPLATES = list(Path("site/templates").glob("*.html"))


def test_banned_css():
    for banned in ("text-transform", "gradient", "@keyframes", "animation", "box-shadow", "blur"):
        assert banned not in CSS, banned


def test_spacing_uses_the_4px_scale():
    pattern = r"(?:^|[;{\s])(?:margin|padding|gap)[a-z-]*:\s*([^;}]+)"
    for value in re.findall(pattern, CSS):
        for px in re.findall(r"(\d+)px", value):
            assert int(px) % 4 == 0, value


def test_tokens_stay_on_scale():
    sizes = dict(re.findall(r"--s-(\d+):\s*(\d+)px", CSS))
    assert all(int(v) == int(k) * 4 for k, v in sizes.items())
    fonts = {int(v) for v in re.findall(r"--t-[a-z0-9]+:\s*(\d+)px", CSS)}
    assert fonts == {14, 16, 18, 22, 28, 36, 48}


def test_every_font_size_comes_from_the_scale():
    for value in re.findall(r"font-size:\s*([^;]+);", CSS):
        assert value.strip().startswith("var(--t-"), value


def test_no_third_party_requests():
    for t in TEMPLATES:
        text = t.read_text()
        assert not re.search(r"<(script|link|img)[^>]+(src|href)=\"https?://", text), t.name
    assert "url(http" not in CSS


def test_motion_transparency_and_contrast_preferences_are_handled():
    for q in ("prefers-reduced-motion", "prefers-reduced-transparency", "prefers-contrast"):
        assert q in CSS
    assert "prefers-color-scheme: dark" in CSS


def luminance(hexcolor: str) -> float:
    rgb = [int(hexcolor[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("block", [0, 1])
def test_text_contrast_in_both_themes(block):
    root = re.findall(r":root \{(.*?)\}", CSS, re.S)[block]
    values = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6})", root))
    for name in ("ink", "muted", "link"):
        assert contrast(values[name], values["paper"]) >= 4.5, name


def test_templates_avoid_banned_words():
    for t in TEMPLATES:
        text = t.read_text().lower()
        for word in ("abandoned", "takeover", "take over", "vulnerable", "donate", "sponsor"):
            assert word not in text, f"{word} in {t.name}"


def sample_context():
    metric = {
        "n": 100,
        "positives": 10,
        "log_loss": 0.3,
        "brier": 0.1,
        "roc_auc": 0.7,
        "pr_auc": 0.3,
        "precision_top_decile": 0.3,
    }
    by = {
        "logistic": metric,
        "lightgbm": metric,
        "last_commit": metric,
        "commits_past_year": metric,
    }
    cal = [{"n": 10, "mean_predicted": 0.1 * i, "observed": 0.1 * i} for i in range(1, 4)]
    backtest = {
        "overall": by,
        "by_year": {"2022-11-09": by},
        "best_baseline": "last_commit",
        "logistic_vs_best_baseline": {"gain": 0.001, "ci": [-0.001, 0.002]},
        "passed": False,
        "strict": {"overall": by, "best_baseline": "last_commit"},
        "criticality": None,
        "calibration": {"logistic": cal, "last_commit": cal},
        "coverage": {
            "repos_unreadable": 5,
            "cohort_repos": 100,
            "test_base_rate": 0.1,
            "base_rate_if_all_unreadable_were_quiet": 0.12,
        },
    }
    from datetime import date

    return narrative.context(
        backtest, {"weeks": [], "next_due": None}, date(2026, 11, 9), "last_commit", "a note."
    )


def write_fixture(data: Path) -> None:
    row = {
        "name": "alpha",
        "rank": 1,
        "downloads": 1000,
        "dependent_packages": 2,
        "total_dependents": 1,
        "state": "unknown",
        "state_label": "Unknown",
        "state_class": 0,
        "unknown_reason": "We couldn't read its git history.",
        "has_history": False,
        "few_people": False,
        "bus_factor": None,
        "prob": None,
        "has_funding": False,
        "shared_repo": 1,
        "reasons": [],
    }
    keys = (
        "active_humans regular_humans top_share_pct commits_365d commits_prev_365d "
        "days_since_human handovers_3y bot_share_pct prob_pct band_label band_class"
    )
    row.update(dict.fromkeys(keys.split(), None))
    live = {
        **row,
        "name": "beta",
        "rank": 2,
        "state": "active",
        "state_label": "Active",
        "state_class": 1,
        "unknown_reason": None,
        "has_history": True,
        "few_people": True,
        "bus_factor": 1,
        "active_humans": 2,
        "regular_humans": 1,
        "top_share_pct": 80,
        "commits_365d": 10,
        "commits_prev_365d": 12,
        "days_since_human": 4,
        "handovers_3y": 0,
        "bot_share_pct": 0,
        "prob": 0.2,
        "prob_pct": 20,
        "band_label": "Middle chance",
        "band_class": 2,
        "reasons": ["Few commits in the past year"],
    }
    pd.DataFrame([row, live]).to_parquet(data / "site_packages.parquet")
    pd.DataFrame(
        [
            {
                "name": "alpha",
                "n_direct": 1,
                "n_indirect": 0,
                "downloads_sum": 9,
                "downloads_max": 9,
                "direct": ["beta"],
                "indirect": [],
            }
        ]
    ).to_parquet(data / "simulator.parquet")
    (data / "site_context.json").write_text(json.dumps(sample_context()))


def test_site_renders_and_unknown_is_never_healthy(tmp_path):
    write_fixture(tmp_path)
    out = tmp_path / "out"
    site.build(tmp_path, out)
    page = (out / "p/alpha/index.html").read_text()
    assert "Unknown" in page and "doesn't mean healthy" in page
    assert "Active" not in page.split("<main")[1].split("</main>")[0]
    assert "nan" not in page.lower().split("<main")[1].replace("finance", "")
    home = (out / "index.html").read_text()
    assert "correction" in home and "owe nobody free labour" in home
    for rel in ("packages/", "simulator/", "simulator/alpha/", "track-record/", "method/"):
        assert (out / rel / "index.html").exists()


def test_every_page_links_a_skip_target_and_has_no_personal_fields(tmp_path):
    write_fixture(tmp_path)
    out = tmp_path / "out"
    site.build(tmp_path, out)
    for path in out.rglob("*.html"):
        text = path.read_text()
        assert 'class="skip"' in text and 'id="content"' in text
        assert "github.com/sponsors" not in text and "@users.noreply" not in text


def test_packages_page_offers_no_health_sort_or_combined_filter(tmp_path):
    write_fixture(tmp_path)
    out = tmp_path / "out"
    site.build(tmp_path, out)
    text = (out / "packages/index.html").read_text()
    assert text.count("<select") == 1
    assert "sort" not in text.split("<script>")[1]


def test_a_failed_test_reads_as_a_failure():
    ctx = sample_context()
    assert "Not better than a simple rule" in ctx["result_summary"]
