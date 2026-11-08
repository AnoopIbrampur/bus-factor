"""Shared constants in one place, so a rule can't quietly differ between two modules.

Dates that define the backtest live here because they are part of the pre-registration in
docs/decisions.md. Changing one is a rule change and needs a dated note there.
"""

from datetime import date
from pathlib import Path

USER_AGENT = "internet-bus-factor-research"
TOP_N = 5000
DATA_DIR = Path("data")
PRIVATE_DIR = DATA_DIR / "private"  # holds repo URLs; encrypted before leaving the machine

SNAPSHOT_DATE = date(2022, 11, 9)
TEST_CUTOFFS = (date(2022, 11, 9), date(2023, 11, 1), date(2024, 11, 1), date(2025, 11, 1))
TRAIN_CUTOFFS = tuple(date(y, 11, 1) for y in range(2017, 2025))
HORIZON_DAYS = 365

# D18: the survival test reads a pinned harvest, so later weekly runs can't change its answer.
SURVIVAL_AS_OF = date(2026, 11, 7)
