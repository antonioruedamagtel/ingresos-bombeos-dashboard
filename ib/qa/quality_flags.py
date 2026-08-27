"""Resumen de calidad y cobertura por mercado y clase de dato."""
from __future__ import annotations

import numpy as np
import pandas as pd


def coverage(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail.copy()
    d["abs_q"] = pd.to_numeric(d["quantity"], errors="coerce").abs()
    g = d.groupby("market").apply(lambda x: pd.Series({
        "cantidad_abs": x["abs_q"].sum(),
        "con_precio": x.loc[x["price"].notna(), "abs_q"].sum(),
        "filas": len(x),
        "observado_pct": 100.0 * (x["data_class"] == "OBSERVADO").mean(),
    }), include_groups=False).reset_index()
    g["cobertura_precio_pct"] = 100.0 * g["con_precio"] / g["cantidad_abs"].replace(0, np.nan)
    return g


def flags(detail: pd.DataFrame) -> pd.DataFrame:
    return (detail.groupby(["market", "quality_flag"], as_index=False)
                  .size().rename(columns={"size": "filas"}))


def data_class_mix(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail.copy()
    return (d.groupby(["asset", "data_class"], as_index=False)["revenue_incremental"].sum()
             .pivot(index="asset", columns="data_class", values="revenue_incremental")
             .fillna(0.0).reset_index())


def trace(detail: pd.DataFrame, asset: str, market: str | None = None,
          start=None, end=None) -> pd.DataFrame:
    """Trazabilidad: devuelve las filas que componen una cifra del cuadro."""
    d = detail[detail["asset"] == asset].copy()
    if market:
        d = d[d["market"] == market]
    if start is not None:
        d = d[pd.to_datetime(d["datetime"]) >= pd.Timestamp(start)]
    if end is not None:
        d = d[pd.to_datetime(d["datetime"]) <= pd.Timestamp(end)]
    return d.sort_values("datetime")
