"""El despacho debe ser optimo, no una regla heuristica."""
import numpy as np
import pandas as pd

from ib.engines.forecast_engine import StorageConfig, dispatch_metrics, optimize_dispatch


def _prices(n=48):
    """Perfil diario con el valle por la madrugada y la punta por la tarde."""
    idx = pd.date_range("2030-01-01", periods=n, freq="h")
    base = 50 - 40 * np.cos((np.arange(n) % 24 - 4) / 24 * 2 * np.pi)
    return pd.Series(base, index=idx)


def test_respeta_capacidad_y_almacenamiento():
    cfg = StorageConfig(p_turbine_mw=100, p_pump_mw=100, energy_mwh=400, rte=0.75)
    d = optimize_dispatch(_prices(), cfg)
    assert d["generation_mw"].max() <= 100 + 1e-6
    assert d["pumping_mw"].max() <= 100 + 1e-6
    assert d["soc_mwh"].max() <= 400 + 1e-6
    assert d["soc_mwh"].min() >= -1e-6


def test_nunca_bombea_y_turbina_a_la_vez():
    cfg = StorageConfig(p_turbine_mw=100, p_pump_mw=100, energy_mwh=400, rte=0.75)
    p = _prices()
    p.iloc[5:8] = -20.0                     # horas de precio negativo
    d = optimize_dispatch(p, cfg)
    assert not d["simultaneous"].any()


def test_supera_a_la_regla_de_las_n_horas_mas_baratas():
    """La optimizacion nunca puede ser peor que una heuristica factible."""
    cfg = StorageConfig(p_turbine_mw=100, p_pump_mw=100, energy_mwh=400, rte=0.80,
                        soc_init_frac=0.0, soc_final_frac=0.0)
    p = _prices(72)
    d = optimize_dispatch(p, cfg)
    opt = d["cashflow"].sum()
    et, ep = cfg.efficiencies()
    naive = 0.0
    for _, day in p.groupby(p.index.date):
        if len(day) < 24:
            continue
        cheap_idx = day.nsmallest(4).index
        # solo es factible generar despues de haber bombeado
        exp_idx = [t for t in day.nlargest(8).index if t > cheap_idx.max()][:4]
        if len(exp_idx) < 4:
            continue
        bought = 4 * 100.0
        sellable = bought * ep * et
        naive += day.loc[exp_idx].mean() * sellable - day.loc[cheap_idx].sum() * 100.0
    assert naive > 0
    assert opt >= naive - 1e-6


def test_cierra_el_balance_de_almacenamiento():
    cfg = StorageConfig(p_turbine_mw=80, p_pump_mw=90, energy_mwh=500, rte=0.78,
                        soc_init_frac=0.4, soc_final_frac=0.4)
    d = optimize_dispatch(_prices(96), cfg)
    et, ep = cfg.efficiencies()
    soc = 0.4 * 500
    for _, r in d.iterrows():
        soc = soc + r["pumping_mwh"] * ep - r["generation_mwh"] / et
    assert abs(soc - d["soc_mwh"].iloc[-1]) < 1e-6
    assert d["soc_mwh"].iloc[-1] >= 0.4 * 500 - 1e-6
