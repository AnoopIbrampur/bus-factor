"""Work out what sits behind each package: who depends on it, directly and indirectly.

The graph only covers the tracked top packages, so "indirect" means "within the top 5,000". The
real number is higher, never lower. Download totals overlap heavily (one install can pull in many
of these packages), so the largest single dependent is kept as an honest floor beside the sum.
"""

from collections import defaultdict, deque

import pandas as pd


def reverse_graph(edges: pd.DataFrame) -> dict[str, set[str]]:
    """Map each package to the packages that directly require it."""
    rev: dict[str, set[str]] = defaultdict(set)
    for dependent, dependency in edges.itertuples(index=False):
        rev[dependency].add(dependent)
    return rev


def reach(rev: dict[str, set[str]], start: str) -> dict[str, int]:
    """Every dependent of start with its distance in hops. Cycles are safe."""
    depth = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for dep in rev.get(node, ()):
            if dep not in depth:
                depth[dep] = depth[node] + 1
                queue.append(dep)
    del depth[start]
    return depth


def simulate(edges: pd.DataFrame, downloads: dict[str, int]) -> pd.DataFrame:
    """One row per package with dependents, sorted lists held as Python lists."""
    rev = reverse_graph(edges)
    rows = []
    for name in downloads:
        depth = reach(rev, name)
        direct = sorted((d for d, h in depth.items() if h == 1), key=lambda n: -downloads.get(n, 0))
        indirect = sorted(
            (d for d, h in depth.items() if h > 1), key=lambda n: -downloads.get(n, 0)
        )
        behind = [downloads.get(d, 0) for d in depth]
        rows.append(
            {
                "name": name,
                "n_direct": len(direct),
                "n_indirect": len(indirect),
                "downloads_sum": sum(behind),
                "downloads_max": max(behind, default=0),
                "max_depth": max(depth.values(), default=0),
                "direct": direct,
                "indirect": indirect,
            }
        )
    return pd.DataFrame(rows)
