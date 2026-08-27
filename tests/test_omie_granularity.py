"""OMIE cambió el intradiario a cuarto de hora el 19/03/2025.

En los ficheros cuartohorarios el valor publicado es potencia en MW, de modo
que la energía es valor por 0,25 h. Deducir la granularidad por mes, o
asumirla, produce un error de factor cuatro justo en el periodo de producción.
"""
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from ib.parsers.omie_parsers import _granularity_of, parse_pibci_zip

DATA = Path(__file__).resolve().parent / "data" / "omie"


def test_deduccion_de_granularidad():
    horario = [(pd.Timestamp("2025-01-01"), p, 1, "AGUG", 10.0) for p in range(1, 25)]
    qh = [(pd.Timestamp("2025-05-01"), p, 1, "AGUG", 10.0) for p in range(1, 97)]
    assert _granularity_of(horario) == ("H", 1.0)
    assert _granularity_of(qh) == ("QH", 0.25)


def _make_zip(tmp_path, name, day, n_periods, value):
    lines = ["PIBCI;"]
    for p in range(1, n_periods + 1):
        lines.append(f"{day[:4]};{day[4:6]};{day[6:]};{p};1;AGUG;{value};0;1;")
    z = tmp_path / "pibci_test.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(name, "\n".join(lines))
    return z


def test_fichero_horario_devuelve_energia_de_la_hora(tmp_path):
    z = _make_zip(tmp_path, "pibci_2025010101.1", "20250101", 24, 10.0)
    d = parse_pibci_zip(z, {"AGUG"})
    assert d["granularity"].eq("H").all()
    assert abs(d["energy_mwh"].sum() - 240.0) < 1e-9      # 24 h x 10 MW


def test_fichero_cuartohorario_pondera_por_la_duracion(tmp_path):
    z = _make_zip(tmp_path, "pibci_2025050101.1", "20250501", 96, 10.0)
    d = parse_pibci_zip(z, {"AGUG"})
    assert d["granularity"].eq("QH").all()
    assert abs(d["energy_mwh"].sum() - 240.0) < 1e-9      # 96 x 10 MW x 0,25 h


def test_transicion_real_del_19_de_marzo_de_2025():
    z = DATA / "pibci_202503.zip"
    if not z.exists():
        pytest.skip("fichero mensual de OMIE no incluido en el paquete")
    with zipfile.ZipFile(z) as zf:
        def max_period(name):
            mx = 0
            for ln in zf.read(name).decode("latin-1").splitlines():
                p = ln.split(";")
                if len(p) >= 7 and p[0].isdigit():
                    mx = max(mx, int(p[3]))
            return mx
        assert max_period("pibci_2025031801.1") == 24
        assert max_period("pibci_2025031901.1") == 96
