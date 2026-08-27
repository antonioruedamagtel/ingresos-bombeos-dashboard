import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="session")
def i90_month() -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in sorted((DATA / "i90" / "2023" / "01").glob("*.parquet"))]
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="session")
def i90_day() -> pd.DataFrame:
    return pd.read_parquet(DATA / "i90" / "2023" / "01" / "20230115.parquet")


@pytest.fixture(scope="session")
def assets():
    from ib.pipeline import load_assets
    return load_assets(ROOT / "config" / "assets.csv")


@pytest.fixture(scope="session")
def aliases(assets):
    from ib.domain.aliases import AliasTable
    return AliasTable.from_assets(assets)


@pytest.fixture(scope="session")
def pmd_month() -> pd.DataFrame:
    from ib.pipeline import _marginal_to_grid
    from ib.util.timeframe import iter_days
    out = []
    for d in iter_days(date(2023, 1, 1), date(2023, 1, 31)):
        f = DATA / "omie" / "marginalpdbc" / f"{d:%Y%m%d}.1"
        if f.exists():
            out.append(_marginal_to_grid(f, d, "pmd"))
    return pd.concat(out, ignore_index=True).drop_duplicates(["day", "qh"])
