"""Estructura real de las hojas I90, verificada contra ficheros publicados."""
import pandas as pd

from ib.engines.balancing_revenue_engine import split_real_time
from ib.parsers.i90_parser import _find_layout, _long_from_matrix


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


def test_formato_2026_sin_columna_total_detecta_inicio_de_periodos():
    """Enero--mayo 2026 no separa los metadatos de los cuartos de hora."""
    periods = [f"{h:02d}:00-{(h + 1) % 24:02d}:00" for h in range(24)]
    header = ["Unidad de Programación", "Tipo", *periods]
    cells = [["I90DIA08"], header, ["AGUG", "UPLTROR", *range(1, 25)]]
    layout = _find_layout(cells)
    assert layout == (1, 1, None, 2)
    got = _long_from_matrix(cells, *layout, len(header), "I90DIA08", "2026-02-03", {"AGUG"})
    assert len(got) == 24
    assert got["up"].eq("AGUG").all()
    assert got["total_declared"].isna().all()


def test_formato_2026_con_cuarto_de_hora_del_dia_como_separador():
    periods = [f"{h:02d}:00-{(h + 1) % 24:02d}:00" for h in range(24)]
    header = ["Unidad de Programación", "Tipo", "Cuarto de Hora del dia", *periods]
    cells = [["I90DIA08"], header, ["AGUG", "UPOTROR", "", *range(1, 25)]]
    layout = _find_layout(cells)
    assert layout == (1, 1, 2, 3)
    got = _long_from_matrix(cells, *layout, len(header), "I90DIA08", "2026-06-03", {"AGUG"})
    assert len(got) == 24


def test_codigos_2026_de_redespacho_se_clasifican_como_restriccion_tiempo_real():
    source = pd.DataFrame({
        "sheet": ["I90DIA08", "I90DIA08", "I90DIA08"],
        "concept": ["upltror", "UPOTROR", "indisponibilidad"],
    })
    result = split_real_time(source)
    assert len(result["RT_TIEMPO_REAL"]) == 2
    assert len(result["DESVIOS_RT"]) == 1
