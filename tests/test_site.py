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
    # The font shorthand carries a size too.
    for value in re.findall(r"(?<![-\w])font:\s*([^;]+);", CSS):
        assert not re.search(r"\d+px", value), value


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
    pd.DataFrame(
        {
            "name": ["alpha", "Beta"],
            "found": [True, True],
            "declared": [True, False],
            "requires": [["Beta", "outside_pkg"], []],
        }
    ).to_parquet(data / "requires.parquet")


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


def test_checker_files_hold_page_facts_only(tmp_path):
    write_fixture(tmp_path)
    out = tmp_path / "out"
    site.build(tmp_path, out)
    assert (out / "check/index.html").exists()
    names = json.loads((out / "check/names.json").read_text())
    assert names == ["alpha", "beta"]  # names only, alphabetical, no health
    alpha = json.loads((out / "p/alpha/data.json").read_text())
    assert alpha["requires"] == ["beta", "outside-pkg"]
    assert alpha["state"] == "unknown" and alpha["chance"] is None
    beta = json.loads((out / "p/beta/data.json").read_text())
    assert set(beta) == {
        "name",
        "state",
        "label",
        "mark",
        "few",
        "chance",
        "band",
        "band_mark",
        "requires",
    }
    assert beta["few"] is True and beta["chance"] == 20


def survival_result(passed: bool) -> dict:
    m = {"n": 50, "positives": 20, "log_loss": 0.4, "brier": 0.1, "roc_auc": 0.8}
    by = {k: m for k in ("logistic", "lightgbm", "km", "last_commit", "commits_past_year")}
    gain = {"gain": 0.01, "ci": [0.005, 0.02] if passed else [-0.01, 0.02]}
    return {
        "overall": by,
        "by_horizon": {"90": by, "730": by},
        "best_baseline": "km",
        "logistic_vs_best_baseline": gain,
        "lightgbm_vs_logistic": {"gain": -0.01, "ci": [-0.02, -0.001]},
        "lightgbm_vs_best_baseline": gain,
        "passed": passed,
        "published_model": "logistic" if passed else None,
        "n_items": 100,
        "n_repos": 40,
        "at_365_vs_d13_refit": {**{k: 0.3 for k in by}, "d13_lightgbm": 0.31},
        "calibration": {
            h: {k: [{"n": 5, "mean_predicted": 0.3, "observed": 0.45}] for k in by}
            for h in ("90", "730")
        },
    }


@pytest.mark.parametrize("passed", [True, False])
def test_survival_result_and_curve_render(tmp_path, passed):
    write_fixture(tmp_path)
    table = pd.read_parquet(tmp_path / "site_packages.parquet")
    if passed:
        curve = {
            "s90": [None, 40],
            "s180": [None, 30],
            "s730": [None, 10],
            "s90_band": [None, "Higher chance"],
            "s180_band": [None, "Higher chance"],
            "s730_band": [None, "Middle chance"],
            "s90_mark": [None, 3],
            "s180_mark": [None, 3],
            "s730_mark": [None, 2],
            "s_adjusted": [None, ["s180"]],
            "s_visible": [None, []],
        }
        table = table.assign(**curve)
        table.to_parquet(tmp_path / "site_packages.parquet")
    (tmp_path / "survival.json").write_text(json.dumps(survival_result(passed)))
    out = tmp_path / "out"
    site.build(tmp_path, out)
    method = (out / "method/index.html").read_text()
    assert "How long a project may stay silent" in method
    assert ("Yes." in method) == passed and ("show a curve" in method) != passed
    beta = (out / "p/beta/index.html").read_text()
    alpha = (out / "p/alpha/index.html").read_text()
    assert ("How long it may stay silent" in beta) == passed
    assert "How long it may stay silent" not in alpha  # unknown never gets a curve
    if passed:
        assert "30%*" in beta and "Nudged" in beta and "1 of 1 packages" in method
    assert "said 30% for 3 months where 45% stayed silent" in method


def test_recalibration_attempt_is_reported(tmp_path):
    write_fixture(tmp_path)
    (tmp_path / "survival.json").write_text(json.dumps(survival_result(True)))
    top = {"mean_predicted": 0.42, "observed": 0.45, "n": 10}
    recal = {
        "recal_vs_d18": {"gain": 0.0015, "ci": [-0.0002, 0.0032]},
        "passed": False,
        "top_tenth": {"730": {"lightgbm": top, "lightgbm_recal": top}},
    }
    (tmp_path / "survival_recal.json").write_text(json.dumps(recal))
    out = tmp_path / "out"
    site.build(tmp_path, out)
    method = (out / "method/index.html").read_text()
    assert "original curve stays" in method and "42% said against 45% observed" in method


def test_revival_section_and_quiet_page(tmp_path):
    write_fixture(tmp_path)
    table = pd.read_parquet(tmp_path / "site_packages.parquet")
    table.loc[0, ["state", "state_label", "has_history"]] = ["quiet", "Looks quiet", True]
    filled = dict.fromkeys(
        "active_humans regular_humans bus_factor top_share_pct commits_365d handovers_3y "
        "bot_share_pct".split(),
        0,
    )
    for col, value in {**filled, "commits_prev_365d": 3, "days_since_human": 400}.items():
        table[col] = table[col].astype(object)
        table.loc[0, col] = value
    table["revive_pct"] = [12, None]
    table["revive_band"] = ["Middle chance", None]
    table["revive_mark"] = [2, None]
    table.to_parquet(tmp_path / "site_packages.parquet")
    m = {"n": 100, "positives": 16, "log_loss": 0.4, "brier": 0.12, "roc_auc": 0.73}
    result = {
        "best_baseline": "days_since_human",
        "published_model": "logistic",
        "passed": True,
        "logistic_vs_best_baseline": {"gain": 0.0036, "ci": [0.0011, 0.0062]},
        "lightgbm_vs_best_baseline": {"gain": -0.005, "ci": [-0.009, -0.001]},
        "overall": {k: m for k in ("logistic", "lightgbm", "days_since_human", "releases_365d")},
        "revival_rate_by_year": {"2022-11-09": 0.22, "2023-11-01": 0.16},
        "n_rows": 100,
    }
    (tmp_path / "revival.json").write_text(json.dumps(result))
    out = tmp_path / "out"
    site.build(tmp_path, out)
    method = (out / "method/index.html").read_text()
    assert "Do quiet projects come back?" in method and "only just" in method
    alpha = (out / "p/alpha/index.html").read_text()
    assert "Will it come back?" in alpha and "12%" in alpha
    beta = (out / "p/beta/index.html").read_text()
    assert "Will it come back?" not in beta
