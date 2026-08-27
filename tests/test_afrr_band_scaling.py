"""Regresion del hallazgo A-2: la banda no puede multiplicarse por cuatro."""
import numpy as np
import pandas as pd

from ib.engines import afrr_engine as afrr


def _band_price(i90_month):
    d = i90_month[i90_month["sheet"] == "I90DIA05"]
    hours = pd.to_datetime(d["datetime"]).dt.floor("h").drop_duplicates().sort_values()
    return pd.DataFrame({"hour": hours, "band_price": 20.0})


def test_banda_pondera_por_duracion_y_solo_sentido_subir(i90_month, aliases):
    price = _band_price(i90_month)
    out = afrr.band_revenue(i90_month, price, aliases)
    ag = out[out["asset"] == "Aguayo"]
    # la banda media a subir de Aguayo en enero 2023 es del orden de 50 MW
    assert 45 < ag["quantity"].mean() < 55
    # ingreso = MW medio horario x precio x horas
    esperado = ag["quantity"].sum() * 20.0
    assert abs(ag["revenue_gross"].sum() - esperado) < 1.0


def test_formula_erronea_daria_el_cuadruple(i90_month, aliases):
    """Suma de filas cuartohorarias, ambos sentidos y precio a la mitad."""
    price = _band_price(i90_month)
    correcto = afrr.band_revenue(i90_month, price, aliases)
    correcto_ag = correcto[correcto["asset"] == "Aguayo"]["revenue_gross"].sum()
    d = i90_month[i90_month["sheet"] == "I90DIA05"]
    d = d[d["up"].isin(["AGUG", "AGUB"])]
    erroneo = (d["value"].abs() * 10.0).sum()      # 10 = precio a la mitad
    assert abs(erroneo / correcto_ag - 4.0) < 0.05
