"""Motor de regulación secundaria (aFRR).

Dos componentes que nunca deben mezclarse:

  BANDA   remuneración de capacidad, en euros por MW asignado y hora.
          Observable por unidad de programación hasta el 20/11/2024.
  ENERGIA energía efectivamente activada. No forma parte de P48 y no se
          publica por unidad de programación en el periodo histórico, por lo
          que sólo puede estimarse.

Errores corregidos respecto de la versión anterior del proyecto:
  1. la banda se pondera por la duración real del periodo, de modo que una
     tabla cuartohoraria no multiplica el ingreso por cuatro;
  2. se toma únicamente el sentido a subir, porque la hoja publica banda a
     subir y a bajar y sumar ambas duplica la capacidad;
  3. el precio pre-SRS es el indicador 10388 y no el 634, que vale la mitad.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..domain.revenue_components import DataClass, QualityFlag, finalize

SRS_CUTOFF = pd.Timestamp("2024-11-20")


def band_revenue(i90: pd.DataFrame, band_price: pd.DataFrame, alias_table) -> pd.DataFrame:
    """Ingreso de banda observado por UP. Sólo válido antes del cambio SRS."""
    d = i90[(i90["sheet"] == "I90DIA05") & (i90["datetime"] < SRS_CUTOFF)].copy()
    if d.empty:
        return finalize(pd.DataFrame())
    d = d[d["direction"].fillna("").str.lower().str.startswith("subir")].copy()
    if d.empty:
        return finalize(pd.DataFrame())
    d["hour"] = pd.to_datetime(d["datetime"]).dt.floor("h")
    # MW medio de la hora: la tabla puede ser horaria o cuartohoraria.
    mw = d.groupby(["hour", "up"], as_index=False).apply(
        lambda g: pd.Series({"mw": float((g["value"] * g["period_hours"]).sum() /
                                         max(g["period_hours"].sum(), 1e-9))}),
        include_groups=False)
    mw = mw.merge(band_price[["hour", "band_price"]], on="hour", how="left")
    mw["asset"] = mw["up"].map(lambda u: alias_table.asset_of(u))
    mw["datetime"] = mw["hour"]
    mw["market"] = "AFRR_BANDA"
    mw["quantity"] = mw["mw"]
    mw["unit"] = "MW"
    mw["price"] = mw["band_price"]
    mw["price_ref"] = np.nan
    mw["formula"] = "MW_banda_subir x precio_banda x 1h"
    mw["revenue_gross"] = mw["quantity"] * mw["band_price"]
    mw["revenue_incremental"] = mw["revenue_gross"]
    mw["source"] = "I90DIA05 + esios 10388"
    mw["data_class"] = DataClass.OBSERVED.value
    mw["quality_flag"] = np.where(mw["band_price"].isna(), QualityFlag.MISSING_PRICE.value,
                                  QualityFlag.OK.value)
    return finalize(mw)


def secondary_energy_net_estimate(i90: pd.DataFrame, system_net: pd.DataFrame,
                                  alias_table) -> pd.DataFrame:
    """Neto económico estimado de energía de regulación secundaria por activo.

    Por qué sólo el NETO y no un reparto entre subir y bajar: la banda retribuye
    disponibilidad y la energía secundaria remunera utilización efectiva. La
    cuota de banda de un activo no es su cuota de energía activada en cada
    sentido, y repartir por sentido produce precios efectivos absurdos. La cuota
    de banda se usa aquí como proxy de participación económica, nunca como
    asignación física, y el resultado no se reparte entre generación y bombeo.

    En el periodo histórico la energía secundaria se prestaba y liquidaba por
    zona de regulación, no por unidad de programación, de modo que esta capa es
    ESTIMADA por construcción y así queda etiquetada.
    """
    d = i90[i90["sheet"] == "I90DIA05"].copy()
    if d.empty or system_net is None or system_net.empty:
        return finalize(pd.DataFrame())
    d = d[d["direction"].fillna("").str.lower().str.startswith("subir")]
    if d.empty:
        return finalize(pd.DataFrame())
    d["hour"] = pd.to_datetime(d["datetime"]).dt.floor("h")
    d["asset"] = d["up"].map(lambda u: alias_table.asset_of(u))
    mw = d.groupby(["hour", "asset"], as_index=False)["value"].mean().rename(
        columns={"value": "asset_band_mw"})
    m = mw.merge(system_net[["hour", "system_band_mw", "net_cashflow"]], on="hour", how="left")
    m = m.dropna(subset=["system_band_mw", "net_cashflow"])
    m = m[m["system_band_mw"] > 0]
    if m.empty:
        return finalize(pd.DataFrame())
    m["share"] = m["asset_band_mw"] / m["system_band_mw"]
    m["datetime"] = m["hour"]
    m["up"] = ""
    m["market"] = "AFRR_ENERGIA"
    m["quantity"] = np.nan
    m["unit"] = "EUR"
    m["price"] = np.nan
    m["price_ref"] = np.nan
    m["formula"] = "neto_secundaria_sistema x banda_activo / banda_sistema"
    m["revenue_gross"] = m["net_cashflow"] * m["share"]
    m["revenue_incremental"] = m["revenue_gross"]
    m["source"] = "I90DIA05 + esios 632/680/681/10389/10390"
    m["data_class"] = DataClass.ESTIMATED.value
    m["quality_flag"] = "ESTIMATED_SECONDARY_NET_BAND_SHARE"
    return finalize(m)


def post_srs_estimate(assets: pd.DataFrame, rates: dict, start, end,
                      driver: str = "band_mw") -> pd.DataFrame:
    """Estimación post-SRS por tasa histórica.

    El driver por defecto es la banda media asignada, no la potencia instalada:
    la banda es la magnitud que realmente genera el ingreso y es la única que
    permite extrapolar a una central futura.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if end < SRS_CUTOFF:
        return finalize(pd.DataFrame())
    rows = []
    months = pd.date_range(max(start, SRS_CUTOFF).to_period("M").to_timestamp(),
                           end.to_period("M").to_timestamp(), freq="MS")
    for r in assets.itertuples():
        rate = rates.get(r.asset)
        drv = getattr(r, driver, None)
        if rate is None or pd.isna(rate) or float(rate) <= 0 or drv in (None, 0) or pd.isna(drv):
            continue
        for m in months:
            month_end = m + pd.offsets.MonthEnd(0)
            eff_start = max(start, SRS_CUTOFF, m)
            eff_end = min(end, month_end)
            if eff_end < eff_start:
                continue
            frac = ((eff_end.normalize() - eff_start.normalize()).days + 1) / month_end.day
            rows.append({
                "asset": r.asset, "up": "", "datetime": eff_start, "market": "AFRR_BANDA",
                "quantity": float(drv) * frac, "unit": "MW-mes", "price": float(rate),
                "price_ref": np.nan,
                "formula": f"tasa_historica x {driver} x fraccion_mes",
                "revenue_gross": float(rate) * float(drv) * frac,
                "revenue_incremental": float(rate) * float(drv) * frac,
                "source": "modelo historico pre-SRS",
                "data_class": DataClass.ESTIMATED.value,
                "quality_flag": QualityFlag.ESTIMATED_RATE.value,
            })
    return finalize(pd.DataFrame(rows))
