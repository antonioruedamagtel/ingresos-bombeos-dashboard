"""Capa ANALYTICS en Parquet particionado, con compatibilidad CSV de transición."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


class ProcessedStore:
    def __init__(self, root: Path, write_csv_mirror: bool = True):
        self.root = Path(root) / "analytics"
        self.root.mkdir(parents=True, exist_ok=True)
        self.write_csv_mirror = write_csv_mirror

    def write(self, name: str, df: pd.DataFrame) -> Path:
        p = self.root / f"{name}.parquet"
        df.to_parquet(p, index=False)
        if self.write_csv_mirror:
            df.to_csv(self.root / f"{name}.csv", index=False, encoding="utf-8-sig")
        return p

    def read(self, name: str) -> pd.DataFrame:
        p = self.root / f"{name}.parquet"
        if p.exists():
            return pd.read_parquet(p)
        c = self.root / f"{name}.csv"
        return pd.read_csv(c) if c.exists() else pd.DataFrame()
