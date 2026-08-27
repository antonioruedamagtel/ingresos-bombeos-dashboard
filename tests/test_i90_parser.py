"""Estructura real de las hojas I90, verificada contra ficheros publicados."""
import pandas as pd


def test_granularidad_mixta_en_el_mismo_libro(i90_day):
    g = i90_day.groupby("sheet")["granularity"].first()
    assert g["I90DIA02"] == "QH"     # P48 cuartohorario
    assert g["I90DIA26"] == "H"      # PBF horario
    assert g["I90DIA03"] == "H"      # restricciones del diario, horario
    assert g["I90DIA06"] == "QH"


def test_i90dia11_no_tiene_unidad_ni_sentido(i90_day):
    d = i90_day[i90_day["sheet"] == "I90DIA11"]
    assert not d.empty
    assert (d["up"] == "").all()
    assert (d["direction"] == "").all()
    # el discriminante real es el tipo de redespacho
    assert any("rrfron" in c for c in d["concept"].unique())
    assert any(c.endswith("|rr") for c in d["concept"].unique())


def test_i90dia30_conserva_el_sentido(i90_day):
    d = i90_day[i90_day["sheet"] == "I90DIA30"]
    assert not d.empty
    conc = set(d["concept"].unique())
    assert any("terpro" in c and "subir" in c for c in conc)
    assert any("terpro" in c and "bajar" in c for c in conc)


def test_redespacho_eco_identificado(i90_day):
    d = i90_day[i90_day["sheet"] == "I90DIA03"]
    assert not d.empty
    assert any(c.startswith("eco|") for c in d["concept"].unique())
