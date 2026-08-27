import numpy as np
import pandas as pd
import pytest

from ib.engines.forecast_engine import (
    StorageConfig,
    annual_projection,
    optimize_dispatch,
    reservoir_potential_mwh,
    storage_from_inputs,
)


def _prices(days: int = 7) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=24 * days, freq="h")
    hour = np.arange(len(idx)) % 24
    values = 55.0 - 35.0 * np.cos((hour - 4) / 24.0 * 2.0 * np.pi)
    return pd.Series(values, index=idx)


def test_conversion_balsa_a_mwh():
    hydraulic = reservoir_potential_mwh(1.0, 100.0)
    assert hydraulic == pytest.approx(272.5, rel=1e-6)
    storage = storage_from_inputs(volume_hm3=1.0, net_head_m=100.0,
                                  turbine_efficiency=0.90)
    assert storage["hydraulic_mwh"] == pytest.approx(272.5, rel=1e-6)
    assert storage["usable_output_mwh"] == pytest.approx(245.25, rel=1e-6)


def test_conversion_mwh_electricos_conserva_capacidad_util():
    storage = storage_from_inputs(usable_output_mwh=4000.0, turbine_efficiency=0.90)
    assert storage["usable_output_mwh"] == pytest.approx(4000.0)
    assert storage["hydraulic_mwh"] == pytest.approx(4000.0 / 0.90)


def test_soc_final_es_exacto():
    cfg = StorageConfig(100, 100, 500, rte=0.78,
                        soc_init_frac=0.35, soc_final_frac=0.35)
    dispatch = optimize_dispatch(_prices(3), cfg)
    assert dispatch["soc_mwh"].iloc[-1] == pytest.approx(175.0, abs=1e-6)


def test_limite_de_ciclos_diarios():
    cfg = StorageConfig(100, 100, 500, rte=0.80, eff_turbine=0.90,
                        eff_pump=0.80 / 0.90, soc_init_frac=0.0,
                        soc_final_frac=0.0, max_cycles_day=0.5)
    dispatch = optimize_dispatch(_prices(4), cfg)
    daily_generation = dispatch.assign(day=dispatch["datetime"].dt.date).groupby("day")["generation_mwh"].sum()
    assert (daily_generation <= 500 * 0.90 * 0.5 + 1e-6).all()


def test_precios_negativos_no_permiten_bombeo_y_turbinado_simultaneos():
    idx = pd.date_range("2025-01-01", periods=48, freq="h")
    # Con precio negativo constante la relajación LP intentaría disipar energía
    # mediante pérdidas de ciclo. La formulación física debe impedirlo.
    prices = pd.Series(-50.0, index=idx)
    cfg = StorageConfig(100, 100, 500, rte=0.78,
                        soc_init_frac=0.5, soc_final_frac=0.5)
    dispatch = optimize_dispatch(prices, cfg)
    assert not dispatch["simultaneous"].any()


def test_proyeccion_reconcilia_componentes_y_varia_por_escenario():
    cfg = StorageConfig(100, 100, 500, rte=0.78, soc_init_frac=0.5,
                        soc_final_frac=0.5, max_cycles_day=1.0)
    projection, operations = annual_projection(
        _prices(7), cfg, start_year=2027, end_year=2030,
        ancillary_eur_mw_year=20_000, ancillary_level="Central",
        arbitrage_growth_pct=1.0, ancillary_growth_pct=0.5,
        variable_opex_eur_mwh=1.0, fixed_opex_eur_kw_year=5.0,
    )
    assert len(projection) == 12
    assert len(operations) == 3
    assert set(projection["escenario"]) == {"Low", "Base", "High"}
    reconstructed = (projection["arbitraje_eur"] + projection["ssaa_eur"]
                     - projection["opex_variable_eur"] - projection["opex_fijo_eur"])
    assert np.allclose(reconstructed, projection["ingreso_neto_eur"])
    first = projection[projection["anio"] == 2027].set_index("escenario")
    assert first.loc["High", "ingreso_neto_eur"] > first.loc["Low", "ingreso_neto_eur"]
