"""Sistema visual del cuadro de mando.

La paleta categórica es la de referencia validada: ocho tonos en orden fijo, que
superan la banda de luminosidad, el suelo de croma, la separación para daltonismo
y el suelo de visión normal en modo claro y oscuro. El orden es el mecanismo de
seguridad, no una decisión estética: no se rota ni se generan tonos nuevos.

Tres tonos quedan por debajo de 3:1 de contraste sobre la superficie clara, de
modo que se aplica la regla de alivio: toda gráfica va acompañada de etiquetas
directas o de su tabla de datos.
"""
from __future__ import annotations

LIGHT = {
    "surface": "#fcfcfb", "surface_2": "#f4f4f2", "grid": "#e6e5e1",
    "text_primary": "#0b0b0b", "text_secondary": "#52514e", "text_muted": "#7a7975",
    "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    "good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b",
}

DARK = {
    "surface": "#1a1a19", "surface_2": "#232322", "grid": "#3a3a37",
    "text_primary": "#ffffff", "text_secondary": "#c3c2b7", "text_muted": "#8f8e85",
    "series": ["#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767"],
    "good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b",
}

# Agrupación fija de mercados en ocho segmentos. Nunca se ciclan colores: si
# apareciera un mercado nuevo, se pliega en el grupo que le corresponda.
MARKET_GROUPS = {
    "DA": "Mercado diario",
    "IDA": "Intradiario",
    "MIC": "Intradiario",
    "RT_DIARIO": "Restricciones diario",
    "REEQUILIBRIO": "Restricciones diario",
    "RT_TIEMPO_REAL": "Restricciones tiempo real",
    "DESVIOS_RT": "Restricciones tiempo real",
    "RR": "RR",
    "MFRR": "mFRR",
    "AFRR_BANDA": "aFRR banda",
    "AFRR_ENERGIA": "aFRR energia",
}

GROUP_ORDER = ["Mercado diario", "Intradiario", "Restricciones diario",
               "Restricciones tiempo real", "RR", "mFRR", "aFRR banda", "aFRR energia"]


def group_color(theme: dict) -> dict:
    return {g: theme["series"][i] for i, g in enumerate(GROUP_ORDER)}


def layout(theme: dict, title: str = "", height: int = 380, showlegend: bool = True) -> dict:
    return dict(
        template="plotly_white",
        title=dict(text=title, font=dict(size=15, color=theme["text_primary"]), x=0, xanchor="left"),
        paper_bgcolor=theme["surface"], plot_bgcolor=theme["surface"],
        font=dict(family="Inter, Segoe UI, system-ui, sans-serif", size=12,
                  color=theme["text_secondary"]),
        margin=dict(l=56, r=20, t=46, b=42), height=height,
        showlegend=showlegend,
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=11)),
        xaxis=dict(showgrid=False, linecolor=theme["grid"], zeroline=False,
                   tickfont=dict(size=11)),
        yaxis=dict(gridcolor=theme["grid"], zerolinecolor=theme["grid"],
                   linecolor="rgba(0,0,0,0)", tickfont=dict(size=11)),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=theme["surface_2"], font=dict(color=theme["text_primary"], size=12),
                        bordercolor=theme["grid"]),
        bargap=0.28,
    )
