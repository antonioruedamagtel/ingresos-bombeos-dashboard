"""Motor de energía: base del diario y ajustes de los mercados intradiarios.

Todas las operaciones se hacen sobre la rejilla canónica (día, cuarto de hora).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..domain.revenue_components import DataClass, QualityFlag, finalize
from ..util.grid import attach_datetime

KEY = ["day", "qh"]


def _finish(d: pd.DataFrame, market: str, formula: str, source: str,
            alias_table, incremental: bool) -> pd.DataFrame:
    d = attach_datetime(d)
    d["asset"] = d["up"].map(lambda u: alias_table.asset_of(u))
    d["market"] = market
    d["unit"] = "MWh"
    d["price_ref"] = d.get("pmd")
    d["formula"] = formula
    d["source"] = source
    d["revenue_gross"] = d["quantity"] * d["price"]
    d["revenue_incremental"] = (d["quantity"] * (d["price"] - d["pmd"])
                                if incremental else d["revenue_gross"])
    d["data_class"] = DataClass.OBSERVED.value
    d["quality_flag"] = np.where(
        d["price"].isna(), QualityFlag.MISSING_PRICE.value,
        np.where(d["pmd"].isna(), QualityFlag.MISSING_DA_PRICE.value, QualityFlag.OK.value))
    return finalize(d)


def day_ahead_base(p48: pd.DataFrame, pmd: pd.DataFrame, alias_table) -> pd.DataFrame:
    """P48 x PMD. El signo de P48 es nativo y no se reaplica ningún signo de rol."""
    d = p48.merge(pmd, on=KEY, how="left")
    d["quantity"] = pd.to_numeric(d["energy_mwh"], errors="coerce")
    d["price"] = d["pmd"]
    return _finish(d, "DA", "P48 x PMD", "I90DIA02 + OMIE MARGINALPDBC", alias_table, False)


def intraday_auction(pibci: pd.DataFrame, ida_prices: pd.DataFrame, pmd: pd.DataFrame,
                     alias_table) -> pd.DataFrame:
    """IDA: programa incremental de OMIE valorado al marginal de su sesión."""
    if pibci.empty:
        return finalize(pd.DataFrame())
    d = (pibci.merge(ida_prices, on=KEY + ["session"], how="left")
              .merge(pmd, on=KEY, how="left"))
    d["quantity"] = pd.to_numeric(d["energy_mwh"], errors="coerce")
    return _finish(d, "IDA", "dE_IDA x (P_IDA - PMD)", "OMIE PIBCI + MARGINALPIBC",
                   alias_table, True)


def intraday_continuous(trades: pd.DataFrame, pmd: pd.DataFrame, alias_table) -> pd.DataFrame:
    """MIC: operaciones reales del continuo. Energía = cantidad x duración."""
    if trades.empty:
        return finalize(pd.DataFrame())
    d = trades.merge(pmd, on=KEY, how="left")
    d["quantity"] = pd.to_numeric(d["energy_mwh"], errors="coerce")
    return _finish(d, "MIC", "dE_MIC x (P_trade - PMD)", "OMIE TRADES (cantidad x duracion)",
                   alias_table, True)
