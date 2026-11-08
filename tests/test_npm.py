"""npm names, manifests and the D23 comparison."""

import json

import pandas as pd

from busfactor import compare, npm, site
from tests.test_site import write_fixture


def test_names_and_manifest_urls():
    assert npm.norm(" Left-Pad ") == "left-pad"
    assert npm.manifest_url("@babel/core").endswith("/@babel%2Fcore/latest")


def test_repo_field_forms():
    gh = "https://github.com/a/b"
    assert npm.repo_from_manifest({"type": "git", "url": "git+https://github.com/a/b.git"}) == gh
    assert npm.repo_from_manifest("github:a/b") == gh
    assert npm.repo_from_manifest("a/b") == gh
    assert npm.repo_from_manifest("gitlab:a/b") == "https://gitlab.com/a/b"
    assert npm.repo_from_manifest({"url": None}) is None


def test_only_runtime_dependencies_count():
    manifest = {
        "dependencies": {"Chalk": "^5", "debug": "*"},
        "devDependencies": {"jest": "*"},
        "peerDependencies": {"react": "*"},
        "optionalDependencies": {"fsevents": "*"},
        "maintainers": [{"name": "x", "email": "x@example.com"}],
    }
    assert npm.required_names(manifest) == ["chalk", "debug"]


def table(rows):
    cols = [
        "name",
        "rank",
        "repo_key",
        "state",
        "has_history",
        "bus_factor",
        "few_people",
        "active_humans",
    ]
    return pd.DataFrame(rows, columns=cols)


def test_comparison_counts_repos_once_and_flags_only_clear_differences():
    pypi = table([(f"p{i}", i + 1, f"r{i}", "active", True, 2, False, 5) for i in range(40)])
    # npm: 40 packages from 4 repos, every one with a single main committer.
    npm_t = table([(f"n{i}", i + 1, f"m{i % 4}", "active", True, 1, True, 1) for i in range(40)])
    out = compare.compare(pypi, npm_t, reps=200)
    pkg = out["top_all_package"]["measures"]["bus_factor_1"]
    assert pkg["pypi"] == 0.0 and pkg["npm"] == 1.0 and pkg["different"]
    assert out["top_all_repo"]["n_npm"] == 4 and out["top_all_repo"]["n_pypi"] == 40
    same = out["top_all_package"]["measures"]["looks_quiet"]
    assert same["pypi"] == same["npm"] == 0.0 and not same["different"]


def test_npm_pages_render_with_scoped_names(tmp_path):
    write_fixture(tmp_path)
    base = pd.read_parquet(tmp_path / "site_packages.parquet")
    npm_t = base.copy()
    npm_t["name"] = ["@scope/alpha", "beta-js"]
    npm_t.to_parquet(tmp_path / "npm_site_packages.parquet")
    pd.DataFrame(
        [
            {
                "name": "beta-js",
                "n_direct": 1,
                "n_indirect": 0,
                "downloads_sum": 1,
                "downloads_max": 1,
                "direct": ["@scope/alpha"],
                "indirect": [],
            }
        ]
    ).to_parquet(tmp_path / "npm_simulator.parquet")
    block = {
        "n_pypi": 2,
        "n_npm": 2,
        "measures": {
            "bus_factor_1": {
                "pypi": 0.5,
                "npm": 0.5,
                "pypi_ci": [0, 1],
                "npm_ci": [0, 1],
                "diff_ci": [-0.5, 0.5],
                "different": False,
            }
        },
    }
    cmp = {k: block for k in ("top_all_package", "top_all_repo", "top_100_package", "top_100_repo")}
    (tmp_path / "compare.json").write_text(json.dumps(cmp))
    out = tmp_path / "out"
    site.build(tmp_path, out)
    scoped = (out / "npm/p/@scope/alpha/index.html").read_text()
    assert 'href="../../../../static/style.css"' in scoped
    assert "None for npm" in scoped and "doesn't mean healthy" in scoped
    beta = (out / "npm/p/beta-js/index.html").read_text()
    assert 'href="../../../npm/p/@scope/alpha/"' in beta
    listing = (out / "npm/index.html").read_text()
    assert "No clear difference" in listing and "Top 5,000, per package" in listing
