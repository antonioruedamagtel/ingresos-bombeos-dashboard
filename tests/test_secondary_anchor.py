"""Ancla de sistema de la energía de regulación secundaria.

    680 x 10389 - 681 x 10390 = 718 - 719

Se usan 10389 y 10390, horarios, y no 682 y 683, cuartohorarios: cruzar una
serie horaria con una cuartohoraria por marca temporal toma sólo uno de los
cuatro precios de cada hora.
"""
from pathlib import Path

import pandas as pd
import pytest

DATA = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="module")
def anchor():
    a = DATA / "system_secondary_net_202301.parquet"
    b = DATA / "system_secondary_718_719_202301.parquet"
    if not (a.exists() and b.exists()):
        pytest.skip("fixtures de secundaria no incluidas")
    return pd.read_parquet(a), pd.read_parquet(b)


def test_identidad_del_sistema(anchor):
    net, rights = anchor
    a = float(net["net_cashflow"].sum())
    b = float(rights["rights"].iloc[0] - rights["obligations"].iloc[0])
    assert abs(a - b) < 1.0
    assert a > 0


def test_estimacion_neta_de_aguayo_por_cuota_de_banda(anchor):
    net, _ = anchor
    i90 = pd.concat([pd.read_parquet(p) for p in
                     sorted((DATA / "i90" / "2023" / "01").glob("*.parquet"))], ignore_index=True)
    b = i90[(i90["sheet"] == "I90DIA05") & (i90["up"] == "AGUG") &
            (i90["direction"].str.startswith("subir"))].copy()
    b["hour"] = pd.to_datetime(b["datetime"]).dt.floor("h")
    mw = b.groupby("hour")["value"].mean().rename("mw")
    m = net.set_index("hour").join(mw, how="inner").dropna()
    est = float((m["net_cashflow"] * m["mw"] / m["system_band_mw"]).sum())
    assert 400_000 < est < 540_000        # v0.6.6 del proyecto: ~0,47 MEUR
