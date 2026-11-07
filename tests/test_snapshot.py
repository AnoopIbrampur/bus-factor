"""The cohort decides what the backtest means, so parse the dump format carefully."""

import io
import json

import pandas as pd

from busfactor.snapshot import cohort, copy_tables, extract, unescape

COLS = (
    "id, registry_id, name, homepage, repository_url, repo_metadata, "
    "dependent_packages_count, downloads, downloads_period, dependent_repos_count, status"
)


def line(*values):
    return "\t".join(values) + "\n"


def dump():
    meta = json.dumps({"html_url": "https://github.com/Real/Repo", "archived": False})
    return io.StringIO(
        'COPY public.registries (id, name, ecosystem, "default") FROM stdin;\n'
        + line("1", "pypi.org", "pypi", "t")
        + line("2", "npmjs.org", "npm", "t")
        + "\\.\n\n"
        + f"COPY public.packages ({COLS}) FROM stdin;\n"
        + line(
            "1",
            "1",
            "alpha",
            r"\N",
            "https://github.com/x/old",
            meta,
            "3",
            "500",
            "last-month",
            "9",
            r"\N",
        )
        + line("2", "2", "npm-thing", r"\N", r"\N", "{}", "0", "999", r"\N", "0", r"\N")
        + line(
            "3",
            "1",
            "beta",
            "https://gitlab.com/a/b",
            r"\N",
            "{}",
            "1",
            "700",
            "last-month",
            "1",
            r"\N",
        )
        + line("4", "1", "gamma", r"\N", r"\N", "{}", "0", r"\N", r"\N", "0", r"\N")
        + "\\.\n"
    )


def test_unescape():
    assert unescape(r"\N") is None
    assert unescape(r"a\tb\\c") == "a\tb\\c"


def test_only_pypi_rows_survive():
    assert set(extract(dump())["name"]) == {"alpha", "beta", "gamma"}


def test_repo_metadata_url_is_preferred():
    df = extract(dump()).set_index("name")
    assert df.loc["alpha", "_url"] == "https://github.com/real/repo"
    assert df.loc["beta", "_url"] == "https://gitlab.com/a/b"


def test_cohort_ranks_by_downloads_and_drops_unranked():
    top = cohort(extract(dump()), top_n=5)
    assert top["name"].tolist() == ["beta", "alpha"]
    assert top["rank_2022"].tolist() == [1, 2]


def test_unknown_table_ends_cleanly():
    s = io.StringIO("COPY public.x (a) FROM stdin;\n1\n\\.\nnoise\n")
    assert list(copy_tables(s)) == [("x", {"a": "1"})]


def test_no_person_columns_are_kept():
    cols = set(cohort(extract(dump())).columns) | set(pd.Index(["x"]))
    assert not cols & {"maintainers", "email", "login", "owner"}
