"""Render the static site from data files, with no server and almost no JavaScript.

The rules from the brief are enforced here rather than left to templates: a project is never
called abandoned, unknown never renders as healthy, and nothing person-related can appear
because this module only ever receives counts. Pages are plain files, so they load fast and
every simulator result has its own shareable URL.
"""

import json
import math
import shutil
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES = Path("site/templates")
STATIC = Path("site/static")
LIST_LIMIT = 200


def comma(v) -> str:
    return f"{int(v):,}"


def short(v) -> str:
    v = float(v)
    for limit, suffix in ((1e9, " billion"), (1e6, " million")):
        if v >= limit:
            return f"{v / limit:.1f}{suffix}"
    return f"{int(v):,}"


def clean(value):
    """NaN and pandas NA become None, so templates can't print 'nan' as if it were data."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=False,
    )
    env.filters["comma"] = comma
    env.filters["short"] = short
    return env


def records(table: pd.DataFrame) -> list[dict]:
    return [{k: clean(v) for k, v in row.items()} for row in table.to_dict("records")]


def write(out: Path, rel: str, html: str) -> None:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)


def summary(pkgs: list[dict]) -> dict:
    known = [p for p in pkgs if p["has_history"]]
    n_bf1 = sum(1 for p in known if p["bus_factor"] == 1)
    quiet = sum(1 for p in pkgs if p["state"] == "quiet")
    return {
        "n_packages": len(pkgs),
        "n_known": len(known),
        "n_bf1": n_bf1,
        "pct_bf1": round(100 * n_bf1 / len(known)) if known else 0,
        "n_quiet": quiet,
        "pct_quiet": round(100 * quiet / len(known)) if known else 0,
        "n_unknown": sum(1 for p in pkgs if p["state"] == "unknown"),
    }


def build(data_dir: Path, out: Path) -> None:
    """Render every page into out, replacing what was there."""
    table = pd.read_parquet(data_dir / "site_packages.parquet")
    context = json.loads((data_dir / "site_context.json").read_text())
    sim = pd.read_parquet(data_dir / "simulator.parquet").set_index("name")
    pkgs = records(table.sort_values("rank"))
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out / "static")
    (out / ".nojekyll").write_text("")
    env = environment()
    n = len(pkgs)
    base = {"updated": context["updated"], "n_packages": n}

    def page(template: str, rel: str, root: str, title: str, active: str = "", **kw) -> None:
        html = env.get_template(template).render(
            root=root, title=title, active=active, **base, **kw
        )
        write(out, rel, html)

    active_few = [p for p in pkgs if p["few_people"] and p["state"] in ("active", "slowing")]
    active_few.sort(key=lambda p: (-p["total_dependents"], p["name"]))
    page(
        "home.html",
        "index.html",
        "",
        "Overview",
        "home",
        s=summary(pkgs),
        help=active_few[:25],
        result_summary=context["result_summary"],
    )
    page("packages.html", "packages/index.html", "../", "Packages", "packages", pkgs=pkgs)
    examples = [p["name"] for p in sorted(pkgs, key=lambda p: -p["total_dependents"])[:4]]
    page(
        "simulator.html",
        "simulator/index.html",
        "../",
        "Failure simulator",
        "simulator",
        names=[p["name"] for p in pkgs],
        examples=examples,
    )
    page("track.html", "track-record/index.html", "../", "Track record", "track", ctx=context)
    page("method.html", "method/index.html", "../", "Method and limits", "method", ctx=context)
    for p in pkgs:
        name = p["name"]
        page("package.html", f"p/{name}/index.html", "../../", name, "packages", p=p)
        row = sim.loc[name] if name in sim.index else None
        direct = list(row["direct"]) if row is not None else []
        indirect = list(row["indirect"]) if row is not None else []
        q = {
            **p,
            "direct": direct[:LIST_LIMIT],
            "indirect": indirect[:LIST_LIMIT],
            "direct_more": len(direct) > LIST_LIMIT,
            "indirect_more": len(indirect) > LIST_LIMIT,
        }
        page(
            "sim_one.html",
            f"simulator/{name}/index.html",
            "../../",
            f"If {name} stopped",
            "simulator",
            p=q,
        )
