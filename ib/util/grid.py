"""Rejilla temporal canónica del proyecto: (día, cuarto de hora físico).

Por qué no se usa el timestamp local como clave de cruce: en el día de 25 horas
la hora repetida produce dos timestamps naive idénticos, y cualquier merge se
abre en abanico. La clave (día, número de cuarto de hora en orden físico) es
unívoca en los tres tipos de día, 92, 96 y 100 periodos.

Todas las magnitudes se llevan a cuarto de hora antes de operar:
  * energía en MWh se reparte entre los cuatro cuartos de la hora;
  * potencia en MW y precios en euros por MWh o por MW se replican;
  * la duración del periodo queda registrada para poder pasar MW a MWh.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .timeframe import period_index


def expand(df: pd.DataFrame, kind: str, value_col: str = "value",
           period_col: str = "period", gran_col: str = "granularity",
           day_col: str = "day") -> pd.DataFrame:
    """Lleva un marco horario o cuartohorario a la rejilla de cuartos de hora.

    kind: 'E' energía o cantidad extensiva, se divide entre cuatro;
          'P' precio o potencia, magnitud intensiva, se replica.
    """
    if df is None or df.empty:
        out = df.copy() if df is not None else pd.DataFrame()
        if out is not None and not out.empty:
            out["qh"] = pd.NA
        return out
    d = df.copy()
    d[day_col] = pd.to_datetime(d[day_col]).dt.normalize()
    gran = d[gran_col].astype(str).str.upper() if gran_col in d.columns else pd.Series("QH", index=d.index)
    is_h = gran.eq("H")
    qh_part = d[~is_h].copy()
    if not qh_part.empty:
        qh_part["qh"] = qh_part[period_col].astype(int)
    h_part = d[is_h].copy()
    if not h_part.empty:
        rep = h_part.loc[h_part.index.repeat(4)].copy()
        rep["_k"] = rep.groupby(level=0).cumcount()
        rep["qh"] = (rep[period_col].astype(int) - 1) * 4 + rep["_k"] + 1
        if kind.upper() == "E":
            rep[value_col] = rep[value_col] / 4.0
        rep = rep.drop(columns=["_k"])
        h_part = rep
    out = pd.concat([p for p in (qh_part, h_part) if not p.empty], ignore_index=True)
    out["period_hours"] = 0.25
    out["granularity"] = "QH"
    return out


def attach_datetime(df: pd.DataFrame, day_col: str = "day", qh_col: str = "qh") -> pd.DataFrame:
    """Añade el timestamp local real correspondiente a (día, cuarto de hora)."""
    d = df.copy()
    d[day_col] = pd.to_datetime(d[day_col]).dt.normalize()
    stamps = []
    for day, g in d.groupby(day_col):
        idx = period_index(day.date(), "QH")
        q = g[qh_col].astype(int).clip(1, len(idx))
        stamps.append(pd.Series(idx[(q - 1).to_numpy()], index=g.index))
    d["datetime"] = pd.concat(stamps).sort_index() if stamps else pd.NaT
    return d


def hourly_to_qh_frame(df: pd.DataFrame, value_col: str, kind: str,
                       day_col: str = "day", hour_col: str = "period") -> pd.DataFrame:
    d = df.copy()
    d["granularity"] = "H"
    return expand(d, kind, value_col=value_col, period_col=hour_col, day_col=day_col)
