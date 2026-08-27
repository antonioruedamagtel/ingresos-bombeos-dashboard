"""El cambio horario es un defecto abierto y el control debe detectarlo.

Este test no afirma que el motor cierre en los dias de 23 y 25 horas: afirma que
el sistema los identifica y que la puerta de volumenes los marca. Un dia de
cambio horario nunca debe pasar como validado en silencio.
"""
from datetime import date

import pandas as pd

from ib.qa import reconciliation as rc
from ib.util.timeframe import n_hours


def test_identifica_los_dias_de_cambio_horario():
    dias = pd.date_range("2023-03-20", "2023-04-02", freq="D")
    dst = rc.dst_days_in(dias)
    assert dst == [date(2023, 3, 26)]
    dias = pd.date_range("2023-10-23", "2023-11-05", freq="D")
    assert rc.dst_days_in(dias) == [date(2023, 10, 29)]


def test_ningun_dia_normal_se_marca():
    dias = pd.date_range("2023-01-01", "2023-01-31", freq="D")
    assert rc.dst_days_in(dias) == []
    assert all(n_hours(d.date()) == 24 for d in dias)


def test_la_puerta_de_volumen_rechaza_un_residuo_alto():
    rec = pd.DataFrame({"entity": ["Aguayo"], "role": ["generation"],
                        "residual": [1400.0], "residual_pct": [12.3]})
    ok, detalle = rc.gate_volume(rec)
    assert ok is False
    assert detalle["ok"].eq(False).all()


def test_la_nota_del_defecto_esta_documentada():
    assert "cambio horario" in rc.DST_DEFECT_NOTE
