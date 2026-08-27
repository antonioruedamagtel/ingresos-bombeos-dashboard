"""Registro canónico de componentes de ingreso, con trazabilidad completa.

Toda fila del motor económico debe poder responder, sin salir del propio
registro: qué central, qué unidad, qué instante, qué mercado, qué volumen, qué
precio, contra qué precio de referencia, con qué fórmula, de qué fichero
público procede y con qué clase de dato y bandera de calidad.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class DataClass(str, Enum):
    OBSERVED = "OBSERVADO"            # volumen y precio publicados por UP
    RECONSTRUCTED = "RECONSTRUIDO"    # derivado por identidad a partir de observados
    OBSERVED_PROXY = "PROXY_OBSERVADO"  # precio publicado pero no específico de la UP
    ESTIMATED = "ESTIMADO"            # imputado con un modelo, no observable
    FORECAST = "FORECAST"             # prospectivo


class QualityFlag(str, Enum):
    OK = "OK"
    MISSING_PRICE = "MISSING_PRICE"
    AMBIGUOUS_PRICE = "AMBIGUOUS_PRICE"
    MISSING_DA_PRICE = "MISSING_DAY_AHEAD_PRICE"
    SIGN_CONFLICT = "SIGN_CONFLICT"
    NOT_AVAILABLE_YET = "NOT_AVAILABLE_YET"
    ESTIMATED_SHARE = "ESTIMATED_BY_BAND_SHARE"
    ESTIMATED_RATE = "ESTIMATED_BY_HISTORICAL_RATE"


COMPONENT_COLUMNS = [
    "asset", "up", "datetime", "market", "quantity", "unit",
    "price", "price_ref", "formula", "revenue_gross", "revenue_incremental",
    "source", "data_class", "quality_flag",
]


def empty_components() -> pd.DataFrame:
    return pd.DataFrame(columns=COMPONENT_COLUMNS)


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in COMPONENT_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA
    return out[COMPONENT_COLUMNS]
