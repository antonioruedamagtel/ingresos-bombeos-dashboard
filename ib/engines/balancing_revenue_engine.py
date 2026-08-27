"""Motor de servicios de ajuste.

Cada mercado declara explícitamente su clave de cruce de precio. No hay
fallbacks implícitos: la estrategia que casó queda registrada en cada fila, de
modo que una cobertura del 0 % puede diagnosticarse mirando el dato y no el
código.

Correcciones incorporadas respecto de la versión anterior del proyecto:
  * RR se cruza por (periodo, tipo de redespacho). La tabla I90DIA11 no tiene
    columna de unidad de programación ni de sentido, y publica un único precio
    marginal por periodo y tipo.
  * El signo nativo publicado en la hoja de energía se respeta; el sentido se
    usa sólo como control de coherencia.
  * El redespacho ECO del mercado diario se separa de la restricción técnica.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..domain.revenue_components import DataClass, QualityFlag, finalize


def _tag(concept: pd.Series, patterns: dict[str, str]) -> pd.Series:
    c = concept.fillna("").astype(str)
    out = pd.Series("", index=c.index, dtype=object)
    for tag, pat in patterns.items():
        out = out.mask(out.eq("") & c.str.contains(pat, regex=True, na=False), tag)
    return out


def _direction_from_concept(concept: pd.Series) -> pd.Series:
    c = concept.fillna("").astype(str)
    out = pd.Series("", index=c.index, dtype=object)
    out = out.mask(c.str.contains(r"\bsubir\b", regex=True, na=False), "subir")
    out = out.mask(out.eq("") & c.str.contains(r"\bbajar\b", regex=True, na=False), "bajar")
    return out


def _prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    p = prices.copy()
    p["direction"] = np.where(p["direction"].fillna("").astype(str).str.len() > 0,
                              p["direction"].fillna("").astype(str).str.lower(),
                              _direction_from_concept(p["concept"]))
    p["up"] = p["up"].fillna("").astype(str).str.upper()
    p["value"] = pd.to_numeric(p["value"], errors="coerce")
    return p.dropna(subset=["value"])


KEY = ["day", "qh"]


def join_price(energy: pd.DataFrame, prices: pd.DataFrame, strategies: list[str],
               tag_patterns: dict[str, str] | None = None) -> pd.DataFrame:
    """Cruza precio siguiendo estrategias declaradas en orden.

    Estrategias soportadas:
      up_direction, up, direction, tag, period
    """
    e = energy.copy()
    e["up"] = e["up"].fillna("").astype(str).str.upper()
    e["direction"] = np.where(e["direction"].fillna("").astype(str).str.len() > 0,
                              e["direction"].fillna("").astype(str).str.lower(),
                              _direction_from_concept(e["concept"]))
    e["price"] = np.nan
    e["price_join"] = ""
    e["price_ambiguity"] = np.nan
    if prices is None or prices.empty:
        return e
    p = _prepare_prices(prices)
    if tag_patterns:
        e["_tag"] = _tag(e["concept"], tag_patterns)
        p["_tag"] = _tag(p["concept"], tag_patterns)

    key_map = {
        "up_direction": KEY + ["up", "direction"],
        "up": KEY + ["up"],
        "direction": KEY + ["direction"],
        "tag": KEY + ["_tag"],
        "tag_direction": KEY + ["_tag", "direction"],
        "period": list(KEY),
    }
    for strat in strategies:
        keys = key_map[strat]
        if any(k not in p.columns for k in keys):
            continue
        src = p
        if strat in ("direction", "tag", "period", "tag_direction"):
            # sólo filas de precio globales, nunca promediar UPs distintas
            src = p[p["up"].isin(["", "NAN"])] if (p["up"] != "").any() else p
        if src.empty:
            continue
        agg = src.groupby(keys, dropna=False)["value"].agg(["mean", "nunique"]).reset_index()
        agg = agg.rename(columns={"mean": "_p", "nunique": "_amb"})
        agg.loc[agg["_amb"] != 1, "_p"] = np.nan
        missing = e["price"].isna()
        if not missing.any():
            break
        merged = e.loc[missing, keys].merge(agg, on=keys, how="left")
        e.loc[missing, "price"] = merged["_p"].to_numpy()
        e.loc[missing, "price_ambiguity"] = merged["_amb"].to_numpy()
        e.loc[missing & e["price"].notna(), "price_join"] = strat
    return e.drop(columns=[c for c in ["_tag"] if c in e.columns])


MARKET_JOINS = {
    "RT_DIARIO":      dict(strategies=["up_direction", "up"], tags=None),
    "REEQUILIBRIO":   dict(strategies=["up_direction", "up"], tags=None),
    "RT_TIEMPO_REAL": dict(strategies=["up_direction", "up"], tags=None),
    "DESVIOS_RT":     dict(strategies=["up_direction", "up"], tags=None),
    # I90DIA11 no tiene UP ni sentido: la clave real es (periodo, tipo redespacho)
    "RR":             dict(strategies=["tag", "period"],
                           tags={"rrfron": r"rrfron", "rr": r"\brr\b"}),
    # I90DIA30: TERPRO marginal por sentido; TERDIR por sentido y QH0/QH1
    "MFRR":           dict(strategies=["tag_direction", "tag"],
                           tags={"terdir": r"terdir", "terpro": r"terpro"}),
}


def value_market(energy: pd.DataFrame, prices: pd.DataFrame, market: str,
                 pmd: pd.DataFrame, alias_table, inside_p48: bool = True) -> pd.DataFrame:
    """Valora un mercado de servicios y devuelve componentes trazables.

    energy y prices llegan ya en la rejilla canónica (día, cuarto de hora):
    la energía repartida entre los cuatro cuartos de la hora si la tabla era
    horaria, y el precio replicado.
    """
    from ..util.grid import attach_datetime
    cfg = MARKET_JOINS.get(market, dict(strategies=["up_direction", "up", "period"], tags=None))
    e = join_price(energy, prices, cfg["strategies"], cfg["tags"])
    e = e.merge(pmd, on=KEY, how="left")
    e = attach_datetime(e)
    e["asset"] = e["up"].map(lambda u: alias_table.asset_of(u))
    e["quantity"] = pd.to_numeric(e["value"], errors="coerce")   # signo nativo
    e["revenue_gross"] = e["quantity"] * e["price"]
    e["revenue_incremental"] = e["quantity"] * (e["price"] - e["pmd"])
    if not inside_p48:
        e["revenue_incremental"] = e["revenue_gross"]
    e["unit"] = "MWh"
    e["price_ref"] = e["pmd"]
    e["formula"] = np.where(
        inside_p48,
        "quantity x (price - PMD)",
        "quantity x price",
    )
    e["source"] = e["sheet"].fillna("") + " + " + market
    # La clave documentada de cada mercado se considera observacion. Sólo el
    # descenso a una clave menos específica degrada el dato a proxy.
    canonical = ["up_direction", "up", "tag", "tag_direction"]
    e["data_class"] = np.where(
        e["price_join"].isin(canonical), DataClass.OBSERVED.value,
        np.where(e["price"].notna(), DataClass.OBSERVED_PROXY.value, DataClass.OBSERVED.value))
    e["quality_flag"] = np.where(
        e["price"].isna(), QualityFlag.MISSING_PRICE.value,
        np.where(e["pmd"].isna(), QualityFlag.MISSING_DA_PRICE.value,
                 np.where(e["price_ambiguity"].fillna(1) > 1,
                          QualityFlag.AMBIGUOUS_PRICE.value, QualityFlag.OK.value)))
    e["market"] = market
    return finalize(e)


def split_daily_restrictions(i90: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Separa el redespacho ECO de la restricción técnica en I90DIA03."""
    d = i90[i90["sheet"] == "I90DIA03"].copy()
    if d.empty:
        return {"RT_DIARIO": d, "REEQUILIBRIO": d}
    is_eco = d["concept"].fillna("").str.contains(r"\beco\b", regex=True, na=False)
    return {"REEQUILIBRIO": d[is_eco].copy(), "RT_DIARIO": d[~is_eco].copy()}


def split_real_time(i90: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Separa restricciones técnicas de desvíos e indisponibilidad en I90DIA08."""
    d = i90[i90["sheet"] == "I90DIA08"].copy()
    if d.empty:
        return {"RT_TIEMPO_REAL": d, "DESVIOS_RT": d}
    is_rt = d["concept"].fillna("").str.contains("restricciones", na=False)
    return {"RT_TIEMPO_REAL": d[is_rt].copy(), "DESVIOS_RT": d[~is_rt].copy()}
