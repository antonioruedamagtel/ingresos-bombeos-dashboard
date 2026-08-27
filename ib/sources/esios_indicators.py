"""Indicadores de e·sios con caché local y reloj de mercado normalizado.

Identificadores relevantes, verificados durante la auditoría:

  632   asignación de reserva secundaria a subir (MW)
  633   asignación de reserva secundaria a bajar (MW)
  634   precio de reserva secundaria a bajar. En el periodo pre-SRS equivale a
        la mitad del precio de banda remunerado: NO usar como precio de banda.
  10388 precio medio ponderado de reserva secundaria a subir. Es el precio que
        reproduce el coste publicado del sistema y el que debe usarse pre-SRS.
  10463 precio medio ponderado de reserva a bajar. Vale cero en el periodo
        pre-SRS, lo que confirma que la banda se remunera por el lado a subir.
  2130  precio de reserva secundaria a subir en el periodo post-SRS.
  680/681 energía activada de secundaria a subir y bajar en el sistema.
  682/683 precio de energía de secundaria a subir y bajar.
  676/677 precio marginal de terciaria a bajar y subir de activación programada.
  2197  precio de energías de balance mFRR de activación programada.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..util.timeframe import esios_to_market_clock
from .esios_archive import API_BASE, headers
from .http import Fetch, build_session, get_bytes

SEC_ENERGY_UP = 680          # energia activada de secundaria a subir (horaria)
SEC_ENERGY_DOWN = 681        # energia activada de secundaria a bajar (horaria)
SEC_PRICE_UP = 10389         # precio medio ponderado horario, compatible con 680
SEC_PRICE_DOWN = 10390       # precio medio ponderado horario, compatible con 681
SEC_RIGHTS = 718             # derechos de cobro por energia de secundaria
SEC_OBLIGATIONS = 719        # obligaciones de pago por energia de secundaria
SYSTEM_BAND_UP = 632         # asignacion de reserva secundaria a subir

BAND_PRICE_PRE_SRS = 10388
BAND_PRICE_POST_SRS = 2130
SRS_CUTOFF = pd.Timestamp("2024-11-20")


def load_indicator(indicator_id: int, start: date, end: date, token: str | None = None,
                   session=None, cache_dir: Path | None = None) -> pd.DataFrame:
    cache_dir = Path(cache_dir) if cache_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cp = cache_dir / f"ind_{indicator_id}_{start:%Y%m%d}_{end:%Y%m%d}.parquet"
        if cp.exists():
            return pd.read_parquet(cp)
    session = session or build_session()
    frames = []
    chunk = start
    while chunk <= end:
        chunk_end = min(end, chunk + timedelta(days=89))
        url = f"{API_BASE}/indicators/{indicator_id}"
        params = {
            "start_date": f"{chunk.isoformat()}T00:00:00+01:00",
            "end_date": f"{(chunk_end + timedelta(days=1)).isoformat()}T00:00:00+01:00",
        }
        status, content = get_bytes(session, url, headers=headers(token), params=params, timeout=180)
        if status == Fetch.OK:
            import json
            payload = json.loads(content).get("indicator", {})
            vals = payload.get("values", [])
            if vals:
                frames.append(pd.DataFrame(vals))
        chunk = chunk_end + timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["datetime", "value"])
    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = esios_to_market_clock(df["datetime"])
    if "geo_name" in df.columns and df["geo_name"].notna().any():
        pen = df["geo_name"].astype(str).str.contains("pen", case=False, na=False)
        if pen.any():
            df = df[pen]
    out = df[["datetime", "value"]].dropna().drop_duplicates("datetime").sort_values("datetime")
    if cache_dir:
        out.to_parquet(cp, index=False)
    return out


def band_price_series(start: date, end: date, token=None, session=None, cache_dir=None) -> pd.DataFrame:
    """Precio de banda aFRR con el indicador correcto según el régimen.

    La distinción es material: usar 634 en el periodo pre-SRS subestima el
    precio a la mitad, y sumar filas cuartohorarias sin ponderación temporal lo
    multiplica por cuatro. Aquí el precio se devuelve como serie horaria media.
    """
    frames = []
    if pd.Timestamp(start) < SRS_CUTOFF:
        pre_end = min(pd.Timestamp(end), SRS_CUTOFF - pd.Timedelta(days=1)).date()
        s = load_indicator(BAND_PRICE_PRE_SRS, start, pre_end, token, session, cache_dir)
        if not s.empty:
            s = s.assign(regime="PRE_SRS")
            frames.append(s)
    if pd.Timestamp(end) >= SRS_CUTOFF:
        post_start = max(pd.Timestamp(start), SRS_CUTOFF).date()
        s = load_indicator(BAND_PRICE_POST_SRS, post_start, end, token, session, cache_dir)
        if not s.empty:
            s = s.assign(regime="POST_SRS")
            frames.append(s)
    if not frames:
        return pd.DataFrame(columns=["hour", "band_price", "regime"])
    d = pd.concat(frames, ignore_index=True)
    d["hour"] = pd.to_datetime(d["datetime"]).dt.floor("h")
    return (d.groupby(["hour", "regime"], as_index=False)["value"].mean()
              .rename(columns={"value": "band_price"}))


def system_secondary_net(start: date, end: date, token=None, session=None, cache_dir=None) -> pd.DataFrame:
    """Cashflow neto horario de energía de regulación secundaria del sistema.

    Identidad verificada en enero de 2023 con diferencia nula:

        680 x 10389 - 681 x 10390 = 718 - 719

    Es importante usar 10389 y 10390 y no 682 y 683: los primeros son horarios y
    por tanto compatibles con 680 y 681, mientras que 682 y 683 son
    cuartohorarios y un cruce directo por marca temporal sólo toma uno de los
    cuatro precios de cada hora.
    """
    def s_(i):
        d = load_indicator(i, start, end, token, session, cache_dir)
        if d.empty:
            return pd.Series(dtype=float)
        d = d.copy()
        d["hour"] = pd.to_datetime(d["datetime"]).dt.floor("h")
        return d.groupby("hour")["value"].mean()

    e_up, e_dn = s_(SEC_ENERGY_UP), s_(SEC_ENERGY_DOWN)
    p_up, p_dn = s_(SEC_PRICE_UP), s_(SEC_PRICE_DOWN)
    band = s_(SYSTEM_BAND_UP)
    df = pd.concat([e_up.rename("e_up"), e_dn.rename("e_dn"),
                    p_up.rename("p_up"), p_dn.rename("p_dn"),
                    band.rename("system_band_mw")], axis=1).dropna(
        subset=["e_up", "e_dn", "p_up", "p_dn"])
    df["net_cashflow"] = df["e_up"] * df["p_up"] - df["e_dn"] * df["p_dn"]
    return df.reset_index().rename(columns={"index": "hour"})


def system_secondary_check(start: date, end: date, token=None, session=None, cache_dir=None) -> dict:
    """Control del ancla de sistema frente a los indicadores 718 y 719."""
    net = system_secondary_net(start, end, token, session, cache_dir)
    rights = load_indicator(SEC_RIGHTS, start, end, token, session, cache_dir)
    obligations = load_indicator(SEC_OBLIGATIONS, start, end, token, session, cache_dir)
    a = float(net["net_cashflow"].sum()) if not net.empty else 0.0
    b = float(rights["value"].sum() - obligations["value"].sum()) if not rights.empty else 0.0
    return {"cashflow_680_681": a, "cashflow_718_719": b, "diferencia": a - b}
