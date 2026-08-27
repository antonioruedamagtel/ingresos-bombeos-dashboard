"""Contraste contra la tabla de volúmenes por mercado publicada por un tercero.

Aguayo, enero a mayo de 2025, en MWh. Es el contraste externo más exigente
disponible: no una cifra agregada, sino once magnitudes por cinco meses.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

DATA = Path(__file__).resolve().parent / "data" / "i90_2025" / "aguayo_2025_h1.parquet"

PUBLICADO = {
    "Day-ahead":        {"2025-01": 68383.60, "2025-02": 100888.80, "2025-03": 84949.30,
                         "2025-04": 98487.00, "2025-05": 80156.40},
    "RR dw":            {"2025-01": -29497.25, "2025-02": -48623.75, "2025-03": -44467.05,
                         "2025-04": -26010.80, "2025-05": -10152.80},
    "RR up":            {"2025-01": 6688.00, "2025-02": 4900.75, "2025-03": 8153.88,
                         "2025-04": 9170.90, "2025-05": 8636.88},
    "TTCC dw":          {"2025-01": -64894.90, "2025-02": -63635.00, "2025-03": -70198.50,
                         "2025-04": -129884.90, "2025-05": -134658.80},
    "TTCC up":          {"2025-02": 586.50},
    "Real time dw":     {"2025-03": -112.75, "2025-05": -106.25},
    "Real time up":     {"2025-04": 70.00},
    "Terciaria dw":     {"2025-01": -7519.25, "2025-02": -10851.50, "2025-03": -10172.00,
                         "2025-04": -10422.75, "2025-05": -6103.00},
    "Terciaria up":     {"2025-01": 8118.25, "2025-02": 3703.75, "2025-03": 6580.75,
                         "2025-04": 11514.50, "2025-05": 9627.00},
    "Unavailabilities": {"2025-01": 1870.73, "2025-02": 1002.23, "2025-03": 433.20,
                         "2025-04": 102.51, "2025-05": 1859.33},
}


@pytest.fixture(scope="module")
def ag():
    if not DATA.exists():
        pytest.skip("fixture 2025 no incluida")
    d = pd.read_parquet(DATA)
    d["month"] = pd.to_datetime(d["datetime"]).dt.to_period("M").astype(str)
    return d


def _net(d, sheet, sign=None, concept=None):
    x = d[d["sheet"] == sheet]
    if concept is not None:
        x = x[x["concept"].str.contains(concept, na=False)]
    if sign == "dw":
        x = x[x["value"] < 0]
    if sign == "up":
        x = x[x["value"] > 0]
    return x.groupby("month")["value"].sum()


SERIES = {
    "Day-ahead":        ("I90DIA26", None, None),
    "RR dw":            ("I90DIA06", "dw", None),
    "RR up":            ("I90DIA06", "up", None),
    "TTCC dw":          ("I90DIA03", "dw", None),
    "TTCC up":          ("I90DIA03", "up", None),
    "Real time dw":     ("I90DIA08", "dw", "restricciones"),
    "Real time up":     ("I90DIA08", "up", "restricciones"),
    "Terciaria dw":     ("I90DIA07", "dw", None),
    "Terciaria up":     ("I90DIA07", "up", None),
    "Unavailabilities": ("I90DIA08", None, "indispon"),
}


@pytest.mark.parametrize("linea", list(PUBLICADO))
def test_volumenes_por_mercado(ag, linea):
    sheet, sign, concept = SERIES[linea]
    got = _net(ag, sheet, sign, concept)
    for mes, esperado in PUBLICADO[linea].items():
        # abril de 2025 pierde el dia 29, que el I90 no publica por unidad
        tol = 5.0 if mes != "2025-04" else 60.0
        assert abs(float(got.get(mes, 0.0)) - esperado) < tol, (linea, mes, got.get(mes))


def test_cuota_de_restricciones_a_bajar_sobre_energia_de_ajuste(ag):
    """El benchmark publica 50-55 % antes, 69 % en abril y 79 % en mayo."""
    ssaa = ag[ag["sheet"].isin(["I90DIA03", "I90DIA06", "I90DIA07"]) |
              ((ag["sheet"] == "I90DIA08") & ag["concept"].str.contains("restricciones", na=False))]
    total = ssaa.groupby("month")["value"].apply(lambda s: s.abs().sum())
    ttcc = ag[(ag["sheet"] == "I90DIA03") & (ag["value"] < 0)].groupby("month")["value"].apply(
        lambda s: s.abs().sum())
    cuota = 100 * ttcc / total
    assert 50 <= cuota["2025-01"] <= 58
    assert abs(cuota["2025-04"] - 69) < 1.5
    assert abs(cuota["2025-05"] - 79) < 1.5
