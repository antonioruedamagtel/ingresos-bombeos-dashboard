from pathlib import Path

import pandas as pd
import pytest

from ib.ui.dashboard import _storage_control_state, build_app


ROOT = Path(__file__).resolve().parents[1]


def _component(component, target_id):
    if getattr(component, "id", None) == target_id:
        return component
    children = getattr(component, "children", None)
    if not isinstance(children, (list, tuple)):
        children = [children] if children is not None else []
    for child in children:
        found = _component(child, target_id)
        if found is not None:
            return found
    return None


def test_mwh_activa_solo_la_capacidad_electrica():
    state = _storage_control_state("mwh", 5, 350, 0.90)
    assert state["mwh_disabled"] is False
    assert state["volume_disabled"] is True
    assert state["head_disabled"] is True
    assert state["calculated_mwh"] is None


def test_balsa_activa_geometria_y_calcula_mwh_utiles():
    state = _storage_control_state("reservoir", 5, 350, 0.90)
    assert state["mwh_disabled"] is True
    assert state["volume_disabled"] is False
    assert state["head_disabled"] is False
    assert state["calculated_mwh"] == pytest.approx(4291.88, abs=0.01)


def test_balsa_incompleta_no_conserva_un_resultado_anterior():
    state = _storage_control_state("reservoir", None, 350, 0.90)
    assert state["calculated_mwh"] is None


def test_calendarios_permiten_navegar_hasta_el_año_actual():
    app = build_app(ROOT / "data", ROOT / "config" / "assets.csv")
    for target_id in ("f-start", "f-end"):
        picker = _component(app.layout, target_id)
        assert pd.Timestamp(picker.max_date_allowed).year >= pd.Timestamp.today().year


def test_etiqueta_anual_usa_la_notacion_solicitada():
    app = build_app(ROOT / "data", ROOT / "config" / "assets.csv")
    metric = _component(app.layout, "f-metric")
    labels = {option["label"] for option in metric.options}
    assert "EUR/MW-año" in labels
