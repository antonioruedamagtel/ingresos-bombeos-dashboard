"""El sistema no puede asumir 24 ni 96 periodos."""
from datetime import date

from ib.util.timeframe import n_hours, n_quarters, period_index, periods_to_datetime


def test_dias_normales():
    assert n_hours(date(2023, 1, 15)) == 24
    assert n_quarters(date(2023, 1, 15)) == 96


def test_dia_de_23_horas_marzo():
    for d in (date(2023, 3, 26), date(2024, 3, 31), date(2026, 3, 29)):
        assert n_hours(d) == 23
        assert n_quarters(d) == 92
        assert len(period_index(d, "QH")) == 92


def test_dia_de_25_horas_octubre():
    for d in (date(2023, 10, 29), date(2024, 10, 27), date(2026, 10, 25)):
        assert n_hours(d) == 25
        assert n_quarters(d) == 100
        assert len(period_index(d, "H")) == 25


def test_periodo_a_timestamp_sin_ambiguedad():
    d = date(2023, 10, 29)
    idx = period_index(d, "H")
    # la hora repetida aparece dos veces en reloj local pero el orden fisico
    # del periodo la desambigua
    assert (idx == idx[2]).sum() == 2
    ts = periods_to_datetime(d, [1, 25], "H")
    assert ts.iloc[0].hour == 0 and ts.iloc[1].hour == 23


def test_periodo_fuera_de_rango_no_inventa_fecha():
    ts = periods_to_datetime(date(2023, 3, 26), [95], "QH")
    assert ts.isna().all()
