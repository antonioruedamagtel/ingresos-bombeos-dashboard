"""Motor de programa físico: P48, PBF y cierre de volúmenes.

El cierre de volúmenes es una puerta obligatoria: si la identidad

    P48 = PBF + DeltaIDA + DeltaMIC + Delta_servicios

no cierra dentro de tolerancia, no se calcula ningún euro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..util.grid import expand

SHEET_P48 = "I90DIA02"
SHEET_PBF = "I90DIA26"
SHEET_PHFC = "I90DIA36"


def _energy(i90: pd.DataFrame, sheet: str) -> pd.DataFrame:
    """Energía en MWh por UP en la rejilla canónica (día, cuarto de hora)."""
    d = i90[i90["sheet"] == sheet]
    if d.empty:
        return pd.DataFrame(columns=["day", "qh", "up", "energy_mwh"])
    d = expand(d, "E")
    return (d.groupby(["day", "qh", "up"], as_index=False)["value"].sum()
              .rename(columns={"value": "energy_mwh"}))


def p48(i90: pd.DataFrame) -> pd.DataFrame:
    return _energy(i90, SHEET_P48)


def pbf(i90: pd.DataFrame) -> pd.DataFrame:
    return _energy(i90, SHEET_PBF)


def check_native_sign(i90: pd.DataFrame, alias_table) -> pd.DataFrame:
    """Compara el signo nativo publicado con el rol configurado de la unidad.

    Nunca se corrige el dato: se emite un aviso. Reaplicar un signo de rol sobre
    una fuente que ya trae signo nativo es el error catalogado del proyecto.
    """
    d = i90[i90["sheet"].isin([SHEET_P48, SHEET_PBF])]
    if d.empty:
        return pd.DataFrame(columns=["up", "sheet", "role", "n_positive", "n_negative", "conflict"])
    rows = []
    for (up, sheet), g in d.groupby(["up", "sheet"]):
        role = alias_table.role_of(up)
        npos = int((g["value"] > 0).sum())
        nneg = int((g["value"] < 0).sum())
        expected_pos = role == "generation"
        conflict = (npos > 0 and nneg > 0) or (expected_pos and npos == 0 and nneg > 0) or \
                   ((not expected_pos) and nneg == 0 and npos > 0)
        rows.append({"up": up, "sheet": sheet, "role": role, "n_positive": npos,
                     "n_negative": nneg, "conflict": bool(conflict)})
    return pd.DataFrame(rows)


def reconcile(p48_df: pd.DataFrame, pbf_df: pd.DataFrame, deltas: dict[str, pd.DataFrame],
              alias_table=None, level: str = "asset") -> pd.DataFrame:
    """Cierre de volúmenes en la rejilla canónica.

    El cierre se hace por ACTIVO y por rol, no por código de unidad, porque los
    códigos difieren entre OMIE e I90 (por ejemplo IPG en OMIE frente a CHIPG en
    el I90, o MUEL frente a MUEG). Cerrar por código produciría residuos
    artificiales del cien por cien.
    """
    def key(df):
        d = df.copy()
        if alias_table is not None and level == "asset":
            d["entity"] = d["up"].map(lambda u: alias_table.asset_of(u))
            d["role"] = d["up"].map(lambda u: alias_table.role_of(u))
            d["entity"] = d["entity"].fillna(d["up"])
            d["role"] = d["role"].fillna("")
        else:
            d["entity"], d["role"] = d["up"], ""
        return d

    base = key(p48_df).rename(columns={"energy_mwh": "p48"}).groupby(
        ["day", "qh", "entity", "role"], as_index=False)["p48"].sum()
    pbf_k = key(pbf_df).rename(columns={"energy_mwh": "pbf"}).groupby(
        ["day", "qh", "entity", "role"], as_index=False)["pbf"].sum()
    base = base.merge(pbf_k, on=["day", "qh", "entity", "role"], how="outer")
    for name, d in deltas.items():
        if d is None or d.empty:
            base[name] = 0.0
            continue
        s = key(d).groupby(["day", "qh", "entity", "role"], as_index=False)["energy_mwh"].sum().rename(
            columns={"energy_mwh": name})
        base = base.merge(s, on=["day", "qh", "entity", "role"], how="outer")
    base = base.fillna(0.0)
    cols = list(deltas.keys())
    base["sum_deltas"] = base[cols].sum(axis=1)
    base["residual"] = base["p48"] - base["pbf"] - base["sum_deltas"]
    return base


def reconciliation_summary(rec: pd.DataFrame, tolerance_pct: float = 0.5) -> pd.DataFrame:
    skip = {"day", "qh", "entity", "role", "up", "datetime", "sum_deltas", "residual"}
    cols = [c for c in rec.columns if c not in skip]
    grp = ["entity", "role"] if "entity" in rec.columns else ["up"]
    g = rec.groupby(grp)[cols + ["sum_deltas", "residual"]].sum()
    g["gross_mwh"] = rec.groupby(grp)["pbf"].apply(lambda s: s.abs().sum())
    g["residual_pct"] = np.where(g["gross_mwh"] > 0, 100 * g["residual"].abs() / g["gross_mwh"], np.nan)
    g["closes"] = g["residual_pct"] < tolerance_pct
    return g.reset_index()
