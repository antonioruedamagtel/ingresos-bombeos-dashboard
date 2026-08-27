"""Manejo explícito de tiempo de mercado: Europe/Madrid, DST y granularidad variable.

Reglas del proyecto:
  * Nunca se asume 24 ni 96 periodos. La granularidad se deduce de los datos.
  * Un día puede tener 23, 24 o 25 horas y 92, 96 o 100 cuartos de hora.
  * El reloj de mercado es Europe/Madrid. Internamente se trabaja con
    timestamps naive en hora local de mercado, que es la convención de los
    ficheros de OMIE y del I90. La conversión desde series con zona horaria
    (indicadores e·sios) se hace una sola vez, en la frontera.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

MARKET_TZ = "Europe/Madrid"


def market_day_bounds(day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Inicio y fin del día de mercado en UTC, respetando el cambio horario."""
    start_local = pd.Timestamp(day).tz_localize(MARKET_TZ, nonexistent="shift_forward")
    end_local = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(
        MARKET_TZ, nonexistent="shift_forward"
    )
    return start_local.tz_convert("UTC"), end_local.tz_convert("UTC")


def n_hours(day: date) -> int:
    """Horas reales del día local: 23, 24 o 25."""
    a, b = market_day_bounds(day)
    return int((b - a).total_seconds() // 3600)


def n_quarters(day: date) -> int:
    """Cuartos de hora reales del día local: 92, 96 o 100."""
    return n_hours(day) * 4


def period_index(day: date, granularity: str) -> pd.DatetimeIndex:
    """Índice de timestamps locales naive para los periodos reales del día.

    granularity: 'H' u 'QH'. Devuelve exactamente n_hours o n_quarters puntos,
    de modo que un día de 23 o 25 horas produce el número correcto de periodos.
    """
    a, b = market_day_bounds(day)
    freq = "15min" if granularity.upper() == "QH" else "h"
    idx = pd.date_range(a, b, freq=freq, inclusive="left", tz="UTC")
    return idx.tz_convert(MARKET_TZ).tz_localize(None)


def periods_to_datetime(day: date, periods, granularity: str) -> pd.Series:
    """Traduce números de periodo 1..N a timestamp local real del día.

    Se usa el orden físico del periodo, no una aritmética de horas sobre la
    medianoche, para que los días de 23 y 25 horas se resuelvan sin ambigüedad.
    """
    idx = period_index(day, granularity)
    p = pd.to_numeric(pd.Series(periods), errors="coerce")
    valid = p.notna() & (p >= 1) & (p <= len(idx))
    out = pd.Series(pd.NaT, index=p.index, dtype="datetime64[ns]")
    out.loc[valid] = idx[(p[valid].astype(int) - 1).to_numpy()]
    return out


def infer_granularity(max_period: int | float | None, n_labels: int) -> str:
    """Deduce granularidad a partir de las etiquetas de periodo de una tabla."""
    m = 0 if max_period is None or pd.isna(max_period) else int(max_period)
    if m > 25 or n_labels > 25:
        return "QH"
    return "H"


def hours_per_period(granularity: str) -> float:
    """Duración de un periodo en horas. Imprescindible para pasar MW a MWh."""
    return 0.25 if granularity.upper() == "QH" else 1.0


def esios_to_market_clock(series: pd.Series) -> pd.Series:
    """Convierte marcas temporales con zona horaria al reloj de mercado naive."""
    s = pd.to_datetime(series, errors="coerce", utc=True)
    return s.dt.tz_convert(MARKET_TZ).dt.tz_localize(None)


def to_hour(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.floor("h")


def iter_days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def month_windows(start: date, end: date) -> list[str]:
    """Meses YYYYMM cubiertos, incluyendo el anterior al primero.

    Las operaciones del intradiario continuo cerradas el último día de un mes
    pueden tener entrega en el primer día del siguiente, de modo que la ventana
    de ficheros mensuales de OMIE debe incluir el mes anterior.
    """
    first = pd.Timestamp(start).to_period("M") - 1
    last = pd.Timestamp(end).to_period("M")
    out, cur = [], first
    while cur <= last:
        out.append(f"{cur.year:04d}{cur.month:02d}")
        cur += 1
    return out
