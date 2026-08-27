"""Catálogo de mercados y regla de valoración de cada uno.

Principio rector, demostrado en la auditoría:

    liquidacion = PBF x PMD + Sum_m  DeltaE_m x P_m
                = P48 x PMD + Sum_{m dentro de P48} DeltaE_m x (P_m - PMD)
                            + Sum_{m fuera de P48} E_m x P_m

Un mercado cuya energía ya está incorporada al programa final P48 se valora en
forma incremental frente al precio del diario. Un mercado cuya energía no está
en P48 se valora en bruto. Mezclar ambas convenciones sobre la misma base es el
origen del doble conteo.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Valuation(str, Enum):
    BASE_DA = "base_diario"          # P48 x PMD
    INCREMENTAL = "incremental"      # DeltaE x (P - PMD), energía dentro de P48
    GROSS = "bruto"                  # E x P, energía fuera de P48
    CAPACITY = "capacidad"           # MW x precio, no es energía


@dataclass(frozen=True)
class Market:
    key: str
    label: str
    valuation: Valuation
    inside_p48: bool
    energy_sheet: str | None = None
    price_sheet: str | None = None
    notes: str = ""


MARKETS: dict[str, Market] = {
    "DA": Market("DA", "Mercado diario (base P48 a PMD)", Valuation.BASE_DA, True,
                 "I90DIA02", None,
                 "Base energética. P48 trae signo nativo, no se le aplica signo de rol."),
    "IDA": Market("IDA", "Intradiario de subastas", Valuation.INCREMENTAL, True,
                  None, None, "OMIE PIBCI incremental, precio MARGINALPIBC por sesión."),
    "MIC": Market("MIC", "Intradiario continuo", Valuation.INCREMENTAL, True,
                  None, None, "OMIE TRADES, energía = cantidad x duración. No sumar PIBCIC."),
    "RT_DIARIO": Market("RT_DIARIO", "Restricciones técnicas del diario", Valuation.INCREMENTAL, True,
                        "I90DIA03", "I90DIA09", "Precio por UP y sentido, pay as bid."),
    "REEQUILIBRIO": Market("REEQUILIBRIO", "Reequilibrio económico del diario (ECO)", Valuation.INCREMENTAL, True,
                           "I90DIA03", "I90DIA09",
                           "Redespacho ECO. Se separa de la restricción técnica por naturaleza económica."),
    "RT_TIEMPO_REAL": Market("RT_TIEMPO_REAL", "Restricciones en tiempo real", Valuation.INCREMENTAL, True,
                             "I90DIA08", "I90DIA10",
                             "El precio sólo se publica para la familia de restricciones técnicas."),
    "DESVIOS_RT": Market("DESVIOS_RT", "Gestión de desvíos e indisponibilidad en tiempo real", Valuation.INCREMENTAL, True,
                         "I90DIA08", None, "Energía publicada, precio no publicado en I90DIA10."),
    "RR": Market("RR", "Reserva de sustitución (RR)", Valuation.INCREMENTAL, True,
                 "I90DIA06", "I90DIA11",
                 "Precio marginal global por periodo y tipo de redespacho. Sin UP ni sentido."),
    "MFRR": Market("MFRR", "mFRR / terciaria", Valuation.INCREMENTAL, True,
                   "I90DIA07", "I90DIA30", "TERPRO marginal; TERDIR por sentido y QH0/QH1."),
    "AFRR_ENERGIA": Market("AFRR_ENERGIA", "Energía de regulación secundaria", Valuation.GROSS, False,
                           None, None,
                           "No está en P48 y no se publica por UP antes del cambio SRS. Estimada."),
    "AFRR_BANDA": Market("AFRR_BANDA", "Banda de regulación secundaria", Valuation.CAPACITY, False,
                         "I90DIA05", None,
                         "Capacidad. No entra en el saldo generacion-consumo ni en precios capturados."),
}

INSIDE_P48 = [m.key for m in MARKETS.values() if m.inside_p48 and m.valuation is Valuation.INCREMENTAL]
ENERGY_MARKETS = [m.key for m in MARKETS.values() if m.valuation is not Valuation.CAPACITY]
