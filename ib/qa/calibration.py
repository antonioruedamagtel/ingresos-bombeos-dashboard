"""Benchmarks externos y regresiones doradas.

Un benchmark es una referencia externa con su propia definición, que puede no
coincidir con la del motor. Por eso se guarda siempre la definición declarada y
el residuo se publica con signo, sin ajustar ningún coeficiente.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Benchmark:
    key: str
    asset: str
    period_start: str
    period_end: str
    metric: str
    value: float
    unit: str
    tolerance_pct: float
    definition: str
    source: str


BENCHMARKS = [
    Benchmark("AGUAYO_RRTT_SHARE_ABR2025", "Aguayo", "2025-04-01", "2025-04-30",
              "cuota_restricciones_bajar_sobre_ssaa", 69.0, "%", 2.0,
              "Energia de restricciones tecnicas a bajar sobre energia total en "
              "servicios de ajuste (RR, restricciones, terciaria y tiempo real).",
              "publicacion externa"),
    Benchmark("AGUAYO_RRTT_SHARE_MAY2025", "Aguayo", "2025-05-01", "2025-05-31",
              "cuota_restricciones_bajar_sobre_ssaa", 79.0, "%", 2.0,
              "Misma definicion que el anterior.", "publicacion externa"),
    Benchmark("AGUAYO_ENE2023_SALDO", "Aguayo", "2023-01-01", "2023-01-31",
              "saldo_generacion_consumo", 5_081_706, "EUR", 10.0,
              "Saldo de ENERGIA: diario, intradiarios, restricciones, RR, mFRR y "
              "energia de secundaria. NO incluye la banda de secundaria, que es "
              "capacidad. Denominador implicito de 349,7 MW.",
              "publicacion externa con pies de figura metodologicos"),
    Benchmark("AGUAYO_ENE2023_PGEN", "Aguayo", "2023-01-01", "2023-01-31",
              "precio_capturado_generacion", 115.95, "EUR/MWh", 10.0,
              "Precio conseguido de generacion.", "publicacion externa"),
    Benchmark("AGUAYO_ENE2023_PBOM", "Aguayo", "2023-01-01", "2023-01-31",
              "coste_capturado_bombeo", 22.12, "EUR/MWh", 10.0,
              "Precio pagado por el bombeo.", "publicacion externa"),
    Benchmark("AGUAYO_RRTT_PRE", "Aguayo", "2024-05-01", "2025-04-30",
              "rrtt_ajustado_mensual", 320_000, "EUR/mes", 10.0,
              "Restricciones tecnicas ajustadas frente a PMD, pre apagon.", "benchmark interno"),
    Benchmark("AGUAYO_RRTT_POST", "Aguayo", "2025-05-01", "2026-04-30",
              "rrtt_ajustado_mensual", 1_070_000, "EUR/mes", 10.0,
              "Restricciones tecnicas ajustadas frente a PMD, post apagon.", "benchmark interno"),
]


def compare(value: float, bm: Benchmark) -> dict:
    dev = 100.0 * (value - bm.value) / bm.value if bm.value else float("nan")
    return {
        "benchmark": bm.key, "activo": bm.asset, "metrica": bm.metric,
        "valor_motor": value, "valor_benchmark": bm.value, "unidad": bm.unit,
        "desviacion_pct": dev, "tolerancia_pct": bm.tolerance_pct,
        "resultado": "DENTRO" if abs(dev) <= bm.tolerance_pct else "FUERA",
        "definicion_benchmark": bm.definition,
    }


def report(values: dict[str, float]) -> pd.DataFrame:
    rows = [compare(values[b.key], b) for b in BENCHMARKS if b.key in values]
    return pd.DataFrame(rows)
