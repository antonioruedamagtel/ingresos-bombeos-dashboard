"""Puertas de control. Si una puerta no pasa, no se publica ningún euro."""
from __future__ import annotations

import pandas as pd


DST_DEFECT_NOTE = (
    "Defecto abierto: en los dias de cambio horario, 23 y 25 horas, la identidad "
    "de volumenes no cierra. El residuo neto por activo tiende a cero pero el "
    "absoluto no, lo que es la firma de un desalineamiento de periodo entre las "
    "hojas horarias y las cuartohorarias, no de una energia que falte. Afecta a "
    "14 de 15 combinaciones activo-rol el 26/03/2023 y a 6 de 14 el 29/10/2023, "
    "mientras el resto de dias de esas ventanas cierra en 0,0 MWh. Hasta "
    "resolverlo, un periodo que contenga un cambio horario no debe publicarse "
    "como validado."
)


def dst_days_in(days) -> list:
    """Días de cambio horario presentes en un conjunto de fechas."""
    from ..util.timeframe import n_hours
    out = []
    for d in pd.to_datetime(pd.Series(list(days))).dt.date.unique():
        if n_hours(d) != 24:
            out.append(d)
    return out


def gate_volume(rec_summary: pd.DataFrame, tolerance_pct: float = 0.5) -> tuple[bool, pd.DataFrame]:
    r = rec_summary.copy()
    r["ok"] = r["residual_pct"].fillna(0) < tolerance_pct
    return bool(r["ok"].all()), r


def gate_sign(sign_check: pd.DataFrame) -> tuple[bool, pd.DataFrame]:
    return bool(not sign_check["conflict"].any()), sign_check[sign_check["conflict"]]


def gate_trades_vs_pibcic(control: pd.DataFrame, tolerance_mwh: float = 1e-6) -> tuple[bool, float]:
    if control is None or control.empty:
        return True, 0.0
    mae = float(control["abs_error"].mean())
    return mae <= tolerance_mwh, mae


def gate_price_coverage(cov: pd.DataFrame, minimum: dict[str, float]) -> tuple[bool, pd.DataFrame]:
    c = cov.copy()
    c["minimo"] = c["market"].map(minimum).fillna(0.0)
    c["ok"] = c["cobertura_precio_pct"].fillna(0) >= c["minimo"]
    return bool(c["ok"].all()), c[~c["ok"]]


DEFAULT_MIN_COVERAGE = {
    "DA": 99.0, "RR": 99.0, "MFRR": 95.0, "REEQUILIBRIO": 95.0,
    "RT_DIARIO": 90.0, "IDA": 95.0, "MIC": 99.0, "AFRR_BANDA": 95.0,
    # La publicación pública no da precio a desvíos ni indisponibilidad.
    "RT_TIEMPO_REAL": 0.0, "DESVIOS_RT": 0.0,
}
